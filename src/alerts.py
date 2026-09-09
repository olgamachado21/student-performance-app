"""
Avisos e Alertas: gera avisos automáticos a partir do estado atual dos dados.

Inspirado na página "Avisos e Alertas" de referência, mas adaptado ao que o
nosso projeto tem disponível (dataset + modelos), sem depender de calendário
ou plano de estudo (essas ferramentas ainda não existem neste projeto).
"""
from __future__ import annotations

# pandas: para trabalhar com o dataset como tabela (DataFrame).
import pandas as pd

from src import config
# Importado com um "apelido" (settings_module) para não colidir com o nome
# do parâmetro "settings" que poderia ser usado nas funções abaixo.
from src import settings as settings_module

# 30% dos estudantes em risco -> aviso geral (valor por omissão, pode ser
# personalizado em Configurações — ver settings.py).
RISK_RATE_WARNING_THRESHOLD = 0.30


def generate_alerts(
    df: pd.DataFrame,
    risk_rate_threshold: float | None = None,
    min_absences: int | None = None,
) -> list[dict]:
    """
    Constrói uma lista de avisos, ordenados por gravidade
    (urgente > aviso > info), com base no estado atual do dataset.

    Os dois limiares abaixo podem ser personalizados em Configurações (ver
    src/settings.py, Ideia 6 — alertas configuráveis). Quando não são
    passados explicitamente (o caso normal, usado pelo endpoint /alerts),
    generate_alerts lê os valores guardados — ou os valores por omissão, se
    nunca tiverem sido alterados. min_absences=None (por omissão) mantém o
    cálculo estatístico automático (média + 2 desvios-padrão); um número
    fixo substitui esse cálculo por um limiar direto e mais previsível.
    """
    # Se algum dos limiares não foi passado explicitamente, vai buscar os
    # valores guardados nas Configurações (ou os valores por omissão).
    if risk_rate_threshold is None or min_absences is None:
        configured = settings_module.get_settings()
        if risk_rate_threshold is None:
            # float(...) além de garantir o tipo em runtime (o valor guardado
            # nas Configurações vem de uma tabela SQL, por isso não é 100%
            # garantido pelo Python que já seja float), também resolve o
            # "Unknown | float | None" que o Pylance via aqui: sem isto, não
            # conseguia confirmar que a variável deixava de poder ser None
            # depois deste bloco, apesar da verificação acima.
            risk_rate_threshold = float(configured.get("alert_risk_threshold", RISK_RATE_WARNING_THRESHOLD))
        if min_absences is None:
            min_absences = configured.get("alert_min_absences")

    # Lista de avisos a devolver, construída passo a passo abaixo.
    alerts: list[dict] = []

    # --- Aviso geral: percentagem de estudantes em risco ---
    # Média da coluna "at_risk" (0/1) dá diretamente a percentagem em risco.
    risk_rate = df["at_risk"].mean()
    if risk_rate >= risk_rate_threshold:
        alerts.append({
            "id": "risk_rate_high",
            "severity": "urgente",
            "title": "Taxa de risco elevada no conjunto de dados",
            "description": (
                f"{risk_rate*100:.1f}% dos estudantes estão em risco "
                f"(nota final < {config.PASS_THRESHOLD}, já reprovaram antes, "
                f"ou têm mais de 15 faltas) — acima do limiar configurado de "
                f"{risk_rate_threshold*100:.0f}%."
            ),
            "action_label": "Ver Fatores de Risco",
            "action_page": "risk",
        })

    # --- Estudantes com faltas muito acima da média ---
    absences_mean = df["absences"].mean()
    absences_std = df["absences"].std()
    # Usa o limiar configurado manualmente, se existir; senão calcula
    # automaticamente (média + 2 desvios-padrão, um critério estatístico comum).
    high_absence_threshold = min_absences if min_absences is not None else absences_mean + 2 * absences_std
    n_high_absences = int((df["absences"] > high_absence_threshold).sum())
    if n_high_absences > 0:
        alerts.append({
            "id": "high_absences",
            "severity": "aviso",
            "title": "Estudantes com faltas muito acima da média",
            "description": (
                f"{n_high_absences} estudante(s) têm mais de "
                f"{high_absence_threshold:.0f} faltas (média geral: {absences_mean:.1f})."
            ),
            "action_label": "Ver Perfil do Estudante",
            "action_page": "profile",
        })

    # --- Estudantes com reprovações anteriores e nota a piorar ---
    # Filtra estudantes que já reprovaram (failures >= 1) E cuja nota desceu
    # do 1º para o 3º período (grade_trend negativo).
    worsening = df[(df["failures"] >= 1) & (df["grade_trend"] < 0)]
    if len(worsening) > 0:
        alerts.append({
            "id": "worsening_with_failures",
            "severity": "aviso",
            "title": "Estudantes com reprovações e notas a piorar",
            "description": (
                f"{len(worsening)} estudante(s) já reprovaram antes e a nota "
                f"desceu entre o 1º e o 3º período - merecem atenção prioritária."
            ),
            "action_label": "Ver Segmentação de Perfis",
            "action_page": "segmentation",
        })

    # --- Risco combinado: faltas altas E já reprovou antes ---
    # Os avisos "high_absences" e (indiretamente) "worsening_with_failures"
    # acima já olham para faltas e para reprovações em separado. Juntar os
    # dois fatores no MESMO estudante é um sinal bem mais forte do que
    # qualquer um isoladamente — no dataset atual, quem tem faltas acima da
    # mediana E já reprovou antes tem uma média de nota muito abaixo do
    # resto (perto de 3 valores de diferença), não é só "duas coisas más ao
    # mesmo tempo por coincidência".
    combined_alert = generate_combined_risk_alert(df)
    if combined_alert:
        alerts.append(combined_alert)

    # --- Consumo de álcool elevado associado a baixo desempenho ---
    heavy_drinkers_low_grade = df[(df["alcohol_avg"] >= 3) & (df["G3"] < config.PASS_THRESHOLD)]
    if len(heavy_drinkers_low_grade) > 0:
        alerts.append({
            "id": "alcohol_low_grade",
            "severity": "info",
            "title": "Consumo de álcool elevado associado a reprovação",
            "description": (
                f"{len(heavy_drinkers_low_grade)} estudante(s) com consumo de "
                f"álcool elevado (média ≥3) e nota final abaixo de "
                f"{config.PASS_THRESHOLD}."
            ),
            "action_label": "Ver Fatores de Risco",
            "action_page": "risk",
        })

    # Se nenhum dos avisos acima foi gerado, mostra uma mensagem tranquilizadora.
    if not alerts:
        alerts.append({
            "id": "all_clear",
            "severity": "info",
            "title": "Sem avisos de momento",
            "description": "Não foram detetados sinais de alerta no conjunto de dados atual.",
            "action_label": None,
            "action_page": None,
        })

    # Ordena os avisos por gravidade: urgentes primeiro, depois avisos, depois informativos.
    severity_order = {"urgente": 0, "aviso": 1, "info": 2}
    alerts.sort(key=lambda a: severity_order.get(a["severity"], 99))
    return alerts


