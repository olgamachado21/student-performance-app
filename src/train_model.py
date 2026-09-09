"""
Treino, avaliação e seleção de modelos de Machine Learning para:
1) Regressão: prever a nota final (G3) a partir dos hábitos/contexto do estudante.
2) Classificação: prever aprovado/reprovado (G3 >= 10).

Para cada tarefa treina-se um conjunto de dois modelos:
- "habitos": usa apenas hábitos de estudo + demografia (sem G1/G2) -> interpretativo,
    responde à pergunta "que hábitos influenciam o desempenho?".
- "completo": inclui também G1/G2 -> maior poder preditivo.

Os melhores modelos (pipeline de pré-processamento + estimador) são guardados em models/
junto com um relatório de métricas em reports/model_report.md
"""
from __future__ import annotations

# json: para guardar o resumo final das métricas em formato .json.
import json

# joblib: para gravar/carregar os modelos treinados em disco (.joblib).
import joblib
# numpy: cálculos numéricos auxiliares.
import numpy as np
# pandas: para trabalhar com os dados como tabela.
import pandas as pd
# ColumnTransformer: aplica transformações diferentes a colunas diferentes
# (normalização às numéricas, codificação às categóricas) dentro do mesmo pipeline.
from sklearn.compose import ColumnTransformer
# Modelos candidatos: Random Forest e Gradient Boosting, tanto para regressão como classificação.
from sklearn.ensemble import (GradientBoostingClassifier,
                            GradientBoostingRegressor,
                            RandomForestClassifier, RandomForestRegressor)
# Modelos lineares "clássicos", usados como candidatos mais simples/interpretáveis.
from sklearn.linear_model import LinearRegression, LogisticRegression
# Métricas de avaliação, tanto para regressão como para classificação.
from sklearn.metrics import (accuracy_score, f1_score, mean_absolute_error,
                            precision_score, r2_score, recall_score,
                            roc_auc_score, root_mean_squared_error)
# cross_val_score: avalia um modelo com validação cruzada. train_test_split: divide os dados em treino/teste.
from sklearn.model_selection import cross_val_score, train_test_split
# Pipeline: encadeia o pré-processamento e o modelo num único objeto reutilizável.
from sklearn.pipeline import Pipeline
# OneHotEncoder: converte colunas categóricas em colunas binárias (0/1). StandardScaler: normaliza colunas numéricas.
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src import config
from src.data_processing import get_processed_data


def build_preprocessor(feature_cols: list[str]) -> ColumnTransformer:
    """Constrói o pré-processador: normaliza colunas numéricas, codifica colunas categóricas."""
    # Separa as colunas indicadas em categóricas e numéricas, segundo a lista definida em config.py.
    cat_cols = [c for c in feature_cols if c in config.CATEGORICAL_COLS]
    num_cols = [c for c in feature_cols if c not in cat_cols]
    return ColumnTransformer(
        transformers=[
            # Colunas numéricas: normalizadas (média 0, desvio-padrão 1).
            ("num", StandardScaler(), num_cols),
            # Colunas categóricas: codificação one-hot; handle_unknown="ignore" evita
            # erro se aparecer uma categoria nova que o modelo nunca viu no treino.
            ("cat", OneHotEncoder(handle_unknown="ignore"), cat_cols),
        ]
    )


def evaluate_regression(y_true, y_pred) -> dict:
    """Calcula as métricas-padrão de avaliação para modelos de regressão."""
    return {
        # R²: proporção da variação explicada pelo modelo (0 a 1, quanto maior melhor).
        "R2": round(r2_score(y_true, y_pred), 4),
        # MAE: erro médio absoluto (em valores da nota, mais fácil de interpretar).
        "MAE": round(mean_absolute_error(y_true, y_pred), 4),
        # RMSE: penaliza mais os erros grandes do que o MAE.
        "RMSE": round(root_mean_squared_error(y_true, y_pred), 4),
    }


