"""Testes para src/formula_engine.py — o avaliador seguro de fórmulas
personalizadas (sem eval()/exec()) usado pela página "Fórmulas
Personalizadas" do Dataset Personalizado. Testado diretamente sobre um
DataFrame sintético, sem precisar de base de dados nem da API."""
import numpy as np
import pandas as pd
import pytest

from src.formula_engine import FormulaError, evaluate


def _sample_df() -> pd.DataFrame:
    return pd.DataFrame({
        "row_id": [1, 2, 3, 4, 5, 6],
        "G1": [10.0, 12.0, 8.0, 15.0, 9.0, 18.0],
        "G2": [11.0, 13.0, 7.0, 16.0, 10.0, 17.0],
        "G3": [12.0, 14.0, 6.0, 17.0, 8.0, 19.0],
        "studytime": [1, 2, 3, 4, 2, 3],
        "absences": [5, 0, 10, 2, 8, 1],
        "sex": ["F", "M", "F", "M", "F", "M"],
    })


# --- Coluna calculada (resultado por linha) ----------------------------------
def test_weighted_average_formula_returns_one_value_per_row():
    df = _sample_df()
    result = evaluate(df, "G1*0.3 + G2*0.3 + G3*0.4")
    assert result["type"] == "column"
    assert result["n_rows"] == 6
    assert len(result["rows"]) == 6
    expected_first = 10.0 * 0.3 + 11.0 * 0.3 + 12.0 * 0.4
    assert result["rows"][0]["resultado"] == pytest.approx(expected_first, abs=1e-6)
    assert result["summary"] is not None


def test_column_formula_is_paginated():
    df = _sample_df()
    result = evaluate(df, "G3 * 2", page=1, page_size=2)
    assert result["n_rows"] == 6
    assert result["total_pages"] == 3
    assert len(result["rows"]) == 2
    result_p2 = evaluate(df, "G3 * 2", page=2, page_size=2)
    assert result_p2["rows"][0]["row_id"] != result["rows"][0]["row_id"]


def test_column_formula_out_of_range_page_clamped():
    df = _sample_df()
    result = evaluate(df, "G3", page=999, page_size=2)
    assert result["page"] == result["total_pages"]


def test_se_function_row_wise_conditional():
    df = _sample_df()
    result = evaluate(df, "se(G3 >= 10, 1, 0)")
    assert result["type"] == "column"
    values = [r["resultado"] for r in result["rows"]]
    assert values == [1, 1, 0, 1, 0, 1]


def test_absoluto_and_arredondar_functions():
    df = _sample_df()
    result = evaluate(df, "arredondar(G3 - G1, 1)")
    assert result["type"] == "column"
    assert result["rows"][0]["resultado"] == pytest.approx(2.0)


# --- Resultado agregado (escalar) --------------------------------------------
def test_average_aggregate_formula_returns_scalar():
    df = _sample_df()
    result = evaluate(df, "media(G3)")
    assert result["type"] == "scalar"
    # O resultado é arredondado a 4 casas decimais para uma saída JSON limpa
    # (ver _clean_value) — por isso a comparação usa uma tolerância absoluta
    # compatível com esse arredondamento, em vez da tolerância relativa
    # (muito mais apertada) por omissão do pytest.approx.
    assert result["result"] == pytest.approx(df["G3"].mean(), abs=1e-4)
    assert result["n_rows_considered"] == 6


def test_aggregate_formula_combined_arithmetically():
    df = _sample_df()
    result = evaluate(df, "media(G3) - media(G1)")
    assert result["type"] == "scalar"
    assert result["result"] == pytest.approx(df["G3"].mean() - df["G1"].mean(), abs=1e-4)


def test_soma_minimo_maximo_mediana_desvio_contar():
    df = _sample_df()
    assert evaluate(df, "soma(absences)")["result"] == pytest.approx(df["absences"].sum(), abs=1e-4)
    assert evaluate(df, "minimo(G3)")["result"] == pytest.approx(df["G3"].min(), abs=1e-4)
    assert evaluate(df, "maximo(G3)")["result"] == pytest.approx(df["G3"].max(), abs=1e-4)
    assert evaluate(df, "mediana(G3)")["result"] == pytest.approx(df["G3"].median(), abs=1e-4)
    assert evaluate(df, "desvio(G3)")["result"] == pytest.approx(df["G3"].std(), abs=1e-4)
    assert evaluate(df, "contar(G3)")["result"] == 6
    assert evaluate(df, "contar()")["result"] == 6


def test_accented_function_names_are_accepted():
    df = _sample_df()
    result = evaluate(df, "média(G3)")
    assert result["result"] == pytest.approx(df["G3"].mean(), abs=1e-4)


