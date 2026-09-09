# Testes para o endpoint GET /scatter (src/api.py) — pontos + regressão simples.
import pytest
from fastapi import HTTPException

from src.api import scatter
from src.data_processing import get_processed_data


def test_scatter_returns_one_point_per_student_pair():
    # Deve devolver exatamente um ponto por cada par de valores válido (sem NaN).
    df = get_processed_data()
    result = scatter(x="studytime", y="G3")
    sub = df[["studytime", "G3"]].dropna()
    assert len(result["points"]) == len(sub)


def test_scatter_points_have_x_and_y():
    result = scatter(x="absences", y="G3")
    for point in result["points"]:
        assert "x" in point and "y" in point


def test_scatter_includes_regression_for_different_variables():
    # Com duas variáveis diferentes, a regressão deve vir preenchida com os campos esperados.
    result = scatter(x="failures", y="G3")
    reg = result["regression"]
    assert reg is not None
    assert reg["x"] == "failures"
    assert reg["y"] == "G3"
    assert "coeficiente" in reg and "intercept" in reg and "r2" in reg


def test_scatter_regression_is_none_when_same_variable_both_axes():
    # Com a mesma variável nos dois eixos, não faz sentido calcular regressão.
    result = scatter(x="G3", y="G3")
    assert result["regression"] is None
    # Mesma variável nos dois eixos: todos os pontos ficam sobre a diagonal.
    for point in result["points"]:
        assert point["x"] == point["y"]


def test_scatter_rejects_invalid_variable():
    # Uma variável desconhecida deve devolver erro HTTP 400, não rebentar.
    with pytest.raises(HTTPException) as exc_info:
        scatter(x="nome_inventado", y="G3")
    assert exc_info.value.status_code == 400


def test_scatter_regression_matches_heatmap_correlation_sign():
    # Coerência com o heatmap de correlação (/correlations): o sinal do
    # coeficiente de regressão deve concordar com o sinal da correlação
    # entre as mesmas duas variáveis (faltas -> nota é uma relação negativa,
    # tal como aparece a azul/vermelho no heatmap).
    df = get_processed_data()
    corr = df[["absences", "G3"]].corr().iloc[0, 1]
    result = scatter(x="absences", y="G3")
    coeficiente = result["regression"]["coeficiente"]
    assert (coeficiente < 0) == (corr < 0)