def evaluate_classification(y_true, y_pred, y_proba) -> dict:
    """Calcula as métricas-padrão de avaliação para modelos de classificação."""
    return {
        "Accuracy": round(accuracy_score(y_true, y_pred), 4),
        # zero_division=0: evita erro/aviso quando não há nenhum caso positivo previsto.
        # float(...): o tipo devolvido por estas funções do scikit-learn é
        # "float | ndarray" nos stubs (o caso ndarray só acontece com
        # average=None) — o float(...) explícito resolve essa ambiguidade
        # para o verificador de tipos, sem mudar o valor em runtime.
        "Precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "Recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "F1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        # ROC-AUC precisa das probabilidades previstas, não só da classe final (0/1).
        "ROC_AUC": round(roc_auc_score(y_true, y_proba), 4),
    }


def train_regression_variant(df: pd.DataFrame, feature_cols: list[str], variant_name: str) -> dict:
    """Treina e compara vários modelos de regressão, guardando o melhor em disco."""
    X = df[feature_cols]
    y = df[config.TARGET_REGRESSION]
    # Divide os dados em treino (80%) e teste (20%), com semente fixa para reprodutibilidade.
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=config.TEST_SIZE, random_state=config.RANDOM_STATE
    )

    # Três modelos candidatos, do mais simples (linear) ao mais complexo (boosting).
    candidates = {
        "LinearRegression": LinearRegression(),
        "RandomForestRegressor": RandomForestRegressor(
            n_estimators=300, random_state=config.RANDOM_STATE, max_depth=8
        ),
        "GradientBoostingRegressor": GradientBoostingRegressor(random_state=config.RANDOM_STATE),
    }

    results = {}
    # Guarda o melhor modelo encontrado até agora (começa "vazio", com a pior pontuação possível).
    best_name, best_pipe, best_score = None, None, -np.inf
    for name, model in candidates.items():
        # Pipeline: primeiro o pré-processamento, depois o modelo — tudo num só objeto.
        pipe = Pipeline([
            ("prep", build_preprocessor(feature_cols)),
            ("model", model),
        ])
        # Validação cruzada (5 divisões) sobre os dados de treino, para uma estimativa
        # mais robusta da qualidade do modelo do que um único split treino/teste.
        cv_scores = cross_val_score(pipe, X_train, y_train, cv=5, scoring="r2")
        # Treina o modelo final com todos os dados de treino.
        pipe.fit(X_train, y_train)
        # Avalia no conjunto de teste (dados nunca vistos durante o treino).
        y_pred = pipe.predict(X_test)
        metrics = evaluate_regression(y_test, y_pred)
        metrics["CV_R2_mean"] = round(cv_scores.mean(), 4)
        metrics["CV_R2_std"] = round(cv_scores.std(), 4)
        results[name] = metrics

        # Atualiza o "melhor modelo" se este tiver um R² mais alto no teste.
        if metrics["R2"] > best_score:
            best_name, best_pipe, best_score = name, pipe, metrics["R2"]

    # Grava o melhor modelo (pipeline completo) em disco, com metadados sobre as features usadas.
    model_path = config.MODELS_DIR / f"regression_{variant_name}.joblib"
    joblib.dump({"pipeline": best_pipe, "features": feature_cols, "best_model": best_name}, model_path)

    return {"variant": variant_name, "results": results, "best_model": best_name, "model_path": str(model_path)}


def compute_naive_baseline(df: pd.DataFrame) -> dict:
    """
    Baseline "ingénuo": em vez de qualquer modelo, prever sempre a média das
    notas de treino para toda a gente, ignorando hábitos e contexto —
    referência mínima para mostrar que os modelos reais acrescentam valor,
    e não só se ajustam ao ruído dos dados. Usa exatamente o mesmo
    random_state/test_size dos modelos de regressão (train_regression_variant)
    para a comparação ser justa — mesma divisão treino/teste, mesmas linhas.
    Não retreina nem grava nada; é só uma métrica de referência calculada em
    tempo real a partir do dataset processado.
    """
    y = df[config.TARGET_REGRESSION]
    # Mesma divisão treino/teste usada nos modelos reais, para a comparação ser justa.
    _, _, y_train, y_test = train_test_split(
        df, y, test_size=config.TEST_SIZE, random_state=config.RANDOM_STATE
    )
    # A "previsão" é sempre a mesma: a média das notas de treino.
    baseline_value = float(y_train.mean())
    baseline_pred = np.full(len(y_test), baseline_value)
    return {
        "predicted_value": round(baseline_value, 2),
        "MAE": round(mean_absolute_error(y_test, baseline_pred), 4),
        "RMSE": round(root_mean_squared_error(y_test, baseline_pred), 4),
        "description": (
            "Prever sempre a nota média da turma (sem olhar a nenhum hábito "
            "ou dado do estudante) — a referência mínima que qualquer modelo "
            "a sério tem de superar."
        ),
    }


