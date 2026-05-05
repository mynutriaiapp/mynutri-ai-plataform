"""
Arquitetura de dois passos para geração de dietas:

  Passo 1 — LLM (temp=0.3): seleciona alimentos e quantidades (sem macros)
  Backend:  consulta nutrition_db.py e calcula macros deterministicamente
  Passo 2 — LLM (temp=0.7): escreve explicação usando os valores calculados

Isso elimina a variabilidade de macros causada por delegar aritmética ao modelo.
"""

import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from .models import Anamnese, DietPlan, Meal
import unicodedata

from .nutrition_db import lookup_food_nutrition

# Palavras-chave que identificam fontes proteicas primárias.
# Usadas em _adjust_to_calorie_target para preservar porções de proteína.
_PROTEIN_KEYWORDS = frozenset([
    'frango', 'carne', 'peixe', 'atum', 'salmao', 'tilapia', 'merluza',
    'bacalhau', 'sardinha', 'camarao', 'robalo', 'ovo', 'ovos', 'clara',
    'whey', 'proteina', 'feijao', 'lentilha', 'tofu', 'soja',
    'patinho', 'alcatra', 'picanha', 'file', 'musculo', 'contrafile',
    'acem', 'lagarto', 'peru', 'presunto', 'queijo', 'iogurte', 'cottage',
])

# Palavras-chave que identificam alimentos densos em gordura.
# Usadas em _adjust_to_calorie_target para evitar que escalas grandes
# multipliquem óleos/castanhas/manteiga a porções absurdas.
_FAT_KEYWORDS = frozenset([
    'azeite', 'oleo', 'manteiga', 'margarina', 'creme',
    'castanha', 'nozes', 'amendoim', 'amendoa', 'pasta amendoim',
    'abacate', 'coco', 'bacon', 'banha', 'toucinho',
])

# ─────────────────────────────────────────────────────────────────────────────
#  ARREDONDAMENTO DE PORÇÕES — medidas práticas de consumo
# ─────────────────────────────────────────────────────────────────────────────
#
# Regras: (frozenset de palavras-chave, múltiplo de arredondamento, mínimo)
#
# A ordem importa: a primeira regra que casar é usada.
# Palavras-chave são testadas como substring no nome normalizado (sem acentos).

_ROUNDING_RULES: list[tuple[frozenset, int, int]] = [
    # Óleos e gorduras puras: colher de chá = 5g
    (frozenset(['azeite', 'oleo', 'manteiga', 'margarina', 'banha']),        5,   5),
    # Proteína em pó, aveia, farinha, granola: colher de sopa ≈ 10g
    (frozenset(['aveia', 'whey', 'farinha', 'granola', 'cereal']),          10,  10),
    # Castanhas e oleaginosas: porção = 10g
    (frozenset(['castanha', 'amendoa', 'noze', 'pasta amendoim']),          10,  10),
    # Amendoim (inteiro): punhado ≈ 15g
    (frozenset(['amendoim torrado', 'amendoim']),                            15,  15),
    # Tapioca: meia tapioca ≈ 40g, inteira ≈ 80g → múltiplo de 20
    (frozenset(['tapioca']),                                                 20,  20),
    # Queijo e laticínios sólidos: fatia ≈ 30g
    (frozenset(['queijo', 'requeijao', 'cottage']),                         30,  30),
    # Ovos: 1 ovo médio ≈ 50g (para arredondar 1, 2, 3 ovos)
    (frozenset(['ovo', 'ovos', 'clara', 'omelete']),                        50,  50),
    # Embutidos e pão: fatia/unidade ≈ 25g
    (frozenset(['pao', 'presunto', 'peito peru', 'salsicha', 'linguica']),  25,  25),
    # Carnes, aves e peixes: filé/bife ≈ 25g de precisão, mínimo 50g
    (frozenset(['frango', 'carne', 'peixe', 'tilapia', 'salmao', 'atum',
                'sardinha', 'camarao', 'file', 'patinho', 'alcatra',
                'picanha', 'musculo', 'contrafile', 'acem', 'lagarto',
                'bacalhau', 'merluza', 'robalo', 'peru', 'carne moida',
                'carne seca', 'paio']),                                     25,  50),
    # Arroz, massas, tubérculos, leguminosas: medida de colher/concha ≈ 50g
    (frozenset(['arroz', 'macarrao', 'esparguete', 'massa', 'batata',
                'mandioca', 'aipim', 'macaxeira', 'cuscuz', 'feijao',
                'lentilha', 'grao', 'ervilha', 'milho', 'soja']),           50,  50),
    # Leite e iogurte: copo/pote ≈ 50g de precisão, mínimo 100g
    (frozenset(['leite', 'iogurte']),                                        50, 100),
    # Frutas: unidade ≈ 50g de precisão, mínimo 50g
    (frozenset(['banana', 'maca', 'laranja', 'mamao', 'manga', 'uva',
                'morango', 'melancia', 'kiwi', 'pera', 'abacaxi', 'caju',
                'tangerina', 'mexerica', 'pessego', 'goiaba']),              50,  50),
]


def _round_food_quantity(food_name: str, qty_g: float) -> int:
    """
    Arredonda a quantidade de um alimento para o múltiplo prático mais próximo.

    Usa as regras de _ROUNDING_RULES por categoria; para alimentos sem
    categoria específica aplica arredondamento graduado:
      ≤ 50g  → múltiplos de 5g
      ≤ 200g → múltiplos de 25g
       > 200g → múltiplos de 50g
    """
    normalized = _strip_accents(food_name.lower())

    for keywords, multiple, minimum in _ROUNDING_RULES:
        if any(kw in normalized for kw in keywords):
            rounded = round(qty_g / multiple) * multiple
            return int(max(minimum, rounded))

    # Arredondamento graduado para alimentos sem categoria específica
    if qty_g <= 50:
        return int(max(5, round(qty_g / 5) * 5))
    elif qty_g <= 200:
        return int(round(qty_g / 25) * 25)
    else:
        return int(round(qty_g / 50) * 50)


