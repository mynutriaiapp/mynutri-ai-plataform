"""
Constantes determinísticas usadas no cálculo calórico e de macros.
Nenhum LLM acessa este módulo — é usado exclusivamente pelo backend.
"""

# ─── Proteína (g/kg de peso corporal, por objetivo) ──────────────────────────
PROTEIN_PER_KG: dict[str, float] = {
    'lose':     2.0,   # alto para preservar massa magra no déficit
    'maintain': 1.6,
    'gain':     2.0,   # alto para síntese proteica
}

PROTEIN_MIN_PER_KG = 1.6   # mínimo para preservação de massa magra
PROTEIN_MAX_PER_KG = 2.2   # acima não traz benefício adicional

# ─── Gordura (g/kg de peso corporal, por objetivo) ───────────────────────────
FAT_PER_KG: dict[str, float] = {
    'lose':     0.8,   # moderado — preserva função hormonal no déficit
    'maintain': 0.8,
    'gain':     0.7,   # menor gordura = mais kcal restam para carboidratos
}

FAT_MIN_PER_KG = 0.6   # mínimo para produção hormonal e vitaminas lipossolúveis
FAT_MAX_PER_KG = 1.0   # acima não há benefício metabólico documentado

# ─── Fatores de atividade (Harris-Benedict / Mifflin-St Jeor) ────────────────
ACTIVITY_FACTORS: dict[str, float] = {
    'sedentary': 1.2,
    'light':     1.375,
    'moderate':  1.55,
    'intense':   1.725,
    'athlete':   1.9,
}

# ─── Ajustes calóricos por objetivo (kcal/dia) ───────────────────────────────
GOAL_ADJUSTMENTS: dict[str, int] = {
    'lose':     -450,
    'maintain':    0,
    'gain':      350,
}

GOAL_ADJUSTMENT_LABELS: dict[str, str] = {
    'lose':     'Déficit de 450 kcal (emagrecimento)',
    'maintain': 'Sem ajuste (manutenção)',
    'gain':     'Superávit de 350 kcal (ganho de massa)',
}

# ─── Calorias mínimas por sexo ────────────────────────────────────────────────
MIN_CALORIES: dict[str, int] = {
    'M': 1500,
    'F': 1200,
    'O': 1350,
}

# ─── Distribuição calórica por número de refeições ───────────────────────────
# Cada entrada: lista de (nome_da_refeição, fração_do_total_diário).
MEAL_PLANS: dict[int, list[tuple[str, float]]] = {
    1: [('Refeição principal', 1.00)],
    2: [('Café da manhã', 0.45), ('Jantar', 0.55)],
    3: [('Café da manhã', 0.25), ('Almoço', 0.40), ('Jantar', 0.35)],
    4: [('Café da manhã', 0.25), ('Almoço', 0.35), ('Lanche', 0.10), ('Jantar', 0.30)],
    5: [('Café da manhã', 0.20), ('Almoço', 0.30), ('Lanche da manhã', 0.10),
        ('Lanche da tarde', 0.10), ('Jantar', 0.30)],
    6: [('Café da manhã', 0.20), ('Almoço', 0.25), ('Lanche da manhã', 0.10),
        ('Lanche da tarde', 0.10), ('Jantar', 0.25), ('Ceia', 0.10)],
}
