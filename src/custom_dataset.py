"""
Dataset Personalizado: permite ao utilizador carregar QUALQUER ficheiro seu
(CSV ou Excel) — dados de estudantes ou não — e calcular estatísticas
descritivas e fórmulas personalizadas sobre ele, treinar um modelo de
Machine Learning genérico (escolhendo a própria coluna-alvo e as
colunas-recurso) e, se o ficheiro tiver colunas parecidas com as da StudentPerfomance
(idade, sexo, tempo de estudo, faltas, etc.), também gerar Previsões
reaproveitando o modelo principal já treinado.

Tudo isto vive numa área completamente separada do dataset e dos modelos
principais da app — fica guardado em tabelas próprias da base de dados
(RAW_TABLE / META_TABLE) e, se for treinado um modelo, em ficheiros próprios
(models/custom/), nunca substituindo os ficheiros principais. Importar,
treinar ou apagar o dataset personalizado nunca afeta o resto da aplicação.

Ao contrário da primeira versão desta funcionalidade, aqui NÃO se exige ao
utilizador que associe as colunas do seu ficheiro a um esquema fixo — um
dataset de vendas, de RH, ou de qualquer outra coisa é importado tal como
está, com os nomes de coluna originais. As colunas parecidas com as da
StudentPerfomance são detetadas automaticamente (ver _detect_studentperfomance_fields), só para
decidir se a página de Previsões faz sentido para este dataset em concreto —
nunca é um passo obrigatório nem impede a importação.
"""
from __future__ import annotations

# io: para ler o ficheiro carregado (bytes) como se fosse um ficheiro em disco.
import io
# json: para guardar os metadados e as métricas de treino em texto.
import json
# re: para normalizar nomes de coluna na deteção automática (ver _normalize_for_detection).
import re

# joblib: para gravar o modelo treinado neste dataset em ficheiro.
import joblib
# numpy: para gerar os row_id sequenciais e cálculos numéricos.
import numpy as np
# pandas: para trabalhar com o dataset carregado como tabela.
import pandas as pd
# Modelos candidatos: os mesmos géneros usados no treino principal (ver train_model.py),
# mas com menos candidatos e árvores mais pequenas — datasets personalizados
# tendem a ser mais pequenos do que o dataset principal (649 estudantes).
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (accuracy_score, f1_score, mean_absolute_error,
                            precision_score, r2_score, recall_score,
                            roc_auc_score, root_mean_squared_error)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer

from src import config, database, formula_engine
# Reaproveita o modelo principal já treinado para gerar previsões sobre o
# dataset personalizado (ver compute_predictions), quando o dataset tiver
# colunas suficientes parecidas com as da StudentPerfomance — campos não detetados são
# preenchidos com os valores típicos do dataset principal, tal como acontece
# em qualquer previsão manual no Simulador.
from src.predict import full_prediction

# --- Persistência -------------------------------------------------------
# Nome da tabela com os dados importados (já limpos/tipados, mas com os
# nomes de coluna ORIGINAIS do ficheiro do utilizador).
RAW_TABLE = "Custom_Dataset"
# Nome da tabela (uma só linha) com metadados: nome do ficheiro, nº de
# linhas, colunas, campos da StudentPerfomance detetados automaticamente, data de importação.
META_TABLE = "Custom_Dataset_Meta"

# Pasta própria para os modelos treinados sobre datasets personalizados —
# nunca a mesma pasta dos modelos principais (config.MODELS_DIR diretamente),
# para nunca haver risco de um treino personalizado sobrescrever sem querer
# o modelo usado pelo resto da aplicação.
CUSTOM_MODELS_DIR = config.MODELS_DIR / "custom"
CUSTOM_MODELS_DIR.mkdir(parents=True, exist_ok=True)
# Métricas do último modelo personalizado treinado, em ficheiro próprio
# (nunca reports/model_metrics.json, que é o dos modelos principais).
CUSTOM_METRICS_PATH = config.REPORTS_DIR / "custom_model_metrics.json"

# --- Limites -------------------------------------------------------------
# Sem limite de linhas no upload — um ficheiro é sempre aceite, seja qual for
# o seu tamanho. Os limiares abaixo não restringem a IMPORTAÇÃO em si; só
# decidem quando as estatísticas/o treino seriam pouco fiáveis com muito
# poucos dados (o dataset continua sempre importado e visível de qualquer forma).
MIN_ROWS_FOR_STATS = 5       # abaixo disto, as estatísticas não seriam fiáveis
MIN_ROWS_FOR_TRAIN = 30      # treinar com menos do que isto dá modelos pouco fiáveis
MIN_CLASS_COUNT_FOR_TRAIN = 5  # cada categoria da coluna-alvo (se for classificação) precisa de pelo menos isto

