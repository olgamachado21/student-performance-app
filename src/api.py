"""
API REST (FastAPI) que expõe a análise e os modelos de previsão, e serve também
a interface web (HTML/CSS/JS em web/) — tudo a partir de um único endereço.

Correr localmente:
    uvicorn src.api:app --reload
Depois abre http://127.0.0.1:8000 no browser (ou usa desktop_app.py para uma
janela nativa, sem browser).
Documentação interativa da API em http://127.0.0.1:8000/docs
"""
from __future__ import annotations

# lru_cache: guarda em cache o resultado de funções (dataset processado, modelo carregado).
from functools import lru_cache
# Optional: para campos/parâmetros que podem não ser fornecidos.
from typing import Optional

# json: para ler o ficheiro de métricas dos modelos.
import json
# logging: para registar no terminal (consola do servidor) o erro completo
# (incluindo o traceback) sempre que algo corre mal de forma inesperada num
# pedido — ex.: um ficheiro carregado pelo utilizador (CSV/Excel) com um
# formato tão fora do previsto que nem chega a ser apanhado como um erro
# "normal" (ValueError). Sem isto, o utilizador só via "Erro 500" sem
# qualquer pista do que realmente aconteceu, e nós não tínhamos como
# diagnosticar à distância.
import logging

# joblib: para carregar modelos treinados a partir de ficheiro.
import joblib
# pandas: para trabalhar com o dataset como tabela.
import pandas as pd
# FastAPI: framework usado para construir a API. File/UploadFile: para
# receber ficheiros (CSV) por upload. HTTPException: para devolver erros
# HTTP com código e mensagem. Query: para parâmetros de query string com validação.
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
# CORSMiddleware: permite que a interface web chame a API mesmo vinda de outra origem.
from fastapi.middleware.cors import CORSMiddleware
# Response: para devolver respostas "cruas" (PDF, ZIP, CSV) em vez de JSON.
from fastapi.responses import Response
# StaticFiles: para servir os ficheiros estáticos da interface web (HTML/CSS/JS).
from fastapi.staticfiles import StaticFiles
# BaseModel/Field: para definir e validar os dados recebidos em cada pedido (payloads).
from pydantic import BaseModel, Field

from src import config
from src.add_student import add_student as add_student_fn
from src.alerts import generate_alerts, get_at_risk_students
from src.data_processing import get_processed_data
from src.optimizer import otimizar_plano_estudo, simular_intervencao_turma
from src.predict import (detect_outliers, explain_prediction,
                          full_prediction, get_defaults)
from src.reports_pdf import (gerar_ficha_pdf, gerar_fichas_lote_zip,
                              gerar_relatorio_turma_pdf)
from src.segmentation import SEGMENTATION_FEATURES, radar_profile, run_segmentation
from src.statistics_analysis import (compare_multiple_groups, compare_two_groups,
                                      generate_overview_summary, simple_linear_regression)
from src.bulk_import import add_students_bulk
from src.chatbot import EXAMPLE_QUESTIONS, answer_question
from src import custom_dataset
from src.data_export import export_students_csv
from src.data_quality import check_unusual_values
from src.suggestions import suggest_field_values
from src import settings as settings_module
from src import prediction_tracking
from src import notes as notes_module
from src import exam_week
from src import backup as backup_module
from src.train_model import compute_naive_baseline, get_feature_importance

# Logger da API — usado nos pontos onde se recebe conteúdo imprevisível do
# utilizador (ficheiros carregados) para que, se algo correr mal de um jeito
# não antecipado, o erro completo (com traceback) fique visível no terminal
# onde o servidor está a correr, em vez de se perder.
logger = logging.getLogger("studentperfomance.api")

# Pasta onde está a interface web (HTML/CSS/JS), servida no fim deste ficheiro.
WEB_DIR = config.BASE_DIR / "web"

# Instância principal da aplicação FastAPI — todos os endpoints (@app.get/@app.post/...)
# ficam registados nela.
app = FastAPI(
    title="StudentPerfomance API — Desempenho Académico e Hábitos de Estudo",
    description=(
        "API para analisar e prever o desempenho académico de estudantes "
        "com base nos seus hábitos de estudo e estilo de vida."
    ),
    version="1.1.0",
)

# Permitir que a interface web (servida de outra origem/porta) chame a API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def no_cache_for_web_assets(request, call_next):
    """Evita que a janela do desktop (WebView) fique presa em versões antigas
    do HTML/CSS/JS depois de uma atualização — o motor de renderização do
    Windows guarda cache entre execuções da app (ao contrário de um separador
    de navegador normal), por isso sem isto era possível abrir a app e
    continuar a ver o código antigo mesmo depois de corrigido."""
    # Deixa o pedido seguir normalmente, e só depois ajusta os cabeçalhos da resposta.
    response = await call_next(request)
    path = request.url.path
    # Só desativa a cache para a página principal e os ficheiros estáticos (não para a API).
    if path == "/" or path.endswith((".js", ".css", ".html")):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


@lru_cache(maxsize=1)
def _dataset() -> pd.DataFrame:
    """Dataset processado, carregado uma única vez e reutilizado por todos os endpoints."""
    return get_processed_data()


@lru_cache(maxsize=1)
def _classification_artifact():
    """Carrega o modelo de classificação (aprovado/reprovado) treinado, uma única vez."""
    path = config.MODELS_DIR / "classification_habitos.joblib"
    return joblib.load(path)


