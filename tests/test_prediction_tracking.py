# Testes para src/prediction_tracking.py — guardar "instantâneos" (snapshots)
# de previsões, registar a nota real depois e medir a precisão do modelo ao
# longo do tempo com dados reais (não só no conjunto de teste do treino).
import pytest

from src import prediction_tracking
from src.predict import full_prediction


HABITS_ONLY = {"studytime": 4, "absences": 2, "failures": 0, "goout": 2, "Dalc": 1, "Walc": 1}
HABITS_WITH_GRADES = {**HABITS_ONLY, "G1": 14, "G2": 15}


def test_save_snapshot_uses_habitos_variant_when_no_grades():
    # Sem G1/G2, o snapshot deve guardar a previsão da variante "hábitos", pendente de nota real.
    result = full_prediction(HABITS_ONLY)
    snap = prediction_tracking.save_snapshot(result, HABITS_ONLY, label="Sem notas")
    assert snap["model_variant"] == "habitos"
    assert snap["predicted_grade"] == result["nota_prevista_habitos"]["predicted_grade"]
    assert snap["status"] == "pendente"
    assert snap["actual_grade"] is None


def test_save_snapshot_uses_completa_variant_when_g1_and_g2_present():
    # Com G1/G2 presentes, deve usar a variante "completa" (mais precisa).
    result = full_prediction(HABITS_WITH_GRADES)
    snap = prediction_tracking.save_snapshot(result, HABITS_WITH_GRADES, label="Com notas")
    assert snap["model_variant"] == result["nota_prevista_completa"]["model_variant"]
    assert snap["predicted_grade"] == result["nota_prevista_completa"]["predicted_grade"]


def test_save_snapshot_rejects_invalid_prediction_result():
    # Um resultado de previsão vazio/inválido deve ser rejeitado.
    with pytest.raises(ValueError):
        prediction_tracking.save_snapshot({}, HABITS_ONLY, label="Inválido")


def test_save_snapshot_strips_label_and_defaults_to_empty():
    # O rótulo deve ter os espaços extremos removidos; só espaços vira rótulo vazio.
    result = full_prediction(HABITS_ONLY)
    snap = prediction_tracking.save_snapshot(result, HABITS_ONLY, label="   ")
    assert snap["label"] == ""

    snap2 = prediction_tracking.save_snapshot(result, HABITS_ONLY, label="  Com espaços  ")
    assert snap2["label"] == "Com espaços"


def test_get_snapshots_returns_most_recent_first():
    # Os snapshots devem vir ordenados do mais recente para o mais antigo.
    result = full_prediction(HABITS_ONLY)
    first = prediction_tracking.save_snapshot(result, HABITS_ONLY, label="Primeira")
    second = prediction_tracking.save_snapshot(result, HABITS_ONLY, label="Segunda")

    snapshots = prediction_tracking.get_snapshots()
    ids = [s["id"] for s in snapshots]
    assert ids.index(second["id"]) < ids.index(first["id"])


def test_get_snapshots_habits_round_trip_as_dict():
    # Os hábitos guardados devem ser recuperáveis intactos como dicionário.
    result = full_prediction(HABITS_ONLY)
    snap = prediction_tracking.save_snapshot(result, HABITS_ONLY, label="Hábitos")
    reloaded = next(s for s in prediction_tracking.get_snapshots() if s["id"] == snap["id"])
    assert reloaded["habits"] == HABITS_ONLY


def test_record_actual_grade_better_than_predicted():
    # Uma nota real bem acima da prevista deve marcar o status "melhor que previsto".
    result = full_prediction(HABITS_ONLY)
    snap = prediction_tracking.save_snapshot(result, HABITS_ONLY, label="Melhor")
    updated = prediction_tracking.record_actual_grade(snap["id"], snap["predicted_grade"] + 2)
    assert updated["status"] == "melhor_que_previsto"
    assert updated["diff"] == pytest.approx(2.0, abs=0.01)
    assert updated["actual_recorded_at"] is not None