# Ficheiro carregado mas ainda não confirmado ("em espera") — vive só em
# memória (não em disco/BD), porque é um passo transitório: ou o utilizador
# confirma a importação a seguir (e passa a ficar em RAW_TABLE), ou desiste e
# o upload é esquecido. Um dicionário simples chega perfeitamente bem, já que
# a StudentPerfomance corre como um único processo por utilizador (local ou desktop),
# sem vários pedidos em simultâneo a disputar este estado.
_staged: dict = {}


# --- Leitura do ficheiro ---------------------------------------------------
def parse_uploaded_file(filename: str, file_bytes: bytes) -> pd.DataFrame:
    """
    Lê um ficheiro CSV ou Excel (.xlsx/.xls) cru, tal como foi carregado —
    sem qualquer limpeza ainda. Deteta o formato pela extensão do nome do
    ficheiro.
    """
    name = (filename or "").lower()
    if name.endswith((".xlsx", ".xls")):
        try:
            df = pd.read_excel(io.BytesIO(file_bytes))
        except Exception as exc:
            raise ValueError(f"Não foi possível ler o ficheiro Excel: {exc}") from exc
    else:
        # Por omissão assume-se CSV (mesmo que a extensão não seja ".csv") —
        # mais tolerante do que recusar logo ficheiros com extensão em falta.
        try:
            text = file_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError(f"Não foi possível ler o ficheiro como texto (UTF-8): {exc}") from exc
        try:
            # sep=None + engine="python": deteta automaticamente o separador
            # (vírgula ou ponto-e-vírgula), tal como em bulk_import.py.
            df = pd.read_csv(io.StringIO(text), sep=None, engine="python")
        except Exception as exc:
            raise ValueError(f"Não foi possível interpretar o ficheiro como CSV: {exc}") from exc

    # Remove espaços a mais à volta dos nomes das colunas.
    df.columns = [str(c).strip() for c in df.columns]
    if df.empty or len(df.columns) == 0:
        raise ValueError("O ficheiro está vazio ou não tem colunas reconhecíveis.")
    # Sem limite de linhas: o ficheiro é sempre aceite por inteiro, seja qual for o seu tamanho.
    return df


def _preview(df: pd.DataFrame, filename: str | None) -> dict:
    """Resumo do ficheiro em espera: colunas, nº de linhas, e as primeiras linhas como texto."""
    return {
        "filename": filename or "",
        "columns": list(df.columns),
        "n_rows": int(len(df)),
        # astype(str) evita problemas de serialização JSON com tipos do numpy/pandas.
        "preview": df.head(8).astype(str).to_dict(orient="records"),
    }


def stage_upload(filename: str, file_bytes: bytes) -> dict:
    """Lê e guarda em memória um ficheiro acabado de carregar, pronto a ser importado."""
    df = parse_uploaded_file(filename, file_bytes)
    _staged["filename"] = filename
    _staged["df"] = df
    return _preview(df, filename)


def get_staged_upload() -> dict | None:
    """Devolve o resumo do ficheiro em espera, ou None se nenhum tiver sido carregado ainda."""
    if "df" not in _staged:
        return None
    return _preview(_staged["df"], _staged.get("filename"))


# --- Deteção automática de colunas parecidas com as da StudentPerfomance --------------
# Usada só para decidir se a página de Previsões faz sentido para este
# dataset em concreto — nunca é pedida ao utilizador, nem impede nada. A
# comparação de nomes é insensível a maiúsculas/acentos/pontuação (ver
# _normalize_for_detection) e aceita tanto o nome técnico exato do campo
# (ex.: "age"/"Age"/"AGE") como um sinónimo comum em português (ex.: "Idade")
# — ver _PT_FIELD_SYNONYMS logo abaixo.
_STUDENTPERFOMANCE_FIELD_NAMES = config.FEATURES_WITH_GRADES + ["G3"]