# Campos aceites no corpo de um pedido de previsão (/predict, /predict/explain, etc.) —
# todos opcionais: o que não for indicado é preenchido com o valor típico do dataset.
class StudentInput(BaseModel):
    studytime: Optional[int] = Field(None, ge=1, le=4, description="1=<2h, 2=2-5h, 3=5-10h, 4=>10h por semana")
    absences: Optional[int] = Field(None, ge=0, le=93, description="Número de faltas")
    failures: Optional[int] = Field(None, ge=0, le=4, description="Reprovações anteriores")
    goout: Optional[int] = Field(None, ge=1, le=5, description="Sair com amigos (1=muito pouco, 5=muito)")
    freetime: Optional[int] = Field(None, ge=1, le=5)
    Dalc: Optional[int] = Field(None, ge=1, le=5, description="Consumo de álcool em dias úteis")
    Walc: Optional[int] = Field(None, ge=1, le=5, description="Consumo de álcool ao fim de semana")
    health: Optional[int] = Field(None, ge=1, le=5)
    traveltime: Optional[int] = Field(None, ge=1, le=4)
    famrel: Optional[int] = Field(None, ge=1, le=5)
    internet: Optional[str] = Field(None, description="'yes' ou 'no'")
    higher: Optional[str] = Field(None, description="Deseja estudo superior: 'yes'/'no'")
    schoolsup: Optional[str] = Field(None, description="Apoio educativo extra: 'yes'/'no'")
    famsup: Optional[str] = Field(None)
    paid: Optional[str] = Field(None, description="Explicações pagas: 'yes'/'no'")
    activities: Optional[str] = Field(None)
    romantic: Optional[str] = Field(None)
    sex: Optional[str] = Field(None, description="'F' ou 'M'")
    age: Optional[int] = Field(None, ge=15, le=22)
    address: Optional[str] = Field(None, description="'U' (urbano) ou 'R' (rural)")
    Medu: Optional[int] = Field(None, ge=0, le=4)
    Fedu: Optional[int] = Field(None, ge=0, le=4)
    G1: Optional[int] = Field(None, ge=0, le=20, description="Nota do 1º período (opcional)")
    G2: Optional[int] = Field(None, ge=0, le=20, description="Nota do 2º período (opcional)")

    class Config:
        # Permite campos extra além dos listados acima, sem dar erro de validação
        # (útil porque a app envia por vezes mais campos do que os estritamente necessários).
        extra = "allow"


@app.on_event("startup")
def _start_background_jobs():
    """
    Arranca o agendador de backups automáticos da base de dados assim que a
    API sobe (tanto a correr como servidor web normal, como dentro da app de
    desktop — ver desktop_app.py, que também usa este mesmo "app"). Corre
    numa thread em segundo plano (ver src/backup.py) e nunca bloqueia o
    arranque da aplicação, mesmo que a base de dados ainda não exista ou o
    motor configurado seja SQL Server (nesse caso simplesmente não faz nada,
    de forma silenciosa — ver _require_sqlite em src/backup.py).
    """
    backup_module.start_auto_backup()


@app.get("/health")
def health():
    """Endpoint simples para verificar se a API está a responder."""
    return {"status": "ok"}


@app.get("/meta")
def meta():
    """Metadados dos campos esperados — útil para gerar o formulário da interface web."""
    return {
        "habit_fields": config.HABIT_COLS,
        "demographic_fields": config.DEMOGRAPHIC_COLS,
        "grade_fields": config.GRADE_COLS,
        "pass_threshold": config.PASS_THRESHOLD,
        "grade_scale": "0-20",
    }


@app.get("/stats")
def stats():
    """Estatísticas gerais do dataset (KPIs), para a página de Visão Geral."""
    df = _dataset()
    return {
        "n_students": int(len(df)),
        "average_grade": round(float(df["G3"].mean()), 2),
        "pass_rate": round(float(df["aprovado"].mean()), 4),
        "average_studytime_level": round(float(df["studytime"].mean()), 2),
        "average_absences": round(float(df["absences"].mean()), 2),
        "pass_rate_by_studytime": df.groupby("studytime")["aprovado"].mean().round(4).to_dict(),
        "avg_grade_by_internet": df.groupby("internet")["G3"].mean().round(2).to_dict(),
        # Resumo automático em linguagem natural (ver generate_overview_summary
        # em src/statistics_analysis.py) — recalculado sempre a partir do
        # dataset atual, não é texto fixo.
        "summary_text": generate_overview_summary(df),
    }


@app.get("/grade-distribution")
def grade_distribution():
    """Histograma da nota final (G3), pronto a desenhar num gráfico de barras."""
    df = _dataset()
    # Divide as notas em 20 intervalos ("bins") e conta quantos estudantes caem em cada um.
    counts, bin_edges = pd.cut(df["G3"], bins=20, retbins=True)
    hist = counts.value_counts(sort=False)
    # Constrói os rótulos de cada intervalo (ex.: "8.5-9.0"), a partir dos limites calculados.
    labels = [f"{bin_edges[i]:.1f}-{bin_edges[i+1]:.1f}" for i in range(len(bin_edges) - 1)]
    return {
        "labels": labels,
        "counts": [int(v) for v in hist.values],
        "pass_threshold": config.PASS_THRESHOLD,
    }


@app.get("/pass-fail-counts")
def pass_fail_counts():
    """Contagem aprovados vs reprovados, para um gráfico circular (donut)."""
    df = _dataset()
    counts = df["aprovado"].value_counts()
    return {
        "aprovados": int(counts.get(1, 0)),
        "reprovados": int(counts.get(0, 0)),
    }


@app.get("/correlations")
def correlations():
    """Matriz de correlação entre variáveis numéricas e a nota final, para um heatmap."""
    df = _dataset()
    cols = config.NUMERIC_COLS + ["G3"]
    corr = df[cols].corr().round(3)
    return {
        "columns": list(corr.columns),
        "matrix": corr.values.tolist(),
    }


@app.get("/scatter")
def scatter(
    x: str = Query(..., description="Variável no eixo X (uma das colunas do heatmap de correlação)"),
    y: str = Query(..., description="Variável no eixo Y (uma das colunas do heatmap de correlação)"),
):
    """
    Pontos individuais (x, y) e reta de regressão linear simples para um par
    de variáveis — usado quando se clica numa célula do heatmap de correlação
    em Fatores de Risco, para ver a relação real por trás de um único
    coeficiente de correlação.
    """
    df = _dataset()
    valid_cols = config.NUMERIC_COLS + ["G3"]
    # Valida que as duas variáveis pedidas são conhecidas, antes de calcular seja o que for.
    if x not in valid_cols or y not in valid_cols:
        raise HTTPException(
            status_code=400,
            detail=f"Variáveis inválidas. Escolhe entre: {', '.join(valid_cols)}",
        )

    # Mesma variável nos dois eixos: df[[x, y]] daria duas colunas com o
    # mesmo nome (sub[x] deixaria de ser uma Series só), por isso este caso
    # trata-se à parte — sem regressão (não faz sentido "prever x a partir
    # de x"), com os pontos todos sobre a diagonal.
    if x == y:
        xs = ys = df[[x]].astype(float).dropna()[x]
        reg = None
    else:
        # Remove linhas com valores em falta em qualquer uma das duas colunas.
        sub = df[[x, y]].astype(float).dropna()
        xs, ys = sub[x], sub[y]
        reg = simple_linear_regression(sub, x_col=x, y_col=y)

    return {
        "x": x,
        "y": y,
        "points": [{"x": round(float(a), 2), "y": round(float(b), 2)} for a, b in zip(xs, ys)],
        "regression": reg,
    }


