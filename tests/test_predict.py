# Testes para src/predict.py — previsão de nota/aprovação, explicabilidade,
# deteção de outliers e margem de erro (MAE) das previsões.
import pytest

from src.data_processing import get_processed_data
from src.predict import (detect_outliers, explain_prediction, full_prediction,
                          get_model_mae, predict_grade, predict_pass_probability)


# Perfil de hábitos "médio", usado como base em vários testes.
SAMPLE_INPUT = {
    "studytime": 3,
    "absences": 2,
    "failures": 0,
    "goout": 2,
    "Dalc": 1,
    "Walc": 1,
    "internet": "yes",
    "higher": "yes",
}


def test_predict_grade_habits_only():
    # Sem G1/G2, deve usar a variante "hábitos" e prever uma nota válida.
    result = predict_grade(SAMPLE_INPUT, use_previous_grades=False)
    assert 0 <= result["predicted_grade"] <= 20
    assert result["model_variant"] == "habitos"


def test_predict_grade_with_previous_grades():
    # Com G1/G2 fornecidos, deve usar a variante "completo" (mais precisa).
    inp = dict(SAMPLE_INPUT, G1=14, G2=15)
    result = predict_grade(inp, use_previous_grades=True)
    assert 0 <= result["predicted_grade"] <= 20
    assert result["model_variant"] == "completo"


def test_predict_pass_probability_range():
    # A probabilidade de aprovação deve estar entre 0 e 1, com veredito booleano.
    result = predict_pass_probability(SAMPLE_INPUT)
    assert 0 <= result["probabilidade_aprovacao"] <= 1
    assert isinstance(result["aprovado_previsto"], bool)


def test_full_prediction_structure():
    # A previsão completa deve trazer tanto a nota (variante hábitos) como a aprovação.
    result = full_prediction(SAMPLE_INPUT)
    assert "nota_prevista_habitos" in result
    assert "aprovacao" in result


def test_good_habits_predict_higher_grade_than_bad_habits():
    # Um perfil de bons hábitos deve sempre prever nota mais alta do que um perfil de maus hábitos.
    good = {"studytime": 4, "absences": 0, "failures": 0, "goout": 1, "Dalc": 1, "Walc": 1, "higher": "yes"}
    bad = {"studytime": 1, "absences": 20, "failures": 3, "goout": 5, "Dalc": 5, "Walc": 5, "higher": "no"}
    grade_good = predict_grade(good)["predicted_grade"]
    grade_bad = predict_grade(bad)["predicted_grade"]
    assert grade_good > grade_bad


def test_explain_prediction_structure():
    # A explicação deve ter uma nota de partida (baseline) e uma lista de contribuições por fator.
    result = explain_prediction(SAMPLE_INPUT)
    assert "baseline_grade" in result
    assert "contributions" in result
    assert 0 <= result["baseline_grade"] <= 20
    for c in result["contributions"]:
        assert set(c.keys()) == {"feature", "label", "student_value", "typical_value", "impact"}


def test_explain_prediction_sorted_by_impact_magnitude():
    # As contribuições devem vir ordenadas do maior para o menor impacto (em valor absoluto).
    inp = {"studytime": 1, "absences": 25, "failures": 3, "goout": 5, "Dalc": 5, "Walc": 5, "higher": "no"}
    result = explain_prediction(inp)
    impacts = [abs(c["impact"]) for c in result["contributions"]]
    assert impacts == sorted(impacts, reverse=True)


def test_explain_prediction_bad_failures_has_negative_impact():
    # Muitas reprovações face à mediana do dataset deve puxar a nota para
    # baixo (impact negativo) — confirma que o sinal está correto.
    inp = {"studytime": 3, "absences": 2, "failures": 3, "goout": 2, "Dalc": 1, "Walc": 1, "higher": "yes"}
    result = explain_prediction(inp)
    failures_contrib = next((c for c in result["contributions"] if c["feature"] == "failures"), None)
    assert failures_contrib is not None
    assert failures_contrib["impact"] < 0


def test_explain_prediction_empty_input_has_no_contributions():
    # Sem nenhum valor fornecido pelo estudante, não há nada para isolar.
    result = explain_prediction({})
    assert result["contributions"] == []


# ----------------------------------------------------------------------------
# Deteção de outliers (perfis atípicos): estudantes cuja nota real se desvia
# muito da nota que o modelo previa para o SEU próprio perfil.
# ----------------------------------------------------------------------------
def test_detect_outliers_returns_at_most_limit():
    # O número de outliers devolvidos nunca deve ultrapassar o limite pedido.
    df = get_processed_data()
    result = detect_outliers(df, limit=5)
    assert len(result) <= 5


