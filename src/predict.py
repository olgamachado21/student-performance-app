"""
Carrega os modelos treinados e disponibiliza funções de previsão prontas
a serem usadas por uma aplicação (CLI, API ou interface web).
"""
from __future__ import annotations

# json: para ler o ficheiro de métricas dos modelos (model_metrics.json).
import json
# lru_cache: guarda em cache o resultado de uma função (evita recarregar
# ficheiros/modelos do disco repetidamente).
from functools import lru_cache

# joblib: para carregar os modelos treinados a partir de ficheiro.
import joblib
# pandas: para construir a linha de entrada dos modelos como DataFrame.
import pandas as pd

from src import config
from src.data_processing import get_processed_data

# Preenchido em runtime por get_defaults() — mantido aqui só como referência histórica.
DEFAULT_FIELDS_INFO = None

# Nome do relatório usado tanto pela variante "regressao_habitos" como
# "regressao_completo" em reports/model_metrics.json (ver train_model.py).
_METRICS_REPORT_KEYS = {"habitos": "regressao_habitos", "completo": "regressao_completo"}


@lru_cache(maxsize=1)
def _load_model_metrics_report() -> dict:
    """Lê o relatório de métricas dos modelos (guardado em cache, só é lido do disco uma vez)."""
    path = config.REPORTS_DIR / "model_metrics.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def get_model_mae(variant: str) -> float | None:
    """
    MAE (erro médio absoluto, em valores) do modelo escolhido como "melhor"
    para esta variante, medido no conjunto de teste (ver evaluate_regression
    em train_model.py) — usado como margem de erro típica a mostrar junto da
    previsão, para não apresentar um único número como se fosse exato. Não é
    um intervalo de confiança estatístico formal (isso exigiria assumir uma
    distribuição dos erros), é a honestidade mínima: "em média, o modelo
    erra XX valores para mais ou para menos".
    """
    report = _load_model_metrics_report()
    key = _METRICS_REPORT_KEYS.get(variant)
    entry = report.get(key) if key else None
    if not entry:
        return None
    best_model = entry.get("best_model")
    results = entry.get("results", {})
    metrics = results.get(best_model)
    if not metrics or "MAE" not in metrics:
        return None
    return float(metrics["MAE"])


@lru_cache(maxsize=1)
def _load_artifact(name: str):
    """Carrega um modelo treinado (.joblib) do disco, guardado em cache (só é lido uma vez)."""
    path = config.MODELS_DIR / name
    if not path.exists():
        raise FileNotFoundError(
            f"Modelo '{name}' não encontrado em {path}. Corre `python -m src.train_model` primeiro."
        )
    return joblib.load(path)


@lru_cache(maxsize=1)
def get_defaults() -> dict:
    """Valores por omissão (mediana/moda) para preencher campos não fornecidos."""
    df = get_processed_data()
    defaults = {}
    for col in config.FEATURES_WITH_GRADES:
        if col in config.CATEGORICAL_COLS:
            # Categóricas: usa o valor mais frequente (moda).
            defaults[col] = df[col].mode()[0]
        else:
            # Numéricas: usa a mediana (mais robusta a outliers do que a média).
            defaults[col] = float(df[col].median())
    return defaults


def _build_input_frame(user_input: dict, feature_cols: list[str]) -> pd.DataFrame:
    """Constrói a linha de entrada para o modelo, preenchendo campos em falta com os valores por omissão."""
    defaults = get_defaults()
    row = {}
    for col in feature_cols:
        # Usa o valor fornecido pelo utilizador, ou o valor típico se não tiver sido indicado.
        row[col] = user_input.get(col, defaults.get(col))
    # O modelo espera um DataFrame (mesmo que seja só uma linha).
    return pd.DataFrame([row])


def predict_grade(user_input: dict, use_previous_grades: bool = False) -> dict:
    """
    Prevê a nota final (G3, escala 0-20).
    use_previous_grades=True usa também G1/G2 (se fornecidos) para maior precisão.
    """
    # Escolhe qual dos dois modelos de regressão usar, consoante se têm ou não G1/G2.
    variant = "completo" if use_previous_grades else "habitos"
    artifact = _load_artifact(f"regression_{variant}.joblib")
    pipe, feature_cols = artifact["pipeline"], artifact["features"]

    X = _build_input_frame(user_input, feature_cols)
    pred = float(pipe.predict(X)[0])
    # Garante que a previsão fica sempre dentro da escala válida (0-20).
    pred = max(0.0, min(20.0, pred))

    mae = get_model_mae(variant)
    return {
        "predicted_grade": round(pred, 2),
        "scale": "0-20",
        "model_variant": variant,
        "model_used": artifact["best_model"],
        "mae": round(mae, 2) if mae is not None else None,
    }


