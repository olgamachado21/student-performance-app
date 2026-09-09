# Testes para src/database.py e src/etl.py — usa uma base de dados SQLite
# temporária (em /tmp), separada da base de dados real da aplicação.
import os

# Define o caminho da BD de teste ANTES de importar src.database, para que
# a aplicação use este ficheiro temporário em vez da base de dados real.
os.environ.setdefault("SQLITE_DB_PATH", "/tmp/test_student_performance.db")

import importlib

from src import config, database


def _reset_engine():
    # Força a recriação da ligação à base de dados (limpa a cache), para
    # garantir que cada teste usa a configuração mais recente.
    database._engine = None


def test_get_engine_and_connection():
    # Verifica que é possível estabelecer ligação à base de dados de teste.
    _reset_engine()
    assert database.test_connection() is True


def test_write_and_read_table():
    # Escreve uma tabela simples e volta a lê-la, confirmando que os dados batem certo.
    import pandas as pd
    _reset_engine()
    df = pd.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})
    database.write_table(df, "tmp_test_table")
    assert database.table_exists("tmp_test_table")
    result = database.read_table("tmp_test_table")
    assert len(result) == 3


def test_etl_creates_clean_table():
    # Corre o pipeline ETL completo e confirma que as duas tabelas (raw e clean) ficam criadas.
    from src.etl import run_etl
    _reset_engine()
    clean_df = run_etl()
    assert len(clean_df) > 0
    assert "aprovado" in clean_df.columns
    assert database.table_exists(config.TABLE_RAW)
    assert database.table_exists(config.TABLE_CLEAN)
