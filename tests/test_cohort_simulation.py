# Testes para src/optimizer.py — simulação de intervenção na turma inteira
# (aplicar um "delta" de hábito a todos os estudantes em risco e ver o efeito).
import json

import pytest

from src.data_processing import get_processed_data
from src.optimizer import simular_intervencao_turma


def test_cohort_simulation_result_structure_and_json_serializable():
    # O resultado deve ter todos os campos esperados pelo frontend, e ser
    # 100% serializável em JSON (sem tipos numpy que o json.dumps rejeite).
    df = get_processed_data()
    result = simular_intervencao_turma(df, {"studytime": 1, "absences": -2})

    assert result["n_students"] == int(df["at_risk"].sum())
    assert "pass_rate_before" in result and "pass_rate_after" in result
    assert "avg_grade_before" in result and "avg_grade_after" in result
    assert result["newly_passing"] == result["n_passing_after"] - result["n_passing_before"]
    assert "message" in result and result["message"]

    json.dumps(result)


def test_cohort_simulation_improves_or_maintains_avg_grade_with_positive_studytime_delta():
    df = get_processed_data()
    result = simular_intervencao_turma(df, {"studytime": 1})
    # Aumentar o tempo de estudo nunca deveria PIORAR a nota média prevista
    # do grupo em risco (o modelo é monótono nesta alavanca).
    assert result["avg_grade_after"] >= result["avg_grade_before"]
    assert result["n_passing_after"] >= result["n_passing_before"]


def test_cohort_simulation_rejects_empty_deltas():
    # Sem nenhuma alavanca escolhida, não há intervenção nenhuma para simular.
    df = get_processed_data()
    with pytest.raises(ValueError):
        simular_intervencao_turma(df, {})


def test_cohort_simulation_rejects_invalid_column():
    # Uma coluna que não existe no modelo deve ser rejeitada.
    df = get_processed_data()
    with pytest.raises(ValueError):
        simular_intervencao_turma(df, {"nota_ficticia": 1})


def test_cohort_simulation_clamps_to_real_value_limits():
    df = get_processed_data()
    # Um delta enorme não deve gerar hábitos impossíveis (ex.: estudytime > 4)
    # — apenas confirma que a função não rebenta e que o resultado é coerente
    # (nota depois >= nota antes, já que o delta só pode "ajudar" ou saturar).
    result = simular_intervencao_turma(df, {"studytime": 100})
    assert result["avg_grade_after"] >= result["avg_grade_before"]


def test_cohort_simulation_with_no_at_risk_students_returns_zeroed_result():
    # Sem nenhum estudante em risco, a simulação deve devolver tudo a zero,
    # em vez de rebentar com uma divisão por zero.
    df = get_processed_data()
    empty_at_risk = df.copy()
    empty_at_risk["at_risk"] = 0
    result = simular_intervencao_turma(empty_at_risk, {"studytime": 1})
    assert result["n_students"] == 0
    assert result["n_passing_before"] == 0
    assert result["n_passing_after"] == 0
