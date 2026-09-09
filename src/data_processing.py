"""
Carregamento, limpeza e preparação dos dados de desempenho académico.
"""
from __future__ import annotations

# numpy: usado para gerar sequências numéricas (ex.: os student_id).
import numpy as np
# pandas: para trabalhar com os dados como tabela (DataFrame).
import pandas as pd

from src import config


def load_raw_data(path=None) -> pd.DataFrame:
    """Carrega o ficheiro Excel original com os dados dos estudantes."""
    # Se não for indicado um caminho específico, usa o caminho definido em config.py.
    path = path or config.DATA_RAW_PATH
    df = pd.read_excel(path)
    return df


def load_added_students() -> pd.DataFrame:
    """
    Estudantes adicionados manualmente através da página 'Adicionar Dados',
    persistidos na base de dados (tabela Students_Added). Devolve um
    DataFrame vazio se ainda não existir nenhum.
    """
    from src import database  # import tardio: evita import circular

    table_name = "Students_Added"
    # Só tenta ler a tabela se ela já existir (evita erro na primeira execução,
    # antes de qualquer estudante ter sido adicionado).
    if database.table_exists(table_name):
        return database.read_table(table_name)
    return pd.DataFrame()


def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    """Limpeza básica: remove duplicados, normaliza tipos, valida intervalos."""
    # Copia o DataFrame para não alterar o original por engano (boa prática do pandas).
    df = df.copy()

    # Remover duplicados exatos
    df = df.drop_duplicates()

    # Garantir tipos numéricos corretos
    int_cols = [
        "age", "Medu", "Fedu", "traveltime", "studytime", "failures",
        "famrel", "freetime", "goout", "Dalc", "Walc", "health",
        "absences", "G1", "G2", "G3",
    ]
    for col in int_cols:
        if col in df.columns:
            # Converte para número; valores que não conseguem ser convertidos
            # (texto inválido, por exemplo) tornam-se NaN em vez de dar erro.
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Remover linhas sem nota final (não é possível treinar sem alvo)
    df = df.dropna(subset=["G3"])

    # Validar intervalo das notas (0-20, escala portuguesa)
    for col in ["G1", "G2", "G3"]:
        df = df[(df[col] >= 0) & (df[col] <= 20)]

    # Preencher eventuais nulos residuais em numéricas com a mediana
    numeric_cols = df.select_dtypes(include="number").columns
    df[numeric_cols] = df[numeric_cols].fillna(df[numeric_cols].median())

    # Preencher nulos em categóricas com a moda
    categorical_cols = df.select_dtypes(include="object").columns
    for col in categorical_cols:
        if df[col].isnull().any():
            df[col] = df[col].fillna(df[col].mode()[0])

    # Reindexa as linhas de 0 em diante, depois de terem sido removidas
    # algumas (duplicados, notas inválidas) — evita "buracos" nos índices.
    df = df.reset_index(drop=True)
    return df


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """Cria variáveis derivadas úteis para análise e modelação."""
    df = df.copy()

    # Alvo de classificação: aprovado se G3 >= 10
    df[config.TARGET_CLASSIFICATION] = (df["G3"] >= config.PASS_THRESHOLD).astype(int)

    # Consumo médio de álcool (dia útil + fim de semana) — pondera 5 dias
    # úteis e 2 dias de fim de semana, dividido pelos 7 dias da semana.
    df["alcohol_avg"] = (df["Dalc"] * 5 + df["Walc"] * 2) / 7

    # Escolaridade média dos pais
    df["parent_edu_avg"] = (df["Medu"] + df["Fedu"]) / 2

    # Evolução da nota entre períodos
    df["grade_trend"] = df["G3"] - df["G1"]

    # Selo de progresso: direção da evolução ao longo dos 3 períodos
    # (G1 -> G2 -> G3), não só a diferença entre o primeiro e o último (isso
    # já existe em grade_trend, acima) — "Em Ascensão" exige as duas
    # transições a subir, "Queda a Vigiar" exige as duas a descer; qualquer
    # outro padrão (oscila, estagna) fica "Estável".
    step1 = df["G2"] - df["G1"]
    step2 = df["G3"] - df["G2"]
    # Valor por omissão: "Estável", só é substituído nas linhas que
    # correspondem claramente a uma subida ou descida consistente.
    df["progress_badge"] = "Estável"
    df.loc[(step1 > 0) & (step2 > 0), "progress_badge"] = "Em Ascensão"
    df.loc[(step1 < 0) & (step2 < 0), "progress_badge"] = "Queda a Vigiar"

    # Estudante em risco: critério amplo, usado nos avisos/alertas e na
    # segmentação (nota final baixa, OU já reprovou antes, OU faltas excessivas)
    df["at_risk"] = (
        (df["G3"] < config.PASS_THRESHOLD) | (df["failures"] >= 1) | (df["absences"] > 15)
    ).astype(int)

    # Nível de desempenho, por faixas da nota final (usado no explorador de dados)
    df["perf_band"] = pd.cut(
        df["G3"],
        bins=[-0.1, 9.99, 13.99, 16.99, 20],
        labels=["Insuficiente", "Suficiente", "Bom", "Excelente"],
    ).astype(str)

    return df


