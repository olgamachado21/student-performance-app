"""
ETL (Extract, Transform, Load): importa os dados originais para a base de dados
SQL, aplica a limpeza/transformação e grava o resultado numa segunda tabela.

Fluxo:
    Excel (data/raw) --extract--> Students_Raw (BD)
                      --transform (data_processing)--> Students_Clean (BD)
"""
# Permite usar anotações de tipo modernas (como "DataFrame | None") em
# versões do Python que normalmente não as aceitam.
from __future__ import annotations

# pandas: biblioteca para trabalhar com tabelas de dados (DataFrame).
import pandas as pd

# config: caminhos e nomes das tabelas. database: funções de leitura/escrita na BD.
from src import config, database
# Funções de limpeza/transformação usadas na fase "Transform" do ETL.
from src.data_processing import (add_features, clean_data, load_raw_data,
                                  normalize_columns, treat_outliers)


def extract_and_load_raw() -> pd.DataFrame:
    """Lê o Excel original e carrega-o, sem alterações, na tabela Students_Raw."""
    # Fase "Extract": lê o ficheiro Excel original tal como está, sem alterações.
    df = load_raw_data()
    # Copia o DataFrame para não alterar o original por engano.
    df_to_store = df.copy()
    # Insere uma coluna "student_id" no início, numerada de 1 até ao total de
    # linhas — serve como identificador único de cada estudante.
    df_to_store.insert(0, "student_id", range(1, len(df_to_store) + 1))
    # Fase "Load": grava a tabela (ainda sem limpeza) na base de dados.
    database.write_table(df_to_store, config.TABLE_RAW)
    # Mensagem informativa no terminal a confirmar quantos registos foram carregados.
    print(f"[ETL] {len(df_to_store)} registos carregados em '{config.TABLE_RAW}'.")
    return df_to_store


def transform_and_load_clean(raw_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Aplica limpeza, tratamento de outliers e transformação, e grava em Students_Clean."""
    # Se não foi passado um DataFrame já carregado, vai buscar os dados em
    # bruto: primeiro tenta ler da BD (mais rápido), só corre o extract
    # completo se a tabela Students_Raw ainda não existir.
    if raw_df is None:
        if database.table_exists(config.TABLE_RAW):
            raw_df = database.read_table(config.TABLE_RAW)
        else:
            raw_df = extract_and_load_raw()

    # Remove o student_id antes de limpar (é recalculado no fim, para garantir
    # que fica sempre sequencial mesmo que alguma linha seja removida na limpeza).
    df = raw_df.drop(columns=["student_id"], errors="ignore")
    # Fase "Transform", passo a passo:
    df = clean_data(df)        # corrige erros e valores em falta
    df = treat_outliers(df)    # trata valores fora do normal (outliers)
    df = add_features(df)      # cria colunas derivadas (ex.: aprovado, perf_band)
    df = normalize_columns(df)  # normaliza nomes/tipos de colunas
    # Volta a numerar o student_id de forma sequencial, já sobre os dados limpos.
    df.insert(0, "student_id", range(1, len(df) + 1))

    # Fase "Load": grava a versão limpa/transformada na tabela Students_Clean.
    database.write_table(df, config.TABLE_CLEAN)
    print(f"[ETL] {len(df)} registos limpos/transformados carregados em '{config.TABLE_CLEAN}'.")
    return df


def run_etl() -> pd.DataFrame:
    """Corre o pipeline ETL completo e devolve o dataset limpo final."""
    # Mostra no terminal qual o motor de base de dados configurado (sqlite/mssql).
    print(f"[ETL] Motor de base de dados: {config.DB_DRIVER}")
    # Verifica a ligação à BD antes de começar, para dar um erro claro logo
    # no início em vez de falhar a meio do processo.
    if not database.test_connection():
        raise RuntimeError(
            "Não foi possível ligar à base de dados. Verifica as definições em .env "
            "(ver .env.example) — em particular DB_DRIVER e, se usares SQL Server, "
            "se já correste sql/schema.sql no SSMS."
        )
    # Corre as duas fases do pipeline, em sequência.
    raw_df = extract_and_load_raw()
    clean_df = transform_and_load_clean(raw_df)
    return clean_df


# Permite correr "python -m src.etl" diretamente a partir da linha de comandos,
# sem passar pela API — útil para preparar a base de dados antes de arrancar a app.
if __name__ == "__main__":
    run_etl()
