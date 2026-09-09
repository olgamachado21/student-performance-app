"""
Análise Exploratória de Dados (EDA): estatísticas, correlações e gráficos
sobre a relação entre hábitos de estudo/estilo de vida e desempenho académico.

Gera figuras em reports/figures/ e um relatório em reports/eda_report.md
"""
from __future__ import annotations

# matplotlib: biblioteca de gráficos. "Agg" é um modo sem interface gráfica,
# necessário porque este código corre num servidor, sem ecrã.
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
# pandas: para trabalhar com os dados como tabela.
import pandas as pd
# seaborn: biblioteca de gráficos estatísticos, construída sobre o matplotlib
# (histogramas, heatmaps, boxplots mais bonitos e fáceis de configurar).
import seaborn as sns

from src import config
from src.data_processing import get_processed_data

# Define o estilo visual (fundo com grelha clara) para todos os gráficos gerados.
sns.set_theme(style="whitegrid")


def plot_grade_distribution(df: pd.DataFrame):
    """Gera um histograma da distribuição das notas finais (G3)."""
    # Cria uma figura (fig) e um eixo de desenho (ax) com um tamanho definido.
    fig, ax = plt.subplots(figsize=(7, 4.5))
    # Histograma com curva de densidade (kde=True) sobreposta.
    sns.histplot(df["G3"], bins=20, kde=True, color="#4C72B0", ax=ax)
    # Linha vertical tracejada a marcar o limiar de aprovação (nota 10).
    ax.axvline(config.PASS_THRESHOLD, color="red", linestyle="--", label="Limiar de aprovação (10)")
    ax.set_title("Distribuição da nota final (G3)")
    ax.set_xlabel("Nota final (0-20)")
    ax.legend()
    # Ajusta o espaçamento para nada ficar cortado.
    fig.tight_layout()
    # Grava a imagem em disco, com resolução de 150 pontos por polegada.
    fig.savefig(config.FIGURES_DIR / "01_distribuicao_notas.png", dpi=150)
    # Fecha a figura para libertar memória (importante quando se geram muitos gráficos seguidos).
    plt.close(fig)


def plot_correlation_heatmap(df: pd.DataFrame):
    """Gera um mapa de calor (heatmap) com a correlação entre todas as variáveis numéricas."""
    # Todas as colunas numéricas relevantes, incluindo as notas e as variáveis derivadas.
    numeric_cols = config.NUMERIC_COLS + ["G1", "G2", "G3", "alcohol_avg", "parent_edu_avg"]
    # Matriz de correlação: cada célula mostra a correlação entre duas variáveis (-1 a 1).
    corr = df[numeric_cols].corr()
    fig, ax = plt.subplots(figsize=(11, 9))
    # annot=True mostra os valores numéricos dentro de cada célula do heatmap.
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="coolwarm", center=0, ax=ax,
                annot_kws={"size": 7})
    ax.set_title("Matriz de correlação entre variáveis numéricas e nota final")
    fig.tight_layout()
    fig.savefig(config.FIGURES_DIR / "02_matriz_correlacao.png", dpi=150)
    plt.close(fig)


def plot_habit_vs_grade(df: pd.DataFrame):
    """Gera uma grelha de boxplots: cada hábito (eixo X) vs a nota final (eixo Y)."""
    habits = ["studytime", "absences", "goout", "Dalc", "Walc", "failures"]
    # Grelha de 2 linhas x 3 colunas de gráficos (um por hábito).
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    # axes.flat percorre todos os subgráficos em sequência, emparelhados com cada hábito.
    for ax, col in zip(axes.flat, habits):
        sns.boxplot(x=col, y="G3", data=df, hue=col, palette="Blues", legend=False, ax=ax)
        ax.set_title(f"{col} vs Nota Final")
    fig.suptitle("Hábitos e estilo de vida vs desempenho (G3)", fontsize=14)
    fig.tight_layout()
    fig.savefig(config.FIGURES_DIR / "03_habitos_vs_nota.png", dpi=150)
    plt.close(fig)


def plot_categorical_vs_grade(df: pd.DataFrame):
    """Gera uma grelha de boxplots: cada variável categórica (eixo X) vs a nota final (eixo Y)."""
    cats = ["internet", "romantic", "activities", "schoolsup", "higher", "paid"]
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    for ax, col in zip(axes.flat, cats):
        sns.boxplot(x=col, y="G3", data=df, hue=col, palette="Set2", legend=False, ax=ax)
        ax.set_title(f"{col} vs Nota Final")
    fig.suptitle("Fatores contextuais vs desempenho (G3)", fontsize=14)
    fig.tight_layout()
    fig.savefig(config.FIGURES_DIR / "04_categoricas_vs_nota.png", dpi=150)
    plt.close(fig)


def plot_studytime_pass_rate(df: pd.DataFrame):
    """Gera um gráfico de barras: taxa de aprovação por nível de tempo de estudo."""
    # Agrupa por tempo de estudo e calcula a média de "aprovado" (0 ou 1) em cada grupo
    # — a média de valores 0/1 dá diretamente a percentagem de aprovados.
    rate = df.groupby("studytime")["aprovado"].mean().reset_index()
    fig, ax = plt.subplots(figsize=(6.5, 4.5))
    sns.barplot(x="studytime", y="aprovado", data=rate, ax=ax, color="#55A868")
    ax.set_title("Taxa de aprovação por nível de tempo de estudo")
    ax.set_xlabel("Tempo de estudo semanal (1=<2h, 2=2-5h, 3=5-10h, 4=>10h)")
    ax.set_ylabel("Taxa de aprovação")
    # Fixa o eixo Y entre 0 e 1 (0% a 100%), para não distorcer visualmente as diferenças.
    ax.set_ylim(0, 1)
    fig.tight_layout()
    fig.savefig(config.FIGURES_DIR / "05_taxa_aprovacao_estudo.png", dpi=150)
    plt.close(fig)