def test_record_actual_grade_worse_than_predicted():
    # Uma nota real bem abaixo da prevista deve marcar o status "pior que previsto".
    result = full_prediction(HABITS_ONLY)
    snap = prediction_tracking.save_snapshot(result, HABITS_ONLY, label="Pior")
    updated = prediction_tracking.record_actual_grade(snap["id"], max(snap["predicted_grade"] - 2, 0))
    assert updated["status"] == "pior_que_previsto"


def test_record_actual_grade_within_tolerance_is_como_previsto():
    # Uma nota real muito próxima da prevista deve marcar "como previsto".
    result = full_prediction(HABITS_ONLY)
    snap = prediction_tracking.save_snapshot(result, HABITS_ONLY, label="Igual")
    close_grade = min(max(snap["predicted_grade"] + 0.2, 0), 20)
    updated = prediction_tracking.record_actual_grade(snap["id"], close_grade)
    assert updated["status"] == "como_previsto"


def test_record_actual_grade_not_found_raises():
    # Um id de snapshot inexistente deve levantar erro com mensagem clara.
    with pytest.raises(ValueError, match="não encontrada"):
        prediction_tracking.record_actual_grade(9_999_999, 15.0)


def test_record_actual_grade_out_of_range_raises():
    # Uma nota real fora da escala válida (0-20) deve ser rejeitada.
    result = full_prediction(HABITS_ONLY)
    snap = prediction_tracking.save_snapshot(result, HABITS_ONLY, label="Fora de gama")
    with pytest.raises(ValueError, match="entre 0 e 20"):
        prediction_tracking.record_actual_grade(snap["id"], 25)
    with pytest.raises(ValueError, match="entre 0 e 20"):
        prediction_tracking.record_actual_grade(snap["id"], -1)


def test_delete_snapshot_removes_it_and_returns_true():
    # Apagar um snapshot existente deve devolver True e removê-lo da lista.
    result = full_prediction(HABITS_ONLY)
    snap = prediction_tracking.save_snapshot(result, HABITS_ONLY, label="Para apagar")
    assert prediction_tracking.delete_snapshot(snap["id"]) is True
    remaining_ids = {s["id"] for s in prediction_tracking.get_snapshots()}
    assert snap["id"] not in remaining_ids


def test_delete_snapshot_unknown_id_returns_false():
    # Apagar um id inexistente deve devolver False, sem levantar erro.
    assert prediction_tracking.delete_snapshot(9_999_999) is False


# ------------------------------------------------------------------
# Camada da API
# ------------------------------------------------------------------

def test_api_save_and_list_snapshot():
    # O endpoint de guardar deve devolver o snapshot criado, visível depois na listagem.
    from src.api import PredictionSnapshotInput, save_prediction_snapshot, list_prediction_snapshots

    payload = PredictionSnapshotInput(studytime=3, absences=1, label="Via API")
    created = save_prediction_snapshot(payload)
    assert created["label"] == "Via API"

    listing = list_prediction_snapshots()
    assert any(s["id"] == created["id"] for s in listing["snapshots"])


def test_api_record_actual_grade_endpoint():
    # O endpoint de registar nota real deve atualizar o snapshot com status válido.
    from src.api import (ActualGradeInput, PredictionSnapshotInput,
                          record_prediction_snapshot_actual, save_prediction_snapshot)

    created = save_prediction_snapshot(PredictionSnapshotInput(studytime=3, absences=1, label="Via API 2"))
    updated = record_prediction_snapshot_actual(created["id"], ActualGradeInput(actual_grade=14))
    assert updated["actual_grade"] == 14.0
    assert updated["status"] in {"melhor_que_previsto", "pior_que_previsto", "como_previsto"}


def test_api_record_actual_grade_endpoint_404_on_unknown_id():
    # Um id inexistente deve devolver erro HTTP 404.
    from fastapi import HTTPException

    from src.api import ActualGradeInput, record_prediction_snapshot_actual

    with pytest.raises(HTTPException) as exc_info:
        record_prediction_snapshot_actual(9_999_999, ActualGradeInput(actual_grade=14))
    assert exc_info.value.status_code == 404


