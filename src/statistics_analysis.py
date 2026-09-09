"""
Análise estatística: comparações entre grupos (testes de hipóteses) e
regressão linear simples. Complementa a análise exploratória (eda.py) com
testes formais de significância estatística.
"""
from __future__ import annotations

# pandas: para trabalhar com os dados como tabela.
import pandas as pd
# statsmodels: biblioteca de modelos estatísticos (usada aqui para a regressão linear).
import statsmodels.api as sm
# scipy.stats: funções de testes estatísticos (teste t, ANOVA).
from scipy import stats

from src import config
from src.data_processing import get_processed_data


def compare_two_groups(df: pd.DataFrame, group_col: str, value_col: str = "G3") -> dict:
    """
    Teste t de Student para comparar a média de `value_col` entre dois grupos
    definidos por `group_col` (ex.: internet "yes" vs "no").
    """
    # Valores únicos da coluna de agrupamento (ex.: "yes"/"no").
    groups = df[group_col].dropna().unique()
    # Este teste só funciona com exatamente 2 grupos — valida antes de prosseguir.
    if len(groups) != 2:
        raise ValueError(f"'{group_col}' deve ter exatamente 2 categorias, tem {len(groups)}.")

    # Separa os valores da variável de interesse (ex.: G3) em dois grupos.
    g1_vals = df.loc[df[group_col] == groups[0], value_col]
    g2_vals = df.loc[df[group_col] == groups[1], value_col]

    # Teste t de Welch (equal_var=False): não assume que os dois grupos têm a
    # mesma variância, mais seguro quando os grupos têm tamanhos diferentes.
    t_stat, p_value = stats.ttest_ind(g1_vals, g2_vals, equal_var=False)

    return {
        "grupo": group_col,
        "variavel": value_col,
        "categorias": {str(groups[0]): round(float(g1_vals.mean()), 2), str(groups[1]): round(float(g2_vals.mean()), 2)},
        "t_stat": round(float(t_stat), 4),
        "p_value": round(float(p_value), 4),
        # Convenção estatística comum: p < 0.05 é considerado estatisticamente significativo.
        "significativo_5pct": bool(p_value < 0.05),
    }


def compare_multiple_groups(df: pd.DataFrame, group_col: str, value_col: str = "G3") -> dict:
    """ANOVA de um fator para comparar a média de `value_col` entre 3+ grupos (ex.: studytime)."""
    groups = df[group_col].dropna().unique()
    # Uma amostra de valores por cada grupo (ex.: nota final de quem tem studytime=1, =2, =3, =4).
    samples = [df.loc[df[group_col] == g, value_col] for g in groups]

    # ANOVA de um fator: testa se pelo menos um dos grupos tem média diferente dos outros.
    f_stat, p_value = stats.f_oneway(*samples)
    # Média da variável de interesse, por cada grupo (ordenados).
    means = {str(g): round(float(df.loc[df[group_col] == g, value_col].mean()), 2) for g in sorted(groups)}

    return {
        "grupo": group_col,
        "variavel": value_col,
        "medias_por_grupo": means,
        "f_stat": round(float(f_stat), 4),
        "p_value": round(float(p_value), 4),
        "significativo_5pct": bool(p_value < 0.05),
    }


def simple_linear_regression(df: pd.DataFrame, x_col: str, y_col: str = "G3") -> dict:
    """
    Regressão linear simples (uma única variável preditora), usando statsmodels
    para obter coeficientes, R² e significância estatística (p-value).
    """
    # add_constant acrescenta a coluna do termo independente (intercept) ao modelo.
    X = sm.add_constant(df[[x_col]].astype(float))
    y = df[y_col].astype(float)
    # OLS = Ordinary Least Squares (mínimos quadrados ordinários) — o método
    # clássico de regressão linear. .fit() treina o modelo com os dados.
    model = sm.OLS(y, X).fit()

    return {
        "x": x_col,
        "y": y_col,
        # Coeficiente: quanto y muda, em média, por cada unidade de aumento em x.
        "coeficiente": round(float(model.params[x_col]), 4),
        # Intercept (ordenada na origem): valor previsto de y quando x=0.
        "intercept": round(float(model.params["const"]), 4),
        # R²: proporção da variação de y explicada pelo modelo (0 a 1, quanto maior melhor).
        "r2": round(float(model.rsquared), 4),
        "p_value": round(float(model.pvalues[x_col]), 6),
        "significativo_5pct": bool(model.pvalues[x_col] < 0.05),
        "interpretacao": (
            f"Cada unidade adicional em '{x_col}' está associada a uma variação de "
            f"{model.params[x_col]:.2f} pontos em '{y_col}' (R²={model.rsquared:.3f})."
        ),
    }


# Rótulos em português para os fatores numéricos que podem ser destacados no
# resumo automático da Visão Geral — só os que fazem sentido como frase
# ("quanto maior for X, ..."), por isso não inclui id/notas em si.
OVERVIEW_FACTOR_LABELS = {
    "failures": "as reprovações anteriores",
    "studytime": "o tempo de estudo semanal",
    "absences": "o número de faltas",
    "goout": "sair com amigos",
    "Dalc": "o consumo de álcool em dias úteis",
    "Walc": "o consumo de álcool ao fim de semana",
    "famrel": "a relação familiar",
    "freetime": "o tempo livre",
    "health": "a saúde",
    "age": "a idade",
    "traveltime": "o tempo de deslocação até à escola",
    "Medu": "a educação da mãe",
    "Fedu": "a educação do pai",
}