@app.get("/feature-importance")
def feature_importance():
    """Importância das variáveis no modelo de classificação (aprovado/reprovado)."""
    artifact = _classification_artifact()
    fi = get_feature_importance(artifact["pipeline"], artifact["features"], top_n=10)
    if fi is None:
        # get_feature_importance devolve None quando o modelo não tem
        # feature_importances_ nem coef_ (não acontece com os modelos atuais
        # da StudentPerfomance, mas fica aqui como salvaguarda explícita em
        # vez de deixar rebentar mais abaixo com um erro pouco claro).
        raise HTTPException(
            status_code=404,
            detail="Não foi possível calcular a importância das variáveis para o modelo atual.",
        )
    # Remove os prefixos técnicos ("num__"/"cat__") que o pré-processador
    # acrescenta aos nomes das colunas, para ficarem legíveis na interface.
    fi = fi.rename(lambda x: x.replace("num__", "").replace("cat__", ""))
    return {
        "features": list(fi.index),
        "importance": [round(float(v), 4) for v in fi.values],
    }


@app.get("/group-stats")
def group_stats(variable: str = Query(..., description="Nome da coluna a agrupar, ex: studytime, goout, Dalc")):
    """Nota média e nº de estudantes por categoria de uma variável (para gráfico de barras/boxplot)."""
    df = _dataset()
    if variable not in df.columns:
        raise HTTPException(status_code=400, detail=f"Variável '{variable}' não existe no dataset.")

    grouped = df.groupby(variable)["G3"]
    result = {
        "variable": variable,
        "categories": [str(c) for c in grouped.mean().index],
        "avg_grade": [round(float(v), 2) for v in grouped.mean().values],
        "n_students": [int(v) for v in grouped.count().values],
        # quartis, úteis para desenhar um boxplot simplificado no frontend
        "q1": [round(float(v), 2) for v in grouped.quantile(0.25).values],
        "median": [round(float(v), 2) for v in grouped.median().values],
        "q3": [round(float(v), 2) for v in grouped.quantile(0.75).values],
    }
    return result


@app.get("/statistical-tests")
def statistical_tests():
    """
    Resumo dos testes estatísticos (t-test/ANOVA/regressão simples) usados
    nos destaques da app.

    Inclui, além dos hábitos já cobertos, um bloco de contexto familiar e
    socioeconómico (paid, school, address, Mjob, Fjob, reason, Medu, Fedu)
    — colunas que já estavam limpas na base de dados mas nunca tinham sido
    analisadas na interface, apesar de o dataset original (Cortez & Silva,
    2008) já apontar estas variáveis como relevantes.
    """
    df = _dataset()
    return {
        "internet": compare_two_groups(df, "internet"),
        "higher": compare_two_groups(df, "higher"),
        "studytime_regression": simple_linear_regression(df, "studytime"),
        "failures_regression": simple_linear_regression(df, "failures"),
        "alcohol_regression": simple_linear_regression(df, "alcohol_avg"),
        # --- Contexto familiar e socioeconómico ---
        "paid": compare_two_groups(df, "paid"),
        "school": compare_two_groups(df, "school"),
        "address": compare_two_groups(df, "address"),
        "mjob": compare_multiple_groups(df, "Mjob"),
        "fjob": compare_multiple_groups(df, "Fjob"),
        "reason": compare_multiple_groups(df, "reason"),
        "medu_regression": simple_linear_regression(df, "Medu"),
        "fedu_regression": simple_linear_regression(df, "Fedu"),
        # Apoio educativo extra: incluído aqui (e não só no relatório
        # offline de statistics_analysis.py) porque o resultado é
        # contra-intuitivo — quem tem apoio tem nota mais baixa — e a
        # interface precisa de mostrar o contexto de causalidade inversa
        # junto do número, não deixá-lo mal interpretado.
        "schoolsup": compare_two_groups(df, "schoolsup"),
        # Efeito de teto do tempo de estudo: a mesma regressão simples de
        # sempre (studytime -> G3), mas calculada em separado para quem
        # nunca reprovou e para quem já reprovou pelo menos uma vez — o
        # modelo de regressão linear usado no Otimizador de Estudo não tem
        # termo de interação, por isso não capta sozinho que o ganho de
        # estudar mais é bem mais fraco (e deixa de ser significativo) em
        # quem já reprovou. Ver optimizer.py e prediction.js, que usam
        # estes dois valores para não prometer a mesma coisa a todos.
        "studytime_regression_no_failures": simple_linear_regression(
            df[df["failures"] == 0], "studytime"
        ),
        "studytime_regression_with_failures": simple_linear_regression(
            df[df["failures"] >= 1], "studytime"
        ),
    }


@app.get("/model-metrics")
def model_metrics():
    """
    Métricas de qualidade dos modelos de Machine Learning (R²/MAE/RMSE para a
    regressão da nota final, Accuracy/Precision/Recall/F1/ROC-AUC para a
    classificação aprovado/reprovado, com validação cruzada) — já calculadas
    uma vez no treino (ver train_model.py) e gravadas em
    reports/model_metrics.json; este endpoint só as lê e devolve, sem
    recalcular nada. Sem isto, estas métricas só existiam num ficheiro,
    nunca chegavam à interface.

    Inclui também um baseline "ingénuo" (prever sempre a média da turma,
    ver compute_naive_baseline) calculado em tempo real a partir do mesmo
    split treino/teste — não vem do ficheiro porque não precisa de
    retreino nenhum, é só a referência mínima que os modelos reais têm de
    superar para a comparação fazer sentido na interface.
    """
    path = config.REPORTS_DIR / "model_metrics.json"
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="Métricas do modelo ainda não foram geradas — corre o treino (train_model.py) primeiro.",
        )
    data = json.loads(path.read_text(encoding="utf-8"))

    # O caminho do ficheiro .joblib no disco é um detalhe interno de
    # implementação (e muda consoante o computador) — não faz sentido
    # mostrá-lo na interface, por isso não sai daqui.
    def _strip_path(variant: dict) -> dict:
        return {k: v for k, v in variant.items() if k != "model_path"}

    # Baseline calculado em tempo real (não vem do ficheiro), sobre o dataset atual.
    baseline = compute_naive_baseline(get_processed_data())

    def _best_mae(variant: dict) -> float:
        # MAE do melhor modelo escolhido para esta variante.
        return variant["results"][variant["best_model"]]["MAE"]

    def _improvement_pct(model_mae: float) -> float:
        # Quanto o modelo real melhora face ao baseline ingénuo, em percentagem.
        if baseline["MAE"] == 0:
            return 0.0
        return round((1 - model_mae / baseline["MAE"]) * 100, 1)

    return {
        "regressao_habitos": _strip_path(data["regressao_habitos"]),
        "regressao_completo": _strip_path(data["regressao_completo"]),
        "classificacao": _strip_path(data["classificacao"]),
        "baseline_ingenuo": {
            **baseline,
            "melhoria_habitos_pct": _improvement_pct(_best_mae(data["regressao_habitos"])),
            "melhoria_completo_pct": _improvement_pct(_best_mae(data["regressao_completo"])),
        },
    }


