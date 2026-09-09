# Testes para radar_profile em src/segmentation.py — gráfico radar do Perfil do Estudante.
from src.data_processing import get_processed_data
from src.segmentation import RADAR_FEATURES, radar_profile


def test_radar_profile_structure():
    # Verifica que todas as listas devolvidas têm o tamanho certo (uma entrada por variável do radar).
    df = get_processed_data()
    mask = df["sex"] == "F"
    result = radar_profile(df, mask)

    assert result["features"] == RADAR_FEATURES
    assert len(result["labels"]) == len(RADAR_FEATURES)
    assert len(result["subgroup_values"]) == len(RADAR_FEATURES)
    assert len(result["overall_values"]) == len(RADAR_FEATURES)
    assert result["n_subgroup"] == int(mask.sum())


def test_radar_profile_values_within_0_100_range():
    # A normalização min-max deve manter todos os valores dentro da escala 0-100.
    df = get_processed_data()
    mask = df["studytime"] >= 1  # todo o dataset
    result = radar_profile(df, mask)

    for value in result["subgroup_values"] + result["overall_values"]:
        assert 0 <= value <= 100


def test_radar_profile_full_subgroup_matches_overall():
    # Se o subgrupo for igual ao dataset completo, os dois conjuntos de valores devem coincidir.
    df = get_processed_data()
    mask = df["studytime"] >= 1  # subgrupo == dataset completo
    result = radar_profile(df, mask)
    assert result["subgroup_values"] == result["overall_values"]


def test_radar_profile_empty_subgroup_returns_zeros_without_crashing():
    # Um filtro sem nenhum estudante correspondente não deve rebentar, e deve devolver zeros.
    df = get_processed_data()
    mask = df["age"] > 999  # nenhum estudante corresponde
    result = radar_profile(df, mask)
    assert result["n_subgroup"] == 0
    assert result["subgroup_values"] == [0.0] * len(RADAR_FEATURES)