def _household_measure(food_name: str, qty_g: int) -> str:
    """
    Retorna a medida caseira aproximada para exibição ao usuário.

    Exemplos: '300g' → '≈ 8 col. de sopa' (arroz), '150g' → '≈ 1 filé médio' (frango).
    Retorna string vazia se não houver medida conhecida para o alimento.
    """
    n = _strip_accents(food_name.lower())
    q = qty_g

    # ── Ovos ─────────────────────────────────────────────────────────────────
    if 'clara' in n:
        count = max(1, round(q / 33))
        return f'{count} {"clara" if count == 1 else "claras"}'
    if any(k in n for k in ('ovo', 'ovos', 'omelete')):
        count = max(1, round(q / 50))
        return f'{count} {"unidade" if count == 1 else "unidades"}'

    # ── Óleos e gorduras ─────────────────────────────────────────────────────
    if any(k in n for k in ('azeite', 'oleo', 'manteiga', 'margarina')):
        if q <= 5:   return '1 col. de chá'
        if q <= 10:  return '1 col. de sopa'
        if q <= 15:  return '1 col. de sopa cheia'
        return f'{round(q / 15)} col. de sopa'

    # ── Cereais e tubérculos ─────────────────────────────────────────────────
    if 'arroz' in n:
        col = max(1, round(q / 35))
        return f'{col} col. de sopa'
    if any(k in n for k in ('macarrao', 'esparguete', 'massa', 'penne')):
        xic = round(q / 100)
        return f'{max(1, xic)} {"xícara" if xic <= 1 else "xícaras"}'
    if 'batata doce' in n or 'batata-doce' in n:
        if q <= 100: return '½ unid. média'
        if q <= 180: return '1 unid. média'
        return '1 unid. grande'
    if 'batata' in n:
        if q <= 100: return '1 batata pequena'
        if q <= 180: return '1 batata média'
        return '1 batata grande'
    if 'mandioca' in n or 'aipim' in n or 'macaxeira' in n:
        if q <= 100: return '1 pedaço pequeno'
        return f'{round(q / 100)} pedaços'
    if 'cuscuz' in n:
        col = max(1, round(q / 40))
        return f'{col} col. de sopa'

    # ── Leguminosas ───────────────────────────────────────────────────────────
    if any(k in n for k in ('feijao', 'lentilha', 'grao', 'ervilha')):
        conchas = max(1, round(q / 80))
        return f'{conchas} {"concha" if conchas == 1 else "conchas"}'

    # ── Pão e tapioca ─────────────────────────────────────────────────────────
    if 'tapioca' in n:
        if q <= 45:  return '½ tapioca'
        if q <= 90:  return '1 tapioca'
        if q <= 130: return '1½ tapioca'
        return f'{round(q / 80)} tapiocas'
    if 'pao' in n:
        if q <= 35:  return '½ unidade'
        if q <= 65:  return '1 unidade'
        return f'{round(q / 50)} unidades'

    # ── Cereais e sementes ────────────────────────────────────────────────────
    if any(k in n for k in ('aveia', 'granola')):
        col = max(1, round(q / 10))
        return f'{col} col. de sopa'
    if any(k in n for k in ('whey', 'farinha')):
        col = max(1, round(q / 10))
        return f'{col} col. de sopa'

    # ── Laticínios ────────────────────────────────────────────────────────────
    if 'leite' in n:
        if q <= 100: return '½ copo'
        if q <= 200: return '1 copo'
        return f'{round(q / 200)} copos'
    if 'iogurte' in n:
        if q <= 120: return '½ pote'
        if q <= 220: return '1 pote'
        return f'{round(q / 180)} potes'
    if any(k in n for k in ('queijo', 'requeijao')):
        fatias = max(1, round(q / 25))
        return f'{fatias} {"fatia" if fatias == 1 else "fatias"}'

    # ── Oleaginosas ───────────────────────────────────────────────────────────
    if any(k in n for k in ('castanha', 'amendoa', 'noze')):
        unid = max(1, round(q / 5))
        return f'{unid} unidades'
    if 'amendoim' in n and 'pasta' not in n:
        if q <= 15: return '1 punhado'
        return f'{round(q / 15)} punhados'
    if 'pasta' in n and 'amendoim' in n:
        col = max(1, round(q / 15))
        return f'{col} col. de sopa'

    # ── Carnes, aves e peixes ─────────────────────────────────────────────────
    if any(k in n for k in ('frango', 'tilapia', 'salmao', 'peixe',
                             'file', 'merluza', 'bacalhau', 'robalo')):
        if q <= 100: return '1 filé pequeno'
        if q <= 160: return '1 filé médio'
        if q <= 220: return '1 filé grande'
        return f'{round(q / 150)} filés'
    if any(k in n for k in ('patinho', 'alcatra', 'picanha', 'contrafile',
                             'carne bovina', 'carne moida', 'musculo', 'acem')):
        if q <= 120: return '1 bife pequeno'
        if q <= 180: return '1 bife médio'
        return '1 bife grande'
    if 'atum' in n:
        latas = max(1, round(q / 85))
        return f'{latas} {"lata" if latas == 1 else "latas"}'
    if 'sardinha' in n:
        return '1 lata' if q <= 100 else '2 latas'

    # ── Frutas ────────────────────────────────────────────────────────────────
    if any(k in n for k in ('banana',)):
        if q <= 80: return '½ banana'
        if q <= 130: return '1 banana'
        return '1 banana grande'
    if any(k in n for k in ('maca', 'pera', 'pessego')):
        if q <= 100: return '½ unidade'
        return '1 unidade'
    if any(k in n for k in ('laranja', 'tangerina', 'mexerica')):
        if q <= 80: return '½ unidade'
        return '1 unidade'
    if any(k in n for k in ('mamao', 'manga')):
        if q <= 100: return '1 fatia'
        if q <= 200: return '2 fatias'
        return '3 fatias'

    # ── Legumes e folhas ──────────────────────────────────────────────────────
    if any(k in n for k in ('alface', 'rucula', 'espinafre', 'acelga', 'salada')):
        if q <= 40: return '½ prato'
        return '1 prato'
    if any(k in n for k in ('brocolis', 'couve', 'cenoura', 'abobrinha', 'chuchu')):
        if q <= 80: return '½ xícara'
        return '1 xícara'

    return ''


def _strip_accents(text: str) -> str:
    text = unicodedata.normalize('NFD', text)
    return ''.join(c for c in text if unicodedata.category(c) != 'Mn')


class DietGenerationError(Exception):
    """Base para todos os erros de geração de dieta."""
    pass