def generate_overview_summary(df: pd.DataFrame) -> str:
    """
    Parágrafo automático para o topo da Visão Geral: taxa de aprovação, nota
    média, taxa de risco, e o fator numérico com maior correlação (em valor
    absoluto) com a nota final — recalculado sempre a partir do dataset
    ATUAL (inclui estudantes adicionados manualmente), nunca texto fixo.
    """
    # Estatísticas-base, em percentagem onde faz sentido.
    pass_rate = df["aprovado"].mean() * 100
    avg_grade = df["G3"].mean()
    risk_rate = df["at_risk"].mean() * 100

    # Todas as colunas numéricas (exceto a própria nota final), para calcular a correlação com G3.
    corr_cols = [c for c in config.NUMERIC_COLS if c != "G3" and c in df.columns]
    correlations = df[corr_cols + ["G3"]].corr()["G3"].drop("G3")
    # idxmax() sobre o valor absoluto: encontra a variável com a correlação
    # mais forte, seja ela positiva ou negativa.
    top_factor = correlations.abs().idxmax()
    top_corr = correlations[top_factor]
    # Nome amigável do fator, ou o nome técnico se não existir tradução.
    factor_label = OVERVIEW_FACTOR_LABELS.get(top_factor, top_factor)
    # Frase final depende do sinal da correlação: negativa = "quanto maior, menor a nota".
    relation = "menor" if top_corr < 0 else "maior"

    # Constrói o parágrafo, frase a frase.
    parts = [
        f"Do conjunto de {len(df)} estudantes analisados, {pass_rate:.1f}% estão aprovados "
        f"(nota final ≥ {config.PASS_THRESHOLD} valores), com uma nota média de {avg_grade:.1f} valores."
    ]
    # Só menciona a taxa de risco se houver pelo menos um estudante em risco.
    if risk_rate > 0:
        parts.append(f"{risk_rate:.1f}% dos estudantes estão sinalizados como em risco.")
    parts.append(
        f"Entre os hábitos e o contexto analisados, {factor_label} é o fator com maior associação "
        f"linear individual à nota final (correlação de {top_corr:.2f}): quanto maior o seu valor, "
        f"{relation} tende a ser a nota final."
    )
    # Junta todas as frases num único parágrafo.
    return " ".join(parts)


def run_statistical_analysis() -> dict:
    """Corre todos os testes estatísticos definidos acima e escreve o relatório final."""
    df = get_processed_data()

    results = {
        # Comparações entre pares de grupos (teste t): variáveis binárias interessantes.
        "comparacoes_2_grupos": [
            compare_two_groups(df, "internet"),
            compare_two_groups(df, "romantic"),
            compare_two_groups(df, "higher"),
            compare_two_groups(df, "schoolsup"),
        ],
        # Comparações entre múltiplos grupos (ANOVA): variáveis com 3+ categorias/níveis.
        "comparacoes_multiplos_grupos": [
            compare_multiple_groups(df, "studytime"),
            compare_multiple_groups(df, "goout"),
            compare_multiple_groups(df, "failures"),
        ],
        # Regressões lineares simples: relação direta entre cada variável e a nota final.
        "regressoes_simples": [
            simple_linear_regression(df, "studytime"),
            simple_linear_regression(df, "absences"),
            simple_linear_regression(df, "failures"),
            simple_linear_regression(df, "alcohol_avg"),
        ],
    }

    write_report(results)
    return results


def write_report(results: dict):
    """Escreve o relatório de análise estatística (reports/statistical_analysis_report.md)."""
    lines = ["# Relatório de Análise Estatística\n"]

    lines.append("\n## Comparação entre 2 grupos (teste t de Student)\n")
    for r in results["comparacoes_2_grupos"]:
        sig = "sim" if r["significativo_5pct"] else "não"
        lines.append(
            f"\n**{r['grupo']}** vs `{r['variavel']}`: médias {r['categorias']} | "
            f"t={r['t_stat']}, p={r['p_value']} | significativo (5%)? **{sig}**\n"
        )

    lines.append("\n## Comparação entre múltiplos grupos (ANOVA)\n")
    for r in results["comparacoes_multiplos_grupos"]:
        sig = "sim" if r["significativo_5pct"] else "não"
        lines.append(
            f"\n**{r['grupo']}** vs `{r['variavel']}`: médias por grupo {r['medias_por_grupo']} | "
            f"F={r['f_stat']}, p={r['p_value']} | significativo (5%)? **{sig}**\n"
        )

    lines.append("\n## Regressão linear simples\n")
    for r in results["regressoes_simples"]:
        sig = "sim" if r["significativo_5pct"] else "não"
        lines.append(
            f"\n**{r['y']} ~ {r['x']}**: coeficiente={r['coeficiente']}, "
            f"R²={r['r2']}, p={r['p_value']} | significativo (5%)? **{sig}**\n"
            f"> {r['interpretacao']}\n"
        )

    # Junta tudo e grava o relatório final.
    report_path = config.REPORTS_DIR / "statistical_analysis_report.md"
    report_path.write_text("".join(lines), encoding="utf-8")
    print(f"[Estatística] Relatório: {report_path}")


# Permite correr "python -m src.statistics_analysis" diretamente a partir da linha de comandos.
if __name__ == "__main__":
    run_statistical_analysis()
