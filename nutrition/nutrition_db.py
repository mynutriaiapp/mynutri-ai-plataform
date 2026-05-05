"""
Banco nutricional baseado na Tabela TACO (UNICAMP) para alimentos comuns brasileiros.
Valores por 100g no estado de consumo (cozido, grelhado, etc.).

Usado pelo AIService para calcular macros deterministicamente, sem delegar aritmética à IA.
"""

import logging
import re
import unicodedata
from functools import lru_cache

logger = logging.getLogger(__name__)

# (calories_per_100g, protein_g, carbs_g, fat_g)
_DB: dict[str, tuple[float, float, float, float]] = {
    # ── CEREAIS E DERIVADOS ──────────────────────────────────────────────────
    "arroz branco cozido":          (128, 2.5, 28.1, 0.2),
    "arroz integral cozido":        (124, 2.6, 25.8, 1.0),
    "arroz":                        (128, 2.5, 28.1, 0.2),
    "macarrao cozido":              (147, 4.6, 30.3, 0.7),
    "macarrao":                     (147, 4.6, 30.3, 0.7),
    "esparguete cozido":            (147, 4.6, 30.3, 0.7),
    "pao frances":                  (300, 8.0, 58.6, 3.1),
    "pao integral":                 (253, 8.6, 48.2, 3.5),
    "pao de forma":                 (253, 8.6, 48.2, 3.5),
    "pao":                          (290, 8.0, 56.0, 3.0),
    "tapioca":                      (358, 0.5, 88.3, 0.0),
    "cuscuz milho cozido":          (70,  1.5, 15.5, 0.3),
    "cuscuz":                       (70,  1.5, 15.5, 0.3),
    "aveia flocos":                 (394, 13.9, 66.6, 8.5),
    "aveia":                        (394, 13.9, 66.6, 8.5),
    "granola":                      (408, 8.5, 72.0, 10.0),
    "cereal matinal":               (380, 7.0, 82.0, 2.0),
    "farinha mandioca":             (361, 1.6, 87.9, 0.3),
    "batata doce cozida":           (77,  1.4, 18.4, 0.1),
    "batata doce":                  (77,  1.4, 18.4, 0.1),
    "batata inglesa cozida":        (52,  1.2, 11.9, 0.1),
    "batata cozida":                (52,  1.2, 11.9, 0.1),
    "batata":                       (52,  1.2, 11.9, 0.1),
    "mandioca cozida":              (125, 1.0, 30.1, 0.2),
    "mandioca":                     (125, 1.0, 30.1, 0.2),
    "aipim":                        (125, 1.0, 30.1, 0.2),
    "macaxeira":                    (125, 1.0, 30.1, 0.2),
    "milho cozido":                 (92,  2.9, 19.8, 0.4),
    "milho":                        (92,  2.9, 19.8, 0.4),

    # ── LEGUMINOSAS ──────────────────────────────────────────────────────────
    "feijao preto cozido":          (77,  4.5, 14.0, 0.5),
    "feijao carioca cozido":        (76,  4.8, 13.6, 0.5),
    "feijao cozido":                (77,  4.6, 13.8, 0.5),
    "feijao":                       (77,  4.6, 13.8, 0.5),
    "lentilha cozida":              (93,  6.3, 16.3, 0.5),
    "lentilha":                     (93,  6.3, 16.3, 0.5),
    "grao de bico cozido":          (164, 8.9, 27.4, 2.6),
    "grao de bico":                 (164, 8.9, 27.4, 2.6),
    "ervilha cozida":               (88,  5.4, 16.0, 0.4),
    "ervilha":                      (88,  5.4, 16.0, 0.4),
    "soja cozida":                  (141, 14.4, 11.5, 6.4),

    # ── CARNES E AVES ────────────────────────────────────────────────────────
    "peito frango grelhado":        (159, 32.0, 0.0, 3.2),
    "frango grelhado":              (159, 32.0, 0.0, 3.2),
    "frango cozido":                (148, 27.0, 0.0, 3.5),
    "frango assado":                (195, 23.0, 0.0, 11.0),
    "frango desfiado":              (148, 27.0, 0.0, 3.5),
    "frango refogado":              (165, 25.0, 0.0, 7.0),
    "frango":                       (159, 30.0, 0.0, 4.5),
    "coxa frango assada":           (195, 23.0, 0.0, 11.0),
    "sobrecoxa frango":             (215, 21.0, 0.0, 14.0),
    "carne bovina cozida":          (219, 31.5, 0.0, 10.2),
    "patinho cozido":               (219, 31.5, 0.0, 10.2),
    "acem cozido":                  (218, 26.5, 0.0, 12.0),
    "carne moida refogada":         (215, 26.0, 0.0, 12.0),
    "carne moida":                  (215, 26.0, 0.0, 12.0),
    "alcatra grelhada":             (213, 31.0, 0.0, 9.8),
    "alcatra":                      (213, 31.0, 0.0, 9.8),
    "file mignon grelhado":         (219, 32.0, 0.0, 9.5),
    "contrafile grelhado":          (238, 29.5, 0.0, 13.0),
    "picanha grelhada":             (280, 28.0, 0.0, 18.0),
    "musculo cozido":               (189, 29.0, 0.0, 7.5),
    "carne bovina":                 (215, 29.0, 0.0, 11.0),
    "linguica assada":              (270, 14.0, 2.0, 23.0),
    "linguica":                     (270, 14.0, 2.0, 23.0),
    "peru assado":                  (170, 28.0, 0.0, 6.5),

    # ── PEIXES E FRUTOS DO MAR ───────────────────────────────────────────────
    "tilapia grelhada":             (128, 26.0, 0.0, 2.7),
    "tilapia":                      (128, 26.0, 0.0, 2.7),
    "atum em agua":                 (116, 25.5, 0.0, 1.0),
    "atum lata":                    (116, 25.5, 0.0, 1.0),
    "atum":                         (116, 25.5, 0.0, 1.0),
    "sardinha oleo escorrida":      (208, 24.0, 0.0, 12.0),
    "sardinha":                     (208, 24.0, 0.0, 12.0),
    "salmao grelhado":              (208, 28.0, 0.0, 10.0),
    "salmao":                       (208, 28.0, 0.0, 10.0),
    "camarao cozido":               (99,  20.9, 0.9, 1.1),
    "merluza grelhada":             (108, 22.0, 0.0, 2.5),
    "bacalhau cozido":              (160, 36.0, 0.0, 1.0),
    "peixe grelhado":               (128, 24.0, 0.0, 3.0),

    # ── OVOS ─────────────────────────────────────────────────────────────────
    "ovo cozido":                   (146, 13.0, 1.0, 9.5),
    "ovo mexido":                   (149, 10.0, 1.6, 11.4),
    "ovo frito":                    (196, 13.5, 0.6, 15.5),
    "omelete":                      (154, 11.0, 2.0, 11.5),
    "clara ovo cozida":             (52,  11.0, 0.7, 0.2),
    "ovo":                          (146, 13.0, 1.0, 9.5),

    # ── LATICÍNIOS ───────────────────────────────────────────────────────────
    "queijo minas frescal":         (264, 17.4, 3.2, 20.2),
    "queijo minas padrao":          (361, 25.0, 1.0, 28.5),
    "queijo mussarela":             (327, 24.5, 2.5, 25.0),
    "queijo prato":                 (358, 22.0, 2.0, 28.5),
    "queijo coalho":                (281, 18.5, 1.5, 22.5),
    "queijo":                       (300, 20.0, 2.0, 23.0),
    "requeijao":                    (259, 7.7,  5.3, 23.9),
    "iogurte natural integral":     (61,  3.5,  4.7, 3.2),
    "iogurte natural desnatado":    (45,  4.0,  5.8, 0.4),
    "iogurte natural":              (61,  3.5,  4.7, 3.2),
    "iogurte":                      (61,  3.5,  4.7, 3.2),
    "leite integral":               (60,  3.0,  5.0, 3.0),
    "leite desnatado":              (35,  3.3,  5.0, 0.1),
    "leite semidesnatado":          (47,  3.1,  5.0, 1.5),
    "leite":                        (60,  3.0,  5.0, 3.0),
    "whey protein":                 (370, 80.0, 5.0, 4.0),
    "proteina do soro":             (370, 80.0, 5.0, 4.0),
    "creme de leite":               (334, 2.5,  3.5, 35.0),

    # ── VEGETAIS ─────────────────────────────────────────────────────────────
    "alface":                       (11,  1.3,  1.7, 0.2),
    "tomate":                       (15,  1.1,  2.9, 0.2),
    "pepino":                       (15,  0.7,  2.9, 0.1),
    "cenoura crua":                 (34,  0.9,  8.0, 0.1),
    "cenoura cozida":               (37,  0.8,  8.7, 0.3),
    "cenoura":                      (34,  0.9,  8.0, 0.1),
    "brocolis cozido":              (25,  2.8,  3.3, 0.5),
    "brocolis":                     (25,  2.8,  3.3, 0.5),
    "couve refogada":               (42,  3.1,  4.7, 1.4),
    "couve":                        (42,  3.1,  4.7, 1.4),
    "espinafre cozido":             (21,  2.3,  3.4, 0.5),
    "espinafre":                    (21,  2.3,  3.4, 0.5),
    "abobrinha cozida":             (17,  1.3,  2.9, 0.3),
    "abobrinha":                    (17,  1.3,  2.9, 0.3),
    "chuchu cozido":                (22,  0.9,  4.8, 0.2),
    "chuchu":                       (22,  0.9,  4.8, 0.2),
    "beterraba cozida":             (43,  1.5, 10.0, 0.1),
    "beterraba":                    (43,  1.5, 10.0, 0.1),
    "repolho cozido":               (22,  1.4,  4.6, 0.2),
    "repolho":                      (22,  1.4,  4.6, 0.2),
    "pimentao":                     (20,  0.9,  4.4, 0.1),
    "cebola":                       (28,  0.9,  6.5, 0.1),
    "alho":                         (149, 6.4, 33.1, 0.5),
    "quiabo cozido":                (24,  2.0,  4.7, 0.1),
    "berinjela cozida":             (24,  0.8,  5.5, 0.2),
    "berinjela":                    (24,  0.8,  5.5, 0.2),
    "jiló":                         (21,  1.2,  4.3, 0.2),
    "vagem cozida":                 (25,  1.8,  4.7, 0.3),
    "vagem":                        (25,  1.8,  4.7, 0.3),
    "palmito":                      (28,  2.5,  4.6, 0.2),
    "cogumelo":                     (22,  3.1,  3.3, 0.3),
    "acelga cozida":                (13,  1.4,  1.7, 0.1),
    "rucula":                       (25,  2.6,  3.7, 0.7),
    "salada mista":                 (15,  1.2,  2.5, 0.2),

    # ── FRUTAS ───────────────────────────────────────────────────────────────
    "banana":                       (92,  1.3, 23.8, 0.1),
    "banana prata":                 (92,  1.3, 23.8, 0.1),
    "banana nanica":                (89,  1.1, 22.3, 0.1),
    "maca":                         (56,  0.3, 15.2, 0.1),
    "laranja":                      (37,  1.0,  8.9, 0.1),
    "mamao papaia":                 (40,  0.5, 10.4, 0.1),
    "mamao formosa":                (38,  0.5,  9.8, 0.1),
    "mamao":                        (40,  0.5, 10.4, 0.1),
    "melancia":                     (33,  0.6,  7.9, 0.2),
    "melao":                        (28,  0.7,  6.8, 0.1),
    "morango":                      (27,  0.8,  6.3, 0.3),
    "manga":                        (64,  0.5, 17.0, 0.3),
    "uva":                          (68,  0.6, 17.3, 0.1),
    "abacaxi":                      (48,  0.9, 12.3, 0.1),
    "goiaba":                       (54,  2.3, 12.5, 0.6),
    "abacate":                      (96,  1.2,  6.0, 8.4),
    "caju":                         (43,  0.8, 10.5, 0.2),
    "tangerina":                    (37,  0.8,  9.2, 0.1),
    "mexerica":                     (37,  0.8,  9.2, 0.1),
    "pera":                         (56,  0.5, 15.1, 0.1),
    "pexego":                       (35,  0.6,  9.0, 0.1),
    "pessego":                      (35,  0.6,  9.0, 0.1),
    "kiwi":                         (44,  1.1, 10.5, 0.5),
    "acerola":                      (32,  0.9,  7.1, 0.2),
    "lichia":                       (66,  0.8, 16.5, 0.4),
    "graviola":                     (62,  1.0, 15.8, 0.3),
    "maracuja":                     (68,  2.4, 13.9, 0.7),
    "cupuacu":                      (49,  1.4, 10.7, 0.9),

    # ── GORDURAS E COMPLEMENTOS ──────────────────────────────────────────────
    "azeite oliva":                 (884, 0.0,  0.0, 100.0),
    "oleo soja":                    (884, 0.0,  0.0, 100.0),
    "oleo de coco":                 (892, 0.0,  0.0, 100.0),
    "oleo":                         (884, 0.0,  0.0, 100.0),
    "manteiga":                     (717, 0.5,  0.5, 81.0),
    "margarina":                    (545, 0.5,  1.0, 60.0),
    "amendoim torrado":             (581, 26.0, 21.0, 47.5),
    "amendoim":                     (581, 26.0, 21.0, 47.5),
    "pasta amendoim":               (618, 22.5, 19.0, 51.0),
    "castanha para":                (656, 14.3, 12.3, 63.5),
    "castanha caju":                (570, 18.5, 29.3, 43.9),
    "castanha":                     (600, 14.0, 18.0, 53.0),
    "nozes":                        (607, 14.3, 11.3, 59.4),
    "amendoas":                     (597, 21.3, 19.7, 52.5),

    # ── OUTROS ALIMENTOS ─────────────────────────────────────────────────────
    "mel":                          (309, 0.3, 84.1, 0.0),
    "acucar":                       (387, 0.0, 100.0, 0.0),
    "cafe preto":                   (2,   0.3,  0.0, 0.0),
    "cafe":                         (2,   0.3,  0.0, 0.0),
    "cha":                          (2,   0.0,  0.4, 0.0),
    "agua":                         (0,   0.0,  0.0, 0.0),
    "refrigerante zero":            (0,   0.0,  0.0, 0.0),
    "refrigerante diet":            (0,   0.0,  0.0, 0.0),
    "refrigerante light":           (0,   0.0,  0.0, 0.0),
    "coca zero":                    (0,   0.0,  0.0, 0.0),
    "coca cola zero":               (0,   0.0,  0.0, 0.0),
    "pepsi zero":                   (0,   0.0,  0.0, 0.0),
    "guarana zero":                 (0,   0.0,  0.0, 0.0),
    "bebida zero":                  (0,   0.0,  0.0, 0.0),
    "refrigerante":                 (41,  0.0, 10.6, 0.0),
    "suco laranja natural":         (34,  0.5,  8.3, 0.1),
    "suco":                         (45,  0.4, 10.9, 0.1),
    "presunto":                     (148, 18.5, 3.0, 7.5),
    "peito peru":                   (109, 19.5, 2.5, 3.0),
    "salsicha":                     (273, 14.0, 3.0, 23.5),
    "frango empanado":              (246, 16.0, 17.0, 13.0),
    "shoyu":                        (71,  7.7,  8.0, 0.1),
    "molho tomate":                 (40,  1.8,  7.8, 0.5),
    "maionese":                     (660, 2.0,  4.5, 71.0),
    "proteina texturizada soja":    (340, 50.0, 32.0, 1.0),
    "tofu":                         (76,  8.1,  1.9, 4.8),
    "carne seca":                   (265, 43.0, 0.0, 10.5),
    "paio":                         (230, 15.0, 2.0, 19.0),
    "ovo de codorna cozido":        (158, 13.1, 0.5, 11.1),
}

