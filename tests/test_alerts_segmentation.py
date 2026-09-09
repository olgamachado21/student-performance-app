# Testes para src/alerts.py (alertas automáticos e risco combinado) e
# src/segmentation.py (agrupamento de estudantes em clusters/perfis).
import pandas as pd

from src.alerts import (generate_alerts, generate_combined_risk_alert,
                         get_at_risk_students)
from src.data_processing import get_processed_data
from src.segmentation import run_segmentation


def test_at_risk_column_exists_and_is_binary():
    # A coluna "at_risk" deve existir e conter apenas 0 (não em risco) ou 1 (em risco).
    df = get_processed_data()
    assert "at_risk" in df.columns
    assert set(df["at_risk"].unique()).issubset({0, 1})


def test_generate_alerts_returns_sorted_list():
    # Os alertas devem vir ordenados por gravidade (urgente > aviso > info) e
    # cada um deve ter título e descrição.
    df = get_processed_data()
    alerts = generate_alerts(df)
    assert len(alerts) >= 1
    severities = [a["severity"] for a in alerts]
    order = {"urgente": 0, "aviso": 1, "info": 2}
    assert severities == sorted(severities, key=lambda s: order.get(s, 99))
    for a in alerts:
        assert "title" in a and "description" in a


def test_get_at_risk_students_only_returns_at_risk():
    # A lista de estudantes em risco não deve incluir ninguém com at_risk=0.
    df = get_processed_data()
    students = get_at_risk_students(df, limit=20)
    assert all(s["at_risk"] == 1 for s in students)


def test_run_segmentation_structure():
    # A segmentação deve devolver o número de clusters pedido, com o total de
    # estudantes distribuído corretamente e metadados válidos por grupo.
    df = get_processed_data()
    result = run_segmentation(df, n_clusters=4)
    assert result["n_clusters"] == 4
    assert len(result["groups"]) == 4
    total_size = sum(g["size"] for g in result["groups"])
    assert total_size == result["n_students"]
    for g in result["groups"]:
        assert 0 <= g["risk_pct"] <= 100
        assert len(g["traits"]) >= 1
        assert g["name"]


def test_run_segmentation_clamps_n_clusters():
    # Pedidos de clusters fora do intervalo permitido devem ser ajustados
    # (clamped) para os limites mínimo/máximo, nunca rejeitados.
    df = get_processed_data()
    result = run_segmentation(df, n_clusters=20)
    assert result["n_clusters"] == 8
    result2 = run_segmentation(df, n_clusters=1)
    assert result2["n_clusters"] == 3


# ----------------------------------------------------------------------------
# student_ids por grupo: usados pelo frontend (segmentation.js) para abrir a
# lista de estudantes de um cluster ao clicar no respetivo cartão.
# ----------------------------------------------------------------------------
def test_run_segmentation_groups_include_student_ids():
    # Cada grupo deve trazer a lista de IDs dos estudantes que o compõem.
    df = get_processed_data()
    result = run_segmentation(df, n_clusters=4)
    for g in result["groups"]:
        assert "student_ids" in g
        assert len(g["student_ids"]) == g["size"]
        assert all(isinstance(sid, int) for sid in g["student_ids"])


def test_run_segmentation_student_ids_partition_the_dataset():
    df = get_processed_data()
    result = run_segmentation(df, n_clusters=4)
    all_ids = [sid for g in result["groups"] for sid in g["student_ids"]]
    # Cada estudante pertence a exatamente um grupo — sem sobreposição nem
    # ninguém em falta face ao total de estudantes da segmentação.
    assert len(all_ids) == len(set(all_ids))
    assert len(all_ids) == result["n_students"]
    assert set(all_ids).issubset(set(df["student_id"].tolist()))


# ----------------------------------------------------------------------------
# Risco combinado (faltas altas + reprovação anterior): usa um DataFrame
# sintético em vez do dataset real para os casos de fronteira (nenhum
# estudante em risco combinado), que é determinístico e não depende dos
# dados atuais — mas também confirma o comportamento com o dataset real, já
# que ele tem sempre um grupo de risco combinado (ver verificação manual).
# ----------------------------------------------------------------------------
def _make_df(absences, failures, g3):
    # Helper para construir rapidamente um DataFrame mínimo com as 3 colunas
    # relevantes para o cálculo de risco combinado.
    return pd.DataFrame({"absences": absences, "failures": failures, "G3": g3})


def test_generate_combined_risk_alert_none_when_no_overlap():
    # Mediana de faltas = 2; ninguém está acima da mediana E com reprovação.
    df = _make_df(absences=[1, 2, 2, 3, 4], failures=[0, 0, 1, 0, 0], g3=[15, 14, 13, 12, 11])
    assert generate_combined_risk_alert(df) is None


def test_generate_combined_risk_alert_fires_when_overlap_exists():
    # Aqui há sobreposição real entre faltas altas e reprovações -> deve gerar alerta.
    df = _make_df(
        absences=[0, 1, 2, 8, 9, 10],
        failures=[0, 0, 0, 1, 2, 1],
        g3=[16, 15, 14, 8, 7, 9],
    )
    result = generate_combined_risk_alert(df)
    assert result is not None
    assert result["id"] == "combined_risk_absences_failures"
    assert result["action_page"] == "risk"
    # 3 estudantes (faltas 8,9,10 e failures>=1) formam o grupo combinado.
    assert "3 estudante" in result["description"]


def test_generate_combined_risk_alert_severity_scales_with_group_size():
    # Grupo pequeno (<5% da turma) -> "aviso".
    df_small = _make_df(
        absences=[0] * 95 + [8, 9],
        failures=[0] * 95 + [1, 1],
        g3=[15] * 95 + [7, 8],
    )
    assert generate_combined_risk_alert(df_small)["severity"] == "aviso"

    # Grupo grande (>=5% da turma) -> "urgente".
    df_large = _make_df(
        absences=[0] * 80 + [8] * 20,
        failures=[0] * 80 + [1] * 20,
        g3=[15] * 80 + [7] * 20,
    )
    assert generate_combined_risk_alert(df_large)["severity"] == "urgente"


def test_generate_combined_risk_alert_on_real_dataset():
    # No dataset real, deve sempre existir algum grupo de risco combinado.
    df = get_processed_data()
    result = generate_combined_risk_alert(df)
    assert result is not None
    assert result["severity"] in {"aviso", "urgente"}


def test_generate_alerts_includes_combined_risk_alert_on_real_dataset():
    # A lista geral de alertas deve incluir o alerta de risco combinado.
    df = get_processed_data()
    alerts = generate_alerts(df)
    assert any(a["id"] == "combined_risk_absences_failures" for a in alerts)
