"""Testes para src/data_export.py — exportação do dataset em CSV."""
import io

import pandas as pd
import pytest

from src.data_export import export_students_csv


@pytest.fixture
def sample_df():
    # DataFrame pequeno e controlado, com casos variados de escola,
    # desempenho e risco, para testar os filtros de exportação.
    return pd.DataFrame({
        "student_id": [1, 2, 3, 4],
        "school": ["GP", "GP", "MS", "MS"],
        "sex": ["F", "M", "F", "M"],
        "age": [17, 18, 16, 19],
        "studytime": [2, 3, 1, 4],
        "absences": [3, 0, 8, 1],
        "failures": [0, 1, 2, 0],
        "G1": [14, 10, 8, 18],
        "G2": [15, 11, 7, 19],
        "G3": [15, 10, 6, 20],
        "perf_band": ["Bom", "Suficiente", "Insuficiente", "Excelente"],
        "at_risk": [0, 0, 1, 0],
    })


def test_export_all_rows_no_filters(sample_df):
    # Sem filtros, todas as linhas devem ser exportadas, na mesma ordem.
    csv_text = export_students_csv(sample_df)
    parsed = pd.read_csv(io.StringIO(csv_text))
    assert len(parsed) == 4
    assert list(parsed["student_id"]) == [1, 2, 3, 4]


def test_export_includes_expected_columns(sample_df):
    # O CSV exportado deve conter todas as colunas relevantes para análise externa.
    csv_text = export_students_csv(sample_df)
    parsed = pd.read_csv(io.StringIO(csv_text))
    for col in ["student_id", "school", "sex", "age", "studytime", "absences",
                "failures", "G1", "G2", "G3", "perf_band", "at_risk"]:
        assert col in parsed.columns


def test_export_filters_by_school(sample_df):
    # Filtrar por escola deve devolver só os estudantes dessa escola.
    csv_text = export_students_csv(sample_df, school="GP")
    parsed = pd.read_csv(io.StringIO(csv_text))
    assert len(parsed) == 2
    assert set(parsed["school"]) == {"GP"}


def test_export_filters_by_perf_band(sample_df):
    # Filtrar por faixa de desempenho deve devolver só essa faixa.
    csv_text = export_students_csv(sample_df, perf_band="Insuficiente")
    parsed = pd.read_csv(io.StringIO(csv_text))
    assert len(parsed) == 1
    assert parsed.iloc[0]["student_id"] == 3


def test_export_filters_by_at_risk(sample_df):
    # Filtrar por at_risk=1 deve devolver só os estudantes em risco.
    csv_text = export_students_csv(sample_df, at_risk=1)
    parsed = pd.read_csv(io.StringIO(csv_text))
    assert len(parsed) == 1
    assert parsed.iloc[0]["student_id"] == 3


def test_export_combined_filters(sample_df):
    # Vários filtros combinados devem ser aplicados em conjunto (AND lógico).
    csv_text = export_students_csv(sample_df, school="MS", at_risk=0)
    parsed = pd.read_csv(io.StringIO(csv_text))
    assert len(parsed) == 1
    assert parsed.iloc[0]["student_id"] == 4


def test_export_no_matches_returns_header_only(sample_df):
    # Uma combinação de filtros sem correspondência deve devolver só o cabeçalho, sem erro.
    csv_text = export_students_csv(sample_df, school="GP", at_risk=1)
    parsed = pd.read_csv(io.StringIO(csv_text))
    assert len(parsed) == 0


def test_export_ignores_missing_optional_columns():
    # Colunas opcionais em falta no DataFrame de entrada não devem causar erro.
    df = pd.DataFrame({"student_id": [1], "school": ["GP"]})
    csv_text = export_students_csv(df)
    parsed = pd.read_csv(io.StringIO(csv_text))
    assert list(parsed.columns) == ["student_id", "school"]