def train_classification(df: pd.DataFrame) -> dict:
    """Treina e compara vários modelos de classificação (aprovado/reprovado), guardando o melhor."""
    # Classificação usa só hábitos/demografia (sem G1/G2) — é a variante "interpretativa".
    feature_cols = config.FEATURES_NO_GRADES
    X = df[feature_cols]
    y = df[config.TARGET_CLASSIFICATION]
    # stratify=y: garante que a proporção de aprovados/reprovados é igual no treino e no teste.
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=config.TEST_SIZE, random_state=config.RANDOM_STATE, stratify=y
    )

    candidates = {
        "LogisticRegression": LogisticRegression(max_iter=1000),
        "RandomForestClassifier": RandomForestClassifier(
            n_estimators=300, random_state=config.RANDOM_STATE, max_depth=8
        ),
        "GradientBoostingClassifier": GradientBoostingClassifier(random_state=config.RANDOM_STATE),
    }

    results = {}
    best_name, best_pipe, best_score = None, None, -np.inf
    for name, model in candidates.items():
        pipe = Pipeline([
            ("prep", build_preprocessor(feature_cols)),
            ("model", model),
        ])
        # scoring="f1": prioriza o equilíbrio entre precisão e recall (mais
        # relevante do que "accuracy" quando as classes não estão equilibradas).
        cv_scores = cross_val_score(pipe, X_train, y_train, cv=5, scoring="f1")
        pipe.fit(X_train, y_train)
        y_pred = pipe.predict(X_test)
        # predict_proba dá as probabilidades de cada classe; [:, 1] é a probabilidade da classe "aprovado".
        y_proba = pipe.predict_proba(X_test)[:, 1]
        metrics = evaluate_classification(y_test, y_pred, y_proba)
        metrics["CV_F1_mean"] = round(cv_scores.mean(), 4)
        metrics["CV_F1_std"] = round(cv_scores.std(), 4)
        results[name] = metrics

        if metrics["F1"] > best_score:
            best_name, best_pipe, best_score = name, pipe, metrics["F1"]

    model_path = config.MODELS_DIR / "classification_habitos.joblib"
    joblib.dump({"pipeline": best_pipe, "features": feature_cols, "best_model": best_name}, model_path)

    return {"results": results, "best_model": best_name, "model_path": str(model_path)}


def get_feature_importance(pipe: Pipeline, feature_cols: list[str], top_n: int = 15):
    """Extrai a importância de cada variável no modelo treinado, para explicar o que mais pesa nas previsões."""
    # "model" e "prep" são os nomes dados aos passos do Pipeline (ver build_preprocessor/train_*).
    model = pipe.named_steps["model"]
    prep = pipe.named_steps["prep"]
    try:
        # Nomes finais das colunas depois do one-hot encoding (ex.: "school_GP", "school_MS").
        feature_names = prep.get_feature_names_out()
    except Exception:
        feature_names = feature_cols

    if hasattr(model, "feature_importances_"):
        # Modelos baseados em árvores (Random Forest, Gradient Boosting) têm este atributo.
        importances = model.feature_importances_
    elif hasattr(model, "coef_"):
        # Modelos lineares (Regressão Linear/Logística): usa o valor absoluto dos coeficientes.
        importances = np.abs(model.coef_).flatten()
    else:
        # Modelo sem forma conhecida de extrair importância — não é possível calcular.
        return None

    # Ordena as variáveis da mais para a menos importante, e mantém só as top_n primeiras.
    fi = pd.Series(importances, index=feature_names).sort_values(ascending=False).head(top_n)
    return fi