@app.get("/outliers")
def outliers(
    z_threshold: float = Query(2.0, ge=0.5, le=5.0, description="Nº de desvios-padrão de resíduo a partir do qual um estudante é sinalizado"),
    limit: int = Query(20, ge=1, le=100, description="Nº máximo de estudantes devolvidos"),
):
    """
    Estudantes cujo resultado foge do que seria esperado dado o seu próprio
    perfil (ver detect_outliers em src/predict.py) — não "quem tem nota
    baixa", mas "quem se desviou muito do que o modelo previa para o SEU
    perfil", para cima ou para baixo.
    """
    df = _dataset()
    students_list = detect_outliers(df, z_threshold=z_threshold, limit=limit)
    return {
        "z_threshold": z_threshold,
        "n_outliers": len(students_list),
        "students": students_list,
    }


@app.get("/students")
def students(
    sex: Optional[str] = Query(None, description="F, M ou vazio para ambos"),
    internet: Optional[str] = Query(None, description="yes, no ou vazio para ambos"),
    higher: Optional[str] = Query(None, description="yes, no ou vazio para ambos"),
    studytime_min: int = Query(1, ge=1, le=4),
    studytime_max: int = Query(4, ge=1, le=4),
    limit: int = Query(200, ge=1, le=649),
):
    """Lista filtrada de estudantes + estatísticas do subgrupo, para a página de Perfil do Estudante."""
    df = _dataset()
    # Aplica os filtros um a um, só se o parâmetro correspondente tiver sido indicado.
    filtered = df[df["studytime"].between(studytime_min, studytime_max)]
    if sex:
        filtered = filtered[filtered["sex"] == sex]
    if internet:
        filtered = filtered[filtered["internet"] == internet]
    if higher:
        filtered = filtered[filtered["higher"] == higher]

    cols = ["student_id", "sex", "age", "studytime", "absences", "failures",
            "internet", "G1", "G2", "G3", "aprovado", "progress_badge"]

    # Percentil de cada estudante, sempre calculado sobre o dataset COMPLETO
    # (não sobre o subgrupo filtrado) — para "estás no percentil 80" ter
    # sempre o mesmo significado, quaisquer que sejam os filtros ativos na
    # página. rank(pct=True) dá a fração de estudantes com valor <= ao seu
    # (empates partilham a mesma posição), por isso 100 = melhor nota da
    # turma toda, 0 = pior.
    percentile_g3 = df["G3"].rank(pct=True) * 100
    percentile_studytime = df["studytime"].rank(pct=True) * 100
    percentile_absences = df["absences"].rank(pct=True) * 100

    # Limita o resultado filtrado ao número pedido, e junta as colunas de percentil calculadas.
    result_df = filtered[cols].head(limit).copy()
    result_df["percentile_g3"] = percentile_g3.loc[result_df.index].round(1)
    result_df["percentile_studytime"] = percentile_studytime.loc[result_df.index].round(1)
    result_df["percentile_absences"] = percentile_absences.loc[result_df.index].round(1)

    return {
        "n_students": int(len(filtered)),
        "average_grade": round(float(filtered["G3"].mean()), 2) if len(filtered) else None,
        "pass_rate": round(float(filtered["aprovado"].mean()), 4) if len(filtered) else None,
        "average_absences": round(float(filtered["absences"].mean()), 2) if len(filtered) else None,
        "overall_average_grade": round(float(df["G3"].mean()), 2),
        "overall_pass_rate": round(float(df["aprovado"].mean()), 4),
        "overall_average_absences": round(float(df["absences"].mean()), 2),
        "students": result_df.to_dict(orient="records"),
    }


@app.get("/profile/radar")
def profile_radar(
    sex: Optional[str] = Query(None, description="F, M ou vazio para ambos"),
    internet: Optional[str] = Query(None, description="yes, no ou vazio para ambos"),
    higher: Optional[str] = Query(None, description="yes, no ou vazio para ambos"),
    studytime_min: int = Query(1, ge=1, le=4),
    studytime_max: int = Query(4, ge=1, le=4),
):
    """
    Médias normalizadas (0-100) de um conjunto de hábitos para o subgrupo
    filtrado (os mesmos filtros de /students) vs a turma toda — pronto para
    o gráfico radar do Perfil do Estudante (ver radar_profile em
    src/segmentation.py).
    """
    df = _dataset()
    # Constrói a máscara de filtro combinando todas as condições indicadas (operador &= acumula).
    mask = df["studytime"].between(studytime_min, studytime_max)
    if sex:
        mask &= df["sex"] == sex
    if internet:
        mask &= df["internet"] == internet
    if higher:
        mask &= df["higher"] == higher
    return radar_profile(df, mask)


@app.get("/defaults")
def defaults():
    """Valores por omissão usados para campos não fornecidos numa previsão."""
    return get_defaults()


@app.post("/predict")
def predict(student: StudentInput):
    """
    Recebe os hábitos/contexto de um estudante e devolve:
      - nota final prevista (apenas com base em hábitos)
      - probabilidade de aprovação
      - nota final prevista incluindo G1/G2, se fornecidas
    Campos não fornecidos são preenchidos com valores medianos/mais frequentes do dataset.
    """
    try:
        # exclude_none=True: só inclui os campos que o utilizador realmente preencheu.
        user_input = student.model_dump(exclude_none=True)
        result = full_prediction(user_input)
        return result
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/predict/explain")
def predict_explain(student: StudentInput):
    """
    Explica a previsão de hábitos deste estudante em concreto: para cada
    fator, o quanto o SEU valor (não o de toda a gente) está a puxar a nota
    prevista para cima ou para baixo, face ao valor típico do dataset.
    Ver explain_prediction em src/predict.py para o método exato.
    """
    try:
        user_input = student.model_dump(exclude_none=True)
        return explain_prediction(user_input)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# Igual a StudentInput, mais um rótulo opcional para identificar a previsão guardada.