def predict_pass_probability(user_input: dict) -> dict:
    """Prevê a probabilidade de aprovação (G3 >= 10) a partir dos hábitos do estudante."""
    artifact = _load_artifact("classification_habitos.joblib")
    pipe, feature_cols = artifact["pipeline"], artifact["features"]

    X = _build_input_frame(user_input, feature_cols)
    # predict_proba devolve as probabilidades de cada classe; [0][1] é a probabilidade de "aprovado".
    proba = float(pipe.predict_proba(X)[0][1])
    pred = int(pipe.predict(X)[0])

    return {
        "aprovado_previsto": bool(pred),
        "probabilidade_aprovacao": round(proba, 4),
        "model_used": artifact["best_model"],
    }


def full_prediction(user_input: dict) -> dict:
    """Combina regressão (com e sem notas anteriores) e classificação num único resultado."""
    result = {
        "nota_prevista_habitos": predict_grade(user_input, use_previous_grades=False),
        "aprovacao": predict_pass_probability(user_input),
    }
    # Só calcula a previsão "completa" (com G1/G2) se essas notas tiverem sido fornecidas.
    if "G1" in user_input and "G2" in user_input:
        result["nota_prevista_completa"] = predict_grade(user_input, use_previous_grades=True)
    return result


# Fatores interpretáveis usados na explicação por estudante (o mesmo
# subconjunto de "hábitos" já exposto no simulador da interface — não faz
# sentido explicar com variáveis que o utilizador nem consegue ajustar lá).
EXPLAIN_FEATURES = ["studytime", "absences", "failures", "goout", "Dalc", "Walc", "internet", "higher", "schoolsup"]
# Nomes amigáveis destes fatores, mostrados na explicação da previsão.
EXPLAIN_LABELS = {
    "studytime": "Tempo de estudo semanal",
    "absences": "Número de faltas",
    "failures": "Reprovações anteriores",
    "goout": "Sair com amigos",
    "Dalc": "Consumo de álcool em dias úteis",
    "Walc": "Consumo de álcool ao fim de semana",
    "internet": "Acesso a internet em casa",
    "higher": "Deseja estudar no ensino superior",
    "schoolsup": "Apoio educativo extra",
}


def explain_prediction(user_input: dict) -> dict:
    """
    Explica a previsão de UM estudante em concreto, não a importância
    genérica do modelo (essa é sempre igual para toda a gente e já existe em
    /feature-importance). Para cada fator interpretável, recalcula a
    previsão substituindo só esse valor pelo valor típico do dataset
    (mediana para numéricos, mais comum para categóricos — o mesmo usado em
    get_defaults) e mantém tudo o resto exatamente como o estudante indicou.
    A diferença face à previsão real ("impact") mostra o quanto ESSE fator,
    para ESTE estudante, está a puxar a nota prevista para cima ou para
    baixo — impact > 0 significa que o valor do estudante está a ajudar
    (a nota desceria se fosse trocado pelo valor típico); impact < 0
    significa que está a prejudicar.
    Não é um método de perturbação único por variável (tipo SHAP), mas é
    honesto sobre o que mede: o efeito isolado de trocar UM fator de cada
    vez, mantendo os outros fixos.
    """
    # Previsão real, com todos os valores que o estudante forneceu.
    baseline = predict_grade(user_input, use_previous_grades=False)["predicted_grade"]
    defaults = get_defaults()

    # Lista de contribuições (uma por fator relevante), construída passo a passo.
    contributions = []
    for feat in EXPLAIN_FEATURES:
        if feat not in user_input or user_input[feat] is None:
            continue  # sem valor fornecido pelo estudante, não há nada para isolar
        typical_value = defaults.get(feat)
        if user_input[feat] == typical_value:
            continue  # já está no valor típico, não tem impacto a mostrar
        # Constrói uma versão "hipotética" (contrafactual): tudo igual, exceto este fator,
        # que passa a ter o valor típico do dataset em vez do valor real do estudante.
        counterfactual_input = {**user_input, feat: typical_value}
        counterfactual_grade = predict_grade(counterfactual_input, use_previous_grades=False)["predicted_grade"]
        # Impacto: quanto a nota previsto muda ao trocar este valor pelo valor típico.
        impact = round(baseline - counterfactual_grade, 2)
        if abs(impact) < 0.05:
            continue  # impacto residual, não vale a pena listar
        contributions.append({
            "feature": feat,
            "label": EXPLAIN_LABELS.get(feat, feat),
            "student_value": user_input[feat],
            "typical_value": typical_value,
            "impact": impact,
        })

    # Ordena pelo impacto mais forte (positivo ou negativo) primeiro.
    contributions.sort(key=lambda c: abs(c["impact"]), reverse=True)
    return {"baseline_grade": baseline, "contributions": contributions}