class TransientAIError(DietGenerationError):
    """
    Erro transitório — a task Celery deve fazer retry.

    Indica que a falha pode ser resolvida tentando novamente:
    resposta mal formatada da IA, cobertura nutricional insuficiente,
    alérgeno detectado (a IA pode escolher outros alimentos), ou
    desequilíbrio de macros (a IA pode montar um plano melhor).
    """
    pass


class PermanentAIError(DietGenerationError):
    """
    Erro permanente — retry não resolve, falha deve ser reportada ao usuário.

    Indica problema de configuração ou dado inválido:
    chave de API ausente, anamnese corrompida, etc.
    """
    pass


class AllergenViolation(TransientAIError):
    """Plano gerado contém alimento que viola alergias declaradas."""
    pass


class NutritionDataGap(TransientAIError):
    """
    Muitos alimentos do plano caem no fallback genérico do nutrition_db
    (150 kcal/100g) — o cálculo calórico fica pouco confiável.
    """
    pass


class MacroImbalanceError(TransientAIError):
    """
    Proporções de macronutrientes fora dos limites fisiologicamente razoáveis.

    Exemplos: carboidratos > 65% das calorias, proteína < 65% da meta,
    gordura < 15% das calorias.
    """
    pass


def _parse_allergens(allergies_text: str) -> list[str]:
    """
    Parseia o campo de alergias (texto livre) em lista de alergenos normalizados.

    Aceita separadores: vírgula, ponto-e-vírgula, ponto, quebra de linha, " e ".
    Normaliza para minúsculas sem acentos. Descarta entradas com < 3 caracteres.
    """
    if not allergies_text or not allergies_text.strip():
        return []
    parts = re.split(r'[,;.\n]|\s+e\s+', allergies_text)
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        normalized = _strip_accents(p.strip().lower())
        normalized = re.sub(r'^[^\w\s]+|[^\w\s]+$', '', normalized).strip()
        if len(normalized) >= 3 and normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out


def _food_contains_allergen(food_name: str, allergens: list[str]) -> str | None:
    """
    Retorna o alergeno detectado no nome do alimento, ou None.

    Estratégia:
      - Alergeno de uma palavra (ex: "amendoim"): word boundary, evita falso
        positivo em "novo" → "ovo".
      - Alergeno multi-palavra (ex: "frutos do mar"): substring, garante que
        a frase inteira esteja presente.
    """
    if not food_name or not allergens:
        return None
    normalized = _strip_accents(food_name.lower())
    for allergen in allergens:
        if ' ' in allergen:
            if allergen in normalized:
                return allergen
        else:
            if re.search(rf'\b{re.escape(allergen)}\b', normalized):
                return allergen
    return None


from .prompts import (
    SYSTEM_PROMPT_EXPLANATION,
    SYSTEM_PROMPT_FOODS,
    SYSTEM_PROMPT_MEAL_REGEN,
    SYSTEM_PROMPT_NOTES,
    build_explanation_prompt,
    build_food_selection_prompt,
    build_meal_regen_prompt,
    build_notes_prompt,
    calculate_calories,
    calculate_macros,
)
from .substitutions import generate_meal_substitutions

logger = logging.getLogger(__name__)