class PredictionSnapshotInput(StudentInput):
    label: Optional[str] = Field(None, description="Ex.: 'Depois de aumentar tempo de estudo'")


@app.post("/predict/snapshots")
def save_prediction_snapshot(payload: PredictionSnapshotInput):
    """
    Comparação Antes/Depois: corre a mesma previsão do Simulador e guarda-a
    como ponto de partida, para mais tarde comparar com a nota real
    (ver /predict/snapshots/{id}/actual).
    """
    data = payload.model_dump(exclude_none=True)
    # Separa o rótulo (não faz parte dos hábitos usados na previsão).
    label = data.pop("label", "")
    try:
        prediction_result = full_prediction(data)
        return prediction_tracking.save_snapshot(prediction_result, data, label)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/predict/snapshots")
def list_prediction_snapshots():
    """Lista todas as previsões guardadas (histórico Antes/Depois)."""
    return {"snapshots": prediction_tracking.get_snapshots()}


@app.get("/predict/validation")
def prediction_validation_summary():
    """
    Validação do modelo com dados reais deste utilizador — ver
    get_validation_summary em src/prediction_tracking.py.
    """
    return prediction_tracking.get_validation_summary()


@app.get("/predict/accuracy-over-time")
def prediction_accuracy_over_time():
    """
    Acompanha a precisão do modelo ao longo do tempo (MAE acumulado à medida
    que mais notas reais são registadas) — ver get_accuracy_over_time em
    src/prediction_tracking.py.
    """
    return prediction_tracking.get_accuracy_over_time()


# Corpo do pedido para registar a nota real obtida (ver endpoint abaixo).
class ActualGradeInput(BaseModel):
    actual_grade: float = Field(..., ge=0, le=20)


@app.post("/predict/snapshots/{snapshot_id}/actual")
def record_prediction_snapshot_actual(snapshot_id: int, payload: ActualGradeInput):
    """Regista a nota real obtida, associando-a a uma previsão guardada anteriormente."""
    try:
        return prediction_tracking.record_actual_grade(snapshot_id, payload.actual_grade)
    except ValueError as exc:
        # Distingue "não encontrada" (404) de outros erros de validação (400).
        status = 404 if "não encontrada" in str(exc) else 400
        raise HTTPException(status_code=status, detail=str(exc))


@app.delete("/predict/snapshots/{snapshot_id}")
def delete_prediction_snapshot(snapshot_id: int):
    """Remove uma previsão guardada."""
    if not prediction_tracking.delete_snapshot(snapshot_id):
        raise HTTPException(status_code=404, detail=f"Previsão {snapshot_id} não encontrada.")
    return {"deleted": True}


# Corpo do pedido para criar um comentário (ver endpoint abaixo).
class NoteInput(BaseModel):
    student_id: int
    text: str = Field(..., min_length=1)
    # Opcional: título do alerta que motivou o comentário, quando criado a
    # partir da página Avisos e Alertas em vez do Perfil do Estudante.
    context: Optional[str] = None


@app.post("/notes")
def create_note(payload: NoteInput):
    """
    Regista um novo comentário associado a um estudante — ver src/notes.py.
    Mantém-se sempre ligado a um estudante real do dataset (ao contrário de
    um bloco de notas livre e independente), por isso valida primeiro que o
    student_id indicado existe.
    """
    df = _dataset()
    if payload.student_id not in set(df["student_id"]):
        raise HTTPException(status_code=404, detail=f"Estudante {payload.student_id} não encontrado.")
    try:
        return notes_module.add_note(payload.student_id, payload.text, payload.context)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/notes")
def list_notes(student_id: Optional[int] = Query(None, description="Filtra pelos comentários de um estudante")):
    """Lista os comentários guardados — todos, ou só os de um estudante (uso normal na UI)."""
    return {"notes": notes_module.get_notes(student_id)}


@app.delete("/notes/{note_id}")
def delete_note(note_id: int):
    """Remove um comentário."""
    if not notes_module.delete_note(note_id):
        raise HTTPException(status_code=404, detail=f"Comentário {note_id} não encontrado.")
    return {"deleted": True}


@app.post("/exam-week/checklist")
def exam_week_checklist(student: StudentInput):
    """
    Modo "Última Semana Antes do Exame": checklist curto com as mudanças de
    hábito ainda realistas em poucos dias, priorizadas pelo ganho estimado
    na previsão do modelo. Ver gerar_checklist_ultima_semana em
    src/exam_week.py para o método exato.
    """
    try:
        user_input = student.model_dump(exclude_none=True)
        return exam_week.gerar_checklist_ultima_semana(user_input)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/alerts")
def alerts():
    """Avisos automáticos gerados a partir do estado atual dos dados."""
    df = _dataset()
    return {
        "alerts": generate_alerts(df),
        "at_risk_students": get_at_risk_students(df, limit=50),
        "n_at_risk": int(df["at_risk"].sum()),
        "risk_rate": round(float(df["at_risk"].mean()), 4),
    }


@app.get("/segmentation-features")
def segmentation_features():
    """Lista de variáveis disponíveis para compor a segmentação, para a UI montar os checkboxes."""
    return {"features": SEGMENTATION_FEATURES}


@app.get("/segmentation")
def segmentation(
    n_clusters: int = Query(4, ge=3, le=8, description="Número de perfis (3 a 8)"),
    features: Optional[str] = Query(
        None,
        description="Variáveis a incluir no K-Means, separadas por vírgula (mín. 2). Por omissão usa todas.",
    ),
):
    """Segmentação de estudantes em perfis comportamentais (K-Means)."""
    df = _dataset()
    feature_list = None
    if features is not None:
        # Converte a string "a,b,c" numa lista ["a", "b", "c"], ignorando espaços/entradas vazias.
        feature_list = [f.strip() for f in features.split(",") if f.strip()]
        if not feature_list:
            feature_list = None
    try:
        return run_segmentation(df, n_clusters=n_clusters, features=feature_list)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/ficha/{student_id}")
def ficha_desempenho(student_id: int):
    """Gera e devolve o PDF da ficha de desempenho de um estudante."""
    df = _dataset()
    try:
        pdf_bytes = gerar_ficha_pdf(df, student_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    # Devolve o PDF diretamente como resposta HTTP (não como JSON).
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="ficha_estudante_{student_id}.pdf"'},
    )


