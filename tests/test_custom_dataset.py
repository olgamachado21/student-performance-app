"""Testes para src/custom_dataset.py e os endpoints /custom-dataset/* — a área
de "Dataset Personalizado", que é genuinamente independente: aceita QUALQUER
ficheiro do utilizador (dados de estudantes ou não), importa-o tal como está
(sem exigir mapear colunas para o esquema da StudentPerfomance), e permite calcular
estatísticas, fórmulas personalizadas e treinar um modelo genérico (o
utilizador escolhe a coluna-alvo e as colunas-recurso) sobre ele. Previsões
(que reaproveitam o modelo principal da StudentPerfomance) só ficam disponíveis quando
o ficheiro tem colunas suficientes parecidas com as de estudantes, detetadas
automaticamente."""
import io
import os

# Base de dados SQLite isolada em /tmp, para estes testes não afetarem os
# dados reais nem interferirem com outros ficheiros de teste.
os.environ.setdefault("SQLITE_DB_PATH", "/tmp/test_custom_dataset.db")

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src import custom_dataset as cd
from src import database
from src.api import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_state():
    """Garante que cada teste começa sem dataset personalizado importado."""
    cd.delete_dataset()
    yield
    cd.delete_dataset()


def _csv_bytes(rows: list[dict]) -> bytes:
    """Constrói um CSV em bytes a partir de uma lista de dicionários (uma linha por dicionário)."""
    df = pd.DataFrame(rows)
    return df.to_csv(index=False).encode("utf-8")


def _student_like_rows(n: int = 40, with_g3: bool = True) -> list[dict]:
    """Dataset sintético com nomes de colunas IGUAIS aos usados internamente
    pela StudentPerfomance — para testar a deteção automática de campos e as Previsões."""
    rows = []
    for i in range(n):
        row = {
            "studytime": (i % 4) + 1,
            "absences": i % 21,
            "sex": "F" if i % 2 == 0 else "M",
            "age": 15 + (i % 6),
        }
        if with_g3:
            row["G3"] = round((i % 20) + 0.5, 1)
        rows.append(row)
    return rows


def _sales_like_rows(n: int = 40) -> list[dict]:
    """Dataset sintético SEM nenhuma coluna parecida com as da StudentPerfomance — para
    testar que a importação/estatísticas/fórmulas funcionam à mesma, mas
    Previsões fica indisponível."""
    rows = []
    for i in range(n):
        rows.append({
            "Order ID": f"ORD-{1000 + i}",
            "Region": ["Norte", "Centro", "Sul"][i % 3],
            "Units Sold": (i % 15) + 1,
            "Unit Price": round(9.99 + (i % 10) * 3.5, 2),
            "Total Sales": round((9.99 + (i % 10) * 3.5) * ((i % 15) + 1), 2),
        })
    return rows


def _upload_and_import(rows: list[dict], filename: str = "dados.csv"):
    csv_bytes = _csv_bytes(rows)
    r = client.post("/custom-dataset/upload", files={"file": (filename, csv_bytes, "text/csv")})
    assert r.status_code == 200, r.text
    return client.post("/custom-dataset/import")


# --- Estado inicial ------------------------------------------------------
def test_status_before_any_import_is_not_imported():
    r = client.get("/custom-dataset/status")
    assert r.status_code == 200
    assert r.json() == {"imported": False}


def test_stats_before_import_returns_404():
    r = client.get("/custom-dataset/stats")
    assert r.status_code == 404


def test_predict_before_import_returns_404():
    r = client.get("/custom-dataset/predict")
    assert r.status_code == 404


def test_train_before_import_returns_400():
    r = client.post("/custom-dataset/train", json={"target_col": "G3", "feature_cols": ["studytime"]})
    assert r.status_code == 400


def test_import_before_upload_returns_400():
    r = client.post("/custom-dataset/import")
    assert r.status_code == 400


# --- Upload -----------------------------------------------------------------
def test_upload_returns_columns_and_preview():
    csv_bytes = _csv_bytes(_student_like_rows(10))
    r = client.post("/custom-dataset/upload", files={"file": ("dados.csv", csv_bytes, "text/csv")})
    assert r.status_code == 200
    data = r.json()
    assert data["n_rows"] == 10
    assert "studytime" in data["columns"]
    assert len(data["preview"]) <= 8


def test_staged_available_after_upload_and_gone_after_import():
    csv_bytes = _csv_bytes(_student_like_rows(40))
    client.post("/custom-dataset/upload", files={"file": ("dados.csv", csv_bytes, "text/csv")})
    r = client.get("/custom-dataset/staged")
    assert r.status_code == 200

    r = client.post("/custom-dataset/import")
    assert r.status_code == 200

    r = client.get("/custom-dataset/staged")
    assert r.status_code == 404