# Fallback por categoria quando nenhuma entrada do DB corresponde ao nome
_CATEGORY_FALLBACKS: list[tuple[list[str], tuple[float, float, float, float]]] = [
    (['frango', 'peru', 'pato', 'chester'],     (160, 28.0, 0.0,  5.0)),
    (['carne', 'bife', 'boi', 'bovino', 'vaca', 'contrafile', 'picanha', 'alcatra'], (215, 29.0, 0.0, 11.0)),
    (['peixe', 'tilapia', 'salmao', 'atum', 'merluza', 'bacalhau', 'robalo'],        (130, 24.0, 0.0,  3.5)),
    (['ovo', 'clara'],                           (146, 13.0, 1.0,  9.5)),
    (['queijo'],                                 (300, 20.0, 2.0, 23.0)),
    (['iogurte'],                                (55,  3.7,  5.0,  1.8)),
    (['leite', 'whey'],                          (60,  3.2,  5.0,  2.5)),
    (['arroz'],                                  (128, 2.5, 28.1,  0.2)),
    (['macarrao', 'massa', 'espaguete', 'penne', 'fusilli'], (147, 4.6, 30.3, 0.7)),
    (['pao', 'tapioca', 'cuscuz', 'cuscuzu'],    (280, 7.0, 55.0,  2.5)),
    (['batata'],                                 (65,  1.3, 15.0,  0.1)),
    (['mandioca', 'aipim', 'macaxeira'],         (125, 1.0, 30.0,  0.2)),
    (['feijao', 'lentilha', 'grao', 'ervilha'],  (77,  4.8, 14.0,  0.5)),
    (['banana', 'maca', 'laranja', 'mamao', 'fruta', 'manga', 'melancia', 'uva', 'morango'], (55, 0.7, 13.5, 0.2)),
    (['salada', 'alface', 'tomate', 'pepino', 'rucula'], (15, 1.0, 2.5, 0.2)),
    (['legume', 'verdura', 'brocolis', 'cenoura', 'abobrinha', 'couve'], (30, 2.0, 5.5, 0.4)),
    (['azeite', 'oleo'],                         (884, 0.0,  0.0, 100.0)),
    (['cafe'],                                   (2,   0.2,  0.2,  0.0)),
    (['refrigerante zero', 'refrigerante diet', 'refrigerante light',
      'coca zero', 'pepsi zero', 'guarana zero', 'bebida zero'],
                                                 (0,   0.0,  0.0,  0.0)),
    (['refrigerante'],                            (41,  0.0, 10.6,  0.0)),
    (['amendoim', 'castanha', 'nozes', 'amendoa'], (600, 18.0, 18.0, 52.0)),
]

