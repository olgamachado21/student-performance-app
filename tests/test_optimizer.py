# Testes para src/optimizer.py — otimizador de plano de estudo individual
# (encontra a combinação mínima de mudanças de hábito para atingir uma nota alvo).
import json

import pytest

from src.data_processing import get_processed_data
from src.optimizer import (_format_message, _studytime_calibration_note,
                            otimizar_plano_estudo)


def test_optimizer_result_structure_and_json_serializable():
    # O resultado deve ter todos os campos esperados pelo frontend e ser serializável em JSON.
    df = get_processed_data()
    student_id = int(df.sort_values("G3").iloc[5]["student_id"])
    result = otimizar_plano_estudo(df, student_id, target_grade=12)

    assert result["student_id"] == student_id
    assert result["target_grade"] == 12
    assert "initial_grade" in result and "final_grade" in result
    assert isinstance(result["achieved"], bool)
    assert isinstance(result["changes"], list)
    assert "message" in result and result["message"]

    # Tem de ser serializável em JSON (a API devolve isto diretamente).
    json.dumps(result)


def test_optimizer_already_meets_target_returns_no_changes():
    # Se o estudante já atinge a meta, não deve ser sugerida nenhuma mudança.
    df = get_processed_data()
    student_id = int(df.sort_values("G3", ascending=False).iloc[0]["student_id"])
    result = otimizar_plano_estudo(df, student_id, target_grade=5)

    assert result["achieved"] is True
    assert result["changes"] == []
    assert result["initial_grade"] == result["final_grade"]


def test_optimizer_consolidates_repeated_lever_changes():
    # Mudanças sucessivas na mesma alavanca (ex.: tempo de estudo a subir
    # vários níveis) devem ser consolidadas numa única entrada.
    df = get_processed_data()
    student_id = int(df.sort_values("G3").iloc[5]["student_id"])
    result = otimizar_plano_estudo(df, student_id, target_grade=12)

    labels = [c["label"] for c in result["changes"]]
    # Não deve haver duas entradas consecutivas com o mesmo hábito
    # (devem ter sido consolidadas numa só, ex.: "Tempo de estudo" 1 -> 4).
    assert labels == [labels[i] for i in range(len(labels)) if i == 0 or labels[i] != labels[i - 1]]


def test_optimizer_unknown_student_raises():
    # Um student_id inexistente deve levantar ValueError.
    df = get_processed_data()
    with pytest.raises(ValueError):
        otimizar_plano_estudo(df, 999999, target_grade=15)


def test_optimizer_changes_stay_within_lever_bounds():
    # As mudanças sugeridas nunca devem sair dos limites reais possíveis (ex.: studytime 1-4).
    df = get_processed_data()
    student_id = int(df.sort_values("G3").iloc[5]["student_id"])
    result = otimizar_plano_estudo(df, student_id, target_grade=20)

    for change in result["changes"]:
        if change["label"] == "Tempo de estudo":
            assert 1 <= change["to"] <= 4
        if change["label"] == "Faltas":
            assert change["to"] >= 0


# ----------------------------------------------------------------------------
# Ideia J — nota de calibração: o modelo de regressão linear usado pelo
# Otimizador (variante "completo") não tem termo de interação entre tempo de
# estudo e reprovações anteriores, por isso estima sempre o mesmo ganho por
# nível de tempo de estudo para toda a gente — mesmo sabendo que, nos dados
# reais, esse efeito é bem mais fraco para quem já reprovou (ver
# test_family_context.py / studytime_regression_with_failures). Testa-se a
# função auxiliar diretamente para controlo total sobre os casos, e depois
# confirma-se com um estudante real que o aviso aparece na prática.
# ----------------------------------------------------------------------------
def test_studytime_calibration_note_empty_when_no_prior_failures():
    # Sem reprovações anteriores, não faz sentido mostrar o aviso de calibração.
    changes = [{"label": "Tempo de estudo", "from": 1, "to": 3}]
    assert _studytime_calibration_note(changes, has_prior_failures=False) == ""


def test_studytime_calibration_note_empty_when_studytime_not_in_plan():
    # Se o plano nem sequer mexe no tempo de estudo, o aviso também não se aplica.
    changes = [{"label": "Faltas", "from": 5, "to": 0}]
    assert _studytime_calibration_note(changes, has_prior_failures=True) == ""


def test_studytime_calibration_note_present_when_both_conditions_met():
    # Com reprovações anteriores E mudança no tempo de estudo, o aviso deve aparecer.
    changes = [{"label": "Tempo de estudo", "from": 1, "to": 4}]
    note = _studytime_calibration_note(changes, has_prior_failures=True)
    assert "reprovações anteriores" in note
    assert "otimista" in note


def test_format_message_appends_calibration_note_only_when_relevant():
    # A mensagem final só deve incluir a nota de calibração quando aplicável.
    changes = [{"label": "Tempo de estudo", "from": 1, "to": 4}]
    with_failures = _format_message(False, 8.0, 9.5, 14, changes, has_prior_failures=True)
    without_failures = _format_message(False, 8.0, 9.5, 14, changes, has_prior_failures=False)
    assert "Nota:" in with_failures
    assert "Nota:" not in without_failures


def test_optimizer_message_includes_calibration_note_for_real_student_with_failures():
    # Confirmação de ponta a ponta, com um estudante real do dataset que tem reprovações.
    df = get_processed_data()
    candidates = df[(df["failures"] >= 1) & (df["G3"] < 10)]
    assert len(candidates) > 0  # o dataset real tem sempre casos assim
    student_id = int(candidates.iloc[0]["student_id"])

    result = otimizar_plano_estudo(df, student_id, target_grade=14)
    studytime_in_plan = any(c["label"] == "Tempo de estudo" for c in result["changes"])
    if studytime_in_plan:
        assert "reprovações anteriores" in result["message"]
    else:
        # Se o otimizador nem sequer escolheu mexer no tempo de estudo para
        # este estudante, o aviso não se aplica — nada a testar aqui.
        assert "reprovações anteriores" not in result["message"]
