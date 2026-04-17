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
import urllib.error
import urllib.request

from .models import Anamnese, DietPlan, Meal
from .nutrition_db import lookup_food_nutrition
from .prompts import (
    SYSTEM_PROMPT_EXPLANATION,
    SYSTEM_PROMPT_FOODS,
    build_explanation_prompt,
    build_food_selection_prompt,
    calculate_calories,
)

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
    ) -> dict:
        """Realiza chamada à API de IA (formato OpenAI Chat Completions)."""
        if not self.api_key or not self.api_url:
            raise ValueError('AI_API_KEY e AI_API_URL devem estar configurados no .env')

        body: dict = {
            'model':       self.model,
            'messages':    [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user',   'content': user_prompt},
            ],
            'temperature': temperature,
        }
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

        with urllib.request.urlopen(req, timeout=120) as response:
            return json.loads(response.read().decode('utf-8'))

    def _parse_response(self, api_response: dict) -> dict:
        """Extrai e parseia o JSON gerado pela IA."""
        try:
            content = api_response['choices'][0]['message']['content']
        except (KeyError, IndexError) as e:
            logger.error('Formato inesperado da API: %s | resposta: %s', e, api_response)
            raise ValueError('A IA retornou um formato inesperado. Tente novamente.')

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
            raise ValueError('A IA retornou um formato inesperado. Tente novamente.')

    # ──────────────────────────────────────────────────────────────────────────
    #  ENRIQUECIMENTO NUTRICIONAL (backend — determinístico)
    # ──────────────────────────────────────────────────────────────────────────

    def _enrich_foods_with_macros(self, diet_data: dict) -> dict:
        """
        Consulta o nutrition_db para cada alimento e atribui calorias e macros.
        Também padroniza o campo 'quantity' para exibição no frontend.
        """
        for meal in diet_data.get('meals', []):
            for food in meal.get('foods', []):
                qty_g    = float(food.get('quantity_g') or 100)
                qty_text = food.get('quantity_text', f'{qty_g:.0f}g')

                nutrition = lookup_food_nutrition(food.get('name', ''), qty_g)
                food['calories']  = nutrition['calories']
                food['protein_g'] = nutrition['protein_g']
                food['carbs_g']   = nutrition['carbs_g']
                food['fat_g']     = nutrition['fat_g']

                # Campo 'quantity' usado pelo frontend (combina texto + gramas)
                qty_g_int = round(qty_g)
                if str(qty_g_int) in qty_text or f'{qty_g_int}g' in qty_text:
                    food['quantity'] = qty_text
                else:
                    food['quantity'] = f'{qty_text} ({qty_g_int}g)'

        return diet_data

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

    def _adjust_to_calorie_target(self, diet_data: dict, target_calories: int) -> dict:
        """
        Se o total calculado divergir mais de 10% do alvo, escala quantity_g
        de todos os alimentos proporcionalmente e recalcula os macros.

        Escalar quantity_g (e não só as calorias) mantém a consistência entre
        os valores nutricionais e as quantidades exibidas para o usuário.
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
            'Escalando quantity_g por fator %.4f.',
            actual, divergence * 100, target_calories, scale,
        )

        for meal in diet_data.get('meals', []):
            for food in meal.get('foods', []):
                old_qty = float(food.get('quantity_g') or 100)
                new_qty = round(old_qty * scale)
                food['quantity_g'] = new_qty

                # Atualiza o campo de exibição com a nova quantidade em gramas
                qty_text = food.get('quantity_text', '')
                food['quantity'] = f'{qty_text} ({new_qty}g)' if qty_text else f'{new_qty}g'

                # Recalcula macros para a nova quantidade
                nutrition = lookup_food_nutrition(food.get('name', ''), new_qty)
                food['calories']  = nutrition['calories']
                food['protein_g'] = nutrition['protein_g']
                food['carbs_g']   = nutrition['carbs_g']
                food['fat_g']     = nutrition['fat_g']

        return self._recalculate_totals(diet_data)

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
          1. Backend calcula alvo calórico (Mifflin-St Jeor)
          2. LLM Passo 1 (temp=0.3): seleciona alimentos + quantidades
          3. Backend: enriquece com macros do nutrition_db (determinístico)
          4. Backend: ajusta porções se divergência > 10%
          5. LLM Passo 2 (temp=0.7): gera explicação de transparência
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
                temperature=0.3,
                json_mode=True,
            )
        except urllib.error.HTTPError as e:
            logger.error('Erro HTTP na chamada à IA (Passo 1): %s', e)
            raise Exception(f'Falha ao contatar a API da IA: HTTP {e.code}')
        except Exception as e:
            logger.error('Erro na chamada à IA (Passo 1): %s', e)
            raise Exception('Falha ao gerar o plano alimentar. Tente novamente.')

        diet_data = self._parse_response(raw_response)

        if 'meals' not in diet_data or not diet_data['meals']:
            raise ValueError('A IA não retornou refeições válidas. Tente novamente.')

        # ── Backend: enriquece com macros do banco nutricional ────────────────
        logger.info('Calculando macros via banco nutricional para usuário %s...', anamnese.user_id)
        diet_data = self._enrich_foods_with_macros(diet_data)
        diet_data = self._recalculate_totals(diet_data)
        diet_data = self._adjust_to_calorie_target(diet_data, target_calories)

        logger.info(
            'Macros calculados: %d kcal | P=%dg | C=%dg | G=%dg (alvo: %d kcal)',
            diet_data.get('calories', 0),
            diet_data.get('macros', {}).get('protein_g', 0),
            diet_data.get('macros', {}).get('carbs_g', 0),
            diet_data.get('macros', {}).get('fat_g', 0),
            target_calories,
        )

        # ── Passo 2: explicação (falha silenciosa) ────────────────────────────
        logger.info('Passo 2 — gerando explicação de transparência...')
        explanation = self._generate_explanation(diet_data, anamnese, tmb, tdee, target_calories)
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