# Palavras removidas na normalização — apenas preposições/artigos e descritores
# de tamanho/embalagem que não têm valor nutricional.
#
# IMPORTANTE: palavras de preparo (grelhado, cozido, integral, desnatado…)
# NÃO estão aqui. Elas participam do matching porque o DB tem entradas distintas
# com valores calóricos diferentes para cada preparo (ex: frango grelhado ≠
# frango assado). A normalização simétrica (input e chaves do DB) garante que
# "frango grelhado" bata na entrada correta em vez da entrada genérica "frango".
_STRIP_WORDS = frozenset({
    # Preposições e artigos
    'em', 'de', 'do', 'da', 'dos', 'das', 'ao', 'na', 'no', 'e',
    'sem', 'com', 'para',
    # Tamanho — não afeta macros
    'pequeno', 'pequena', 'medio', 'media', 'grande',
    # Embalagem e contexto irrelevantes
    'lata', 'pele', 'tipo',
})


def _strip_accents(text: str) -> str:
    text = unicodedata.normalize('NFD', text)
    return ''.join(c for c in text if unicodedata.category(c) != 'Mn')


def _normalize(name: str) -> str:
    """Remove acentos, lowercase e palavras irrelevantes para matching."""
    name = _strip_accents(name).lower()
    words = [w for w in re.split(r'[\s\-/,()]+', name.strip())
             if w and w not in _STRIP_WORDS and len(w) > 1]
    return ' '.join(words)


