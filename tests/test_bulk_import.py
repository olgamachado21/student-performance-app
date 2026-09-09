"""Testes para src/bulk_import.py — importação em lote de estudantes via CSV."""
import os

# Base de dados SQLite isolada em /tmp, para estes testes não afetarem os
# dados reais nem interferirem com outros ficheiros de teste.
os.environ.setdefault("SQLITE_DB_PATH", "/tmp/test_bulk_import.db")

import pandas as pd
import pytest

from src import database
from src.add_student import ADDED_STUDENTS_TABLE
from src.bulk_import import add_students_bulk, parse_csv
from src.data_processing import load_added_students


@pytest.fixture(autouse=True)
def _clean_added_students_table():
    """Garante que cada teste começa sem estudantes adicionados anteriormente."""
    try:
        database.write_table(pd.DataFrame(), ADDED_STUDENTS_TABLE, if_exists="replace")
    except Exception:
        pass
    yield


def _csv_bytes(text: str) -> bytes:
    # Helper para converter texto CSV em bytes, como o endpoint de upload recebe.
    return text.encode("utf-8")


def test_parse_csv_comma_separated():
    # CSV separado por vírgulas deve ser lido corretamente, coluna a coluna.
    csv_text = "school,sex,age\nGP,F,17\nMS,M,18\n"
    df = parse_csv(_csv_bytes(csv_text))
    assert list(df.columns) == ["school", "sex", "age"]
    assert len(df) == 2


def test_parse_csv_semicolon_separated():
    # CSV separado por ponto-e-vírgula (comum em Excel PT) também deve funcionar.
    csv_text = "school;sex;age\nGP;F;17\n"
    df = parse_csv(_csv_bytes(csv_text))
    assert list(df.columns) == ["school", "sex", "age"]
    assert len(df) == 1


def test_parse_csv_invalid_content_raises_value_error():
    # Bytes que não sejam CSV/texto válido devem levantar ValueError, não rebentar.
    with pytest.raises(ValueError):
        parse_csv(b"\xff\xfe\x00\x01not valid utf8 csv \xff")


def test_add_students_bulk_valid_rows():
    # Duas linhas válidas devem ser todas adicionadas, sem nenhum erro.
    csv_text = (
        "school,sex,age,studytime,absences,failures,G1,G2\n"
        "GP,F,17,3,2,0,14,15\n"
        "MS,M,18,2,5,1,10,11\n"
    )
    result = add_students_bulk(_csv_bytes(csv_text))
    assert result["added_count"] == 2
    assert result["error_count"] == 0
    assert result["errors"] == []
    assert result["total_added_so_far"] == 2

    stored = load_added_students()
    assert len(stored) == 2
    assert set(stored["school"]) == {"GP", "MS"}


def test_add_students_bulk_writes_table_once_not_per_row():
    """A tabela deve ser escrita uma única vez no fim, não uma vez por linha."""
    csv_text = "school,sex,age\nGP,F,17\nMS,M,18\nGP,F,16\n"
    original_write_table = database.write_table
    call_count = {"n": 0}

    def counting_write_table(*args, **kwargs):
        # Wrapper que conta quantas vezes write_table é chamado, para
        # verificar que a escrita é feita em lote (uma vez) e não por linha.
        call_count["n"] += 1
        return original_write_table(*args, **kwargs)

    import src.bulk_import as bulk_import_module
    bulk_import_module.database.write_table = counting_write_table
    try:
        add_students_bulk(_csv_bytes(csv_text))
    finally:
        # Repõe a função original, mesmo que o teste falhe, para não afetar outros testes.
        bulk_import_module.database.write_table = original_write_table

    assert call_count["n"] == 1


def test_add_students_bulk_mixed_valid_and_invalid_rows():
    # Mistura de linhas válidas e inválidas: só as válidas devem ser
    # adicionadas, e cada erro deve reportar o número da linha correta.
    csv_text = (
        "school,sex,age,G1,G2\n"
        "GP,F,17,14,15\n"          # válida
        "XX,F,17,14,15\n"          # school inválida
        "GP,F,99,14,15\n"          # age fora do intervalo
        "GP,F,17,abc,15\n"         # G1 não numérico
    )
    result = add_students_bulk(_csv_bytes(csv_text))
    assert result["added_count"] == 1
    assert result["error_count"] == 3
    lines_with_errors = {e["line"] for e in result["errors"]}
    assert lines_with_errors == {3, 4, 5}


def test_add_students_bulk_applies_defaults_for_missing_columns():
    # Colunas em falta no CSV devem ser preenchidas automaticamente com valores por omissão.
    csv_text = "school,sex\nGP,F\n"
    result = add_students_bulk(_csv_bytes(csv_text))
    assert result["added_count"] == 1
    stored = load_added_students()
    assert len(stored) == 1
    # age/studytime/etc. não foram fornecidos mas devem ter sido preenchidos
    row = stored.iloc[0]
    assert pd.notna(row["age"])
    assert pd.notna(row["G3"])


def test_add_students_bulk_no_row_limit():
    # Não há limite de linhas: um CSV bem maior do que o antigo limite (500)
    # deve ser processado por inteiro, sem ser rejeitado.
    header = "school,sex,age\n"
    n_rows = 1500
    rows = "\n".join("GP,F,17" for _ in range(n_rows))
    csv_text = header + rows + "\n"
    result = add_students_bulk(_csv_bytes(csv_text))
    assert result["added_count"] == n_rows


def test_add_students_bulk_all_rows_invalid_adds_nothing():
    # Se todas as linhas forem inválidas, nada deve ser adicionado à base de dados.
    csv_text = "school,sex,age\nXX,Q,999\n"
    result = add_students_bulk(_csv_bytes(csv_text))
    assert result["added_count"] == 0
    assert result["error_count"] == 1
    assert result["total_added_so_far"] == 0


def test_add_students_bulk_extra_metadata_columns_preserved():
    # Colunas extra que não fazem parte do modelo (ex.: nome, disciplina) devem
    # ser preservadas tal como vieram no CSV.
    csv_text = "school,sex,age,nome,disciplina,ano\nGP,F,17,Ana Silva,Matematica,10\n"
    result = add_students_bulk(_csv_bytes(csv_text))
    assert result["added_count"] == 1
    stored = load_added_students()
    assert stored.iloc[0]["nome"] == "Ana Silva"
    assert stored.iloc[0]["disciplina"] == "Matematica"
    assert stored.iloc[0]["ano"] == "10"


def test_add_students_bulk_appends_to_existing_students():
    # Uma segunda importação deve somar-se à primeira, não substituí-la.
    csv_text_1 = "school,sex,age\nGP,F,17\n"
    add_students_bulk(_csv_bytes(csv_text_1))
    csv_text_2 = "school,sex,age\nMS,M,18\n"
    result = add_students_bulk(_csv_bytes(csv_text_2))
    assert result["total_added_so_far"] == 2
    stored = load_added_students()
    assert len(stored) == 2
