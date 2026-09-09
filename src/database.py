"""
Camada de acesso à base de dados.

Suporta dois motores, controlados pela variável de ambiente DB_DRIVER:
  - "sqlite" (omissão): ficheiro local, sem servidor — ideal para desenvolvimento/teste.
  - "mssql": SQL Server, ligado via pyodbc — usar com o SSMS (ver sql/schema.sql
    para criar a base de dados e as tabelas antes de correr a aplicação).

Toda a aplicação lê/escreve dados através das funções deste módulo, pelo que
trocar de motor não implica alterar mais nenhum ficheiro (basta definir DB_DRIVER).
"""
# Permite escrever "Engine | None" como anotação de tipo.
from __future__ import annotations

# pandas: para ler/escrever tabelas como DataFrame.
import pandas as pd
# create_engine: cria a ligação à base de dados. text: permite escrever SQL em texto simples.
from sqlalchemy import create_engine, text
# Engine: tipo usado só para anotações (indicar que uma função devolve uma "ligação").
from sqlalchemy.engine import Engine

from src import config

# Guarda a ligação já criada (cache), para não abrir uma nova ligação a cada
# chamada — começa a None (ainda não foi criada nenhuma).
_engine: Engine | None = None


def get_engine() -> Engine:
    """Cria (uma única vez) e devolve a engine SQLAlchemy configurada."""
    # "global" permite alterar a variável _engine definida fora da função.
    global _engine
    # Se já existe uma ligação criada, reaproveita-a em vez de criar outra.
    if _engine is not None:
        return _engine

    if config.DB_DRIVER == "mssql":
        # Autenticação Windows (igual à usada no SSMS) por omissão.
        if config.MSSQL_TRUSTED_CONNECTION.lower() == "yes":
            # String de ligação sem utilizador/palavra-passe: usa a conta
            # Windows com que o utilizador tem sessão iniciada.
            conn_str = (
                f"mssql+pyodbc://{config.MSSQL_SERVER}/{config.MSSQL_DATABASE}"
                f"?driver={config.MSSQL_DRIVER.replace(' ', '+')}&trusted_connection=yes"
            )
        else:
            # String de ligação com utilizador e palavra-passe explícitos.
            conn_str = (
                f"mssql+pyodbc://{config.MSSQL_USER}:{config.MSSQL_PASSWORD}"
                f"@{config.MSSQL_SERVER}/{config.MSSQL_DATABASE}"
                f"?driver={config.MSSQL_DRIVER.replace(' ', '+')}"
            )
        # fast_executemany=True acelera bastante a escrita de muitas linhas de uma vez.
        _engine = create_engine(conn_str, fast_executemany=True)
    else:
        # Modo SQLite: garante que a pasta onde o ficheiro da BD vai ficar existe.
        config.SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
        # Cria a ligação ao ficheiro SQLite local.
        _engine = create_engine(f"sqlite:///{config.SQLITE_PATH}")

    return _engine


def test_connection() -> bool:
    """Testa a ligação à base de dados. Devolve True/False."""
    try:
        # Abre uma ligação temporária e corre a query mais simples possível
        # ("SELECT 1") só para confirmar que a BD responde.
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        # Qualquer erro (servidor em baixo, credenciais erradas, etc.) é
        # apanhado aqui e reportado, em vez de rebentar a aplicação.
        print(f"[database] Falha na ligação ({config.DB_DRIVER}): {exc}")
        return False


def write_table(df: pd.DataFrame, table_name: str, if_exists: str = "replace"):
    """Escreve um DataFrame numa tabela da base de dados."""
    engine = get_engine()
    # if_exists="replace" (omissão): apaga e recria a tabela com os dados novos.
    # index=False: não grava o índice do pandas como coluna extra.
    df.to_sql(table_name, engine, if_exists=if_exists, index=False)


def read_table(table_name: str) -> pd.DataFrame:
    """Lê uma tabela completa da base de dados para um DataFrame."""
    engine = get_engine()
    return pd.read_sql_table(table_name, engine)


def read_query(sql: str) -> pd.DataFrame:
    """Executa uma query SQL livre e devolve o resultado como DataFrame."""
    engine = get_engine()
    # text(sql) envolve a string SQL para o SQLAlchemy a aceitar como query "crua".
    return pd.read_sql_query(text(sql), engine)


def table_exists(table_name: str) -> bool:
    """Verifica se uma tabela com este nome já existe na base de dados."""
    # Importação feita aqui dentro (e não no topo do ficheiro) só para manter
    # o import perto de onde é usado, já que só esta função precisa dele.
    from sqlalchemy import inspect
    return inspect(get_engine()).has_table(table_name)


def drop_table(table_name: str):
    """
    Remove uma tabela por completo (ao contrário de write_table com
    if_exists="replace", que troca o conteúdo mas continua a exigir que a
    tabela "exista" depois). Não faz nada (nem dá erro) se a tabela já não
    existir — usado para "esquecer" por completo um dataset personalizado
    (ver src/custom_dataset.py), incluindo a sua tabela de metadados.
    """
    if not table_exists(table_name):
        return
    engine = get_engine()
    # Nome entre aspas: protege contra nomes de tabela com espaços/caracteres
    # especiais (não é uma preocupação de segurança aqui, já que os nomes
    # usados na aplicação são sempre constantes fixas no código, nunca
    # escritos diretamente pelo utilizador).
    with engine.begin() as conn:
        conn.execute(text(f'DROP TABLE "{table_name}"'))
