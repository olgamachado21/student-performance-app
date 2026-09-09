"""Testes para o endpoint POST /custom-dataset/formula — a "camada API" por
cima de src/formula_engine.py, incluindo o caso de ainda não haver dataset
personalizado importado. Ver tests/test_formula_engine.py para os testes
diretos ao avaliador de fórmulas em si.

Desde que a importação do Dataset Personalizado deixou de exigir mapeamento
(ver src/custom_dataset.py), o dataset de teste usa diretamente os nomes de
coluna que o motor de fórmulas vai referenciar — tal como um utilizador real
faria ao escrever uma fórmula sobre o seu próprio ficheiro, sem qualquer
tradução de nomes pelo meio."""
import os

# Base de dados SQLite isolada em /tmp, tal como nos outros testes deste
# módulo — para não interferir com dados reais nem com outros testes.
os.environ.setdefault("SQLITE_DB_PATH", "/tmp/test_custom_dataset_formula.db")

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src import custom_dataset as cd
from src.api import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_state():
    cd.delete_dataset()
    yield
    cd.delete_dataset()


def _csv_bytes(rows: list[dict]) -> bytes:
    return pd.DataFrame(rows).to_csv(index=False).encode("utf-8")


def _sample_rows(n: int = 40) -> list[dict]:
    rows = []
    for i in range(n):
        rows.append({
            "studytime": (i % 4) + 1,
            "absences": i % 21,
            "sex": "F" if i % 2 == 0 else "M",
            "age": 15 + (i % 6),
            "G1": round((i % 18) + 1.0, 1),
            "G2": round((i % 16) + 2.0, 1),
            "G3": round((i % 20) + 0.5, 1),
        })
    return rows


def _import_sample_dataset(n: int = 40):
    csv_bytes = _csv_bytes(_sample_rows(n))
    r = client.post("/custom-dataset/upload", files={"file": ("dados.csv", csv_bytes, "text/csv")})
    assert r.status_code == 200, r.text
    r = client.post("/custom-dataset/import")
    assert r.status_code == 200, r.text
    return r.json()


def test_formula_before_import_returns_400():
    r = client.post("/custom-dataset/formula", json={"formula": "media(G3)"})
    assert r.status_code == 400


def test_formula_weighted_average_returns_column():
    _import_sample_dataset()
    r = client.post("/custom-dataset/formula", json={"formula": "G1*0.3 + G2*0.3 + G3*0.4"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["type"] == "column"
    assert data["n_rows"] == 40
    assert len(data["rows"]) > 0


def test_formula_aggregate_returns_scalar():
    _import_sample_dataset()
    r = client.post("/custom-dataset/formula", json={"formula": "media(G3)"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["type"] == "scalar"
    assert isinstance(data["result"], float)


def test_formula_with_where_clause():
    _import_sample_dataset()
    r = client.post("/custom-dataset/formula", json={"formula": "media(G3) onde studytime >= 3"})
    assert r.status_code == 200, r.text
    assert r.json()["type"] == "scalar"


def test_formula_pagination_query_params():
    _import_sample_dataset()
    r = client.post("/custom-dataset/formula?page=2&page_size=5", json={"formula": "G3 * 2"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["page"] == 2
    assert len(data["rows"]) == 5


def test_formula_unknown_column_returns_400_with_message():
    _import_sample_dataset()
    r = client.post("/custom-dataset/formula", json={"formula": "coluna_inexistente * 2"})
    assert r.status_code == 400
    assert "desconhecida" in r.json()["detail"]
    assert "coluna_inexistente" in r.json()["detail"]


def test_formula_malicious_input_returns_400_not_500():
    _import_sample_dataset()
    r = client.post("/custom-dataset/formula", json={"formula": "__import__('os').system('id')"})
    assert r.status_code == 400


def test_formula_empty_string_returns_400():
    _import_sample_dataset()
    r = client.post("/custom-dataset/formula", json={"formula": ""})
    assert r.status_code == 400


def test_formula_works_on_dataset_without_any_studentperfomance_like_columns():
    """Confirma que as fórmulas funcionam mesmo quando o dataset não tem
    NENHUMA coluna parecida com as da StudentPerfomance — é exatamente esse o cenário
    que motivou tornar a importação genérica (ex.: um ficheiro de vendas)."""
    rows = [{"Categoria": ["A", "B", "C"][i % 3], "Valor": (i % 10) + 1.5} for i in range(40)]
    csv_bytes = _csv_bytes(rows)
    r = client.post("/custom-dataset/upload", files={"file": ("vendas.csv", csv_bytes, "text/csv")})
    assert r.status_code == 200, r.text
    r = client.post("/custom-dataset/import")
    assert r.status_code == 200, r.text

    r = client.post("/custom-dataset/formula", json={"formula": "media(Valor) onde Categoria == 'A'"})
    assert r.status_code == 200, r.text
    assert r.json()["type"] == "scalar"