# Versão do DB com chaves normalizadas pelo mesmo _normalize aplicado aos inputs.
# Isso garante matching simétrico: "Frango Grelhado" (input) bate em
# "frango grelhado" (chave normalizada) em vez de colapsar para "frango".
_DB_NORMALIZED: dict[str, tuple[float, float, float, float]] = {
    _normalize(k): v for k, v in _DB.items()
}


@lru_cache(maxsize=512)
def _lookup_macros_per_100g(food_name: str) -> tuple[float, float, float, float, str]:
    """
    Retorna (cal, prot, carbs, fat, source) por 100g para um nome de alimento.
    Cacheado por nome — a busca fuzzy O(n) é executada só uma vez por alimento único.
    """
    normalized = _normalize(food_name)

    # 1. Match exato
    if normalized in _DB_NORMALIZED:
        return (*_DB_NORMALIZED[normalized], 'exact')

    # 2. Score por sobreposição de palavras
    food_words = set(normalized.split())
    best_score = 0.0
    best_key   = None

    for key in _DB_NORMALIZED:
        key_words = set(key.split())
        overlap   = len(food_words & key_words)
        if overlap == 0:
            continue
        score = overlap / max(len(food_words), len(key_words))
        if score > best_score:
            best_score = score
            best_key   = key

    if best_score >= 0.40:
        logger.debug(
            'Alimento "%s" → match no banco: "%s" (score=%.2f)',
            food_name, best_key, best_score,
        )
        return (*_DB_NORMALIZED[best_key], 'fuzzy')

    # 3. Fallback por categoria
    norm_original = _strip_accents(food_name.lower())
    for keywords, macros in _CATEGORY_FALLBACKS:
        if any(kw in norm_original for kw in keywords):
            logger.info(
                '[DB_GAP] Alimento "%s" não encontrado — fallback de categoria (palavra-chave: %s).',
                food_name,
                next(kw for kw in keywords if kw in norm_original),
            )
            return (*macros, 'category')

    # 4. Fallback genérico
    logger.warning(
        '[DB_GAP] Alimento "%s" sem correspondência no banco nutricional. '
        'Usando fallback genérico (150 kcal/100g). Considere adicionar ao nutrition_db.py.',
        food_name,
    )
    return (150, 8.0, 20.0, 4.0, 'generic')


