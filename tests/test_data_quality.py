# Testes para src/data_quality.py — deteção de valores invulgares/inconsistentes
# ao introduzir dados de um estudante (usado em "Adicionar Dados").
from src.data_processing import get_processed_data
from src.data_quality import check_unusual_values


def test_no_fields_returns_no_warnings():
    # Sem nenhum campo preenchido, não há nada a avaliar -> lista vazia.
    df = get_processed_data()
    assert check_unusual_values(df, {}) == []


def test_typical_values_produce_no_warnings():
    # Valores típicos (próximos da média) não devem gerar avisos.
    df = get_processed_data()
    warnings = check_unusual_values(df, {
        "age": 17, "studytime": 2, "absences": 4, "failures": 0, "G1": 11, "G2": 11,
    })
    assert warnings == []


def test_extreme_absences_flagged():
    # O valor máximo de faltas do dataset deve ser sinalizado como invulgar.
    df = get_processed_data()
    max_absences = int(df["absences"].max())
    warnings = check_unusual_values(df, {"absences": max_absences})
    assert any(w["field"] == "absences" for w in warnings)


def test_large_grade_jump_between_g1_and_g2_flagged():
    # Um salto grande de nota entre G1 e G2 deve ser sinalizado como suspeito.
    df = get_processed_data()
    warnings = check_unusual_values(df, {"G1": 5, "G2": 18})
    assert any(w["field"] == "G2" for w in warnings)


def test_small_grade_change_not_flagged():
    # Uma pequena variação de nota é normal e não deve gerar aviso.
    df = get_processed_data()
    warnings = check_unusual_values(df, {"G1": 12, "G2": 13})
    assert not any(w["field"] == "G2" for w in warnings)


def test_many_failures_with_high_grades_flagged():
    # Muitas reprovações anteriores combinadas com notas altas é inconsistente -> aviso.
    df = get_processed_data()
    warnings = check_unusual_values(df, {"failures": 3, "G1": 17, "G2": 18})
    assert any(w["field"] == "failures" for w in warnings)


def test_many_failures_with_low_grades_not_flagged_as_inconsistent():
    df = get_processed_data()
    warnings = check_unusual_values(df, {"failures": 3, "G1": 8, "G2": 9})
    # failures=3 sozinho já é invulgar (aviso z-score), mas NÃO deve gerar o
    # aviso específico de inconsistência "reprovações + notas altas", já que
    # G1/G2 aqui são baixas e portanto coerentes com as reprovações.
    assert not any("notas altas" in w["message"] for w in warnings)


def test_none_and_empty_values_ignored():
    # Valores None ou string vazia (campos não preenchidos) devem ser ignorados, não avaliados.
    df = get_processed_data()
    warnings = check_unusual_values(df, {"absences": None, "G1": "", "studytime": 2})
    assert warnings == []


def test_each_warning_has_expected_shape():
    # Cada aviso deve ter exatamente os campos "field", "severity" e "message",
    # com uma mensagem descritiva e severidade válida.
    df = get_processed_data()
    max_absences = int(df["absences"].max())
    warnings = check_unusual_values(df, {"absences": max_absences})
    for w in warnings:
        assert set(w.keys()) == {"field", "severity", "message"}
        assert w["severity"] in {"info", "warning"}
        assert isinstance(w["message"], str) and len(w["message"]) > 10
