# Testes para src/segmentation.py — clustering configurável (o utilizador
# pode escolher quais as variáveis usadas para agrupar os estudantes).
import pytest

from src.data_processing import get_processed_data
from src.segmentation import SEGMENTATION_FEATURES, run_segmentation


def test_default_features_used_when_none_given():
    # Sem nenhuma escolha explícita, deve usar o conjunto completo de variáveis por omissão.
    df = get_processed_data()
    result = run_segmentation(df, n_clusters=4)
    assert result["features"] == SEGMENTATION_FEATURES


def test_custom_subset_of_features_is_used():
    # Um subconjunto de variáveis escolhido pelo utilizador deve ser respeitado.
    df = get_processed_data()
    chosen = ["studytime", "absences", "G3"]
    result = run_segmentation(df, n_clusters=4, features=chosen)
    assert result["features"] == chosen
    total_size = sum(g["size"] for g in result["groups"])
    assert total_size == result["n_students"]


def test_rejects_fewer_than_two_features():
    # Uma única variável não é suficiente para fazer clustering com sentido.
    df = get_processed_data()
    with pytest.raises(ValueError):
        run_segmentation(df, n_clusters=4, features=["studytime"])


def test_rejects_empty_feature_list():
    # Uma lista vazia de variáveis deve ser rejeitada.
    df = get_processed_data()
    with pytest.raises(ValueError):
        run_segmentation(df, n_clusters=4, features=[])


def test_rejects_unknown_feature():
    # Uma variável que não faz parte do conjunto permitido (ex.: "age") deve ser rejeitada.
    df = get_processed_data()
    with pytest.raises(ValueError):
        run_segmentation(df, n_clusters=4, features=["studytime", "age"])


def test_different_feature_sets_can_change_grouping():
    # Não garantimos resultados diferentes sempre (podem coincidir por
    # acaso), mas confirmamos que a função de facto usa só as variáveis
    # passadas: com só 2 variáveis muito correlacionadas com a nota,
    # o traço "Perfil Misto" nunca deveria dominar todos os grupos.
    df = get_processed_data()
    result = run_segmentation(df, n_clusters=3, features=["G1", "G3"])
    assert result["features"] == ["G1", "G3"]
    names = [g["name"] for g in result["groups"]]
    assert len(names) == 3


# ----------------------------------------------------------------------------
# Camada da API (src.api.segmentation) — chamada diretamente como função
# Python, tal como já é feito nos outros ficheiros de teste. Note-se que
# "features=None" tem de ser passado explicitamente: se o parâmetro for
# omitido, o valor por omissão visto pela função é o objeto Query(...) do
# FastAPI (não o None resolvido), porque a resolução automática só acontece
# quando o pedido passa mesmo pelo FastAPI/Starlette.
# ----------------------------------------------------------------------------
def test_api_segmentation_default_returns_all_features():
    from src.api import segmentation

    result = segmentation(n_clusters=4, features=None)
    assert result["features"] == SEGMENTATION_FEATURES


def test_api_segmentation_accepts_comma_separated_features():
    # A API deve aceitar uma string com variáveis separadas por vírgula (com espaços tolerados).
    from src.api import segmentation

    result = segmentation(n_clusters=4, features="studytime, absences, G3")
    assert result["features"] == ["studytime", "absences", "G3"]


def test_api_segmentation_400_on_single_feature():
    # A API deve devolver erro 400 quando só é dada uma variável.
    from fastapi import HTTPException
    from src.api import segmentation

    with pytest.raises(HTTPException) as exc_info:
        segmentation(n_clusters=4, features="studytime")
    assert exc_info.value.status_code == 400


def test_api_segmentation_400_on_unknown_feature():
    # A API deve devolver erro 400 quando alguma variável não é reconhecida.
    from fastapi import HTTPException
    from src.api import segmentation

    with pytest.raises(HTTPException) as exc_info:
        segmentation(n_clusters=4, features="age,studytime")
    assert exc_info.value.status_code == 400


def test_api_segmentation_features_endpoint_lists_all():
    # O endpoint que lista as variáveis disponíveis deve devolver o conjunto completo.
    from src.api import segmentation_features

    result = segmentation_features()
    assert result["features"] == SEGMENTATION_FEATURES
