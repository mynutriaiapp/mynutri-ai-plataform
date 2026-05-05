"""
Cálculos determinísticos de calorias, macros e distribuição de refeições.
Executados 100% no backend — nenhum LLM faz aritmética nutricional.
"""

from ._constants import (
    ACTIVITY_FACTORS,
    FAT_MAX_PER_KG,
    FAT_MIN_PER_KG,
    FAT_PER_KG,
    GOAL_ADJUSTMENTS,
    MEAL_PLANS,
    MIN_CALORIES,
    PROTEIN_MAX_PER_KG,
    PROTEIN_MIN_PER_KG,
    PROTEIN_PER_KG,
)


def calculate_calories(anamnese) -> tuple[int, int, int]:
    """
    Calcula TMB, TDEE e meta calórica via Mifflin-St Jeor.
    Retorna (tmb, tdee, target_calories) — todos inteiros arredondados.
    """
    w = float(anamnese.weight_kg)
    h = float(anamnese.height_cm)
    a = int(anamnese.age)

    if anamnese.gender == 'M':
        tmb = (10 * w) + (6.25 * h) - (5 * a) + 5
    elif anamnese.gender == 'F':
        tmb = (10 * w) + (6.25 * h) - (5 * a) - 161
    else:
        tmb = (10 * w) + (6.25 * h) - (5 * a) - 78

    factor = ACTIVITY_FACTORS.get(anamnese.activity_level, 1.375)
    tdee   = tmb * factor
    adj    = GOAL_ADJUSTMENTS.get(anamnese.goal, 0)
    target = tdee + adj

    min_cal = MIN_CALORIES.get(anamnese.gender, 1350)
    target  = max(target, min_cal)

    return round(tmb), round(tdee), round(target)


def calculate_macros(anamnese, target_calories: int) -> dict:
    """
    Calcula metas de macronutrientes em três passos obrigatórios:

      Passo 1 — Proteína: baseada em g/kg (preservar/construir massa magra)
      Passo 2 — Gordura:  baseada em g/kg (suporte hormonal, vitaminas lipossolúveis)
      Passo 3 — Carboidrato: restante das calorias (energia, desempenho, metabolismo)

    Usar g/kg para proteína e gordura garante que as metas escalam com o peso
    corporal, não com as calorias — evita o problema de dietas hipercalóricas
    de ganho de massa resultarem em gordura excessiva quando calculada como %.

    Faixas de segurança:
      Proteína: 1.6–2.2g/kg | máx 40% das calorias (casos extremos)
      Gordura:  0.6–1.0g/kg | máx 35% das calorias (casos extremos)
      Carb:     restante — sem teto artificial
    """
    w = float(anamnese.weight_kg)

    # ── Passo 1: Proteína ────────────────────────────────────────────────────
    protein_per_kg = PROTEIN_PER_KG.get(anamnese.goal, 1.6)
    protein_g = round(w * protein_per_kg)
    protein_g = max(round(w * PROTEIN_MIN_PER_KG),
                    min(protein_g, round(w * PROTEIN_MAX_PER_KG)))
    protein_g    = min(protein_g, round(target_calories * 0.40 / 4))
    protein_kcal = protein_g * 4

    # ── Passo 2: Gordura ─────────────────────────────────────────────────────
    fat_per_kg = FAT_PER_KG.get(anamnese.goal, 0.8)
    fat_g = round(w * fat_per_kg)
    fat_g = max(round(w * FAT_MIN_PER_KG),
                min(fat_g, round(w * FAT_MAX_PER_KG)))
    fat_g    = min(fat_g, round(target_calories * 0.35 / 9))
    fat_kcal = fat_g * 9

    # ── Passo 3: Carboidrato = restante ──────────────────────────────────────
    carbs_kcal = max(0, target_calories - protein_kcal - fat_kcal)
    carbs_g    = round(carbs_kcal / 4)

    return {
        'protein_g':      protein_g,
        'protein_pct':    round(protein_kcal / target_calories * 100),
        'protein_per_kg': protein_per_kg,
        'fat_g':          fat_g,
        'fat_per_kg':     fat_per_kg,
        'fat_pct':        round(fat_kcal / target_calories * 100),
        'carbs_g':        carbs_g,
        'carbs_pct':      round(carbs_kcal / target_calories * 100),
    }


def build_meal_distribution_hint(meals_per_day: int, target_calories: int) -> str:
    """
    Gera lista de kcal esperada por refeição para incluir no prompt.
    Para >6 refeições distribui uniformemente com nomes genéricos.
    """
    plan = MEAL_PLANS.get(meals_per_day)
    if plan is None:
        frac = 1.0 / meals_per_day
        plan = [(f'Refeição {i + 1}', frac) for i in range(meals_per_day)]

    lines = []
    for name, frac in plan:
        kcal = round(target_calories * frac)
        lines.append(f'  - {name}: ~{kcal} kcal ({round(frac * 100)}%)')
    return '\n'.join(lines)
