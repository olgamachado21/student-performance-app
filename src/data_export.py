"""
Exportação do dataset (ou de uma vista filtrada dele) para CSV, a partir da
página "Dados" — os mesmos filtros disponíveis no explorador (escola, nível
de desempenho, risco) podem ser aplicados antes de descarregar o ficheiro.

i18n: os cabeçalhos do CSV sempre foram os nomes internos das colunas (ex.:
"student_id", "G3") — nunca houve uma "versão PT bonita" deles, por isso o
comportamento por omissão (lang="pt"/None) tinha de se manter exatamente
como estava (nomes internos, testes existentes dependem disto). Só quando
lang="en" é pedido explicitamente é que os cabeçalhos passam a usar
EXPORT_COLUMN_LABELS["en"], com o mesmo vocabulário já usado nos relatórios
PDF (ver STUDYTIME_LABELS e os cabeçalhos de tabela em src/reports_pdf.py),
para o CSV e os PDFs usarem sempre os mesmos termos em inglês.
"""
# Permite usar "Optional[str]" nas anotações de tipo sem problemas de
# compatibilidade entre versões do Python.
from __future__ import annotations

# Optional serve para indicar que um parâmetro pode ser None (não obrigatório).
from typing import Optional

# pandas é a biblioteca usada para manipular o dataset como uma tabela (DataFrame).
import pandas as pd

from src.i18n import normalize_lang

# Mesmas colunas mostradas na tabela do explorador (ver /students/table em
# src/api.py), para que o CSV exportado corresponda ao que o utilizador vê.
EXPORT_COLUMNS = [
    "student_id", "school", "sex", "age", "studytime", "absences",
    "failures", "G1", "G2", "G3", "perf_band", "at_risk",
]

# Cabeçalho amigável de cada coluna exportada, só para inglês — em
# português mantém-se o nome interno da coluna (ver nota de i18n acima).
EXPORT_COLUMN_LABELS_EN = {
    "student_id": "Student ID",
    "school": "School",
    "sex": "Sex",
    "age": "Age",
    "studytime": "Study Time",
    "absences": "Absences",
    "failures": "Failures",
    "G1": "Grade 1st Period (G1)",
    "G2": "Grade 2nd Period (G2)",
    "G3": "Final Grade (G3)",
    "perf_band": "Performance Level",
    "at_risk": "At Risk",
}


def export_students_csv(
    df: pd.DataFrame,
    school: Optional[str] = None,
    perf_band: Optional[str] = None,
    at_risk: Optional[int] = None,
    lang: Optional[str] = None,
) -> str:
    """
    Filtra o dataset (mesmos filtros do explorador de dados) e devolve o
    resultado como texto CSV pronto a descarregar, com os cabeçalhos no
    idioma pedido (só os cabeçalhos mudam — os valores das células, ex.:
    "GP"/"MS" para escola, mantêm-se tal como estão nos dados).
    """
    lang = normalize_lang(lang)
    # Começa com o dataset completo; cada filtro abaixo é aplicado só se
    # o respetivo parâmetro tiver sido indicado.
    filtered = df
    # Filtro por escola (ex.: "GP" ou "MS") — só aplicado se foi passado um valor.
    if school:
        filtered = filtered[filtered["school"] == school]
    # Filtro por nível de desempenho (ex.: "Alto", "Médio", "Baixo").
    if perf_band:
        filtered = filtered[filtered["perf_band"] == perf_band]
    # Filtro por risco: usa "is not None" porque 0 (não está em risco) também
    # é um valor válido e não deve ser tratado como "sem filtro".
    if at_risk is not None:
        filtered = filtered[filtered["at_risk"] == at_risk]

    # Mantém só as colunas de EXPORT_COLUMNS que realmente existem no
    # DataFrame filtrado, para não rebentar caso alguma coluna não exista.
    cols = [c for c in EXPORT_COLUMNS if c in filtered.columns]

    if lang == "en":
        # Cabeçalhos traduzidos; se alguma coluna não tiver tradução definida
        # (não deve acontecer com as colunas de EXPORT_COLUMNS, mas por
        # segurança), usa o nome interno da coluna como fallback.
        header = [EXPORT_COLUMN_LABELS_EN.get(c, c) for c in cols]
        return filtered[cols].to_csv(index=False, header=header)

    # PT (omissão): comportamento inalterado — nomes internos das colunas.
    return filtered[cols].to_csv(index=False)
