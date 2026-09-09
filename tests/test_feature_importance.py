"""Testes para o endpoint /feature-importance (importância das variáveis no
modelo de classificação aprovado/reprovado) — incluindo a salvaguarda para
quando get_feature_importance não consegue calcular nada (ver src/api.py)."""
from fastapi.testclient import TestClient

from src import api

client = TestClient(api.app)


def test_feature_importance_returns_features_and_importance():
    r = client.get("/feature-importance")
    assert r.status_code == 200
    data = r.json()
    assert len(data["features"]) > 0
    assert len(data["features"]) == len(data["importance"])
    # Nenhum nome de coluna deve manter os prefixos técnicos do pré-processador.
    assert all("num__" not in f and "cat__" not in f for f in data["features"])


def test_feature_importance_returns_404_when_model_has_no_importance(monkeypatch):
    # Simula um modelo sem feature_importances_ nem coef_ (ex.: um algoritmo
    # futuro sem forma conhecida de extrair importância) — get_feature_importance
    # devolve None nesse caso; o endpoint deve responder com um 404 claro, não
    # rebentar com um erro de atributo em None.
    monkeypatch.setattr(api, "get_feature_importance", lambda *a, **k: None)
    r = client.get("/feature-importance")
    assert r.status_code == 404
    assert "importância" in r.json()["detail"].lower()