def generate_combined_risk_alert(df: pd.DataFrame) -> dict | None:
    """
    Sinal de risco combinado: faltas acima da mediana da turma E pelo menos
    uma reprovação anterior, no MESMO estudante — não é a soma de dois
    avisos separados sobre a turma toda, é um cruzamento por estudante.

    A comparação de médias (grupo combinado vs. resto) é calculada em tempo
    real sobre o dataset atual (não é um número fixo do relatório de EDA),
    para continuar correta à medida que "Adicionar Dados" muda a turma.
    """
    # Mediana das faltas da turma inteira — o ponto de referência do "normal".
    absences_median = df["absences"].median()
    # Máscara booleana: True para os estudantes que cumprem as duas condições ao mesmo tempo.
    combined_mask = (df["absences"] > absences_median) & (df["failures"] >= 1)
    n_combined = int(combined_mask.sum())
    # Se ninguém cumpre as duas condições, não há aviso a gerar.
    if n_combined == 0:
        return None

    # Nota média do grupo combinado (risco duplo) vs. nota média de todos os restantes.
    combined_grade = float(df.loc[combined_mask, "G3"].mean())
    rest_grade = float(df.loc[~combined_mask, "G3"].mean())
    # Diferença entre as duas médias — quanto maior, mais forte o sinal de risco combinado.
    gap = rest_grade - combined_grade

    return {
        "id": "combined_risk_absences_failures",
        # Gravidade "urgente" se o grupo afetado for pelo menos 5% da turma, senão só "aviso".
        "severity": "urgente" if n_combined / len(df) >= 0.05 else "aviso",
        "title": "Risco combinado: faltas altas e reprovação anterior",
        "description": (
            f"{n_combined} estudante(s) têm faltas acima da mediana da turma "
            f"({absences_median:.0f}) E já reprovaram antes. Este grupo tem nota "
            f"média de {combined_grade:.2f}, contra {rest_grade:.2f} nos restantes — "
            f"uma diferença de {gap:.2f} valores, maior do que olhar a cada fator "
            f"isoladamente."
        ),
        "action_label": "Ver Fatores de Risco",
        "action_page": "risk",
    }


def get_at_risk_students(df: pd.DataFrame, limit: int = 50) -> list[dict]:
    """Lista dos estudantes em risco, para consulta rápida a partir dos avisos."""
    # Colunas mostradas na lista — só o essencial para identificar e avaliar cada estudante.
    cols = ["student_id", "sex", "age", "studytime", "absences", "failures", "G3", "at_risk"]
    # Filtra só os estudantes em risco, ordena pela nota mais baixa primeiro
    # (os mais preocupantes aparecem no topo), e limita ao número pedido.
    at_risk_df = df[df["at_risk"] == 1].sort_values("G3").head(limit)
    # Converte para uma lista de dicionários (formato fácil de devolver na API).
    return at_risk_df[cols].to_dict(orient="records")