# Sinónimos em português para cada campo técnico — permite carregar um
# ficheiro com nomes de coluna totalmente naturais em pt-pt (ex.: "Idade",
# "Faltas", "3º Período") e ainda assim ativar a página de Previsões, sem
# ter de renomear nada para os nomes técnicos ingleses do dataset original.
# Cada entrada tem várias variantes comuns, porque diferentes utilizadores
# tendem a nomear a mesma coluna de formas ligeiramente diferentes.
_PT_FIELD_SYNONYMS: dict[str, list[str]] = {
    "school": ["escola"],
    "sex": ["sexo", "género", "genero"],
    "age": ["idade"],
    "address": ["endereço", "morada", "zona de residência", "tipo de morada"],
    "famsize": ["tamanho da família", "dimensão da família", "agregado familiar"],
    "Pstatus": ["estado civil dos pais", "situação dos pais", "pais vivem juntos"],
    "Medu": ["educação da mãe", "escolaridade da mãe", "habilitações da mãe"],
    "Fedu": ["educação do pai", "escolaridade do pai", "habilitações do pai"],
    "Mjob": ["profissão da mãe", "trabalho da mãe", "emprego da mãe"],
    "Fjob": ["profissão do pai", "trabalho do pai", "emprego do pai"],
    "guardian": ["encarregado de educação", "tutor", "responsável"],
    "traveltime": ["tempo de deslocação", "tempo de deslocação para a escola", "tempo de viagem para a escola"],
    "studytime": ["tempo de estudo", "horas de estudo", "horas de estudo semanais", "tempo de estudo semanal"],
    "failures": ["reprovações", "reprovações anteriores", "número de reprovações", "chumbos"],
    "schoolsup": ["apoio educativo", "apoio escolar"],
    "famsup": ["apoio familiar", "apoio da família"],
    "paid": ["explicações", "explicações pagas", "aulas particulares"],
    "activities": ["atividades extracurriculares", "atividades extra curriculares", "atividades"],
    "internet": ["acesso à internet", "internet em casa", "tem internet"],
    "higher": ["pretende ensino superior", "quer tirar curso superior", "deseja ensino superior"],
    "romantic": ["relação amorosa", "namoro", "tem namorado"],
    "freetime": ["tempo livre"],
    "goout": ["sair com amigos", "saídas com amigos", "frequência de saídas"],
    "Dalc": ["consumo de álcool dias úteis", "álcool durante a semana", "consumo de álcool semanal"],
    "Walc": ["consumo de álcool fim de semana", "álcool ao fim de semana"],
    "health": ["saúde", "estado de saúde"],
    "absences": ["faltas", "número de faltas", "faltas às aulas"],
    "reason": ["motivo de escolha da escola", "razão de escolha da escola"],
    "nursery": ["frequentou infantário", "andou no infantário", "pré-escola"],
    "famrel": ["relação familiar", "qualidade da relação familiar"],
    "G1": ["1º período", "primeiro período", "nota do 1º período", "1º trimestre"],
    "G2": ["2º período", "segundo período", "nota do 2º período", "2º trimestre"],
    "G3": ["3º período", "terceiro período", "nota final", "nota do 3º período", "3º trimestre"],
}


def _normalize_for_detection(text: str) -> str:
    """Normalização usada só para a deteção automática de campos — mais
    tolerante do que formula_engine.normalize_text (que serve para nomes de
    coluna em fórmulas, onde a pontuação importa): além de remover acentos e
    baixar para minúsculas, ignora texto entre parênteses (ex.: "Tempo Livre
    (1-5)" -> "tempo livre") e qualquer pontuação/símbolos (ex.: "3º Período"
    -> "3o periodo"), para aceitar nomes de coluna escritos de forma mais
    livre sem arriscar falsos positivos (continua a exigir as mesmas
    palavras, só ignora como estão pontuadas)."""
    text = formula_engine.normalize_text(str(text))
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _build_detection_lookup() -> dict[str, str]:
    """{nome normalizado: campo técnico}, combinando os nomes técnicos exatos
    (prioridade, ex.: "age") com os sinónimos em português (ex.: "idade")."""
    lookup = {_normalize_for_detection(f): f for f in _STUDENTPERFOMANCE_FIELD_NAMES}
    for field, synonyms in _PT_FIELD_SYNONYMS.items():
        if field not in _STUDENTPERFOMANCE_FIELD_NAMES:
            continue  # segurança: nunca referenciar um campo fora do esquema conhecido
        for synonym in synonyms:
            # setdefault: um nome técnico exato nunca é substituído por um sinónimo.
            lookup.setdefault(_normalize_for_detection(synonym), field)
    return lookup


_DETECTION_LOOKUP = _build_detection_lookup()


def _detect_studentperfomance_fields(columns: list[str]) -> dict[str, str]:
    """Devolve {coluna_do_ficheiro: campo_da_studentperfomance} para as colunas cujo
    nome corresponde ao nome técnico de um campo conhecido (ex.: "age") ou a
    um sinónimo comum em português (ex.: "Idade") — ver _PT_FIELD_SYNONYMS."""
    detected = {}
    for col in columns:
        key = _normalize_for_detection(str(col))
        if key in _DETECTION_LOOKUP:
            detected[col] = _DETECTION_LOOKUP[key]
    return detected