def test_upload_empty_file_returns_400():
    r = client.post("/custom-dataset/upload", files={"file": ("vazio.csv", b"", "text/csv")})
    assert r.status_code == 400


def test_upload_no_row_limit():
    # Não há limite de linhas: um ficheiro bem maior do que o antigo limite
    # (2000) deve ser aceite sem ser rejeitado.
    header = "a,b\n"
    n_rows = 5000
    body = "\n".join("1,2" for _ in range(n_rows))
    csv_bytes = (header + body).encode("utf-8")
    r = client.post("/custom-dataset/upload", files={"file": ("grande.csv", csv_bytes, "text/csv")})
    assert r.status_code == 200
    assert r.json()["n_rows"] == n_rows


def test_import_too_few_rows_returns_400():
    csv_bytes = _csv_bytes(_student_like_rows(2))
    client.post("/custom-dataset/upload", files={"file": ("dados.csv", csv_bytes, "text/csv")})
    r = client.post("/custom-dataset/import")
    assert r.status_code == 400


# --- Importação genérica (sem mapeamento) — dataset parecido com estudantes --
def test_import_student_like_dataset_keeps_original_column_names():
    r = _upload_and_import(_student_like_rows(40))
    assert r.status_code == 200
    data = r.json()
    assert data["imported"] is True
    assert data["n_rows"] == 40
    # As colunas ficam tal como vieram do ficheiro (aqui já coincidem com os
    # nomes da StudentPerfomance, porque o dataset de teste foi construído assim).
    assert set(data["columns"]) == {"studytime", "absences", "sex", "age", "G3"}
    assert set(data["detected_student_fields"].values()) == {"studytime", "absences", "sex", "age", "G3"}
    assert data["can_predict"] is True
    assert data["can_train"] is True

    status = client.get("/custom-dataset/status").json()
    assert status == data


def test_second_import_replaces_first():
    _upload_and_import(_student_like_rows(40))
    r = _upload_and_import(_student_like_rows(50))
    assert r.status_code == 200
    assert r.json()["n_rows"] == 50
    status = client.get("/custom-dataset/status").json()
    assert status["n_rows"] == 50


# --- Importação genérica — dataset sem qualquer semelhança com estudantes ---
def test_import_sales_like_dataset_succeeds_without_mapping():
    r = _upload_and_import(_sales_like_rows(40))
    assert r.status_code == 200
    data = r.json()
    assert data["imported"] is True
    assert data["n_rows"] == 40
    assert set(data["columns"]) == {"Order ID", "Region", "Units Sold", "Unit Price", "Total Sales"}
    # Nenhuma coluna parecida com as da StudentPerfomance -> sem previsões, mas o resto funciona.
    assert data["detected_student_fields"] == {}
    assert data["can_predict"] is False
    # Treinar continua disponível (genérico): há linhas e colunas suficientes.
    assert data["can_train"] is True


