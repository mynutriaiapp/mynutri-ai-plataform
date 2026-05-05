"""
Pacote de prompts — MyNutri AI.

Estrutura:
  _constants.py     — constantes numéricas (macros, atividade, refeições)
  _calculations.py  — cálculo determinístico de calorias, macros e distribuição
  food_selection.py — Passo 1: seleção de alimentos pelo LLM
  explanation.py    — Passo 2a: explicação do plano pelo LLM
  notes.py          — Passo 2b: dicas práticas personalizadas pelo LLM
  meal_regen.py     — Regeneração pontual de refeição pelo LLM

Re-exporta todos os símbolos públicos para manter backward compatibility
com importações existentes (services.py, test_prompts.py, test_critical.py).
"""

# ── Cálculos determinísticos ──────────────────────────────────────────────────
from ._calculations import (
    build_meal_distribution_hint,
    calculate_calories,
    calculate_macros,
)

# ── Passo 1 — Seleção de alimentos ────────────────────────────────────────────
from .food_selection import (
    FOOD_SELECTION_TEMPLATE,
    GOAL_CONTEXT,
    SYSTEM_PROMPT_FOODS,
    build_food_selection_prompt,
)

# ── Passo 2a — Explicação ─────────────────────────────────────────────────────
from .explanation import (
    EXPLANATION_TEMPLATE,
    SYSTEM_PROMPT_EXPLANATION,
    build_explanation_prompt,
)

# ── Passo 2b — Dicas personalizadas ──────────────────────────────────────────
from .notes import (
    NOTES_TEMPLATE,
    SYSTEM_PROMPT_NOTES,
    build_notes_prompt,
)

# ── Regeneração de refeição ───────────────────────────────────────────────────
from .meal_regen import (
    MEAL_REGEN_TEMPLATE,
    SYSTEM_PROMPT_MEAL_REGEN,
    build_meal_regen_prompt,
)

__all__ = [
    # cálculos
    'build_meal_distribution_hint',
    'calculate_calories',
    'calculate_macros',
    # food selection
    'FOOD_SELECTION_TEMPLATE',
    'GOAL_CONTEXT',
    'SYSTEM_PROMPT_FOODS',
    'build_food_selection_prompt',
    # explanation
    'EXPLANATION_TEMPLATE',
    'SYSTEM_PROMPT_EXPLANATION',
    'build_explanation_prompt',
    # notes
    'NOTES_TEMPLATE',
    'SYSTEM_PROMPT_NOTES',
    'build_notes_prompt',
    # meal regen
    'MEAL_REGEN_TEMPLATE',
    'SYSTEM_PROMPT_MEAL_REGEN',
    'build_meal_regen_prompt',
]