# --- Importação (genérica, sem mapeamento) ----------------------------------
def _dedupe_column_names(columns: list[str]) -> list[str]:
    """Garante nomes de coluna únicos (ex.: ficheiros com duas colunas
    chamadas "Total" tornam-se "Total" e "Total_2") — nomes repetidos
    partiam a gravação na base de dados e a maior parte do resto do módulo,
    que assume poder indexar por nome de coluna."""
    seen: dict[str, int] = {}
    result = []
    for col in columns:
        if col not in seen:
            seen[col] = 0
            result.append(col)
        else:
            seen[col] += 1
            result.append(f"{col}_{seen[col]}")
    return result


def _infer_column_types(df: pd.DataFrame) -> pd.DataFrame:
    """
    Converte para numérico as colunas de texto em que TODOS os valores não
    vazios conseguem ser interpretados como número (ex.: uma coluna "Idade"
    lida do CSV como texto) — conservador de propósito: só converte quando
    não há absolutamente nenhuma perda de informação, para nunca estragar
    silenciosamente uma coluna de texto que só por coincidência tenha
    alguns valores numéricos.
    """
    df = df.copy()
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]) or pd.api.types.is_bool_dtype(df[col]):
            continue
        coerced = pd.to_numeric(df[col], errors="coerce")
        original_non_null = df[col].notna().sum()
        if original_non_null > 0 and coerced.notna().sum() == original_non_null:
            df[col] = coerced
    return df


def import_dataset() -> dict:
    """
    Confirma a importação do ficheiro em espera: limpa-o (nomes de coluna
    únicos, deteção automática de tipos) e grava-o como o dataset
    personalizado ativo (substitui qualquer um anterior), SEM exigir nenhum
    mapeamento — as colunas ficam com os nomes originais do ficheiro.
    Devolve o mesmo resumo de get_status().
    """
    staged_df = _staged.get("df")
    if staged_df is None:
        raise ValueError("Nenhum ficheiro foi carregado ainda — faz upload primeiro.")

    df = staged_df.copy()
    df.columns = _dedupe_column_names([str(c) for c in df.columns])
    df = _infer_column_types(df)

    if len(df) < MIN_ROWS_FOR_STATS:
        raise ValueError(
            f"O ficheiro só tem {len(df)} linha(s) — carrega um ficheiro com mais dados (mínimo {MIN_ROWS_FOR_STATS})."
        )

    data_columns = list(df.columns)
    df = df.reset_index(drop=True)
    # Identificador sequencial único por linha — genérico (row_id), já que o
    # dataset pode não ter nada a ver com estudantes.
    df.insert(0, "row_id", np.arange(1, len(df) + 1))

    database.write_table(df, RAW_TABLE, if_exists="replace")

    detected_fields = _detect_studentperfomance_fields(data_columns)
    meta_row = {
        "filename": _staged.get("filename") or "",
        "columns_json": json.dumps(data_columns, ensure_ascii=False),
        "detected_fields_json": json.dumps(detected_fields, ensure_ascii=False),
        "n_rows": int(len(df)),
        "imported_at": pd.Timestamp.now().isoformat(),
    }
    database.write_table(pd.DataFrame([meta_row]), META_TABLE, if_exists="replace")

    # Qualquer modelo personalizado treinado antes pertencia ao dataset
    # anterior — deixaria de fazer sentido (colunas diferentes, dados
    # diferentes), por isso é descartado ao importar um novo dataset.
    _clear_custom_models()

    # O upload em espera já foi "consumido" (confirmado).
    _staged.clear()

    return get_status()


def _clear_custom_models():
    """Apaga qualquer modelo/métricas treinados sobre o dataset personalizado anterior."""
    for path in (
        CUSTOM_MODELS_DIR / "regression_personalizado.joblib",
        CUSTOM_MODELS_DIR / "classification_personalizado.joblib",
        CUSTOM_METRICS_PATH,
    ):
        if not path.exists():
            continue
        try:
            path.unlink()
        except OSError:
            # Alguns sistemas de ficheiros (ex.: pastas sincronizadas de
            # rede/OneDrive) recusam apagar um ficheiro mesmo depois de
            # confirmarem que existe. Tenta-se então "tirá-lo do caminho"
            # (renomear para um nome de lixo, na mesma pasta) — isso já
            # costuma ser permitido mesmo quando apagar não é — para que
            # has_trained_model / get_custom_model_metrics deixem de o ver
            # neste caminho. Se nem isso for possível, desiste-se em
            # silêncio: o pior cenário é o ficheiro antigo ficar para trás
            # até ao próximo treino o substituir (joblib.dump escreve por
            # cima do ficheiro existente, o que é uma operação diferente de
            # apagar e costuma continuar a funcionar).
            try:
                trash_path = path.with_name(f"_stale_{path.name}")
                path.replace(trash_path)
            except OSError:
                pass


