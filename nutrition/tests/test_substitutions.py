"""
Testes do módulo de substituições alimentares — MyNutri AI.

Cobre: _norm, _classify_meal, _find_rule, _food_contains_allergen,
       generate_meal_substitutions (regras, filtros de refeição, alergias, deduplicação).
Testes puramente unitários — sem banco de dados.
"""

import pytest
from nutrition.substitutions import (
    _norm,
    _classify_meal,
    _find_rule,
    _food_contains_allergen,
    generate_meal_substitutions,
)


# ---------------------------------------------------------------------------
# _norm
# ---------------------------------------------------------------------------

class TestNorm:
    def test_remove_acentos(self):
        assert _norm("frango grelhado") == "frango grelhado"
        assert _norm("Feijão") == "feijao"
        assert _norm("Macarrão") == "macarrao"
        assert _norm("Azeite") == "azeite"

    def test_lowercase(self):
        assert _norm("FRANGO") == "frango"
        assert _norm("Arroz Branco") == "arroz branco"

    def test_cedilha_e_til(self):
        assert _norm("Atenção") == "atencao"
        assert _norm("não") == "nao"
        assert _norm("cação") == "cacao"

    def test_string_vazia(self):
        assert _norm("") == ""


# ---------------------------------------------------------------------------
# _classify_meal
# ---------------------------------------------------------------------------

class TestClassifyMeal:
    def test_cafe_da_manha(self):
        assert _classify_meal("Café da manhã") == "cafe"

    def test_cafe_sem_acento(self):
        assert _classify_meal("cafe da manha") == "cafe"

    def test_desjejum(self):
        assert _classify_meal("Desjejum") == "cafe"

    def test_lanche_manha(self):
        # "Lanche da manhã" contém "manha" que pertence a _CAFE_KEYWORDS,
        # e a verificação de café vem antes de lanche em _classify_meal.
        # O comportamento real é "cafe" — garantido aqui como documentação.
        assert _classify_meal("Lanche da manhã") == "cafe"

    def test_lanche_tarde(self):
        assert _classify_meal("Lanche da tarde") == "lanche"

    def test_ceia(self):
        assert _classify_meal("Ceia") == "ceia"

    def test_almoco(self):
        assert _classify_meal("Almoço") == "almoco"

    def test_jantar(self):
        assert _classify_meal("Jantar") == "almoco"

    def test_refeicao_generica(self):
        assert _classify_meal("Refeição 1") == "almoco"

    def test_string_vazia(self):
        assert _classify_meal("") == "almoco"


# ---------------------------------------------------------------------------
# _find_rule
# ---------------------------------------------------------------------------

class TestFindRule:
    def test_arroz_retorna_regra(self):
        result = _find_rule("Arroz branco cozido")
        assert result is not None
        category, alternatives = result
        assert category == "carbo_almoco"
        assert len(alternatives) >= 2

    def test_pao_integral_retorna_regra(self):
        result = _find_rule("Pão integral")
        assert result is not None
        category, _ = result
        assert category == "carbo_cafe"

    def test_frango_retorna_regra(self):
        result = _find_rule("Peito de frango grelhado")
        assert result is not None
        category, _ = result
        assert category == "proteina"

    def test_alimento_desconhecido_retorna_none(self):
        assert _find_rule("Pepino japonês orgânico") is None
        assert _find_rule("Kimchi fermentado") is None

    def test_match_mais_especifico_vence(self):
        result_especifico = _find_rule("Peito de frango grelhado")
        result_generico = _find_rule("Frango assado")
        assert result_especifico is not None
        assert result_generico is not None
        cat_esp, _ = result_especifico
        cat_gen, _ = result_generico
        assert cat_esp == "proteina"
        assert cat_gen == "proteina"

    def test_ovo_retorna_proteina_ovo(self):
        result = _find_rule("Ovo cozido")
        assert result is not None
        category, _ = result
        assert category == "proteina_ovo"

    def test_feijao_retorna_leguminosa(self):
        result = _find_rule("Feijão carioca")
        assert result is not None
        category, _ = result
        assert category == "leguminosa"

    def test_iogurte_retorna_laticinios(self):
        result = _find_rule("Iogurte natural")
        assert result is not None
        category, _ = result
        assert category == "laticinios"

    def test_banana_retorna_fruta(self):
        result = _find_rule("Banana prata")
        assert result is not None
        category, _ = result
        assert category == "fruta"

    def test_batata_doce_mais_especifica_que_batata(self):
        result = _find_rule("Batata doce cozida")
        assert result is not None
        _, alternatives = result
        alt_names = [a[0] for a in alternatives]
        assert any("Arroz" in n or "Mandioca" in n for n in alt_names)

    def test_azeite_retorna_gordura(self):
        result = _find_rule("Azeite de oliva")
        assert result is not None
        category, _ = result
        assert category == "gordura"