def lookup_food_nutrition(food_name: str, quantity_g: float) -> dict:
    """
    Retorna calorias e macros para um alimento dado peso em gramas.

    Estratégia em 4 camadas. O dict retornado inclui '_source' indicando qual
    camada produziu o resultado — usado por services._check_db_coverage para
    rejeitar planos com cobertura insuficiente.

      'exact'    — match exato no DB normalizado
      'fuzzy'    — score por sobreposição ≥ 40% (camada 2)
      'category' — palavra-chave de categoria (camada 3)
      'generic'  — sem match — fallback 150 kcal/100g (camada 4)
      'invalid'  — input inválido (nome vazio ou qty ≤ 0)
    """
    if not food_name or quantity_g <= 0:
        result = _scale(150, 8.0, 20.0, 4.0, quantity_g)
        result['_source'] = 'invalid'
        return result

    cal, prot, carbs, fat, source = _lookup_macros_per_100g(food_name)
    result = _scale(cal, prot, carbs, fat, quantity_g)
    result['_source'] = source
    return result


def _scale(
    cal: float, prot: float, carbs: float, fat: float,
    quantity_g: float,
) -> dict:
    f = quantity_g / 100.0
    return {
        'calories':  round(cal   * f),
        'protein_g': round(prot  * f, 1),
        'carbs_g':   round(carbs * f, 1),
        'fat_g':     round(fat   * f, 1),
    }