def test_api_record_actual_grade_endpoint_400_on_invalid_grade():
    # Uma nota fora da escala válida deve ser rejeitada já na validação do modelo Pydantic.
    from fastapi import HTTPException
    from pydantic import ValidationError

    from src.api import ActualGradeInput, PredictionSnapshotInput, save_prediction_snapshot

    created = save_prediction_snapshot(PredictionSnapshotInput(studytime=3, absences=1, label="Via API 3"))
    with pytest.raises(ValidationError):
        ActualGradeInput(actual_grade=25)


def test_api_delete_snapshot_endpoint():
    # O endpoint de apagar deve confirmar a eliminação.
    from src.api import PredictionSnapshotInput, delete_prediction_snapshot, save_prediction_snapshot

    created = save_prediction_snapshot(PredictionSnapshotInput(studytime=3, absences=1, label="Para apagar via API"))
    result = delete_prediction_snapshot(created["id"])
    assert result == {"deleted": True}


def test_api_delete_snapshot_endpoint_404_on_unknown_id():
    # Apagar um id inexistente via API deve devolver 404.
    from fastapi import HTTPException

    from src.api import delete_prediction_snapshot

    with pytest.raises(HTTPException) as exc_info:
        delete_prediction_snapshot(9_999_999)
    assert exc_info.value.status_code == 404


# ------------------------------------------------------------------
# Validação com dados reais: agrega previsões guardadas + nota real
# registada, para medir o erro do modelo "em produção", não só no
# conjunto de teste separado no treino.
# ------------------------------------------------------------------

def test_validation_summary_no_data_state(monkeypatch):
    # Isola de propósito da tabela partilhada (monkeypatch get_snapshots
    # para devolver vazio) — testar o estado "sem dados" a partir da tabela
    # real não é fiável, porque outros testes deste ficheiro já registaram
    # notas reais nela antes deste correr.
    monkeypatch.setattr(prediction_tracking, "get_snapshots", lambda: [])
    summary = prediction_tracking.get_validation_summary()
    assert summary["has_data"] is False
    assert summary["n_validated"] == 0


def test_validation_summary_structure_when_data_exists():
    # Com pelo menos uma previsão validada, o resumo deve trazer métricas de erro coerentes.
    result = full_prediction(HABITS_ONLY)
    snap = prediction_tracking.save_snapshot(result, HABITS_ONLY, label="Validação")
    prediction_tracking.record_actual_grade(snap["id"], min(snap["predicted_grade"] + 1, 20))

    summary = prediction_tracking.get_validation_summary()
    assert summary["has_data"] is True
    assert summary["n_validated"] >= 1
    assert summary["real_world_mae"] >= 0
    assert summary["real_world_rmse"] >= summary["real_world_mae"]  # RMSE nunca é menor que o MAE
    assert sum(summary["status_counts"].values()) == summary["n_validated"]


def test_validation_summary_ignores_snapshots_without_actual_grade():
    # Snapshots ainda pendentes (sem nota real) não devem contar para o resumo.
    result = full_prediction(HABITS_ONLY)
    before = prediction_tracking.get_validation_summary()["n_validated"]
    prediction_tracking.save_snapshot(result, HABITS_ONLY, label="Ainda pendente")
    after = prediction_tracking.get_validation_summary()["n_validated"]
    assert after == before


def test_api_prediction_validation_endpoint():
    # O endpoint deve expor o mesmo resumo de validação.
    from src.api import prediction_validation_summary

    result = prediction_validation_summary()
    assert "has_data" in result
    assert "n_validated" in result


def test_api_deleted_snapshot_is_permanently_removed():
    # Um snapshot apagado via API não deve reaparecer na listagem.
    from src.api import (PredictionSnapshotInput, delete_prediction_snapshot,
                          list_prediction_snapshots, save_prediction_snapshot)

    created = save_prediction_snapshot(PredictionSnapshotInput(studytime=3, absences=1, label="Para apagar"))
    delete_prediction_snapshot(created["id"])

    listing = list_prediction_snapshots()
    assert not any(s["label"] == "Para apagar" for s in listing["snapshots"])


# ------------------------------------------------------------------
# Precisão do modelo ao longo do tempo: MAE acumulado à medida que mais
# notas reais vão sendo registadas (complementa get_validation_summary, que
# só dá um número agregado "de sempre").
# ------------------------------------------------------------------

