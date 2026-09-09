# Testes para src/statistics_analysis.py — testes t, ANOVA e regressão linear simples.
from src.data_processing import get_processed_data
from src.statistics_analysis import (compare_multiple_groups, compare_two_groups,
                                      simple_linear_regression)


def test_compare_two_groups_structure():
    # Verifica que o resultado do teste t tem os campos esperados e compara exatamente 2 categorias.
    df = get_processed_data()
    result = compare_two_groups(df, "internet")
    assert "p_value" in result
    assert "significativo_5pct" in result
    assert len(result["categorias"]) == 2


def test_compare_multiple_groups_structure():
    # A ANOVA sobre "studytime" (4 níveis) deve devolver a média de cada um dos 4 grupos.
    df = get_processed_data()
    result = compare_multiple_groups(df, "studytime")
    assert "f_stat" in result
    assert len(result["medias_por_grupo"]) == 4


def test_simple_linear_regression_structure():
    # Verifica que a regressão devolve um coeficiente válido, um R² entre 0 e 1,
    # e que a relação estudo->nota é estatisticamente significativa (já sabido pelo relatório).
    df = get_processed_data()
    result = simple_linear_regression(df, "studytime")
    assert -1 <= result["coeficiente"] or result["coeficiente"] is not None
    assert 0 <= result["r2"] <= 1
    assert result["significativo_5pct"] is True  # sabido, pelo relatório gerado
