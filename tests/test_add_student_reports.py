# Testes para src/add_student.py (adicionar estudante manualmente) e para a
# geração de fichas/insights em src/reports_pdf.py associados a esse fluxo.
import os

# Usa uma base de dados SQLite à parte (em /tmp) para não misturar estes
# testes com os dados reais nem com os de outros ficheiros de teste.
os.environ.setdefault("SQLITE_DB_PATH", "/tmp/test_add_student.db")

from src import database
from src.add_student import add_student
from src.data_processing import get_processed_data
from src.reports_pdf import gerar_ficha_pdf, gerar_insight_personalizado


def _reset():
    # Força a recriação da ligação à BD e esvazia a tabela de estudantes
    # adicionados manualmente, para cada teste partir de um estado limpo.
    database._engine = None
    if database.table_exists("Students_Added"):
        # limpa a tabela para os testes serem independentes
        import pandas as pd
        database.write_table(pd.DataFrame(columns=[]), "Students_Added", if_exists="replace")


def test_add_student_predicts_grade_and_persists():
    # Adicionar um estudante deve calcular uma previsão de nota válida e
    # gravá-lo, aumentando o total de estudantes no dataset processado.
    _reset()
    before = get_processed_data()
    n_before = len(before)

    result = add_student({
        "school": "GP", "sex": "F", "age": 16, "studytime": 4,
        "absences": 0, "failures": 0, "G1": 18, "G2": 19,
    })

    assert 0 <= result["added_student"]["G3"] <= 20
    assert result["added_student"]["G3"] >= 14  # bom aluno, nota devia ser alta

    after = get_processed_data()
    assert len(after) == n_before + 1


def test_add_student_fills_defaults():
    # Campos não fornecidos pelo utilizador devem ser preenchidos automaticamente.
    result = add_student({"school": "MS", "sex": "M", "age": 18, "studytime": 1,
                           "absences": 5, "failures": 1, "G1": 8, "G2": 9})
    student = result["added_student"]
    # campos não fornecidos devem ter sido preenchidos com valores por omissão
    assert student["internet"] in ("yes", "no")
    assert student["Medu"] is not None


def test_gerar_insight_personalizado_mentions_grade():
    # O texto de insight gerado para um estudante deve ser uma frase com conteúdo real.
    df = get_processed_data()
    student_id = int(df.iloc[0]["student_id"])
    text = gerar_insight_personalizado(df, student_id)
    assert isinstance(text, str)
    assert len(text) > 20


def test_gerar_ficha_pdf_returns_valid_pdf_bytes():
    # A ficha individual do estudante deve ser um PDF válido e não vazio.
    df = get_processed_data()
    student_id = int(df.iloc[0]["student_id"])
    pdf_bytes = gerar_ficha_pdf(df, student_id)
    assert pdf_bytes[:4] == b"%PDF"
    assert len(pdf_bytes) > 500


def test_gerar_ficha_pdf_invalid_student_raises():
    # Um student_id inexistente deve levantar ValueError em vez de gerar um PDF vazio/quebrado.
    df = get_processed_data()
    try:
        gerar_ficha_pdf(df, 999999)
        assert False, "devia ter lançado ValueError"
    except ValueError:
        pass