class AIService:
    """
    Orquestra a geração de dieta em dois passos via API compatível com OpenAI.

    Variáveis de ambiente:
        AI_API_KEY  → chave de autenticação
        AI_API_URL  → endpoint (ex: https://api.openai.com/v1/chat/completions)
        AI_MODEL    → modelo (padrão: gpt-4o-mini)
    """

    def __init__(self):
        self.api_key = os.getenv('AI_API_KEY', '')
        self.api_url = os.getenv('AI_API_URL', '')
        self.model   = os.getenv('AI_MODEL', 'gpt-4o-mini')

    # ──────────────────────────────────────────────────────────────────────────
    #  HTTP
    # ──────────────────────────────────────────────────────────────────────────

    def _call_api(
        self,
        user_prompt: str,
        system_prompt: str,
        temperature: float = 0.3,
        json_mode: bool = True,
        max_retries: int = 3,
        max_tokens: int | None = None,
    ) -> dict:
        """Realiza chamada à API de IA com retry exponencial em erros transitórios."""
        if not self.api_key or not self.api_url:
            raise PermanentAIError('AI_API_KEY e AI_API_URL devem estar configurados no .env')

        body: dict = {
            'model':       self.model,
            'messages':    [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user',   'content': user_prompt},
            ],
            'temperature': temperature,
        }
        if max_tokens is not None:
            body['max_tokens'] = max_tokens
        if json_mode:
            body['response_format'] = {'type': 'json_object'}

        payload = json.dumps(body).encode('utf-8')
        req = urllib.request.Request(
            self.api_url,
            data=payload,
            headers={
                'Content-Type':  'application/json',
                'Authorization': f'Bearer {self.api_key}',
            },
            method='POST',
        )

        last_exc: Exception | None = None
        for attempt in range(max_retries):
            try:
                with urllib.request.urlopen(req, timeout=120) as response:
                    return json.loads(response.read().decode('utf-8'))
            except urllib.error.HTTPError as e:
                # 429 Too Many Requests e 5xx são transitórios; 4xx são permanentes
                if e.code == 429 or e.code >= 500:
                    last_exc = e
                    wait = 2 ** attempt
                    logger.warning('API HTTP %s na tentativa %d/%d — aguardando %ds', e.code, attempt + 1, max_retries, wait)
                    time.sleep(wait)
                else:
                    raise
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last_exc = e
                wait = 2 ** attempt
                logger.warning('Erro de rede na tentativa %d/%d — aguardando %ds: %s', attempt + 1, max_retries, wait, e)
                time.sleep(wait)

        raise TransientAIError(f'API da IA indisponível após {max_retries} tentativas: {last_exc}')

    def _parse_response(self, api_response: dict) -> dict:
        """Extrai e parseia o JSON gerado pela IA."""
        try:
            content = api_response['choices'][0]['message']['content']
        except (KeyError, IndexError) as e:
            logger.error('Formato inesperado da API: %s | resposta: %s', e, api_response)
            raise TransientAIError('A IA retornou um formato inesperado. Tente novamente.')

        stripped = content.strip()
        # Remove markdown code fences caso a API não suporte json_mode
        if stripped.startswith('```'):
            lines = stripped.split('\n')
            inner = lines[1:]
            if inner and inner[-1].strip() == '```':
                inner = inner[:-1]
            stripped = '\n'.join(inner)

        try:
            return json.loads(stripped)
        except json.JSONDecodeError as e:
            logger.error('JSON inválido da IA: %s | conteúdo: %.200s', e, content)
            raise TransientAIError('A IA retornou um formato inesperado. Tente novamente.')

    # ──────────────────────────────────────────────────────────────────────────
    #  ENRIQUECIMENTO NUTRICIONAL (backend — determinístico)
    # ──────────────────────────────────────────────────────────────────────────

    def _enrich_foods_with_macros(self, diet_data: dict) -> tuple[dict, dict]:
        """
        Consulta o nutrition_db para cada alimento e atribui calorias e macros.
        Também padroniza o campo 'quantity' para exibição no frontend.

        Retorna (diet_data, stats), onde stats agrega contagem por camada de
        match do nutrition_db. Usado por _check_db_coverage para rejeitar planos
        com muitos alimentos no fallback genérico (150 kcal/100g).
        """
        stats = {
            'total': 0, 'exact': 0, 'fuzzy': 0, 'category': 0,
            'generic': 0, 'invalid': 0, 'generic_names': [],
        }
        for meal in diet_data.get('meals', []):
            for food in meal.get('foods', []):
                qty_g    = float(food.get('quantity_g') or 100)
                qty_text = food.get('quantity_text', f'{qty_g:.0f}g')

                nutrition = lookup_food_nutrition(food.get('name', ''), qty_g)
                food['calories']  = nutrition['calories']
                food['protein_g'] = nutrition['protein_g']
                food['carbs_g']   = nutrition['carbs_g']
                food['fat_g']     = nutrition['fat_g']

                source = nutrition.get('_source', 'unknown')
                stats['total'] += 1
                stats[source] = stats.get(source, 0) + 1
                if source == 'generic':
                    stats['generic_names'].append(food.get('name', '?'))

                # Campo 'quantity' usado pelo frontend (combina texto + gramas)
                qty_g_int = round(qty_g)
                if str(qty_g_int) in qty_text or f'{qty_g_int}g' in qty_text:
                    food['quantity'] = qty_text
                else:
                    food['quantity'] = f'{qty_text} ({qty_g_int}g)'

        return diet_data, stats

    def _recalculate_totals(self, diet_data: dict) -> dict:
        """Recalcula macros e calorias totais somando os alimentos individuais."""
        total_cal  = 0
        total_prot = 0.0
        total_carb = 0.0
        total_fat  = 0.0

        for meal in diet_data.get('meals', []):
            for food in meal.get('foods', []):
                total_cal  += food.get('calories',  0) or 0
                total_prot += food.get('protein_g', 0) or 0
                total_carb += food.get('carbs_g',   0) or 0
                total_fat  += food.get('fat_g',     0) or 0

        diet_data['calories'] = total_cal
        diet_data['macros']   = {
            'protein_g': round(total_prot),
            'carbs_g':   round(total_carb),
            'fat_g':     round(total_fat),
        }
        return diet_data

    @staticmethod
    def _is_protein_food(food_name: str) -> bool:
        """Retorna True se o alimento é fonte proteica primária."""
        normalized = _strip_accents(food_name.lower())
        return any(kw in normalized for kw in _PROTEIN_KEYWORDS)

    @staticmethod
    def _is_fat_food(food_name: str) -> bool:
        """
        Retorna True se o alimento é denso em gordura (óleos, castanhas, manteiga).
        Usado em _adjust_to_calorie_target para evitar que escalas grandes
        multipliquem porções a valores absurdos (ex: azeite 10g → 60g).
        """
        normalized = _strip_accents(food_name.lower())
        return any(kw in normalized for kw in _FAT_KEYWORDS)

    def _adjust_to_calorie_target(self, diet_data: dict, target_calories: int) -> dict:
        """
        Se o total calculado divergir mais de 10% do alvo, ajusta quantity_g
        com escala seletiva por categoria:

          - Proteínas (frango, peixe, ovo…):         cap ±15% — preserva adequação proteica
          - Gorduras densas (azeite, castanhas…):     cap ±20% — evita explosão calórica de óleo
          - Demais (arroz, batata, pão, vegetais…):   escala livre — absorvem o ajuste principal

        A hierarquia evita que correções calóricas produzam porções absurdas
        de alimentos calórico-densos enquanto os carboidratos ficam em 30g.
        """
        actual = diet_data.get('calories', 0)
        if not actual or not target_calories:
            return diet_data

        divergence = abs(actual - target_calories) / target_calories
        if divergence <= 0.10:
            return diet_data

        scale = target_calories / actual
        logger.warning(
            'Total calculado (%d kcal) diverge %.1f%% do alvo (%d kcal). '
            'Ajustando porções (escala=%.4f; proteínas ±15%%, gorduras ±20%%).',
            actual, divergence * 100, target_calories, scale,
        )

        for meal in diet_data.get('meals', []):
            for food in meal.get('foods', []):
                old_qty = float(food.get('quantity_g') or 100)
                name    = food.get('name', '')

                if self._is_protein_food(name):
                    # Proteínas: cap ±15% para preservar adequação proteica
                    applied_scale = max(0.85, min(1.15, scale))
                elif self._is_fat_food(name):
                    # Gorduras densas: cap ±20% para evitar porções absurdas de óleo
                    applied_scale = max(0.80, min(1.20, scale))
                else:
                    # Carboidratos e vegetais: escala livre — absorvem o ajuste
                    applied_scale = scale

                new_qty = max(10, round(old_qty * applied_scale))
                food['quantity_g'] = new_qty

                nutrition = lookup_food_nutrition(name, new_qty)
                food['calories']  = nutrition['calories']
                food['protein_g'] = nutrition['protein_g']
                food['carbs_g']   = nutrition['carbs_g']
                food['fat_g']     = nutrition['fat_g']

                measure = _household_measure(name, new_qty)
                food['quantity_text'] = f'{new_qty}g'
                food['quantity']      = f'{new_qty}g ({measure})' if measure else f'{new_qty}g'

        return self._recalculate_totals(diet_data)

    def _round_portions(self, diet_data: dict, target_calories: int | None = None) -> dict:
        """
        Arredonda as quantidades de todos os alimentos para medidas práticas de consumo.

        Após arredondar, recalcula as calorias e macros de cada alimento via
        nutrition_db e atualiza os totais do plano. O campo 'quantity' ganha
        a medida caseira (ex: "300g (≈ 8 col. de sopa)") para exibição no frontend.
        """
        changed = 0
        for meal in diet_data.get('meals', []):
            for food in meal.get('foods', []):
                old_qty = int(food.get('quantity_g') or 10)
                new_qty = _round_food_quantity(food.get('name', ''), old_qty)
                if new_qty != old_qty:
                    changed += 1
                    food['quantity_g'] = new_qty
                    nutrition = lookup_food_nutrition(food.get('name', ''), new_qty)
                    food['calories']  = nutrition['calories']
                    food['protein_g'] = nutrition['protein_g']
                    food['carbs_g']   = nutrition['carbs_g']
                    food['fat_g']     = nutrition['fat_g']

                qty = int(food.get('quantity_g', old_qty))
                measure = _household_measure(food.get('name', ''), qty)
                food['quantity_text'] = f'{qty}g'
                food['quantity'] = f'{qty}g ({measure})' if measure else f'{qty}g'

        if changed:
            diet_data = self._recalculate_totals(diet_data)
            if target_calories:
                total = diet_data.get('calories', 0)
                dev = abs(total - target_calories) / target_calories * 100
                logger.info(
                    '[ROUND_PORTIONS] %d porções arredondadas. Total: %d kcal (desvio: %.1f%% do alvo %d kcal)',
                    changed, total, dev, target_calories,
                )
        return diet_data

    def _check_protein_adequacy(
        self,
        diet_data: dict,
        anamnese: Anamnese,
        target_calories: int,
    ) -> None:
        """
        Verifica se a proteína calculada do plano está próxima da meta.
        Loga aviso se o modelo ignorou a instrução de macros — útil para
        identificar casos onde o prompt não está sendo respeitado.
        """
        target = calculate_macros(anamnese, target_calories)['protein_g']
        actual = diet_data.get('macros', {}).get('protein_g', 0)
        if not target:
            return

        ratio = actual / target
        if ratio < 0.75:
            logger.warning(
                '[PROTEIN_GAP] Proteína do plano: %dg — apenas %.0f%% da meta (%dg) '
                'para usuário %s. O modelo pode não ter respeitado a instrução de macros.',
                actual, ratio * 100, target, anamnese.user_id,
            )
        else:
            logger.info(
                '[PROTEIN_CHECK] Proteína: %dg/%dg (%.0f%% da meta) — usuário %s.',
                actual, target, ratio * 100, anamnese.user_id,
            )

    def _validate_macro_ratios(
        self,
        diet_data: dict,
        anamnese: Anamnese,
        target_calories: int,
    ) -> None:
        """
        Valida que as proporções de macronutrientes do plano estão dentro de
        limites fisiologicamente razoáveis. Levanta MacroImbalanceError
        (retryable) se algum limite for violado.

        Limites absolutos por % de calorias:
          - Carboidratos: máximo 65% das calorias
          - Proteína:     mínimo 15% das calorias
          - Gordura:      mínimo 15% das calorias

        Limites por g/kg de peso corporal:
          - Gordura: máximo 1.2g/kg (20% acima do teto recomendado de 1.0g/kg)
            → detecta excesso de óleos, castanhas, queijo mesmo dentro do % de calorias

        Aderência à meta calculada:
          - Proteína: mínimo 65% da meta calculada pelo backend
        """
        macros    = diet_data.get('macros', {})
        total_cal = diet_data.get('calories', 0)
        if not total_cal:
            return

        protein_g = macros.get('protein_g', 0)
        carbs_g   = macros.get('carbs_g', 0)
        fat_g     = macros.get('fat_g', 0)
        w         = float(anamnese.weight_kg) if anamnese.weight_kg else 1.0

        protein_pct = (protein_g * 4) / total_cal
        carbs_pct   = (carbs_g   * 4) / total_cal
        fat_pct     = (fat_g     * 9) / total_cal
        fat_per_kg  = fat_g / w

        violations = []

        if carbs_pct > 0.65:
            violations.append(
                f'carboidratos em {carbs_pct * 100:.0f}% das calorias (teto: 65%) — '
                f'excesso de alimentos ricos em amido/açúcar'
            )
        if protein_pct < 0.15:
            violations.append(
                f'proteína em {protein_pct * 100:.0f}% das calorias (mínimo: 15%) — '
                f'fontes proteicas insuficientes no plano'
            )
        if fat_pct < 0.15:
            violations.append(
                f'gordura em {fat_pct * 100:.0f}% das calorias (mínimo: 15%) — '
                f'risco de deficiência de vitaminas lipossolúveis'
            )
        # Teto de gordura por kg — detecta excesso de óleos/castanhas mesmo em %
        # aceitável (ex: 37% numa dieta de 3000 kcal parece ok em %, mas 126g para
        # 95kg = 1.33g/kg excede claramente o limite fisiológico de 1.0g/kg)
        if fat_per_kg > 1.2:
            violations.append(
                f'gordura {fat_g}g ({fat_per_kg:.1f}g/kg) excede 1.2g/kg para '
                f'{w:.0f}kg — desbalanceamento por excesso de alimentos gordurosos '
                f'(óleos, castanhas, queijo, manteiga)'
            )

        # Aderência à meta de proteína calculada
        protein_target = calculate_macros(anamnese, target_calories)['protein_g']
        if protein_target > 0:
            protein_ratio = protein_g / protein_target
            if protein_ratio < 0.65:
                violations.append(
                    f'proteína {protein_g}g é apenas {protein_ratio * 100:.0f}% da meta '
                    f'({protein_target}g) — desbalanceamento de macros proteicos'
                )

        if violations:
            detail = '; '.join(violations)
            logger.error(
                '[MACRO_IMBALANCE] Desbalanceamento de macros para usuário %s: %s',
                anamnese.user_id, detail,
            )
            raise MacroImbalanceError(
                f'Desbalanceamento de macros no plano gerado: {detail}. '
                f'Tente gerar novamente.'
            )

        logger.info(
            '[MACRO_VALID] Macros dentro dos limites — usuário %s: '
            'P=%dg (%.0f%%) C=%dg (%.0f%%) G=%dg (%.0f%%, %.1fg/kg)',
            anamnese.user_id,
            protein_g, protein_pct * 100,
            carbs_g,   carbs_pct   * 100,
            fat_g,     fat_pct     * 100, fat_per_kg,
        )

    # ──────────────────────────────────────────────────────────────────────────
    #  COBERTURA DO BANCO NUTRICIONAL — confiabilidade calórica
    # ──────────────────────────────────────────────────────────────────────────

    # Limite acima do qual a cobertura é considerada insuficiente.
    # ≥2 alimentos no fallback genérico E ≥20% do total dispara rejeição.
    # O floor de 2 evita rejeição em planos pequenos onde 1 alimento exótico
    # pode legitimamente estar fora do TACO.
    DB_COVERAGE_MIN_GENERIC_COUNT = 2
    DB_COVERAGE_MAX_GENERIC_RATIO = 0.20

    def _check_db_coverage(self, stats: dict, anamnese: Anamnese) -> None:
        """
        Verifica quantos alimentos caíram no fallback genérico (sem cobertura
        no nutrition_db) e levanta NutritionDataGap se for excessivo.

        O fallback genérico atribui 150 kcal/100g a qualquer alimento desconhecido,
        o que mascara erros graves: pão de queijo (~330), hambúrguer (~280),
        coxinha (~280) — todos seriam subestimados em ~50%.

        Trigger de retry: a exception é ValueError com 'cobertura nutricional'
        na mensagem, capturada por _RETRYABLE_PHRASES em tasks.py.
        """
        total = stats.get('total', 0)
        if total == 0:
            return

        generic = stats.get('generic', 0)
        ratio = generic / total

        if generic >= self.DB_COVERAGE_MIN_GENERIC_COUNT and ratio >= self.DB_COVERAGE_MAX_GENERIC_RATIO:
            names = stats.get('generic_names', [])
            preview = ', '.join(names[:5]) + ('...' if len(names) > 5 else '')
            logger.error(
                '[DB_COVERAGE] Plano para usuário %s: %d/%d (%.0f%%) alimentos sem '
                'cobertura no banco nutricional: %s',
                anamnese.user_id, generic, total, ratio * 100, names,
            )
            raise NutritionDataGap(
                f'Cobertura nutricional insuficiente: {generic} de {total} alimentos '
                f'({ratio * 100:.0f}%) caíram no fallback genérico ({preview}). '
                f'Tente gerar novamente.'
            )

        if generic > 0:
            logger.info(
                '[DB_COVERAGE] Usuário %s: %d/%d alimentos no fallback genérico (%.0f%%) — abaixo do limite.',
                anamnese.user_id, generic, total, ratio * 100,
            )

    # ──────────────────────────────────────────────────────────────────────────
    #  ENFORCEMENT DE ALERGIAS — segurança nutricional crítica
    # ──────────────────────────────────────────────────────────────────────────

    def _enforce_allergies(self, diet_data: dict, anamnese: Anamnese) -> None:
        """
        Verifica se algum alimento do plano viola as alergias declaradas.

        O LLM pode ignorar a instrução "evite completamente" no prompt. Esta
        camada determinística é a última linha de defesa antes de servir um
        plano potencialmente perigoso.

        Levanta AllergenViolation com a lista de violações encontradas.
        Como AllergenViolation é ValueError com "alergia" na mensagem, a task
        do Celery faz retry automático (até 2x) — geração não-determinística
        pode produzir um plano válido na próxima tentativa.
        """
        allergens = _parse_allergens(anamnese.allergies or '')
        if not allergens:
            return

        violations: list[tuple[str, str, str]] = []
        for meal in diet_data.get('meals', []):
            meal_name = meal.get('name', '?')
            for food in meal.get('foods', []):
                food_name = food.get('name', '')
                matched = _food_contains_allergen(food_name, allergens)
                if matched:
                    violations.append((meal_name, food_name, matched))

        if violations:
            details = '; '.join(
                f'"{food}" em "{meal}" (alergeno: {a})'
                for meal, food, a in violations
            )
            logger.error(
                '[ALLERGY_VIOLATION] Plano para usuário %s viola alergias declaradas: %s',
                anamnese.user_id, details,
            )
            raise AllergenViolation(
                f'O plano gerado contém alimentos que violam alergias declaradas: '
                f'{details}. Tente gerar novamente.'
            )

    # ──────────────────────────────────────────────────────────────────────────
    #  DICAS PERSONALIZADAS (chamada separada, falha silenciosamente)
    # ──────────────────────────────────────────────────────────────────────────

    def _generate_notes(
        self,
        diet_data: dict,
        anamnese: Anamnese,
        target_calories: int,
    ) -> dict:
        """
        Gera dicas práticas e personalizadas com base no perfil e plano reais.

        Retorna um dict com:
          - 'notes': string com dicas gerais formatadas em bullet points (ou None)
          - 'meal_notes': dict {int(index): str} com dicas por refeição (ou {})

        Falha silenciosamente — o plano é válido mesmo sem dicas.
        """
        prompt = build_notes_prompt(diet_data, anamnese, target_calories)
        try:
            raw = self._call_api(
                prompt,
                system_prompt=SYSTEM_PROMPT_NOTES,
                temperature=0.7,
                json_mode=True,
                max_tokens=800,  # 3–5 dicas gerais + meal_notes por refeição
            )
            result = self._parse_response(raw)

            # Dicas gerais
            tips = result.get('tips')
            notes_str = None
            if tips and isinstance(tips, list):
                cleaned = [t.strip() for t in tips if isinstance(t, str) and t.strip()]
                notes_str = '\n'.join(f'• {t}' for t in cleaned) if cleaned else None

            # Dicas por refeição — o modelo usa o nome da refeição como chave.
            # Converte para índice inteiro mapeando pelo nome real das refeições,
            # com fallback para chaves numéricas (0-based e 1-based) por compatibilidade.
            meal_notes_raw = result.get('meal_notes', {})
            meal_notes: dict[int, str] = {}
            if isinstance(meal_notes_raw, dict):
                meals = diet_data.get('meals', [])
                meal_name_to_index = {
                    m.get('name', ''): i for i, m in enumerate(meals)
                }
                for k, v in meal_notes_raw.items():
                    if not (isinstance(v, str) and v.strip()):
                        continue
                    if k in meal_name_to_index:
                        meal_notes[meal_name_to_index[k]] = v.strip()
                    elif k.isdigit():
                        idx = int(k)
                        # aceita tanto 0-based quanto 1-based
                        if 0 <= idx < len(meals):
                            meal_notes[idx] = v.strip()
                        elif 1 <= idx <= len(meals):
                            meal_notes[idx - 1] = v.strip()

            return {'notes': notes_str, 'meal_notes': meal_notes}

        except Exception as exc:
            logger.warning('Falha ao gerar dicas personalizadas (não crítico): %s', exc)
            return {'notes': None, 'meal_notes': {}}

    # ──────────────────────────────────────────────────────────────────────────
    #  PASSO 2 — EXPLICAÇÃO (chamada separada, falha silenciosamente)
    # ──────────────────────────────────────────────────────────────────────────

    def _generate_explanation(
        self,
        diet_data: dict,
        anamnese: Anamnese,
        tmb: int,
        tdee: int,
        target_calories: int,
    ) -> dict | None:
        """
        Gera o objeto 'explanation' em chamada separada com temperature mais alta.
        Retorna None se falhar — a explicação é opcional e o frontend tem fallback.
        """
        prompt = build_explanation_prompt(diet_data, anamnese, tmb, tdee, target_calories)
        try:
            raw = self._call_api(
                prompt,
                system_prompt=SYSTEM_PROMPT_EXPLANATION,
                temperature=0.7,
                json_mode=True,
                max_tokens=1200,  # 5 seções × ~3 parágrafos × ~80 tokens cada
            )
            explanation = self._parse_response(raw)
            # Valida que os 5 campos obrigatórios existem
            required = {'calorie_calculation', 'macro_distribution', 'food_choices',
                        'meal_structure', 'goal_alignment'}
            if not required.issubset(explanation.keys()):
                logger.warning('Explanation incompleta: campos faltando. Ignorando.')
                return None
            return explanation
        except Exception as exc:
            logger.warning('Falha ao gerar explanation (não crítico): %s', exc)
            return None

    # ──────────────────────────────────────────────────────────────────────────
    #  MÉTODO PRINCIPAL
    # ──────────────────────────────────────────────────────────────────────────

    def generate_diet(self, anamnese: Anamnese) -> DietPlan:
        """
        Gera e persiste um DietPlan completo.

        Fluxo:
          1. Backend calcula alvo calórico e macros (Mifflin-St Jeor) — determinístico
          2. LLM Passo 1 (temp=0.55): seleciona alimentos + quantidades
          3. Backend: enriquece com macros do nutrition_db, ajusta porções — determinístico
          4. Backend: gera substituições — determinístico
          5. LLM Passos 2+3 (temp=0.7) em paralelo: notas e explicação — simultâneos
          6. Persiste DietPlan + Meals no banco
        """
        tmb, tdee, target_calories = calculate_calories(anamnese)
        logger.info(
            'Alvo calórico para usuário %s: TMB=%d, TDEE=%d, meta=%d kcal (objetivo: %s)',
            anamnese.user_id, tmb, tdee, target_calories, anamnese.goal,
        )

        # ── Passo 1: seleção de alimentos ────────────────────────────────────
        prompt = build_food_selection_prompt(anamnese)
        logger.info('Passo 1 — chamando IA para seleção de alimentos (usuário %s)...', anamnese.user_id)

        try:
            raw_response = self._call_api(
                prompt,
                system_prompt=SYSTEM_PROMPT_FOODS,
                temperature=0.55,
                json_mode=True,
                max_tokens=2500,  # ~6 refeições × ~5 alimentos × ~80 tokens cada + overhead JSON
            )
        except urllib.error.HTTPError as e:
            logger.error('Erro HTTP na chamada à IA (Passo 1): %s', e)
            raise Exception(f'Falha ao contatar a API da IA: HTTP {e.code}')
        except Exception as e:
            logger.error('Erro na chamada à IA (Passo 1): %s', e)
            raise Exception('Falha ao gerar o plano alimentar. Tente novamente.')

        diet_data = self._parse_response(raw_response)

        if 'meals' not in diet_data or not diet_data['meals']:
            raise TransientAIError('A IA não retornou refeições válidas. Tente novamente.')

        # ── Enforcement de alergias (fail-fast antes do trabalho caro) ────────
        self._enforce_allergies(diet_data, anamnese)

        # ── Backend: enriquece com macros do banco nutricional ────────────────
        logger.info('Calculando macros via banco nutricional para usuário %s...', anamnese.user_id)
        diet_data, db_stats = self._enrich_foods_with_macros(diet_data)
        # Rejeita planos com cobertura insuficiente — força retry da task
        self._check_db_coverage(db_stats, anamnese)
        diet_data = self._recalculate_totals(diet_data)
        diet_data = self._adjust_to_calorie_target(diet_data, target_calories)
        diet_data = self._round_portions(diet_data, target_calories)

        logger.info(
            'Macros calculados: %d kcal | P=%dg | C=%dg | G=%dg (alvo: %d kcal)',
            diet_data.get('calories', 0),
            diet_data.get('macros', {}).get('protein_g', 0),
            diet_data.get('macros', {}).get('carbs_g', 0),
            diet_data.get('macros', {}).get('fat_g', 0),
            target_calories,
        )
        self._check_protein_adequacy(diet_data, anamnese, target_calories)
        self._validate_macro_ratios(diet_data, anamnese, target_calories)

        # ── Substituições inteligentes (determinístico — backend, sem IA) ──────
        allergens_list = _parse_allergens(anamnese.allergies or '')
        diet_data['substitutions'] = generate_meal_substitutions(
            diet_data.get('meals', []), allergens_list
        )
        logger.info(
            '[SUBSTITUTIONS] %d substituições geradas para usuário %s.',
            len(diet_data['substitutions']), anamnese.user_id,
        )

        # ── Passos 2 e 3 em paralelo (independentes entre si) ────────────────
        # Notas e explicação dependem apenas do diet_data do Passo 1 — não há
        # dependência entre elas, então rodam simultaneamente em threads separadas.
        logger.info('Passos 2 e 3 — gerando notas e explicação em paralelo (usuário %s)...', anamnese.user_id)
        notes: dict | None = None
        explanation: dict | None = None

        with ThreadPoolExecutor(max_workers=2) as executor:
            fut_notes = executor.submit(
                self._generate_notes, diet_data, anamnese, target_calories
            )
            fut_explanation = executor.submit(
                self._generate_explanation, diet_data, anamnese, tmb, tdee, target_calories
            )
            for fut in as_completed([fut_notes, fut_explanation]):
                try:
                    result = fut.result()
                    if fut is fut_notes:
                        notes = result
                    else:
                        explanation = result
                except Exception as exc:
                    logger.warning('Falha em chamada paralela à IA (não crítico): %s', exc)

        if isinstance(notes, dict):
            if notes.get('notes'):
                diet_data['notes'] = notes['notes']
            meal_notes_map = notes.get('meal_notes', {})
            for i, meal in enumerate(diet_data.get('meals', [])):
                note = meal_notes_map.get(i)
                if note:
                    meal['meal_notes'] = note
        diet_data['explanation'] = explanation

        # ── Persiste DietPlan ─────────────────────────────────────────────────
        diet_plan = DietPlan.objects.create(
            user=anamnese.user,
            anamnese=anamnese,
            raw_response=diet_data,
            total_calories=diet_data.get('calories'),
            goal_description=diet_data.get('goal_description', ''),
        )

        # ── Persiste Meals ────────────────────────────────────────────────────
        meals_to_create = []
        for idx, meal in enumerate(diet_data.get('meals', [])):
            foods = meal.get('foods', [])

            food_lines = [
                f'• {f.get("name", "")} — {f.get("quantity", f.get("quantity_text", ""))}'
                for f in foods if f.get('name')
            ]
            description = '\n'.join(food_lines) if food_lines else ', '.join(
                f.get('name', '') for f in foods
            )

            meal_kcal = sum(f.get('calories', 0) for f in foods)

            meal_name = meal.get('name', f'Refeição {idx + 1}')
            time_suggestion = meal.get('time_suggestion', '')
            if time_suggestion:
                meal_name = f'{meal_name} ({time_suggestion})'

            meals_to_create.append(Meal(
                diet_plan=diet_plan,
                meal_name=meal_name,
                description=description,
                calories=meal_kcal,
                order=idx,
            ))

        Meal.objects.bulk_create(meals_to_create)

        logger.info(
            'DietPlan#%s criado: %d refeições, %d kcal (usuário %s)',
            diet_plan.pk, len(meals_to_create), diet_plan.total_calories, anamnese.user_id,
        )
        return diet_plan

    # ──────────────────────────────────────────────────────────────────────────
    #  REGENERAÇÃO PONTUAL DE REFEIÇÃO
    # ──────────────────────────────────────────────────────────────────────────

    def regenerate_meal(
        self,
        diet_plan: DietPlan,
        meal_index: int,
        reason: str = '',
    ) -> dict:
        """
        Regenera uma refeição específica sem alterar as demais do plano.

        Fluxo:
          1. Monta prompt com contexto do plano completo e perfil do usuário
          2. Chama IA (temp=0.7 para variedade)
          3. Enriquece os novos alimentos com macros do nutrition_db
          4. Retorna dict com os dados da nova refeição (não persiste — a view persiste)

        Returns dict com:
          new_raw_meal     — meal dict enriquecido para raw_response['meals'][meal_index]
          new_description  — string de bullet points para Meal.description
          new_calories     — int para Meal.calories
          new_meal_name    — str com horário para Meal.meal_name
        """
        raw = diet_plan.raw_response or {}
        meals = raw.get('meals', [])

        if not (0 <= meal_index < len(meals)):
            raise ValueError(f'Índice de refeição inválido: {meal_index}')

        if not diet_plan.anamnese_id:
            raise ValueError('DietPlan sem anamnese associada — não é possível regenerar.')

        current_meal = meals[meal_index]
        prompt = build_meal_regen_prompt(diet_plan, meal_index, reason)

        logger.info(
            'Regenerando refeição %d ("%s") do DietPlan#%s (usuário %s)...',
            meal_index,
            current_meal.get('name', '?'),
            diet_plan.pk,
            diet_plan.user_id,
        )

        try:
            raw_response = self._call_api(
                prompt,
                system_prompt=SYSTEM_PROMPT_MEAL_REGEN,
                temperature=0.7,
                json_mode=True,
            )
        except urllib.error.HTTPError as e:
            logger.error('Erro HTTP na chamada à IA (regeneração): %s', e)
            raise Exception(f'Falha ao contatar a API da IA: HTTP {e.code}')
        except Exception as e:
            logger.error('Erro na chamada à IA (regeneração): %s', e)
            raise Exception('Falha ao regenerar a refeição. Tente novamente.')

        new_meal_data = self._parse_response(raw_response)

        if not new_meal_data.get('foods'):
            raise TransientAIError('A IA não retornou alimentos válidos para a refeição.')

        # Preserva nome e horário caso a IA omita ou altere
        new_meal_data.setdefault('name', current_meal.get('name', f'Refeição {meal_index + 1}'))
        new_meal_data.setdefault('time_suggestion', current_meal.get('time_suggestion', ''))

        # Enforcement de alergias antes de enriquecer (fail-fast)
        self._enforce_allergies({'meals': [new_meal_data]}, diet_plan.anamnese)

        # Enriquece com macros do banco nutricional (determinístico)
        enriched, db_stats = self._enrich_foods_with_macros({'meals': [new_meal_data]})
        # Rejeita refeição com cobertura insuficiente — usuário pode tentar de novo manualmente
        self._check_db_coverage(db_stats, diet_plan.anamnese)
        enriched = self._round_portions(enriched)
        new_meal = enriched['meals'][0]

        foods = new_meal.get('foods', [])
        food_lines = [
            f'• {f.get("name", "")} — {f.get("quantity", f.get("quantity_text", ""))}'
            for f in foods if f.get('name')
        ]
        new_description = '\n'.join(food_lines) if food_lines else ', '.join(
            f.get('name', '') for f in foods
        )
        new_calories = sum(f.get('calories', 0) for f in foods)

        meal_name = new_meal.get('name', f'Refeição {meal_index + 1}')
        time_suggestion = new_meal.get('time_suggestion', '')
        new_meal_name = f'{meal_name} ({time_suggestion})' if time_suggestion else meal_name

        logger.info(
            'Refeição %d regenerada: %d kcal, %d alimentos (DietPlan#%s)',
            meal_index, new_calories, len(foods), diet_plan.pk,
        )

        return {
            'new_raw_meal':    new_meal,
            'new_description': new_description,
            'new_calories':    new_calories,
            'new_meal_name':   new_meal_name,
        }