def write_report(reg_no_grades, reg_with_grades, clf, fi_habitos):
    """Escreve o relatório de modelação (reports/model_report.md) com todas as métricas calculadas."""
    lines = ["# Relatório de Modelação — Previsão de Desempenho Académico\n"]

    lines.append("\n## 1. Regressão — prever nota final (G3)\n")
    for variant_result in (reg_no_grades, reg_with_grades):
        lines.append(f"\n### Variante: `{variant_result['variant']}`\n")
        lines.append(f"Melhor modelo: **{variant_result['best_model']}**\n\n")
        lines.append("| Modelo | R2 | MAE | RMSE | CV R2 (média ± dp) |\n")
        lines.append("|---|---|---|---|---|\n")
        for name, m in variant_result["results"].items():
            lines.append(f"| {name} | {m['R2']} | {m['MAE']} | {m['RMSE']} | {m['CV_R2_mean']} ± {m['CV_R2_std']} |\n")

    lines.append("\n## 2. Classificação — aprovado vs reprovado (apenas hábitos, sem G1/G2)\n")
    lines.append(f"Melhor modelo: **{clf['best_model']}**\n\n")
    lines.append("| Modelo | Accuracy | Precision | Recall | F1 | ROC-AUC | CV F1 (média ± dp) |\n")
    lines.append("|---|---|---|---|---|---|---|\n")
    for name, m in clf["results"].items():
        lines.append(
            f"| {name} | {m['Accuracy']} | {m['Precision']} | {m['Recall']} | {m['F1']} | "
            f"{m['ROC_AUC']} | {m['CV_F1_mean']} ± {m['CV_F1_std']} |\n"
        )

    if fi_habitos is not None:
        lines.append("\n## 3. Importância das variáveis (modelo de hábitos, top 15)\n")
        for feat, val in fi_habitos.items():
            lines.append(f"- `{feat}`: {val:.4f}\n")

    lines.append("\n## Conclusão\n")
    lines.append(
        "O modelo que inclui as notas de períodos anteriores (G1/G2) tem, como esperado, "
        "maior poder preditivo - mas o modelo baseado apenas em hábitos e contexto "
        "(sem G1/G2) já explica uma parte relevante da variação da nota final, confirmando "
        "que fatores como tempo de estudo, faltas, reprovações anteriores e consumo de "
        "álcool têm impacto mensurável no desempenho académico.\n"
    )

    report_path = config.REPORTS_DIR / "model_report.md"
    report_path.write_text("".join(lines), encoding="utf-8")
    return report_path


def run_training():
    """Corre o pipeline completo de treino: os dois modelos de regressão + o de classificação."""
    df = get_processed_data()

    # Treina as duas variantes de regressão (sem notas / com notas) e o modelo de classificação.
    reg_no_grades = train_regression_variant(df, config.FEATURES_NO_GRADES, "habitos")
    reg_with_grades = train_regression_variant(df, config.FEATURES_WITH_GRADES, "completo")
    clf = train_classification(df)

    # Recarrega o melhor modelo de classificação já gravado, só para calcular a importância das variáveis.
    best_clf_data = joblib.load(clf["model_path"])
    fi = get_feature_importance(best_clf_data["pipeline"], config.FEATURES_NO_GRADES)

    # Escreve o relatório em Markdown, legível por humanos.
    report_path = write_report(reg_no_grades, reg_with_grades, clf, fi)

    # Guarda também um resumo em JSON, para ser lido facilmente por código (ex.: pela API).
    summary = {
        "regressao_habitos": reg_no_grades,
        "regressao_completo": reg_with_grades,
        "classificacao": clf,
    }
    (config.REPORTS_DIR / "model_metrics.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"Treino concluído. Relatório: {report_path}")
    print(f"Modelos guardados em: {config.MODELS_DIR}")
    return summary


# Permite correr "python -m src.train_model" diretamente a partir da linha de comandos.
if __name__ == "__main__":
    run_training()