@app.get("/reports/class")
def class_report():
    """Gera e devolve o PDF do relatório agregado de turma (KPIs, segmentação e estudantes em risco)."""
    df = _dataset()
    pdf_bytes = gerar_relatorio_turma_pdf(df)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="relatorio_turma.pdf"'},
    )


@app.get("/reports/fichas-lote")
def fichas_lote(
    only_at_risk: bool = Query(True, description="Só estudantes em risco (True) ou todos (False)"),
    limit: int = Query(100, ge=1, le=300, description="Nº máximo de fichas a incluir"),
):
    """Gera e devolve um ZIP com as fichas de desempenho PDF de vários estudantes de uma vez."""
    df = _dataset()
    try:
        zip_bytes = gerar_fichas_lote_zip(df, only_at_risk=only_at_risk, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="fichas_desempenho.zip"'},
    )


# Corpo do pedido para adicionar um novo estudante — só os campos do
# formulário têm valores por omissão sensatos; nome/disciplina/ano são
# apenas identificação, nunca usados pelo modelo.
class NewStudentInput(BaseModel):
    school: str = Field("GP", description="'GP' ou 'MS'")
    sex: str = Field("F", description="'F' ou 'M'")
    age: int = Field(17, ge=15, le=22)
    studytime: int = Field(2, ge=1, le=4)
    absences: int = Field(0, ge=0, le=93)
    failures: int = Field(0, ge=0, le=4)
    G1: int = Field(10, ge=0, le=20, description="Nota do 1º período")
    G2: int = Field(10, ge=0, le=20, description="Nota do 2º período")
    # Metadados só de organização/identificação — não fazem parte do dataset
    # original nem são usados pelo modelo de previsão (ver add_student.py).
    nome: str = Field("", max_length=120, description="Nome do estudante (opcional)")
    disciplina: str = Field("", max_length=80, description="Disciplina/matéria (opcional)")
    ano: str = Field("", max_length=40, description="Ano/nível escolar (opcional)")


@app.post("/students/add")
def students_add(student: NewStudentInput):
    """
    Adiciona um novo estudante ao dataset. A nota final (G3) é sempre
    prevista automaticamente pelo modelo — não é inserida manualmente.
    """
    try:
        result = add_student_fn(student.model_dump())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # o dataset mudou: limpar a cache para os próximos pedidos refletirem o novo estudante
    _dataset.cache_clear()
    df = _dataset()

    return {
        **result,
        "dataset_stats": {
            "n_students": int(len(df)),
            "average_grade": round(float(df["G3"].mean()), 2),
            "pass_rate": round(float(df["aprovado"].mean()), 4),
            "risk_rate": round(float(df["at_risk"].mean()), 4),
        },
    }


class SuggestValuesInput(BaseModel):
    """Todos os campos são opcionais — representam o que o utilizador já
    escreveu no formulário "Adicionar Dados" até agora, campo a campo."""
    school: Optional[str] = Field(None, description="'GP' ou 'MS'")
    sex: Optional[str] = Field(None, description="'F' ou 'M'")
    age: Optional[int] = Field(None, ge=15, le=22)
    studytime: Optional[int] = Field(None, ge=1, le=4)
    absences: Optional[int] = Field(None, ge=0, le=93)
    failures: Optional[int] = Field(None, ge=0, le=4)
    G1: Optional[int] = Field(None, ge=0, le=20)
    G2: Optional[int] = Field(None, ge=0, le=20)


@app.post("/students/suggest-values")
def students_suggest_values(fields: SuggestValuesInput):
    """
    Sugere valores prováveis para os campos do formulário "Adicionar Dados"
    ainda não preenchidos, com base nos estudantes já existentes mais
    parecidos com o que o utilizador já escreveu (ver src/suggestions.py) —
    em vez da mediana/moda de todo o dataset, usada quando nenhum campo
    ainda foi preenchido.
    """
    # Mantém só os campos que o utilizador realmente preencheu (ignora None e strings vazias).
    known = {k: v for k, v in fields.model_dump().items() if v is not None and v != ""}
    return suggest_field_values(_dataset(), known)


@app.post("/students/check-values")
def students_check_values(fields: SuggestValuesInput):
    """
    Avisa sobre valores pouco habituais ou inconsistentes entre si nos
    campos já preenchidos do formulário "Adicionar Dados" — não bloqueia
    nada, é só um alerta para ajudar a apanhar erros de digitação antes de
    gravar (ver src/data_quality.py).
    """
    known = {k: v for k, v in fields.model_dump().items() if v is not None and v != ""}
    return {"warnings": check_unusual_values(_dataset(), known)}


