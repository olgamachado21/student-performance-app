# Testes para src/segmentation.py — sugestões de micro-hábitos associadas
# aos traços dominantes de cada grupo/cluster de estudantes.
from src.data_processing import get_processed_data
from src.segmentation import (MICRO_HABIT_SUGGESTIONS, TRAIT_LABELS,
                               MAX_SUGGESTIONS_PER_GROUP, run_segmentation,
                               _suggest_micro_habits)


def test_every_trait_label_has_a_suggestion():
    # Todos os traços possíveis (extremo alto e baixo de cada característica)
    # devem ter uma sugestão de micro-hábito associada.
    all_labels = set()
    for high, low in TRAIT_LABELS.values():
        all_labels.add(high)
        all_labels.add(low)

    missing = all_labels - set(MICRO_HABIT_SUGGESTIONS.keys())
    assert missing == set(), f"Traços sem sugestão associada: {missing}"


def test_no_unused_suggestion_keys():
    # E o inverso: não deve haver sugestões "órfãs" que não correspondam a nenhum traço real.
    all_labels = set()
    for high, low in TRAIT_LABELS.values():
        all_labels.add(high)
        all_labels.add(low)

    extra = set(MICRO_HABIT_SUGGESTIONS.keys()) - all_labels
    assert extra == set(), f"Chaves de sugestão que não correspondem a nenhum traço: {extra}"


def test_suggest_micro_habits_caps_at_max():
    # O número de sugestões nunca deve ultrapassar o limite máximo por grupo.
    traits = list(TRAIT_LABELS_flat()[:6])
    suggestions = _suggest_micro_habits(traits)
    assert len(suggestions) <= MAX_SUGGESTIONS_PER_GROUP


def test_suggest_micro_habits_uses_first_traits_in_order():
    # As sugestões devem seguir a ordem dos traços fornecidos (os primeiros/mais fortes primeiro).
    traits = ["Dedicados ao Estudo", "Muitas Faltas", "Boa Saúde", "Vida Social Ativa"]
    suggestions = _suggest_micro_habits(traits)
    assert len(suggestions) == MAX_SUGGESTIONS_PER_GROUP
    assert suggestions[0] == MICRO_HABIT_SUGGESTIONS["Dedicados ao Estudo"]
    assert suggestions[1] == MICRO_HABIT_SUGGESTIONS["Muitas Faltas"]
    assert suggestions[2] == MICRO_HABIT_SUGGESTIONS["Boa Saúde"]


def test_suggest_micro_habits_handles_mixed_profile_placeholder():
    # O traço "misto" (sem nenhum traço muito desviante) não está no
    # dicionário de sugestões de propósito — não faz sentido dar um
    # conselho concreto quando não há nenhum traço característico.
    suggestions = _suggest_micro_habits(["Perfil Misto (sem traços muito acima da média geral)"])
    assert suggestions == []


def test_run_segmentation_every_group_has_suggestions():
    # Todo grupo devolvido pela segmentação real deve trazer uma lista de sugestões válidas.
    df = get_processed_data()
    result = run_segmentation(df, n_clusters=4)
    for group in result["groups"]:
        assert "suggestions" in group
        assert isinstance(group["suggestions"], list)
        assert len(group["suggestions"]) <= MAX_SUGGESTIONS_PER_GROUP
        # cada sugestão tem de corresponder a um dos traços do próprio grupo
        for suggestion in group["suggestions"]:
            assert suggestion in MICRO_HABIT_SUGGESTIONS.values()


def test_run_segmentation_suggestions_match_traits_order():
    # As sugestões devem corresponder exatamente aos traços do grupo, pela mesma ordem.
    df = get_processed_data()
    result = run_segmentation(df, n_clusters=5)
    for group in result["groups"]:
        expected = [MICRO_HABIT_SUGGESTIONS[t] for t in group["traits"][:MAX_SUGGESTIONS_PER_GROUP] if t in MICRO_HABIT_SUGGESTIONS]
        assert group["suggestions"] == expected


def TRAIT_LABELS_flat():
    # Helper: "achata" o dicionário de pares (alto, baixo) numa lista simples de labels.
    flat = []
    for high, low in TRAIT_LABELS.values():
        flat.append(high)
        flat.append(low)
    return flat
