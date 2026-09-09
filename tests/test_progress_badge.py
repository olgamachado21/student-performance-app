# Testes para o "selo de progresso" (progress_badge) em src/data_processing.py
# — classifica cada estudante conforme a evolução da nota entre G1 -> G2 -> G3.
import pandas as pd

from src.data_processing import add_features, get_processed_data


def _minimal_df(rows):
    """Constrói um DataFrame mínimo, com todas as colunas que add_features() usa."""
    base = {
        "G1": [], "G2": [], "G3": [], "failures": [], "absences": [],
        "Dalc": [], "Walc": [], "Medu": [], "Fedu": [],
    }
    for r in rows:
        base["G1"].append(r[0])
        base["G2"].append(r[1])
        base["G3"].append(r[2])
        base["failures"].append(0)
        base["absences"].append(0)
        base["Dalc"].append(1)
        base["Walc"].append(1)
        base["Medu"].append(2)
        base["Fedu"].append(2)
    return pd.DataFrame(base)


def test_progress_badge_em_ascensao_when_both_steps_increase():
    # Nota a subir em ambos os passos (G1->G2 e G2->G3) -> "Em Ascensão".
    df = _minimal_df([(8, 10, 14)])
    result = add_features(df)
    assert result.loc[0, "progress_badge"] == "Em Ascensão"


def test_progress_badge_queda_a_vigiar_when_both_steps_decrease():
    # Nota a descer em ambos os passos -> "Queda a Vigiar".
    df = _minimal_df([(16, 12, 8)])
    result = add_features(df)
    assert result.loc[0, "progress_badge"] == "Queda a Vigiar"


def test_progress_badge_estavel_when_mixed_or_flat():
    # Sem alteração, ou tendência mista (sobe-desce/desce-sobe) -> "Estável".
    df = _minimal_df([
        (10, 10, 10),  # sem alteração
        (8, 14, 10),   # sobe e depois desce
        (14, 8, 12),   # desce e depois sobe
    ])
    result = add_features(df)
    assert (result["progress_badge"] == "Estável").all()


def test_progress_badge_column_present_and_valid_on_real_dataset():
    # No dataset real, a coluna deve existir e ter só valores válidos,
    # com estudantes reais em pelo menos as categorias mais comuns.
    df = get_processed_data()
    assert "progress_badge" in df.columns
    valid_values = {"Em Ascensão", "Queda a Vigiar", "Estável"}
    assert set(df["progress_badge"].unique()).issubset(valid_values)
    # o dataset real tem estudantes em cada uma das 3 categorias
    assert (df["progress_badge"] == "Em Ascensão").sum() > 0
    assert (df["progress_badge"] == "Estável").sum() > 0