def compute_insights(df: pd.DataFrame) -> dict:
    """Calcula um conjunto de estatísticas-resumo usadas no relatório de EDA."""
    # Correlação de cada variável numérica com a nota final (G3), excluindo G3 consigo própria.
    corr_g3 = df[config.NUMERIC_COLS + ["G1", "G2", "G3"]].corr()["G3"].drop("G3")
    # As 5 variáveis mais positivamente correlacionadas com a nota.
    top_positive = corr_g3.sort_values(ascending=False).head(5)
    # As 5 variáveis mais negativamente correlacionadas com a nota.
    top_negative = corr_g3.sort_values().head(5)

    # Taxa de aprovação geral (percentagem de estudantes com "aprovado" = 1).
    pass_rate_overall = df["aprovado"].mean()
    # Taxa de aprovação, agrupada por tempo de estudo.
    pass_rate_by_studytime = df.groupby("studytime")["aprovado"].mean()
    # Taxa de aprovação, agrupada por ter ou não acesso a internet em casa.
    pass_rate_by_internet = df.groupby("internet")["aprovado"].mean()
    # Nota média, agrupada por faixas de consumo médio de álcool (baixo/médio/alto).
    avg_grade_by_alcohol = df.groupby(pd.cut(df["alcohol_avg"], bins=[0, 1.5, 3, 5]), observed=True)["G3"].mean()

    return {
        "n_students": len(df),
        "pass_rate_overall": pass_rate_overall,
        "top_positive_corr": top_positive,
        "top_negative_corr": top_negative,
        "pass_rate_by_studytime": pass_rate_by_studytime,
        "pass_rate_by_internet": pass_rate_by_internet,
        "avg_grade_by_alcohol": avg_grade_by_alcohol,
        "avg_grade": df["G3"].mean(),
    }


def write_report(insights: dict):
    """Escreve o relatório de EDA (reports/eda_report.md) a partir dos insights calculados."""
    # Constrói o relatório linha a linha, como uma lista de texto em Markdown.
    lines = []
    lines.append("# Relatório de Análise Exploratória — Desempenho Académico e Hábitos de Estudo\n")
    lines.append(f"Dataset: {insights['n_students']} estudantes.\n")
    lines.append(f"Nota final média (G3): **{insights['avg_grade']:.2f} / 20**\n")
    lines.append(f"Taxa de aprovação geral (G3 >= 10): **{insights['pass_rate_overall']*100:.1f}%**\n")

    lines.append("\n## Variáveis mais correlacionadas positivamente com a nota final\n")
    for var, val in insights["top_positive_corr"].items():
        lines.append(f"- `{var}`: correlação de {val:.2f}\n")

    lines.append("\n## Variáveis mais correlacionadas negativamente com a nota final\n")
    for var, val in insights["top_negative_corr"].items():
        lines.append(f"- `{var}`: correlação de {val:.2f}\n")

    lines.append("\n## Taxa de aprovação por tempo de estudo semanal\n")
    for k, v in insights["pass_rate_by_studytime"].items():
        lines.append(f"- Nível {k}: {v*100:.1f}% de aprovação\n")

    lines.append("\n## Taxa de aprovação por acesso a internet em casa\n")
    for k, v in insights["pass_rate_by_internet"].items():
        lines.append(f"- Internet = {k}: {v*100:.1f}% de aprovação\n")

    lines.append("\n## Nota média por nível de consumo de álcool (médio semanal)\n")
    for k, v in insights["avg_grade_by_alcohol"].items():
        lines.append(f"- {k}: {v:.2f} / 20\n")

    lines.append("\n## Figuras geradas\n")
    lines.append("- `01_distribuicao_notas.png`\n")
    lines.append("- `02_matriz_correlacao.png`\n")
    lines.append("- `03_habitos_vs_nota.png`\n")
    lines.append("- `04_categoricas_vs_nota.png`\n")
    lines.append("- `05_taxa_aprovacao_estudo.png`\n")

    # Junta todas as linhas num único texto e grava no ficheiro do relatório.
    report_path = config.REPORTS_DIR / "eda_report.md"
    report_path.write_text("".join(lines), encoding="utf-8")
    return report_path


def run_eda():
    """Corre a análise exploratória completa: gera todos os gráficos e o relatório final."""
    # Carrega o dataset já limpo e processado.
    df = get_processed_data()
    # Gera cada um dos 5 gráficos, um a um.
    plot_grade_distribution(df)
    plot_correlation_heatmap(df)
    plot_habit_vs_grade(df)
    plot_categorical_vs_grade(df)
    plot_studytime_pass_rate(df)
    # Calcula as estatísticas-resumo e escreve o relatório final em Markdown.
    insights = compute_insights(df)
    report_path = write_report(insights)
    print(f"EDA concluída. Relatório: {report_path}")
    print(f"Figuras em: {config.FIGURES_DIR}")
    return insights


# Permite correr "python -m src.eda" diretamente a partir da linha de comandos.
if __name__ == "__main__":
    run_eda()