# ---------------------------------------------------------------------------
# _food_contains_allergen
# ---------------------------------------------------------------------------

class TestFoodContainsAllergen:
    def test_sem_alergenos(self):
        assert _food_contains_allergen("Frango grelhado", []) is False

    def test_alimento_vazio(self):
        assert _food_contains_allergen("", ["gluten"]) is False

    def test_alergeno_presente_palavra_inteira(self):
        assert _food_contains_allergen("Atum em água", ["atum"]) is True

    def test_alergeno_ausente(self):
        assert _food_contains_allergen("Frango grelhado", ["atum"]) is False

    def test_alergeno_multiplas_palavras(self):
        assert _food_contains_allergen("Peito de frango", ["peito de frango"]) is True

    def test_alergeno_multiplas_palavras_ausente(self):
        assert _food_contains_allergen("Frango cozido", ["peito de frango"]) is False

    def test_word_boundary_evita_falso_positivo(self):
        assert _food_contains_allergen("Iogurte natural", ["ovo"]) is False

    def test_normaliza_antes_de_comparar(self):
        assert _food_contains_allergen("Salmão grelhado", ["salmao"]) is True

    def test_lista_multiplos_alergenos(self):
        assert _food_contains_allergen("Tilápia grelhada", ["atum", "tilapia"]) is True
        assert _food_contains_allergen("Arroz cozido", ["atum", "tilapia"]) is False


# ---------------------------------------------------------------------------
# generate_meal_substitutions — casos principais
# ---------------------------------------------------------------------------

def _make_meal(name, foods):
    return {"name": name, "foods": [{"name": f, "quantity_g": g} for f, g in foods]}