# --- Estado / metadados ------------------------------------------------
def _load_meta() -> dict | None:
    """Lê os metadados do dataset personalizado ativo, ou None se não houver nenhum."""
    if not database.table_exists(META_TABLE):
        return None
    df = database.read_table(META_TABLE)
    if df.empty:
        return None
    row = df.iloc[0].to_dict()
    row["columns"] = json.loads(row.pop("columns_json", "[]") or "[]")
    row["detected_fields"] = json.loads(row.pop("detected_fields_json", "{}") or "{}")
    return row


def has_dataset() -> bool:
    """Indica se existe atualmente um dataset personalizado importado."""
    return database.table_exists(RAW_TABLE) and _load_meta() is not None


def get_status() -> dict:
    """
    Resumo do estado atual: se há dataset importado, quantas linhas/colunas,
    que colunas foram detetadas automaticamente como parecidas com as da
    StudentPerfomance, e que cálculos são possíveis — usado pelo frontend para saber o
    que mostrar/desativar em cada sub-página (Estatísticas, Previsões,
    Treinar Modelo, Fórmulas).
    """
    meta = _load_meta()
    if meta is None:
        return {"imported": False}

    detected_fields = meta["detected_fields"]
    detected_names = set(detected_fields.values())
    # Nº de hábitos/variáveis demográficas detetadas (sem contar as notas) —
    # usado como critério mínimo de qualidade para as Previsões terem alguma
    # base real, em vez de assentarem quase só em valores por omissão.
    feature_cols_detected = [c for c in config.FEATURES_NO_GRADES if c in detected_names]

    df_columns = meta["columns"]
    return {
        "imported": True,
        "filename": meta["filename"],
        "n_rows": meta["n_rows"],
        "n_columns": len(df_columns),
        "imported_at": meta["imported_at"],
        "columns": df_columns,
        "detected_student_fields": detected_fields,
        # Treinar Modelo é genérico — só depende de haver linhas e colunas
        # suficientes, nunca de o dataset "parecer" dados de estudantes.
        "can_train": meta["n_rows"] >= MIN_ROWS_FOR_TRAIN and len(df_columns) >= 2,
        # Previsões continua a depender do modelo PRINCIPAL da StudentPerfomance, que só
        # sabe prever notas — só faz sentido quando há colunas suficientes
        # detetadas automaticamente como parecidas com hábitos/demografia.
        "can_predict": len(feature_cols_detected) >= 3,
        "min_rows_for_train": MIN_ROWS_FOR_TRAIN,
        "has_trained_model": CUSTOM_METRICS_PATH.exists(),
    }


def _load_dataset() -> pd.DataFrame:
    if not database.table_exists(RAW_TABLE):
        raise ValueError("Ainda não importaste nenhum dataset personalizado.")
    df = database.read_table(RAW_TABLE)
    # pd.read_sql_table (usado dentro de database.read_table) devolve os
    # nomes das colunas como objetos "quoted_name" do SQLAlchemy, não como
    # str puro — visualmente idênticos (imprimem-se e comparam-se na
    # perfeição como strings normais), mas o scikit-learn deteta o tipo
    # exato e, não os reconhecendo como "nomes de feature" válidos, falha
    # silenciosamente a guardar feature_names_in_ no ColumnTransformer, o
    # que rebenta mais tarde com "'ColumnTransformer' object has no
    # attribute 'feature_names_in_'" ao treinar (ver train_custom_model).
    # Forçar aqui para str resolve na origem, antes de os dados chegarem a
    # qualquer pipeline de scikit-learn.
    df.columns = [str(c) for c in df.columns]
    return df


def delete_dataset():
    """Esquece por completo o dataset personalizado ativo (dados, metadados e modelo treinado)."""
    database.drop_table(RAW_TABLE)
    database.drop_table(META_TABLE)
    _clear_custom_models()
    _staged.clear()