def test_stats_work_on_sales_like_dataset():
    _upload_and_import(_sales_like_rows(40))
    r = client.get("/custom-dataset/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["n_rows"] == 40
    assert data["columns"]["Total Sales"]["type"] == "numeric"
    assert data["columns"]["Region"]["type"] == "categorical"
    assert set(data["columns"]["Region"]["counts"].keys()) <= {"Norte", "Centro", "Sul"}
    # Sem G3 detetado, não há os indicadores de notas.
    assert "average_grade" not in data


def test_predict_on_sales_like_dataset_returns_404():
    _upload_and_import(_sales_like_rows(40))
    r = client.get("/custom-dataset/predict")
    assert r.status_code == 404


def test_formula_works_on_sales_like_dataset_with_column_without_spaces():
    _upload_and_import(_sales_like_rows(40))
    # "Region" é a única coluna deste dataset sem espaços no nome — as
    # restantes ("Units Sold", "Total Sales", ...) não são identificadores
    # Python válidos e por isso não podem ser referenciadas diretamente numa
    # fórmula (ver teste seguinte para essa limitação a dar um erro claro).
    r = client.post("/custom-dataset/formula", json={"formula": "contar(Region)"})
    assert r.status_code == 200
    assert r.json()["result"] == 40


def test_formula_with_column_name_containing_spaces_returns_clear_400():
    _upload_and_import(_sales_like_rows(40))
    r = client.post("/custom-dataset/formula", json={"formula": "soma(Total Sales)"})
    assert r.status_code == 400


def test_train_generic_regression_on_sales_like_dataset():
    _upload_and_import(_sales_like_rows(60))
    r = client.post("/custom-dataset/train", json={
        "target_col": "Total Sales",
        "feature_cols": ["Units Sold", "Unit Price", "Region"],
    })
    assert r.status_code == 200
    data = r.json()
    assert data["task"] == "regression"
    assert data["regression"]["best_model"]
    assert data["classification"] is None

    metrics = client.get("/custom-dataset/train")
    assert metrics.status_code == 200
    assert metrics.json() == data


def test_train_generic_classification_on_sales_like_dataset():
    _upload_and_import(_sales_like_rows(60))
    r = client.post("/custom-dataset/train", json={
        "target_col": "Region",
        "feature_cols": ["Units Sold", "Unit Price", "Total Sales"],
    })
    assert r.status_code == 200
    data = r.json()
    assert data["task"] == "classification"
    assert data["classification"]["best_model"]
    assert data["regression"] is None


def test_train_unknown_target_col_returns_400():
    _upload_and_import(_sales_like_rows(60))
    r = client.post("/custom-dataset/train", json={
        "target_col": "ColunaQueNaoExiste",
        "feature_cols": ["Units Sold"],
    })
    assert r.status_code == 400


def test_train_unknown_feature_col_is_ignored_not_fatal():
    _upload_and_import(_sales_like_rows(60))
    r = client.post("/custom-dataset/train", json={
        "target_col": "Total Sales",
        "feature_cols": ["Units Sold", "ColunaQueNaoExiste"],
    })
    assert r.status_code == 200


def test_train_no_valid_feature_cols_returns_400():
    _upload_and_import(_sales_like_rows(60))
    r = client.post("/custom-dataset/train", json={
        "target_col": "Total Sales",
        "feature_cols": ["ColunaQueNaoExiste"],
    })
    assert r.status_code == 400


# --- Previsões (dataset parecido com estudantes) -----------------------------
def test_predict_returns_paginated_results():
    _upload_and_import(_student_like_rows(40))
    r = client.get("/custom-dataset/predict?page=1&page_size=10")
    assert r.status_code == 200
    data = r.json()
    assert data["total"] == 40
    assert data["total_pages"] == 4
    assert len(data["predictions"]) == 10
    entry = data["predictions"][0]
    assert 0 <= entry["predicted_grade"] <= 20
    assert 0 <= entry["pass_probability"] <= 1
    assert "actual_grade" in entry  # G3 estava presente no ficheiro


def test_predict_second_page_has_different_rows():
    _upload_and_import(_student_like_rows(40))
    page1 = client.get("/custom-dataset/predict?page=1&page_size=10").json()
    page2 = client.get("/custom-dataset/predict?page=2&page_size=10").json()
    ids1 = {p["row_id"] for p in page1["predictions"]}
    ids2 = {p["row_id"] for p in page2["predictions"]}
    assert ids1.isdisjoint(ids2)


# --- Treino genérico sobre dataset parecido com estudantes -------------------
def test_train_with_enough_rows_returns_regression():
    _upload_and_import(_student_like_rows(60))
    r = client.post("/custom-dataset/train", json={
        "target_col": "G3",
        "feature_cols": ["studytime", "absences", "sex", "age"],
    })
    assert r.status_code == 200
    data = r.json()
    assert data["task"] == "regression"
    assert data["regression"]["best_model"]
    assert set(data["feature_cols"]) == {"studytime", "absences", "sex", "age"}

    status = client.get("/custom-dataset/status").json()
    assert status["has_trained_model"] is True


def test_train_with_too_few_rows_returns_400():
    _upload_and_import(_student_like_rows(20))  # abaixo de MIN_ROWS_FOR_TRAIN (30)
    r = client.post("/custom-dataset/train", json={"target_col": "G3", "feature_cols": ["studytime"]})
    assert r.status_code == 400


def test_train_get_metrics_before_training_returns_404():
    _upload_and_import(_student_like_rows(60))
    r = client.get("/custom-dataset/train")
    assert r.status_code == 404


# --- Apagar -------------------------------------------------------------------
def test_delete_clears_dataset_and_status():
    _upload_and_import(_student_like_rows(40))
    r = client.delete("/custom-dataset")
    assert r.status_code == 200
    assert r.json() == {"deleted": True}

    assert client.get("/custom-dataset/status").json() == {"imported": False}
    assert client.get("/custom-dataset/stats").status_code == 404
    assert client.get("/custom-dataset/predict").status_code == 404
    assert client.post(
        "/custom-dataset/train", json={"target_col": "G3", "feature_cols": ["studytime"]}
    ).status_code == 400


# --- Testes diretos ao módulo (sem passar pela API) --------------------------
def test_detect_studentperfomance_fields_matches_case_and_accent_insensitively():
    detected = cd._detect_studentperfomance_fields(["Studytime", "ABSENCES", "coluna_qualquer", "g3"])
    assert detected == {"Studytime": "studytime", "ABSENCES": "absences", "g3": "G3"}


# --- Sinónimos em português (ativar Previsões sem nomes técnicos ingleses) ---
def test_detect_studentperfomance_fields_matches_portuguese_synonyms():
    detected = cd._detect_studentperfomance_fields(
        ["Idade", "Faltas", "Escola", "3º Período", "Nome", "Cidade"]
    )
    assert detected == {
        "Idade": "age",
        "Faltas": "absences",
        "Escola": "school",
        "3º Período": "G3",
    }
    # "Nome" e "Cidade" não correspondem a nada — continuam de fora.
    assert "Nome" not in detected
    assert "Cidade" not in detected


def test_detect_studentperfomance_fields_ignores_parenthetical_suffix():
    # "Tempo Livre (1-5)" deve continuar a corresponder a "freetime", mesmo
    # com a nota da escala entre parênteses.
    detected = cd._detect_studentperfomance_fields(["Tempo Livre (1-5)", "Relação Familiar (1-5)"])
    assert detected == {"Tempo Livre (1-5)": "freetime", "Relação Familiar (1-5)": "famrel"}


def test_exact_technical_name_takes_priority_over_synonym():
    # Um nome técnico exato nunca deve ser "roubado" por um sinónimo em
    # português com a mesma forma normalizada (não há colisão real na lista
    # atual, mas a prioridade do lookup é testada diretamente).
    lookup = cd._DETECTION_LOOKUP
    assert lookup[cd._normalize_for_detection("age")] == "age"
    assert lookup[cd._normalize_for_detection("Idade")] == "age"


def test_import_portuguese_named_dataset_activates_predictions():
    # Ficheiro com nomes de coluna totalmente em português (nenhum nome
    # técnico inglês) — ainda assim deve detetar campos suficientes para
    # ativar Previsões, graças aos sinónimos em português.
    rows = []
    for i in range(40):
        rows.append({
            "Nome": f"Estudante {i}",
            "Idade": 15 + (i % 6),
            "Sexo": "F" if i % 2 == 0 else "M",
            "Horas de Estudo Semanais": (i % 4) + 1,
            "Faltas": i % 21,
            "3º Período": round((i % 20) + 0.5, 1),
        })
    r = _upload_and_import(rows)
    assert r.status_code == 200
    data = r.json()
    assert data["detected_student_fields"]["Idade"] == "age"
    assert data["detected_student_fields"]["Sexo"] == "sex"
    assert data["detected_student_fields"]["Faltas"] == "absences"
    assert data["detected_student_fields"]["3º Período"] == "G3"
    assert data["detected_student_fields"]["Horas de Estudo Semanais"] == "studytime"
    # "Nome" não corresponde a nenhum campo conhecido — continua de fora.
    assert "Nome" not in data["detected_student_fields"]
    assert data["can_predict"] is True

    pred = client.get("/custom-dataset/predict")
    assert pred.status_code == 200
    assert len(pred.json()["predictions"]) > 0


def test_dedupe_column_names_handles_repeats():
    result = cd._dedupe_column_names(["Total", "Total", "Total", "Regiao"])
    assert result == ["Total", "Total_1", "Total_2", "Regiao"]


def test_infer_column_types_converts_purely_numeric_text_columns():
    df = pd.DataFrame({"nums_as_text": ["1", "2", "3"], "mixed": ["1", "x", "3"]})
    result = cd._infer_column_types(df)
    assert pd.api.types.is_numeric_dtype(result["nums_as_text"])
    assert not pd.api.types.is_numeric_dtype(result["mixed"])


# --- Robustez a erros inesperados (nunca "Erro 500" sem explicação) ---------
# Um utilizador pode carregar um ficheiro genuinamente fora do previsto (ex.:
# uma folha de cálculo de vendas em vez de dados de estudantes, com colunas,
# tipos ou dependências do Excel completamente diferentes) — nesses casos o
# endpoint deve sempre devolver um erro 400 explicativo, nunca um "Erro 500"
# em branco. Estes testes forçam deliberadamente uma exceção que NÃO é um
# ValueError "normal" (ex.: um TypeError vindo de código interno) para
# confirmar que o tratamento genérico de exceções em src/api.py apanha
# mesmo assim o problema.
def test_upload_unexpected_error_returns_400_not_500(monkeypatch):
    def _boom(filename, file_bytes):
        raise TypeError("falha inesperada a processar o ficheiro")

    monkeypatch.setattr(cd, "stage_upload", _boom)
    r = client.post("/custom-dataset/upload", files={"file": ("dados.csv", b"a,b\n1,2\n", "text/csv")})
    assert r.status_code == 400
    assert "dados.csv" in r.json()["detail"]


def test_import_unexpected_error_returns_400_not_500(monkeypatch):
    def _boom():
        raise TypeError("falha inesperada a importar o dataset")

    monkeypatch.setattr(cd, "import_dataset", _boom)
    r = client.post("/custom-dataset/import")
    assert r.status_code == 400
