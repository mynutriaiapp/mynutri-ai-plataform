import json
import os
import logging
import urllib.request
import urllib.error

from .models import Anamnese, DietPlan, Meal
from .prompts import SYSTEM_PROMPT, build_diet_prompt, calculate_calories

logger = logging.getLogger(__name__)


class AIService:
    """
    Responsável por chamar a API de IA e transformar a resposta
    em registros de DietPlan e Meal no banco de dados.

    Usa as variáveis de ambiente:
        AI_API_KEY  → chave de autenticação da IA
        AI_API_URL  → endpoint da API (ex: OpenAI, Gemini, etc.)
    """

    def __init__(self):
        self.api_key = os.getenv('AI_API_KEY', '')
        self.api_url = os.getenv('AI_API_URL', '')

    def _build_prompt(self, anamnese: Anamnese) -> str:
        return build_diet_prompt(anamnese)

    def _call_api(self, prompt: str) -> dict:
        """
        Realiza a chamada HTTP à API de IA.
        Suporta qualquer API compatível com o formato OpenAI Chat Completions.
        """
        if not self.api_key or not self.api_url:
            raise ValueError(
                'AI_API_KEY e AI_API_URL devem estar configurados no arquivo .env'
            )

        payload = json.dumps({
            'model': os.getenv('AI_MODEL', 'gpt-3.5-turbo'),
            'messages': [
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': prompt},
            ],
            'temperature': 0.6,
        }).encode('utf-8')

        req = urllib.request.Request(
            self.api_url,
            data=payload,
            headers={
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self.api_key}',
            },
            method='POST',
        )

        with urllib.request.urlopen(req, timeout=120) as response:
            raw = response.read().decode('utf-8')
            return json.loads(raw)

    def _parse_response(self, api_response: dict) -> dict:
        """
        Extrai o conteúdo JSON gerado pela IA da resposta da API.
        Suporta o formato padrão OpenAI (choices[0].message.content).
        Remove markdown code blocks (```json ... ```) caso a IA os inclua.
        """
        try:
            content = api_response['choices'][0]['message']['content']
        except (KeyError, IndexError) as e:
            logger.error('Falha ao parsear resposta da IA: %s | Resposta: %s', e, api_response)
            raise ValueError('A IA retornou um formato inesperado. Tente novamente.')

        # Remove markdown code fences: ```json\n...\n``` ou ```\n...\n```
        stripped = content.strip()
        if stripped.startswith('```'):
            lines = stripped.split('\n')
            # Remove primeira linha (```json ou ```) e última linha (```)
            inner = lines[1:] if lines[-1].strip() == '```' else lines[1:]
            if inner and inner[-1].strip() == '```':
                inner = inner[:-1]
            stripped = '\n'.join(inner)

        try:
            return json.loads(stripped)
        except json.JSONDecodeError as e:
            logger.error('Falha ao parsear JSON da IA: %s | Conteúdo: %s', e, content[:200])
            raise ValueError('A IA retornou um formato inesperado. Tente novamente.')

    def _normalize_diet_data(self, diet_data: dict) -> dict:
        """
        Recalcula os totais de calorias e macros somando os valores reais
        de cada alimento (foods[]) em cada refeição (meals[]).

        Garante consistência matemática independentemente do que a IA declarou
        nos campos de nível superior ("calories", "macros").

        Regra: a fonte da verdade são os alimentos individuais, não o total declarado.
        """
        meals = diet_data.get('meals', [])

        total_kcal = 0
        total_protein = 0.0
        total_carbs = 0.0
        total_fat = 0.0
        has_per_food_macros = False

        for meal in meals:
            for food in meal.get('foods', []):
                total_kcal    += food.get('calories', 0) or 0
                p = food.get('protein_g')
                c = food.get('carbs_g')
                f = food.get('fat_g')
                if p is not None or c is not None or f is not None:
                    has_per_food_macros = True
                    total_protein += p or 0
                    total_carbs   += c or 0
                    total_fat     += f or 0

        declared_kcal = diet_data.get('calories') or 0

        if total_kcal > 0:
            divergence = abs(total_kcal - declared_kcal) / declared_kcal if declared_kcal else 1
            if divergence > 0.05:
                logger.warning(
                    'Inconsistência calórica corrigida: IA declarou %d kcal, '
                    'soma real dos alimentos = %d kcal (divergência %.1f%%).',
                    declared_kcal, total_kcal, divergence * 100,
                )
            # Sobrescreve sempre — a soma real é a fonte da verdade
            diet_data['calories'] = total_kcal

        if has_per_food_macros:
            # Recalcula macros a partir dos alimentos individuais
            diet_data['macros'] = {
                'protein_g': round(total_protein),
                'carbs_g':   round(total_carbs),
                'fat_g':     round(total_fat),
            }
        elif diet_data.get('macros') and total_kcal > 0:
            # Macros por alimento não informados: ajusta proporcionalmente
            # se a IA declarou macros mas as calorias divergem.
            macros = diet_data['macros']
            macro_kcal = (
                (macros.get('protein_g', 0) or 0) * 4 +
                (macros.get('carbs_g',   0) or 0) * 4 +
                (macros.get('fat_g',     0) or 0) * 9
            )
            if macro_kcal > 0 and abs(macro_kcal - total_kcal) / total_kcal > 0.05:
                scale = total_kcal / macro_kcal
                diet_data['macros'] = {
                    'protein_g': round((macros.get('protein_g', 0) or 0) * scale),
                    'carbs_g':   round((macros.get('carbs_g',   0) or 0) * scale),
                    'fat_g':     round((macros.get('fat_g',     0) or 0) * scale),
                }

        return diet_data

    def _enforce_calorie_target(self, diet_data: dict, target_calories: int) -> dict:
        """
        Garante que as calorias totais do plano batem com o alvo calculado pelo backend.

        Se a IA gerou um total fora de ±10% do alvo, escala proporcionalmente os valores
        calóricos e de macros de TODOS os alimentos para corrigir o desvio.

        As quantidades em texto (ex: "120g", "2 unidades") não são alteradas — apenas os
        números de calorias e macros, que a IA aproxima de qualquer forma.
        """
        actual = diet_data.get('calories', 0)
        if not actual or not target_calories:
            return diet_data

        divergence = abs(actual - target_calories) / target_calories
        if divergence <= 0.10:
            return diet_data

        scale = target_calories / actual
        logger.warning(
            'Calorias geradas pela IA (%d kcal) divergem %.1f%% do alvo (%d kcal). '
            'Escalando todos os alimentos por fator %.4f.',
            actual, divergence * 100, target_calories, scale,
        )

        for meal in diet_data.get('meals', []):
            for food in meal.get('foods', []):
                if food.get('calories') is not None:
                    food['calories'] = round(food['calories'] * scale)
                for macro in ('protein_g', 'carbs_g', 'fat_g'):
                    if food.get(macro) is not None:
                        food[macro] = round(food[macro] * scale, 1)

        # Re-normaliza para recalcular os campos de nível superior com os valores escalados
        return self._normalize_diet_data(diet_data)

    def generate_diet(self, anamnese: Anamnese) -> DietPlan:
        """
        Método principal: monta o prompt, chama a IA, parseia JSON e
        persiste DietPlan + Meals no banco de dados.

        Returns:
            DietPlan: objeto criado no banco com todas as refeições.

        Raises:
            ValueError: se a IA estiver mal configurada ou retornar formato inválido.
            Exception: se a chamada HTTP falhar.
        """
        # Calcula o alvo calórico no backend antes de chamar a IA
        _tmb, _tdee, target_calories = calculate_calories(anamnese)
        logger.info(
            'Alvo calórico para usuário %s: TMB=%d, TDEE=%d, meta=%d kcal (objetivo: %s)',
            anamnese.user_id, _tmb, _tdee, target_calories, anamnese.goal,
        )

        prompt = self._build_prompt(anamnese)
        logger.info('Gerando dieta para usuário %s via IA...', anamnese.user_id)

        try:
            raw_response = self._call_api(prompt)
        except urllib.error.HTTPError as e:
            logger.error('Erro HTTP na chamada à IA: %s', e)
            raise Exception(f'Falha ao contatar a API da IA: HTTP {e.code}')
        except Exception as e:
            logger.error('Erro inesperado na chamada à IA: %s', e)
            raise Exception('Falha ao gerar o plano alimentar via IA, tente novamente mais tarde.')

        diet_data = self._parse_response(raw_response)
        diet_data = self._normalize_diet_data(diet_data)
        diet_data = self._enforce_calorie_target(diet_data, target_calories)

        # Persiste o DietPlan com o JSON bruto completo (já normalizado)
        diet_plan = DietPlan.objects.create(
            user=anamnese.user,
            anamnese=anamnese,
            raw_response=diet_data,
            total_calories=diet_data.get('calories'),
            goal_description=diet_data.get('goal_description') or diet_data.get('notes', ''),
        )

        # Persiste cada refeição individualmente
        # Novo formato: meals[].foods[] — monta descrição a partir dos alimentos
        meals_to_create = []
        for idx, meal in enumerate(diet_data.get('meals', [])):
            foods = meal.get('foods', [])
            # Monta descrição rica: cada alimento em linha separada com quantidade
            food_lines = [
                f'• {f.get("name", "")} — {f.get("quantity", "")}'
                for f in foods
                if f.get('name')
            ]
            description = '\n'.join(food_lines) if food_lines else ', '.join(
                f'{f.get("name", "")} ({f.get("quantity", "")})'
                for f in foods
            )
            total_meal_calories = sum(f.get('calories', 0) for f in foods)
            # Inclui horário sugerido no nome da refeição se disponível
            meal_name = meal.get('name', '')
            time_suggestion = meal.get('time_suggestion', '')
            if time_suggestion:
                meal_name = f'{meal_name} ({time_suggestion})'
            meals_to_create.append(
                Meal(
                    diet_plan=diet_plan,
                    meal_name=meal_name,
                    description=description,
                    calories=total_meal_calories,
                    order=idx,
                )
            )
        Meal.objects.bulk_create(meals_to_create)

        logger.info(
            'Dieta gerada com sucesso: DietPlan#%s (%d refeições, %s kcal)',
            diet_plan.id, len(meals_to_create), diet_plan.total_calories
        )
        return diet_plan