# --- Estatísticas (genéricas, funcionam com qualquer dataset) ---------------
def compute_stats() -> dict:
    """
    Estatísticas descritivas sobre o dataset personalizado: uma entrada por
    coluna (média/mediana/desvio-padrão/mín/máx para colunas numéricas,
    contagens por categoria para colunas de texto — decidido pelo TIPO REAL
    de cada coluna, nunca por um esquema fixo). Se o dataset tiver uma
    coluna detetada automaticamente como "nota final" (G3), mostra também os
    indicadores/gráficos ao estilo da Visão Geral principal, como bónus.
    """
    df = _load_dataset()
    data_cols = [c for c in df.columns if c != "row_id"]

    columns_stats = {}
    for col in data_cols:
        s = df[col].dropna()
        if s.empty:
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            columns_stats[col] = {
                "type": "numeric",
                "mean": round(float(s.mean()), 2),
                "median": round(float(s.median()), 2),
                "std": round(float(s.std()), 2) if len(s) > 1 else 0.0,
                "min": round(float(s.min()), 2),
                "max": round(float(s.max()), 2),
            }
        else:
            counts = df[col].astype(str).value_counts()
            columns_stats[col] = {
                "type": "categorical",
                # Limita a 20 categorias — colunas de texto com muitos
                # valores únicos (ex.: "Order ID") dariam uma lista imensa
                # e pouco útil de mostrar.
                "counts": {str(k): int(v) for k, v in counts.head(20).items()},
                "n_distinct": int(df[col].nunique()),
            }

    result = {
        "n_rows": int(len(df)),
        "n_columns": len(data_cols),
        "columns": columns_stats,
    }

    meta = _load_meta()
    detected_fields = meta["detected_fields"] if meta else {}
    g3_col = next((raw for raw, field in detected_fields.items() if field == "G3"), None)
    if g3_col and g3_col in df.columns:
        g3 = pd.to_numeric(df[g3_col], errors="coerce").dropna()
        if not g3.empty:
            result["average_grade"] = round(float(g3.mean()), 2)
            passed = (g3 >= config.PASS_THRESHOLD).astype(int)
            result["pass_rate"] = round(float(passed.mean()), 4)

            # Nº de intervalos do histograma adaptado a datasets pequenos
            # (nunca mais intervalos do que valores distintos de nota existentes).
            n_bins = max(3, min(20, g3.nunique()))
            counts, bin_edges = pd.cut(g3, bins=n_bins, retbins=True)
            hist = counts.value_counts(sort=False)
            labels = [f"{bin_edges[i]:.1f}-{bin_edges[i + 1]:.1f}" for i in range(len(bin_edges) - 1)]
            result["grade_distribution"] = {"labels": labels, "counts": [int(v) for v in hist.values]}

            pf = passed.value_counts()
            result["pass_fail_counts"] = {"aprovados": int(pf.get(1, 0)), "reprovados": int(pf.get(0, 0))}

    return result


# --- Previsões (reaproveita o modelo principal, só quando faz sentido) ------
def compute_predictions(page: int = 1, page_size: int = 20) -> dict:
    """
    Corre o modelo de previsão PRINCIPAL (já treinado sobre o dataset
    original) sobre cada linha do dataset personalizado — usando as colunas
    detetadas automaticamente como parecidas com hábitos/demografia da
    StudentPerfomance (ver _detect_studentperfomance_fields); as restantes ficam por conta dos
    valores por omissão do modelo, tal como já acontece ao prever
    manualmente no Simulador (ver src/predict.py). Levanta ValueError se o
    dataset não tiver colunas suficientes detetadas.
    """
    df = _load_dataset()
    meta = _load_meta()
    detected_fields = meta["detected_fields"] if meta else {}
    if not detected_fields:
        raise ValueError(
            "Este dataset não tem colunas parecidas com os dados de estudantes da StudentPerfomance "
            "(idade, sexo, tempo de estudo, faltas, etc.) — não é possível gerar previsões."
        )

    # Renomeia só as colunas detetadas para os nomes que full_prediction espera.
    renamed = df.rename(columns=detected_fields)

    total = len(df)
    total_pages = max(1, -(-total // page_size))  # divisão arredondada para cima
    page = min(max(page, 1), total_pages)
    start = (page - 1) * page_size
    subset = renamed.iloc[start:start + page_size]

    feature_candidates = [c for c in config.FEATURES_WITH_GRADES if c in renamed.columns]
    if len([c for c in config.FEATURES_NO_GRADES if c in feature_candidates]) < 3:
        raise ValueError(
            "Este dataset não tem colunas parecidas com os dados de estudantes da StudentPerfomance "
            "(idade, sexo, tempo de estudo, faltas, etc.) — não é possível gerar previsões."
        )

    predictions = []
    for _, row in subset.iterrows():
        user_input = {c: row[c] for c in feature_candidates if pd.notna(row[c])}
        try:
            pred = full_prediction(user_input)
        except Exception:
            # Uma linha problemática (ex.: categoria nunca vista pelo
            # modelo) não deve impedir as restantes de aparecerem.
            continue
        entry = {
            "row_id": int(row["row_id"]),
            "predicted_grade": pred["nota_prevista_habitos"]["predicted_grade"],
            "pass_probability": pred["aprovacao"]["probabilidade_aprovacao"],
            "aprovado_previsto": pred["aprovacao"]["aprovado_previsto"],
        }
        if "G3" in renamed.columns:
            entry["actual_grade"] = float(row["G3"])
        predictions.append(entry)

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "fields_used": feature_candidates,
        "predictions": predictions,
    }


# --- Treino de um modelo novo, genérico (o utilizador escolhe alvo + features) ---
def _build_generic_preprocessor(df: pd.DataFrame, feature_cols: list[str]) -> ColumnTransformer:
    """
    Pré-processador genérico (normalização + one-hot encoding), equivalente
    ao build_preprocessor de train_model.py, mas que decide colunas
    numéricas vs. categóricas pelo TIPO REAL de cada coluna do dataset em
    vez de uma lista fixa de nomes — o de train_model.py não pode ser
    reutilizado aqui porque assume sempre os nomes de coluna do esquema da
    StudentPerfomance (ex.: trataria uma coluna "Region" de um dataset de vendas como
    numérica só por não constar dessa lista, e rebentaria ao tentar
    normalizá-la).
    """
    num_cols = [c for c in feature_cols if pd.api.types.is_numeric_dtype(df[c])]
    cat_cols = [c for c in feature_cols if c not in num_cols]
    return ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), num_cols),
            ("cat", OneHotEncoder(handle_unknown="ignore"), cat_cols),
        ]
    )