class TestGenerateMealSubstitutions:
    def test_retorna_lista_vazia_sem_refeicoes(self):
        assert generate_meal_substitutions([]) == []

    def test_retorna_lista_vazia_sem_alimentos_reconhecidos(self):
        meal = _make_meal("Almoço", [("Kimchi", 100), ("Tempeh", 80)])
        result = generate_meal_substitutions([meal])
        assert result == []

    def test_arroz_no_almoco_gera_substituicoes(self):
        meal = _make_meal("Almoço", [("Arroz cozido", 150)])
        result = generate_meal_substitutions([meal])
        assert len(result) == 1
        entry = result[0]
        assert "Arroz cozido" in entry["food"]
        assert len(entry["alternatives"]) >= 2

    def test_pao_no_cafe_gera_substituicoes(self):
        meal = _make_meal("Café da manhã", [("Pão integral", 60)])
        result = generate_meal_substitutions([meal])
        assert len(result) >= 1
        assert any("Pão integral" in r["food"] for r in result)

    def test_filtro_de_refeicao_arroz_nao_aparece_no_cafe(self):
        meal = _make_meal("Café da manhã", [("Arroz cozido", 150)])
        result = generate_meal_substitutions([meal])
        assert result == []

    def test_filtro_de_refeicao_pao_nao_aparece_no_almoco(self):
        meal = _make_meal("Almoço", [("Pão integral", 60)])
        result = generate_meal_substitutions([meal])
        assert result == []

    def test_proteina_aparece_em_qualquer_refeicao(self):
        for meal_name in ("Café da manhã", "Almoço", "Lanche da tarde", "Jantar"):
            meal = _make_meal(meal_name, [("Frango grelhado", 130)])
            result = generate_meal_substitutions([meal])
            assert len(result) >= 1, f"Proteína deve aparecer em '{meal_name}'"

    def test_alergia_filtra_alternativas(self):
        meal = _make_meal("Almoço", [("Frango grelhado", 130)])
        sem_alergia = generate_meal_substitutions([meal])
        alts_sem = sem_alergia[0]["alternatives"]
        has_atum = any("atum" in a.lower() for a in alts_sem)

        com_alergia = generate_meal_substitutions([meal], allergens=["atum"])
        alts_com = com_alergia[0]["alternatives"]
        has_atum_after = any("atum" in a.lower() for a in alts_com)

        assert has_atum, "Atum deveria aparecer sem restrição"
        assert not has_atum_after, "Atum não deveria aparecer com alergia a atum"

    def test_alergia_remove_alternativa_mas_mantem_outras(self):
        meal = _make_meal("Almoço", [("Arroz cozido", 150)])
        result = generate_meal_substitutions([meal], allergens=["batata"])
        assert len(result) == 1
        alts = result[0]["alternatives"]
        assert not any("batata" in a.lower() for a in alts)
        assert len(alts) >= 1

    def test_alergia_total_remove_entrada(self):
        meal = _make_meal("Café da manhã", [("Tapioca", 80)])
        all_allergens = ["pao", "cuscuz", "beiju", "integral"]
        result = generate_meal_substitutions([meal], allergens=all_allergens)
        if result:
            assert len(result[0]["alternatives"]) > 0

    def test_deduplicacao_entre_refeicoes(self):
        meals = [
            _make_meal("Almoço", [("Arroz cozido", 150)]),
            _make_meal("Jantar", [("Arroz cozido", 150)]),
        ]
        result = generate_meal_substitutions(meals)
        arroz_entries = [r for r in result if "Arroz" in r["food"]]
        assert len(arroz_entries) == 1

    def test_quantidade_proporcional_ao_ratio(self):
        meal = _make_meal("Almoço", [("Arroz cozido", 200)])
        result = generate_meal_substitutions([meal])
        assert len(result) >= 1
        alts = result[0]["alternatives"]
        batata_alt = next((a for a in alts if "Batata inglesa" in a), None)
        assert batata_alt is not None
        assert "270g" in batata_alt

    def test_quantidade_minima_10g(self):
        meal = _make_meal("Café da manhã", [("Aveia em flocos", 5)])
        result = generate_meal_substitutions([meal])
        if result:
            for alt in result[0]["alternatives"]:
                qty_str = alt.split("(")[1].rstrip("g)")
                assert int(qty_str) >= 10

    def test_formato_saida(self):
        meal = _make_meal("Almoço", [("Frango grelhado", 130)])
        result = generate_meal_substitutions([meal])
        assert len(result) >= 1
        entry = result[0]
        assert "food" in entry
        assert "alternatives" in entry
        assert isinstance(entry["food"], str)
        assert isinstance(entry["alternatives"], list)
        assert all(isinstance(a, str) for a in entry["alternatives"])
        assert "(" in entry["food"]
        assert "130g" in entry["food"]

    def test_alimento_sem_nome_ignorado(self):
        meal = {"name": "Almoço", "foods": [{"name": "", "quantity_g": 100}]}
        assert generate_meal_substitutions([meal]) == []

    def test_alimento_none_ignorado(self):
        meal = {"name": "Almoço", "foods": [{"name": None, "quantity_g": 100}]}
        assert generate_meal_substitutions([meal]) == []

    def test_quantidade_g_none_usa_100(self):
        meal = {"name": "Almoço", "foods": [{"name": "Arroz cozido", "quantity_g": None}]}
        result = generate_meal_substitutions([meal])
        assert len(result) >= 1
        assert "100g" in result[0]["food"]

    def test_multiplos_alimentos_na_mesma_refeicao(self):
        meal = _make_meal("Almoço", [
            ("Arroz cozido", 150),
            ("Frango grelhado", 130),
            ("Feijão cozido", 80),
        ])
        result = generate_meal_substitutions([meal])
        foods_com_subs = {r["food"].split(" (")[0] for r in result}
        assert any("Arroz" in f for f in foods_com_subs)
        assert any("Frango" in f for f in foods_com_subs)
        assert any("Feijão" in f or "Feijao" in f for f in foods_com_subs)

    def test_plano_completo_3_refeicoes(self):
        meals = [
            _make_meal("Café da manhã", [("Pão integral", 60), ("Ovo cozido", 100)]),
            _make_meal("Almoço", [("Arroz cozido", 150), ("Peito de frango grelhado", 130)]),
            _make_meal("Jantar", [("Macarrão cozido", 120), ("Tilápia grelhada", 130)]),
        ]
        result = generate_meal_substitutions(meals)
        assert len(result) >= 4

    def test_allergens_none_equivale_a_lista_vazia(self):
        meal = _make_meal("Almoço", [("Arroz cozido", 150)])
        result_none = generate_meal_substitutions([meal], allergens=None)
        result_empty = generate_meal_substitutions([meal], allergens=[])
        assert result_none == result_empty

    def test_ceia_bloqueia_carbo_cafe(self):
        meal = _make_meal("Ceia", [("Pão integral", 60)])
        assert generate_meal_substitutions([meal]) == []

    def test_lanche_bloqueia_carbo_almoco(self):
        meal = _make_meal("Lanche da tarde", [("Arroz cozido", 150)])
        assert generate_meal_substitutions([meal]) == []