# Nº de desvios-padrão de resíduo a partir do qual um estudante é
# considerado um "perfil atípico" — 2.0 é um valor comum em deteção de
# outliers (numa distribuição aproximadamente normal, cerca de 5% dos casos
# ficam acima disto), suficiente para ser raro sem ser tão exigente que quase
# nunca sinalize ninguém.
OUTLIER_Z_THRESHOLD = 2.0


def detect_outliers(df: pd.DataFrame, z_threshold: float = OUTLIER_Z_THRESHOLD, limit: int = 20) -> list[dict]:
    """
    Identifica estudantes cujo resultado foge do que seria esperado dado o
    seu próprio perfil — não "quem tem nota baixa" (isso já é `at_risk`),
    mas "quem teve uma nota muito diferente do que os SEUS hábitos e
    contexto normalmente preveem". Usa o modelo de regressão completo (o
    mesmo do treino, com G1/G2) para prever a nota de todos os estudantes de
    uma vez, calcula o resíduo (nota real − nota prevista) e sinaliza quem
    tem um resíduo muito maior que a maioria (z-score do resíduo, em desvios-
    padrão face à média dos resíduos de todos os estudantes).

    Um resíduo muito positivo (z > 0) é um estudante a sair-se melhor do que
    o seu perfil fazia prever — pode ser um caso de superação a destacar. Um
    resíduo muito negativo (z < 0) é o oposto — pode ser um caso a
    investigar, mesmo que a nota em si não seja das piores da turma.
    """
    artifact = _load_artifact("regression_completo.joblib")
    pipe, feature_cols = artifact["pipeline"], artifact["features"]

    # Reindexa de 0 em diante, para os índices de "predicted"/"residual" corresponderem às linhas.
    df = df.reset_index(drop=True)
    # Prevê a nota de TODOS os estudantes de uma só vez (mais eficiente do que um a um).
    predicted = pipe.predict(df[feature_cols])
    # Resíduo: diferença entre a nota real e a nota prevista pelo modelo.
    residual = df["G3"].to_numpy(dtype=float) - predicted

    std_res = residual.std()
    if std_res == 0:
        # Sem variação nos resíduos (caso extremamente raro) — não há outliers a calcular.
        return []
    # z-score de cada resíduo: a quantos desvios-padrão está da média dos resíduos.
    z_scores = (residual - residual.mean()) / std_res

    results = []
    for i in range(len(df)):
        z = float(z_scores[i])
        # Só considera outlier se o desvio ultrapassar o limiar definido.
        if abs(z) < z_threshold:
            continue
        results.append({
            "student_id": int(df.loc[i, "student_id"]),
            "actual_grade": float(df.loc[i, "G3"]),
            "predicted_grade": round(float(predicted[i]), 2),
            "residual": round(float(residual[i]), 2),
            "z_score": round(z, 2),
            "direction": "acima do esperado" if z > 0 else "abaixo do esperado",
        })

    # Ordena pelos casos mais extremos primeiro, e limita ao número pedido.
    results.sort(key=lambda r: abs(r["z_score"]), reverse=True)
    return results[:limit]


# Bloco de teste rápido: permite correr "python -m src.predict" para ver um
# exemplo de previsão completa impresso no terminal.
if __name__ == "__main__":
    example = {
        "studytime": 4,
        "absences": 1,
        "failures": 0,
        "goout": 2,
        "Dalc": 1,
        "Walc": 1,
        "internet": "yes",
        "higher": "yes",
        "schoolsup": "no",
        "romantic": "no",
    }
    import json
    print(json.dumps(full_prediction(example), indent=2, ensure_ascii=False))