def treat_outliers(df: pd.DataFrame, cols: list[str] | None = None, factor: float = 1.5) -> pd.DataFrame:
    """
    Trata outliers pelo método do intervalo interquartil (IQR):
    valores fora de [Q1 - factor*IQR, Q3 + factor*IQR] são "capados" (winsorização)
    em vez de removidos, para não perder estudantes válidos. É também criada uma
    coluna `<col>_is_outlier` a assinalar os casos afetados, para transparência.
    """
    df = df.copy()
    # Colunas verificadas por omissão, se não for indicada uma lista específica.
    cols = cols or ["absences", "age", "G1", "G2", "G3"]

    for col in cols:
        if col not in df.columns:
            continue
        # Q1 (percentil 25) e Q3 (percentil 75) — os limites da "caixa" do boxplot.
        q1, q3 = df[col].quantile(0.25), df[col].quantile(0.75)
        # IQR: intervalo interquartil, a "largura" da distribuição central dos dados.
        iqr = q3 - q1
        # Limites inferior e superior: fora destes valores, é considerado outlier.
        lower, upper = q1 - factor * iqr, q3 + factor * iqr

        # Marca quais as linhas fora dos limites, antes de as alterar.
        is_outlier = (df[col] < lower) | (df[col] > upper)
        df[f"{col}_is_outlier"] = is_outlier.astype(int)
        # "Capa" os valores fora do intervalo, trazendo-os para o limite mais
        # próximo (winsorização), em vez de os remover — mantém o estudante no dataset.
        df[col] = df[col].clip(lower=lower, upper=upper)

    return df


def normalize_columns(df: pd.DataFrame, cols: list[str] | None = None) -> pd.DataFrame:
    """
    Cria versões normalizadas (z-score: média 0, desvio-padrão 1) das principais
    variáveis numéricas, guardadas em colunas `<col>_norm`. As colunas originais
    são mantidas (a normalização é usada para comparação/visualização; os modelos
    de ML fazem a sua própria normalização internamente).
    """
    df = df.copy()
    cols = cols or ["studytime", "absences", "failures", "goout", "Dalc", "Walc", "G3"]

    for col in cols:
        if col not in df.columns:
            continue
        std = df[col].std()
        if std == 0 or pd.isna(std):
            # Sem variação nos dados (todos os valores iguais) — normalizar
            # daria divisão por zero, por isso fica tudo a 0.
            df[f"{col}_norm"] = 0.0
        else:
            # Fórmula do z-score: (valor - média) / desvio-padrão.
            df[f"{col}_norm"] = (df[col] - df[col].mean()) / std

    return df


def get_processed_data(path=None, include_added: bool = True) -> pd.DataFrame:
    """
    Pipeline completo: carregar -> juntar estudantes adicionados manualmente
    -> limpar -> tratar outliers -> enriquecer -> normalizar.
    """
    # Carrega os dados originais do Excel.
    df = load_raw_data(path)

    if include_added:
        # Junta os estudantes adicionados manualmente (se houver algum).
        added = load_added_students()
        if not added.empty:
            # Só junta as colunas que existem nos dois DataFrames, para não
            # rebentar caso os estudantes adicionados tenham colunas extra
            # (como nome/disciplina/ano) que não existem nos dados originais.
            common_cols = [c for c in df.columns if c in added.columns]
            df = pd.concat([df[common_cols], added[common_cols]], ignore_index=True)

    # Aplica todo o pipeline de limpeza e enriquecimento, passo a passo.
    df = clean_data(df)
    df = treat_outliers(df)
    df = add_features(df)
    df = normalize_columns(df)
    # Atribui um identificador único e sequencial a cada estudante, já no fim
    # do processamento (depois de possíveis remoções de duplicados/inválidos).
    df.insert(0, "student_id", np.arange(1, len(df) + 1))
    return df


# Permite correr "python -m src.data_processing" para testar rapidamente o
# pipeline de processamento a partir da linha de comandos.
if __name__ == "__main__":
    data = get_processed_data()
    print(f"Dataset processado: {data.shape[0]} linhas, {data.shape[1]} colunas")
    print(data.head())