def test_detect_outliers_sorted_by_absolute_z_score_desc():
    # Os outliers devem vir ordenados do desvio mais extremo para o menos extremo.
    df = get_processed_data()
    result = detect_outliers(df, limit=20)
    z_abs = [abs(r["z_score"]) for r in result]
    assert z_abs == sorted(z_abs, reverse=True)


def test_detect_outliers_all_above_threshold():
    # Todos os outliers devolvidos devem ter |z_score| acima do limiar pedido.
    df = get_processed_data()
    threshold = 2.0
    result = detect_outliers(df, z_threshold=threshold, limit=50)
    assert all(abs(r["z_score"]) >= threshold for r in result)


def test_detect_outliers_higher_threshold_finds_fewer_or_equal():
    # Um limiar mais rigoroso deve encontrar sempre menos (ou o mesmo número de) outliers.
    df = get_processed_data()
    loose = detect_outliers(df, z_threshold=1.0, limit=100)
    strict = detect_outliers(df, z_threshold=3.0, limit=100)
    assert len(strict) <= len(loose)


def test_detect_outliers_direction_matches_residual_sign():
    # O rótulo "acima/abaixo do esperado" deve concordar com o sinal do resíduo.
    df = get_processed_data()
    result = detect_outliers(df, limit=20)
    for r in result:
        if r["residual"] > 0:
            assert r["direction"] == "acima do esperado"
        elif r["residual"] < 0:
            assert r["direction"] == "abaixo do esperado"


def test_detect_outliers_student_ids_are_unique_and_valid():
    # Não deve haver IDs repetidos, e todos têm de pertencer ao dataset real.
    df = get_processed_data()
    result = detect_outliers(df, limit=20)
    ids = [r["student_id"] for r in result]
    assert len(ids) == len(set(ids))
    valid_ids = set(df["student_id"])
    assert all(i in valid_ids for i in ids)


def test_outliers_endpoint_structure():
    # O endpoint /outliers deve devolver o limiar usado e uma contagem consistente com a lista.
    from src.api import outliers

    result = outliers(z_threshold=2.0, limit=10)
    assert result["z_threshold"] == 2.0
    assert result["n_outliers"] == len(result["students"])
    assert result["n_outliers"] <= 10


# ----------------------------------------------------------------------------
# Margem de erro (MAE) junto da previsão: em vez de mostrar só um número,
# mostrar "13.5 ± MAE" — honesto sobre o quão preciso o modelo costuma ser.
# ----------------------------------------------------------------------------
def test_get_model_mae_habitos_is_positive_number():
    # O erro médio absoluto do modelo de hábitos deve ser um número positivo conhecido.
    mae = get_model_mae("habitos")
    assert mae is not None
    assert mae > 0


def test_get_model_mae_completo_is_positive_number():
    mae = get_model_mae("completo")
    assert mae is not None
    assert mae > 0


def test_get_model_mae_completo_smaller_than_habitos():
    # O modelo "completo" (com G1/G2) é sempre mais preciso do que só com
    # hábitos — se isto deixar de ser verdade, é sinal de um problema no
    # treino, não só neste feature.
    assert get_model_mae("completo") < get_model_mae("habitos")


def test_get_model_mae_unknown_variant_returns_none():
    # Uma variante de modelo desconhecida deve devolver None, não rebentar.
    assert get_model_mae("inexistente") is None


def test_predict_grade_includes_mae():
    # Toda previsão de nota deve trazer o MAE do modelo usado.
    result = predict_grade(SAMPLE_INPUT, use_previous_grades=False)
    assert result["mae"] is not None
    assert result["mae"] > 0


def test_predict_grade_mae_matches_get_model_mae():
    # O MAE devolvido na previsão deve coincidir exatamente com get_model_mae.
    result = predict_grade(SAMPLE_INPUT, use_previous_grades=False)
    assert result["mae"] == round(get_model_mae("habitos"), 2)


def test_full_prediction_carries_mae_in_each_variant():
    # Ambas as variantes da previsão completa (hábitos e completa) devem trazer o seu próprio MAE.
    inp = dict(SAMPLE_INPUT, G1=14, G2=15)
    result = full_prediction(inp)
    assert result["nota_prevista_habitos"]["mae"] is not None
    assert result["nota_prevista_completa"]["mae"] is not None