# --- Filtro "onde"/"where" ----------------------------------------------------
def test_where_clause_filters_rows_for_aggregate():
    df = _sample_df()
    result = evaluate(df, "media(G3) onde studytime >= 3")
    subset = df[df["studytime"] >= 3]
    assert result["result"] == pytest.approx(subset["G3"].mean(), abs=1e-4)
    assert result["n_rows_considered"] == len(subset)


def test_where_clause_filters_rows_for_column_formula():
    df = _sample_df()
    result = evaluate(df, "G3 onde sex == 'F'")
    subset = df[df["sex"] == "F"]
    assert result["n_rows"] == len(subset)


def test_where_clause_with_english_where_keyword():
    df = _sample_df()
    result = evaluate(df, "media(G3) where sex == 'M'")
    subset = df[df["sex"] == "M"]
    assert result["result"] == pytest.approx(subset["G3"].mean(), abs=1e-4)


def test_single_equals_sign_is_normalized_to_equality():
    df = _sample_df()
    result = evaluate(df, "media(G3) onde sex = 'F'")
    subset = df[df["sex"] == "F"]
    assert result["result"] == pytest.approx(subset["G3"].mean(), abs=1e-4)


def test_where_clause_matching_no_rows_raises():
    df = _sample_df()
    with pytest.raises(FormulaError):
        evaluate(df, "media(G3) onde studytime > 100")


# --- Erros de utilização -------------------------------------------------------
def test_empty_formula_raises():
    df = _sample_df()
    with pytest.raises(FormulaError):
        evaluate(df, "")
    with pytest.raises(FormulaError):
        evaluate(df, "   ")


def test_unknown_column_raises_friendly_error():
    df = _sample_df()
    with pytest.raises(FormulaError, match="Coluna desconhecida"):
        evaluate(df, "coluna_que_nao_existe * 2")


def test_unknown_function_raises_friendly_error():
    df = _sample_df()
    with pytest.raises(FormulaError, match="Função desconhecida"):
        evaluate(df, "funcao_inventada(G3)")


def test_syntax_error_raises_friendly_error():
    df = _sample_df()
    with pytest.raises(FormulaError, match="sintaxe"):
        evaluate(df, "G3 + * 2")


def test_aggregate_function_on_number_instead_of_column_raises():
    df = _sample_df()
    with pytest.raises(FormulaError):
        evaluate(df, "media(5)")


def test_aggregate_function_wrong_arg_count_raises():
    df = _sample_df()
    with pytest.raises(FormulaError):
        evaluate(df, "media(G3, G1)")


def test_division_by_zero_raises_friendly_error():
    df = _sample_df()
    # Divisão de dois valores escalares (dois agregados) por zero levanta
    # ZeroDivisionError normal do Python, que o motor traduz numa mensagem
    # amigável. Uma divisão por zero coluna-a-coluna (Series / 0) não é um
    # erro em pandas/numpy — dá "inf" em vez de rebentar — por isso este
    # teste usa deliberadamente dois valores agregados (escalares).
    with pytest.raises(FormulaError, match="[Dd]ivis"):
        evaluate(df, "media(G3) / 0")


def test_huge_exponent_is_rejected():
    df = _sample_df()
    with pytest.raises(FormulaError, match="[Ee]xpoente"):
        evaluate(df, "G3 ** 999999999")


def test_formula_too_long_is_rejected():
    df = _sample_df()
    with pytest.raises(FormulaError):
        evaluate(df, "G3 + " + "1 + " * 200 + "1")


def test_formula_too_complex_is_rejected():
    df = _sample_df()
    huge_expr = "(" * 150 + "G3" + ")" * 150
    with pytest.raises(FormulaError):
        evaluate(df, huge_expr)


# --- Segurança: rejeitar qualquer coisa fora da lista branca --------------------
@pytest.mark.parametrize("malicious", [
    "__import__('os').system('echo pwned')",
    "().__class__.__bases__[0]",
    "[x for x in range(3)]",
    "lambda x: x",
    "open('/etc/passwd').read()",
    "G3.__class__",
    "exec('1')",
    "eval('1')",
    "(1).to_bytes",
    "G3; absences",
])
def test_malicious_or_disallowed_expressions_are_rejected(malicious):
    df = _sample_df()
    with pytest.raises(FormulaError):
        evaluate(df, malicious)


def test_missing_dataset_columns_like_names_are_still_columns_not_python_builtins():
    """Uma fórmula não pode escapar para nomes/builtins do Python que não
    sejam colunas nem funções conhecidas — mesmo nomes "inofensivos" como
    'len' ou 'sum' têm de ser rejeitados como coluna/função desconhecida."""
    df = _sample_df()
    with pytest.raises(FormulaError):
        evaluate(df, "len(G3)")
    with pytest.raises(FormulaError):
        evaluate(df, "sum")
