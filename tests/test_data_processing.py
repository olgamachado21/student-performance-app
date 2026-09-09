# Testes para src/data_processing.py — limpeza e preparação dos dados.
import pandas as pd
import pytest

from src.data_processing import add_features, clean_data, get_processed_data


def test_get_processed_data_shape():
    # O pipeline completo deve devolver dados não vazios, com as colunas derivadas esperadas.
    df = get_processed_data()
    assert len(df) > 0
    assert "aprovado" in df.columns
    assert "alcohol_avg" in df.columns


def test_no_nulls_after_processing():
    # Depois da limpeza, não deve sobrar nenhum valor em falta.
    df = get_processed_data()
    assert df.isnull().sum().sum() == 0


def test_grades_within_valid_range():
    # Todas as notas devem estar dentro da escala válida (0-20).
    df = get_processed_data()
    for col in ["G1", "G2", "G3"]:
        assert df[col].between(0, 20).all()


def test_aprovado_matches_threshold():
    # A coluna "aprovado" deve corresponder exatamente à regra G3 >= 10.
    df = get_processed_data()
    expected = (df["G3"] >= 10).astype(int)
    assert (df["aprovado"] == expected).all()


def test_clean_data_removes_duplicates():
    # Duas linhas exatamente iguais devem ficar reduzidas a uma só depois da limpeza.
    raw = pd.DataFrame({
        "age": [16, 16], "Medu": [2, 2], "Fedu": [2, 2], "traveltime": [1, 1],
        "studytime": [2, 2], "failures": [0, 0], "famrel": [4, 4], "freetime": [3, 3],
        "goout": [3, 3], "Dalc": [1, 1], "Walc": [1, 1], "health": [3, 3],
        "absences": [0, 0], "G1": [10, 10], "G2": [10, 10], "G3": [10, 10],
    })
    cleaned = clean_data(raw)
    assert len(cleaned) == 1


def test_clean_data_drops_invalid_grades():
    # Uma nota fora da escala válida (G3=25, acima de 20) deve fazer a linha ser descartada.
    raw = pd.DataFrame({
        "age": [16], "Medu": [2], "Fedu": [2], "traveltime": [1], "studytime": [2],
        "failures": [0], "famrel": [4], "freetime": [3], "goout": [3], "Dalc": [1],
        "Walc": [1], "health": [3], "absences": [0], "G1": [10], "G2": [10], "G3": [25],
    })
    cleaned = clean_data(raw)
    assert len(cleaned) == 0
