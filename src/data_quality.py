"""
Deteção de valores pouco habituais ao adicionar um novo estudante.

Não bloqueia nada — o utilizador pode sempre confirmar e seguir em frente —
apenas avisa quando um campo já preenchido foge muito do que é típico no
dataset atual, ou quando dois campos juntos são internamente inconsistentes
(ex: notas muito diferentes entre períodos consecutivos), para ajudar a
apanhar erros de digitação antes de gravarem no dataset.
"""
from __future__ import annotations

# numpy: usado para verificar valores inválidos (NaN) nos cálculos estatísticos.
import numpy as np
# pandas: para trabalhar com o dataset como tabela (DataFrame).
import pandas as pd

from src.i18n import t, normalize_lang

# Campos numéricos verificados individualmente contra a distribuição do dataset.
NUMERIC_CHECK_FIELDS = ["age", "studytime", "absences", "failures", "G1", "G2"]

# Nº de desvios-padrão a partir do qual um valor isolado é considerado
# invulgar face ao resto do dataset — 2.5 sinaliza os casos genuinamente
# raros (menos de ~1% numa distribuição normal) sem incomodar por pouco.
Z_THRESHOLD = 2.5

# Diferença entre G1 e G2 a partir da qual vale a pena confirmar — 8 valores
# (numa escala 0-20) é uma mudança grande entre dois períodos consecutivos.
GRADE_JUMP_THRESHOLD = 8

# Nomes amigáveis dos campos, para usar nas mensagens de aviso mostradas ao
# utilizador — por idioma (ver src/i18n.py).
FIELD_LABELS = {
    "pt": {
        "age": "Idade",
        "studytime": "Tempo de estudo",
        "absences": "Número de faltas",
        "failures": "Reprovações anteriores",
        "G1": "Nota do 1º período (G1)",
        "G2": "Nota do 2º período (G2)",
    },
    "en": {
        "age": "Age",
        "studytime": "Study time",
        "absences": "Number of absences",
        "failures": "Prior failures",
        "G1": "1st period grade (G1)",
        "G2": "2nd period grade (G2)",
    },
}


def check_unusual_values(df: pd.DataFrame, fields: dict, lang: str | None = None) -> list[dict]:
    """
    Devolve uma lista de avisos (pode estar vazia) sobre os campos já
    preenchidos em `fields` que fogem do padrão típico do dataset atual, ou
    que são internamente inconsistentes entre si. Cada aviso é um dict com
    "field" (a que campo se refere), "severity" ("info" ou "warning") e
    "message" (texto pronto a mostrar ao utilizador).
    """
    lang = normalize_lang(lang)
    labels = FIELD_LABELS[lang]
    # Ignora campos vazios/não preenchidos — só faz sentido avaliar o que o
    # utilizador já escreveu.
    fields = {k: v for k, v in fields.items() if v is not None and v != ""}
    # Lista de avisos a devolver — começa vazia e vai sendo preenchida abaixo.
    warnings: list[dict] = []

    # 1) Verifica cada campo numérico isoladamente, comparando com a
    # distribuição desse campo em todo o dataset atual.
    for col in NUMERIC_CHECK_FIELDS:
        # Salta campos que o utilizador ainda não preencheu.
        if col not in fields:
            continue
        value = fields[col]
        # Desvio-padrão e média da coluna no dataset — servem de referência
        # do que é "normal" para este campo.
        std = df[col].std()
        mean = df[col].mean()
        # Se o desvio-padrão for zero ou inválido, não é possível calcular o
        # z-score (todos os valores seriam iguais) — salta a verificação.
        if not std or np.isnan(std):
            continue
        # z-score: a quantos desvios-padrão o valor está da média.
        z = (value - mean) / std
        # Só avisa se o valor estiver a mais de Z_THRESHOLD desvios-padrão da média.
        if abs(z) < Z_THRESHOLD:
            continue
        # Percentil do valor no dataset (ex.: 97 = maior que 97% dos estudantes).
        percentile = float((df[col] <= value).mean() * 100)
        # Indica se o valor está acima ou abaixo do normal (frase adaptada por idioma abaixo).
        above = z > 0
        warnings.append({
            "field": col,
            "severity": "warning",
            "message": t(
                lang,
                f"{labels[col]} muito {'acima' if above else 'abaixo'} do habitual "
                f"(percentil {percentile:.0f} do dataset atual) — confirma que o valor está correto.",
                f"{labels[col]} is much {'higher' if above else 'lower'} than usual "
                f"(percentile {percentile:.0f} of the current dataset) — please confirm the value is correct.",
            ),
        })

    # 2) Verifica se G1 e G2 (preenchidos os dois) mudaram de forma
    # invulgarmente grande de um período para o outro.
    if "G1" in fields and "G2" in fields:
        diff = fields["G2"] - fields["G1"]
        if abs(diff) >= GRADE_JUMP_THRESHOLD:
            went_up = diff > 0
            warnings.append({
                "field": "G2",
                "severity": "warning",
                "message": t(
                    lang,
                    f"A nota {'subiu' if went_up else 'desceu'} {abs(diff)} valores entre G1 e G2 — "
                    "uma mudança grande entre dois períodos consecutivos. Confirma que os números "
                    "estão corretos.",
                    f"The grade went {'up' if went_up else 'down'} by {abs(diff)} points between "
                    "G1 and G2 — a large change between two consecutive periods. Please confirm "
                    "the numbers are correct.",
                ),
            })

    # 3) Verifica uma combinação pouco comum: muitas reprovações anteriores
    # (3+) mas notas altas (15+) em G1 ou G2 — não impossível, mas raro.
    failures = fields.get("failures")
    if failures is not None and failures >= 3:
        # Lista das notas (G1 e/ou G2) que são altas, se as houver.
        high_grades = [
            fields[g] for g in ("G1", "G2")
            if fields.get(g) is not None and fields[g] >= 15
        ]
        if high_grades:
            warnings.append({
                "field": "failures",
                "severity": "info",
                "message": t(
                    lang,
                    "3 ou mais reprovações anteriores combinadas com notas altas é pouco comum "
                    "no dataset atual — confirma que os valores correspondem ao mesmo estudante.",
                    "3 or more prior failures combined with high grades is uncommon in the "
                    "current dataset — please confirm the values belong to the same student.",
                ),
            })

    return warnings