def _fill_missing_features(df: pd.DataFrame, feature_cols: list[str]) -> pd.DataFrame:
    """Preenche nulos nas colunas-recurso escolhidas (mediana nas numéricas,
    valor mais frequente nas restantes) — evita descartar linhas só porque
    uma das MUITAS colunas-recurso possíveis tem um valor em falta."""
    df = df.copy()
    for col in feature_cols:
        if not df[col].isnull().any():
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            median = df[col].median()
            df[col] = df[col].fillna(median if pd.notna(median) else 0)
        else:
            mode = df[col].mode()
            df[col] = df[col].fillna(mode[0] if not mode.empty else "desconhecido")
    return df


def train_custom_model(target_col: str, feature_cols: list[str]) -> dict:
    """
    Treina um modelo de Machine Learning para prever "target_col" a partir
    de "feature_cols" — REGRESSÃO se a coluna-alvo for numérica (ex.: prever
    "Total Sales"), CLASSIFICAÇÃO se for categórica (ex.: prever "Region"),
    detetado automaticamente pelo tipo real da coluna. Guardado em
    CUSTOM_MODELS_DIR, nunca nos modelos principais da app.
    """
    df = _load_dataset()

    if target_col not in df.columns or target_col == "row_id":
        raise ValueError(f"Coluna-alvo desconhecida: '{target_col}'.")
    feature_cols = [c for c in dict.fromkeys(feature_cols) if c in df.columns and c not in (target_col, "row_id")]
    if not feature_cols:
        raise ValueError("Escolhe pelo menos uma coluna-recurso (diferente da coluna-alvo e de 'row_id').")

    work = df[[target_col] + feature_cols].dropna(subset=[target_col])
    work = _fill_missing_features(work, feature_cols)
    if len(work) < MIN_ROWS_FOR_TRAIN:
        raise ValueError(
            f"São precisas pelo menos {MIN_ROWS_FOR_TRAIN} linhas válidas (com a coluna-alvo preenchida) "
            f"para treinar um modelo (há {len(work)})."
        )

    is_numeric_target = pd.api.types.is_numeric_dtype(work[target_col])
    X = work[feature_cols]
    preprocessor = _build_generic_preprocessor(work, feature_cols)

    result: dict = {"target": target_col, "feature_cols": feature_cols, "n_rows": int(len(work))}

    if is_numeric_target:
        result["task"] = "regression"
        y = work[target_col]
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=config.RANDOM_STATE)
        candidates = {
            "LinearRegression": LinearRegression(),
            "RandomForestRegressor": RandomForestRegressor(n_estimators=200, random_state=config.RANDOM_STATE, max_depth=6),
        }
        results, best_name, best_pipe, best_score = {}, None, None, -np.inf
        for name, model in candidates.items():
            pipe = Pipeline([("prep", preprocessor), ("model", model)])
            pipe.fit(X_train, y_train)
            y_pred = pipe.predict(X_test)
            metrics = {
                "R2": round(r2_score(y_test, y_pred), 4),
                "MAE": round(mean_absolute_error(y_test, y_pred), 4),
                "RMSE": round(root_mean_squared_error(y_test, y_pred), 4),
            }
            results[name] = metrics
            if metrics["R2"] > best_score:
                best_name, best_pipe, best_score = name, pipe, metrics["R2"]

        joblib.dump(
            {"pipeline": best_pipe, "features": feature_cols, "target": target_col, "best_model": best_name},
            CUSTOM_MODELS_DIR / "regression_personalizado.joblib",
        )
        result["regression"] = {"results": results, "best_model": best_name}
        result["classification"] = None

    else:
        result["task"] = "classification"
        y = work[target_col].astype(str)
        class_counts = y.value_counts()
        if len(class_counts) < 2:
            raise ValueError("A coluna-alvo escolhida só tem uma categoria — não há nada para classificar.")
        if class_counts.min() < MIN_CLASS_COUNT_FOR_TRAIN:
            raise ValueError(
                f"Cada categoria da coluna-alvo precisa de pelo menos {MIN_CLASS_COUNT_FOR_TRAIN} exemplos "
                f"(a categoria menos comum, '{class_counts.idxmin()}', só tem {class_counts.min()})."
            )

        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=0.2, random_state=config.RANDOM_STATE, stratify=y
            )
        except ValueError:
            # Em datasets pequenos/muito desequilibrados a divisão
            # estratificada por vezes não é possível (nem toda a classe cabe
            # nos dois lados) — cai-se então para uma divisão normal, em vez
            # de impedir o treino por completo.
            X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=config.RANDOM_STATE)

        candidates = {
            "LogisticRegression": LogisticRegression(max_iter=1000),
            "RandomForestClassifier": RandomForestClassifier(n_estimators=200, random_state=config.RANDOM_STATE, max_depth=6),
        }
        results, best_name, best_pipe, best_score = {}, None, None, -np.inf
        for name, model in candidates.items():
            pipe = Pipeline([("prep", preprocessor), ("model", model)])
            pipe.fit(X_train, y_train)
            y_pred = pipe.predict(X_test)
            y_proba = pipe.predict_proba(X_test)
            metrics = {
                "Accuracy": round(accuracy_score(y_test, y_pred), 4),
                # float(...): com average="weighted" o resultado é sempre um
                # único número, mas o tipo devolvido por estas funções do
                # scikit-learn é "float | ndarray" (o caso ndarray só
                # acontece com average=None) — o float(...) explícito
                # resolve essa ambiguidade para o verificador de tipos, sem
                # mudar o valor em runtime.
                "Precision": round(float(precision_score(y_test, y_pred, average="weighted", zero_division=0)), 4),
                "Recall": round(float(recall_score(y_test, y_pred, average="weighted", zero_division=0)), 4),
                "F1": round(float(f1_score(y_test, y_pred, average="weighted", zero_division=0)), 4),
            }
            # ROC-AUC: só bem definido quando o conjunto de teste contém
            # todas as classes vistas no treino — em datasets pequenos isso
            # nem sempre acontece, e nesse caso o indicador fica de fora em
            # vez de rebentar o treino todo.
            try:
                if len(pipe.classes_) == 2:
                    metrics["ROC_AUC"] = round(roc_auc_score(y_test, y_proba[:, 1]), 4)
                else:
                    metrics["ROC_AUC"] = round(
                        roc_auc_score(y_test, y_proba, multi_class="ovr", average="weighted"), 4
                    )
            except ValueError:
                metrics["ROC_AUC"] = None
            results[name] = metrics
            if metrics["F1"] > best_score:
                best_name, best_pipe, best_score = name, pipe, metrics["F1"]

        joblib.dump(
            {"pipeline": best_pipe, "features": feature_cols, "target": target_col, "best_model": best_name},
            CUSTOM_MODELS_DIR / "classification_personalizado.joblib",
        )
        result["classification"] = {"results": results, "best_model": best_name}
        result["regression"] = None

    CUSTOM_METRICS_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


def get_custom_model_metrics() -> dict | None:
    """Métricas do último modelo personalizado treinado, ou None se ainda não foi treinado nenhum."""
    if not CUSTOM_METRICS_PATH.exists():
        return None
    return json.loads(CUSTOM_METRICS_PATH.read_text(encoding="utf-8"))


# --- Fórmulas personalizadas ------------------------------------------------
def compute_formula(formula: str, page: int = 1, page_size: int = 20) -> dict:
    """
    Avalia uma fórmula escrita pelo utilizador (ex.: "G1*0.3 + G2*0.3 +
    G3*0.4" ou "media(G3) onde studytime >= 3") sobre o dataset personalizado
    ativo, usando diretamente os nomes de coluna do ficheiro importado — ver
    src/formula_engine.py para a implementação do avaliador seguro (sem
    eval()/exec()). Levanta ValueError (coluna/função desconhecida, sintaxe
    inválida, etc.) se a fórmula não puder ser calculada, para o endpoint da
    API a devolver como erro 400.
    """
    df = _load_dataset()
    return formula_engine.evaluate(df, formula, page=page, page_size=page_size)
