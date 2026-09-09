"""
Exportação do dataset (ou de uma vista filtrada dele) para CSV, a partir da
página "Dados" — os mesmos filtros disponíveis no explorador (escola, nível
de desempenho, risco) podem ser aplicados antes de descarregar o ficheiro.
"""
# Permite usar "Optional[str]" nas anotações de tipo sem problemas de
# compatibilidade entre versões do Python.
from __future__ import annotations

# Optional serve para indicar que um parâmetro pode ser None (não obrigatório).
from typing import Optional

# pandas é a biblioteca usada para manipular o dataset como uma tabela (DataFrame).
import pandas as pd

# Mesmas colunas mostradas na tabela do explorador (ver /students/table em
# src/api.py), para que o CSV exportado corresponda ao que o utilizador vê.
EXPORT_COLUMNS = [
    "student_id", "school", "sex", "age", "studytime", "absences",
    "failures", "G1", "G2", "G3", "perf_band", "at_risk",
]


def export_students_csv(
    df: pd.DataFrame,
    school: Optional[str] = None,
    perf_band: Optional[str] = None,
    at_risk: Optional[int] = None,
) -> str:
    """
    Filtra o dataset (mesmos filtros do explorador de dados) e devolve o
    resultado como texto CSV pronto a descarregar.
    """
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
    # Converte a tabela filtrada para texto CSV, sem incluir o índice do pandas.
    return filtered[cols].to_csv(index=False)