def test_accuracy_over_time_no_data_state(monkeypatch):
    # Sem snapshots validados, deve devolver o estado "sem dados" e lista de pontos vazia.
    monkeypatch.setattr(prediction_tracking, "get_snapshots", lambda: [])
    result = prediction_tracking.get_accuracy_over_time()
    assert result["has_data"] is False
    assert result["n_validated"] == 0
    assert result["points"] == []


def test_accuracy_over_time_single_point_has_data_false(monkeypatch):
    # Uma só previsão validada não é suficiente para mostrar uma "tendência"
    # ao longo do tempo — has_data só fica True com pelo menos 2 pontos.
    result = full_prediction(HABITS_ONLY)
    snap = prediction_tracking.save_snapshot(result, HABITS_ONLY, label="Único")
    prediction_tracking.record_actual_grade(snap["id"], min(snap["predicted_grade"] + 1, 20))

    all_validated = [s for s in prediction_tracking.get_snapshots() if s["actual_grade"] is not None]
    monkeypatch.setattr(prediction_tracking, "get_snapshots", lambda: [all_validated[0]])
    result = prediction_tracking.get_accuracy_over_time()
    assert result["n_validated"] == 1
    assert result["has_data"] is False


def test_accuracy_over_time_structure_and_cumulative_mae(monkeypatch):
    # Com 2 pontos validados, deve calcular o MAE acumulado corretamente ponto a ponto.
    result1 = full_prediction(HABITS_ONLY)
    snap1 = prediction_tracking.save_snapshot(result1, HABITS_ONLY, label="Primeiro")
    updated1 = prediction_tracking.record_actual_grade(snap1["id"], min(snap1["predicted_grade"] + 2, 20))

    result2 = full_prediction(HABITS_WITH_GRADES)
    snap2 = prediction_tracking.save_snapshot(result2, HABITS_WITH_GRADES, label="Segundo")
    updated2 = prediction_tracking.record_actual_grade(snap2["id"], max(snap2["predicted_grade"] - 1, 0))

    monkeypatch.setattr(prediction_tracking, "get_snapshots", lambda: [updated1, updated2])
    accuracy = prediction_tracking.get_accuracy_over_time()

    assert accuracy["n_validated"] == 2
    assert accuracy["has_data"] is True
    assert len(accuracy["points"]) == 2

    first_point, second_point = accuracy["points"]
    assert first_point["n_so_far"] == 1
    assert second_point["n_so_far"] == 2
    # O MAE acumulado do segundo ponto é a média dos erros dos dois pontos.
    expected_cumulative = round((first_point["error"] + second_point["error"]) / 2, 2)
    assert second_point["cumulative_mae"] == expected_cumulative
    for point in accuracy["points"]:
        assert "recorded_at" in point
        assert "predicted_grade" in point
        assert "actual_grade" in point


def test_accuracy_over_time_orders_points_by_recorded_at(monkeypatch):
    # Os pontos devem vir ordenados pela data de registo da nota real, não pela ordem de entrada.
    result = full_prediction(HABITS_ONLY)
    snap_a = prediction_tracking.save_snapshot(result, HABITS_ONLY, label="A")
    updated_a = prediction_tracking.record_actual_grade(snap_a["id"], min(snap_a["predicted_grade"] + 1, 20))
    snap_b = prediction_tracking.save_snapshot(result, HABITS_ONLY, label="B")
    updated_b = prediction_tracking.record_actual_grade(snap_b["id"], max(snap_b["predicted_grade"] - 1, 0))

    # Troca deliberadamente a ordem de entrada para confirmar que a função
    # ordena pela data de registo da nota real, não pela ordem da lista.
    monkeypatch.setattr(prediction_tracking, "get_snapshots", lambda: [updated_b, updated_a])
    accuracy = prediction_tracking.get_accuracy_over_time()
    recorded_ats = [p["recorded_at"] for p in accuracy["points"]]
    assert recorded_ats == sorted(recorded_ats)


def test_api_accuracy_over_time_endpoint():
    # O endpoint deve expor a mesma estrutura de precisão ao longo do tempo.
    from src.api import prediction_accuracy_over_time

    result = prediction_accuracy_over_time()
    assert "has_data" in result
    assert "n_validated" in result
    assert "points" in result