@app.post("/students/bulk-import")
async def students_bulk_import(file: UploadFile = File(...)):
    """
    Importa vários estudantes de uma só vez a partir de um ficheiro CSV
    (mesmas colunas do formulário "Adicionar Dados"). Linhas inválidas são
    reportadas mas não impedem as restantes de serem adicionadas — ver
    src/bulk_import.py.
    """
    # Lê o conteúdo do ficheiro enviado (assíncrono, porque pode ser um ficheiro grande).
    content = await file.read()
    try:
        result = add_students_bulk(content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # O dataset mudou (novos estudantes) — limpa a cache para refletir a alteração.
    _dataset.cache_clear()
    return result


@app.get("/students/table")
def students_table(
    school: Optional[str] = Query(None, description="'GP', 'MS' ou vazio para todas"),
    perf_band: Optional[str] = Query(None, description="Insuficiente/Suficiente/Bom/Excelente ou vazio"),
    at_risk: Optional[int] = Query(None, ge=0, le=1, description="1=em risco, 0=sem risco, vazio=todos"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=5, le=100),
):
    """
    Explorador de dados: lista paginada e filtrável de todos os estudantes
    (inclui os adicionados manualmente), para a página 'Dados'.
    """
    df = _dataset()
    filtered = df
    if school:
        filtered = filtered[filtered["school"] == school]
    if perf_band:
        filtered = filtered[filtered["perf_band"] == perf_band]
    if at_risk is not None:
        filtered = filtered[filtered["at_risk"] == at_risk]

    total = len(filtered)
    # Divisão arredondada para cima (ceil), sem precisar de importar math.ceil.
    total_pages = max(1, -(-total // page_size))  # ceil division
    # Garante que a página pedida não ultrapassa o total de páginas disponíveis.
    page = min(page, total_pages)
    start = (page - 1) * page_size
    end = start + page_size

    cols = ["student_id", "school", "sex", "age", "studytime", "absences",
            "failures", "G1", "G2", "G3", "perf_band", "at_risk"]

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "students": filtered[cols].iloc[start:end].to_dict(orient="records"),
    }


@app.get("/students/export-csv")
def students_export_csv(
    school: Optional[str] = Query(None, description="'GP', 'MS' ou vazio para todas"),
    perf_band: Optional[str] = Query(None, description="Insuficiente/Suficiente/Bom/Excelente ou vazio"),
    at_risk: Optional[int] = Query(None, ge=0, le=1, description="1=em risco, 0=sem risco, vazio=todos"),
):
    """
    Exporta o dataset completo (ou uma vista filtrada, com os mesmos filtros
    do explorador de dados) como ficheiro CSV para descarregar.
    """
    csv_text = export_students_csv(_dataset(), school=school, perf_band=perf_band, at_risk=at_risk)
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="studentperfomance_dataset.csv"'},
    )


class ChatQuestionInput(BaseModel):
    question: str = Field(..., min_length=1, max_length=300, description="Pergunta em texto livre")


@app.post("/chatbot/ask")
def chatbot_ask(payload: ChatQuestionInput):
    """
    Assistente baseado em regras (sem LLM externo, sem chave de API) — ver
    src/chatbot.py. Reconhece um conjunto fixo de tipos de pergunta e
    responde sempre com dados reais do dataset atual.
    """
    return answer_question(_dataset(), payload.question)


@app.get("/chatbot/examples")
def chatbot_examples():
    """Perguntas de exemplo, para o frontend sugerir antes do utilizador escrever."""
    return {"examples": EXAMPLE_QUESTIONS}


@app.get("/optimizer")
def optimizer(
    student_id: int = Query(..., description="Número do estudante"),
    target_grade: float = Query(..., ge=0, le=20, description="Nota-alvo (0-20)"),
):
    """
    Calcula o plano de mudança de hábitos (tempo de estudo, saídas, faltas,
    álcool) que mais aproxima o estudante da nota-alvo, usando o modelo
    de previsão já treinado.
    """
    df = _dataset()
    try:
        return otimizar_plano_estudo(df, student_id, target_grade)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# Deltas (alterações) a aplicar em lote a todos os estudantes em risco —
# todos opcionais, só as alavancas indicadas são alteradas.
class CohortSimulationInput(BaseModel):
    studytime: Optional[float] = Field(None, description="Alteração no tempo de estudo (nível), ex.: 1 para +1 nível")
    goout: Optional[float] = Field(None, description="Alteração em sair com amigos (nível 1-5)")
    absences: Optional[float] = Field(None, description="Alteração no nº de faltas (negativo para reduzir)")
    Dalc: Optional[float] = Field(None, description="Alteração no consumo de álcool em dias úteis")
    Walc: Optional[float] = Field(None, description="Alteração no consumo de álcool ao fim de semana")


@app.post("/optimizer/cohort-simulation")
def optimizer_cohort_simulation(payload: CohortSimulationInput):
    """
    Simulador em lote, ao nível da turma: aplica a mesma alteração
    hipotética de hábitos a TODOS os estudantes em risco de uma só vez, e
    mede o impacto agregado na taxa de aprovação (ver simular_intervencao_turma
    em src/optimizer.py).
    """
    deltas = payload.model_dump(exclude_none=True)
    if not deltas:
        raise HTTPException(status_code=400, detail="Indica pelo menos uma alteração de hábito.")
    df = _dataset()
    try:
        return simular_intervencao_turma(df, deltas)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# Corpo do pedido para atualizar as Configurações — todos os campos são
# opcionais (atualização parcial, ver settings_module.save_settings).
class SettingsInput(BaseModel):
    theme: Optional[str] = None
    font: Optional[str] = None
    alert_risk_threshold: Optional[float] = Field(None, ge=0.01, le=0.99)
    alert_min_absences: Optional[int] = Field(None, ge=-1, description="-1 repõe o cálculo automático")


@app.get("/themes")
def themes():
    """Temas de cores disponíveis, para o seletor de Configurações."""
    return {"themes": settings_module.list_themes(), "fonts": settings_module.FONT_OPTIONS}


@app.get("/settings")
def get_settings():
    """Configurações atuais (tema, fonte, limiares de alerta)."""
    return settings_module.get_settings()


@app.post("/settings")
def save_settings(payload: SettingsInput):
    """Grava as configurações alteradas (só os campos enviados são atualizados)."""
    try:
        return settings_module.save_settings(
            payload.theme, payload.font, payload.alert_risk_threshold, payload.alert_min_absences,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ----------------------------------------------------------------------------
# Cópias de segurança da base de dados (ver src/backup.py): um backup
# automático corre sozinho em segundo plano (arrancado no evento "startup"
# acima), e o utilizador pode ainda pedir um a qualquer momento, ver a lista
# de cópias existentes, restaurar uma anterior ou apagar as que já não quer.
# ----------------------------------------------------------------------------
@app.get("/backup/status")
def backup_status():
    """Se o agendador automático está a correr e quantas cópias existem — para a UI."""
    return {
        "auto_backup_running": backup_module.is_auto_backup_running(),
        "auto_backup_interval_hours": backup_module.AUTO_BACKUP_INTERVAL_SECONDS / 3600,
        "sqlite_supported": config.DB_DRIVER == "sqlite",
        "n_backups": len(backup_module.list_backups()),
    }


@app.get("/backup")
def backup_list():
    """Lista todas as cópias de segurança existentes, mais recente primeiro."""
    return {"backups": backup_module.list_backups()}


@app.post("/backup")
def backup_create():
    """Cria uma cópia de segurança manual, agora mesmo."""
    try:
        return backup_module.create_backup(reason=backup_module.MANUAL_BACKUP_REASON)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/backup/{backup_id}/restore")
def backup_restore(backup_id: str):
    """Substitui a base de dados atual pelo conteúdo desta cópia de segurança."""
    try:
        return backup_module.restore_backup(backup_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.delete("/backup/{backup_id}")
def backup_delete(backup_id: str):
    """Apaga uma cópia de segurança específica."""
    try:
        return backup_module.delete_backup(backup_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


# ----------------------------------------------------------------------------
# Dataset Personalizado: área independente onde o utilizador pode carregar
# QUALQUER ficheiro seu (CSV/Excel) — dados de estudantes ou não — e ver
# logo estatísticas e fórmulas personalizadas sobre ele, tal como está
# (sem ter de mapear colunas para o esquema da StudentPerfomance). Previsões (que
# reaproveitam o modelo principal) só ficam disponíveis quando o próprio
# ficheiro tem colunas parecidas com as da StudentPerfomance, detetadas
# automaticamente; Treinar Modelo é sempre genérico — o utilizador escolhe a
# própria coluna-alvo e colunas-recurso, e funciona com qualquer dataset
# (ver src/custom_dataset.py para o porquê de cada decisão).
# ----------------------------------------------------------------------------
@app.post("/custom-dataset/upload")
async def custom_dataset_upload(file: UploadFile = File(...)):
    """
    Carrega um ficheiro CSV/Excel para memória (ainda não fica "importado")
    e devolve as colunas encontradas + uma pré-visualização, para o
    utilizador confirmar a importação a seguir (ver /custom-dataset/import) —
    sem qualquer mapeamento, as colunas ficam tal como estão no ficheiro.
    """
    try:
        content = await file.read()
        # file.filename é Optional (o cliente HTTP tecnicamente pode enviar
        # um ficheiro sem nome), embora nunca aconteça a partir da interface
        # da app — "or ''" cobre esse caso extremo sem rebentar, e satisfaz o
        # tipo "str" (não "str | None") que stage_upload espera.
        return custom_dataset.stage_upload(file.filename or "", content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        # Ficheiros carregados pelo utilizador podem vir em formatos
        # verdadeiramente inesperados (folhas protegidas, colunas
        # duplicadas, dependências do Excel em falta no ambiente, etc.) —
        # tudo o que não seja já um ValueError "normal" (tratado acima) é
        # apanhado aqui para nunca devolver um "Erro 500" sem explicação
        # nenhuma. O erro completo fica registado no terminal do servidor
        # (ver logger acima) para se poder diagnosticar a causa exata.
        logger.exception("Falha inesperada ao carregar o ficheiro do Dataset Personalizado (%s)", file.filename)
        raise HTTPException(status_code=400, detail=f"Não foi possível processar o ficheiro '{file.filename}': {exc}")


@app.get("/custom-dataset/staged")
def custom_dataset_staged():
    """Ficheiro atualmente em espera de mapeamento (se algum tiver sido carregado)."""
    staged = custom_dataset.get_staged_upload()
    if staged is None:
        raise HTTPException(status_code=404, detail="Nenhum ficheiro em espera — faz upload primeiro.")
    return staged


@app.post("/custom-dataset/import")
def custom_dataset_import():
    """
    Confirma a importação do ficheiro em espera: passa a ser o dataset
    personalizado ativo (substitui um anterior, se existisse), com as
    colunas exatamente como vêm no ficheiro — sem qualquer mapeamento.
    """
    try:
        return custom_dataset.import_dataset()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception("Falha inesperada ao importar o Dataset Personalizado")
        raise HTTPException(status_code=400, detail=f"Não foi possível importar o dataset: {exc}")


@app.get("/custom-dataset/status")
def custom_dataset_status():
    """Estado atual: se há dataset importado, quantas linhas, e que cálculos são possíveis."""
    return custom_dataset.get_status()


@app.get("/custom-dataset/stats")
def custom_dataset_stats():
    """
    Estatísticas descritivas por coluna (calculadas pelo tipo real de cada
    uma — numérica ou categórica), mais os indicadores/gráficos ao estilo da
    Visão Geral principal como bónus, se uma coluna de "nota final" tiver
    sido detetada automaticamente.
    """
    try:
        return custom_dataset.compute_stats()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.get("/custom-dataset/predict")
def custom_dataset_predict(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=5, le=100),
):
    """
    Previsões (nota + probabilidade de aprovação), reaproveitando o modelo
    principal da StudentPerfomance — só disponível quando o dataset tem colunas
    suficientes parecidas com as de estudantes, detetadas automaticamente
    (ver /custom-dataset/status -> can_predict).
    """
    try:
        return custom_dataset.compute_predictions(page=page, page_size=page_size)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


class CustomDatasetTrainInput(BaseModel):
    target_col: str = Field(..., description="Coluna a prever (ex.: 'G3', 'Total Sales', 'Region')")
    feature_cols: list[str] = Field(
        ..., min_length=1, description="Colunas a usar para prever a coluna-alvo"
    )


@app.post("/custom-dataset/train")
def custom_dataset_train(payload: CustomDatasetTrainInput):
    """
    Treina um modelo novo — genérico, funciona com qualquer dataset — para
    prever "target_col" a partir de "feature_cols", ambas escolhidas pelo
    utilizador. Regressão ou classificação é decidido automaticamente pelo
    tipo real da coluna-alvo (numérica vs. categórica).
    """
    try:
        return custom_dataset.train_custom_model(payload.target_col, payload.feature_cols)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/custom-dataset/train")
def custom_dataset_get_train_metrics():
    """Métricas do último modelo personalizado treinado."""
    metrics = custom_dataset.get_custom_model_metrics()
    if metrics is None:
        raise HTTPException(status_code=404, detail="Ainda não foi treinado nenhum modelo personalizado.")
    return metrics


@app.delete("/custom-dataset")
def custom_dataset_delete():
    """Esquece por completo o dataset personalizado ativo (dados, metadados e modelo treinado)."""
    custom_dataset.delete_dataset()
    return {"deleted": True}


class CustomDatasetFormulaInput(BaseModel):
    formula: str = Field(
        ..., description="Fórmula escrita pelo utilizador (ex.: 'G1*0.3 + G2*0.3 + G3*0.4' ou 'media(G3) onde studytime >= 3')"
    )


@app.post("/custom-dataset/formula")
def custom_dataset_formula(
    payload: CustomDatasetFormulaInput,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=5, le=200),
):
    """
    Calcula uma fórmula personalizada (escrita pelo próprio utilizador) sobre
    o dataset personalizado — ou uma coluna nova (um valor por estudante) ou
    um resultado único, consoante a fórmula (ver src/formula_engine.py).
    """
    try:
        return custom_dataset.compute_formula(payload.formula, page=page, page_size=page_size)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ----------------------------------------------------------------------------
# Interface web (HTML/CSS/JS): montada por último, para não sobrepor as rotas
# da API acima. Serve web/index.html em "/" e os restantes ficheiros (css/js)
# nos respetivos caminhos — a app fica toda disponível num único endereço.
# ----------------------------------------------------------------------------
if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
