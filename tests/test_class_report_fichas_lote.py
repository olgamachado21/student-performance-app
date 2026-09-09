# Testes para o relatório de turma e a geração de fichas em lote (src/reports_pdf.py).
import io
import zipfile

import pytest

from src.data_processing import get_processed_data
from src.reports_pdf import gerar_fichas_lote_zip, gerar_relatorio_turma_pdf


def test_gerar_relatorio_turma_pdf_returns_valid_pdf_bytes():
    # O ficheiro gerado deve ser um PDF válido (assinatura "%PDF" no início) e não vazio.
    df = get_processed_data()
    pdf_bytes = gerar_relatorio_turma_pdf(df)

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 2000  # relatório com tabelas, não deve ficar vazio/trivial


def test_gerar_relatorio_turma_pdf_handles_long_segment_names(monkeypatch):
    # Regressão: os nomes de perfil da segmentação (coluna "Perfil" da tabela)
    # são gerados automaticamente e podem ser bastante compridos (ex.: "Consumo
    # de Álcool ao Fim de Semana & Consumo de Álcool em Dias Úteis"). Antes,
    # esse texto era colocado na tabela como string simples — o reportlab NÃO
    # quebra linha em strings simples dentro de uma célula, por isso um nome
    # comprido continuava para além da largura da coluna e ficava sobreposto
    # aos números da coluna seguinte ("Estudantes"). Agora usa-se um Paragraph
    # (que quebra linha automaticamente), e este teste simula um nome ainda
    # mais longo do que qualquer um dos 4 nomes reais para garantir que a
    # função continua a gerar um PDF válido em vez de rebentar ou cortar
    # conteúdo, mesmo num caso extremo.
    nome_muito_comprido = (
        "Perfil Com Um Nome Extremamente Comprido Para Testar Que A Coluna "
        "Quebra Linha Corretamente Em Vez De Sobrepor os Números Vizinhos"
    )

    def fake_run_segmentation(df, n_clusters=4):
        return {
            "groups": [
                {"name": nome_muito_comprido, "size": 100, "size_pct": 50.0, "avg_grade": 12.3, "risk_pct": 10.0},
                {"name": "Perfil Curto", "size": 100, "size_pct": 50.0, "avg_grade": 11.0, "risk_pct": 20.0},
            ]
        }

    # run_segmentation é importado tardiamente (dentro da função, para evitar import
    # circular — ver o código de gerar_relatorio_turma_pdf), por isso o monkeypatch
    # tem de ser feito no módulo de origem (src.segmentation), não em src.reports_pdf.
    import src.segmentation as segmentation_module
    monkeypatch.setattr(segmentation_module, "run_segmentation", fake_run_segmentation)

    df = get_processed_data()
    pdf_bytes = gerar_relatorio_turma_pdf(df)

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 2000


def test_gerar_fichas_lote_zip_returns_valid_zip_with_pdfs():
    # O ZIP deve conter só PDFs válidos, nomeados de forma previsível.
    df = get_processed_data()
    zip_bytes = gerar_fichas_lote_zip(df, only_at_risk=True, limit=5)

    assert isinstance(zip_bytes, bytes)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        assert len(names) > 0
        assert len(names) <= 5
        for name in names:
            assert name.startswith("ficha_estudante_") and name.endswith(".pdf")
            content = zf.read(name)
            assert content.startswith(b"%PDF")


def test_gerar_fichas_lote_zip_respects_limit():
    # O número de fichas geradas nunca deve ultrapassar o limite pedido.
    df = get_processed_data()
    zip_bytes = gerar_fichas_lote_zip(df, only_at_risk=True, limit=3)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        assert len(zf.namelist()) <= 3


def test_gerar_fichas_lote_zip_raises_when_no_students_match():
    # Sem nenhum estudante em risco, deve levantar erro em vez de gerar um ZIP vazio.
    df = get_processed_data()
    empty_at_risk = df.copy()
    empty_at_risk["at_risk"] = 0
    with pytest.raises(ValueError):
        gerar_fichas_lote_zip(empty_at_risk, only_at_risk=True, limit=5)


def test_gerar_fichas_lote_zip_all_students_when_not_only_at_risk():
    # Com only_at_risk=False, gera exatamente "limit" fichas, sem filtrar por risco.
    df = get_processed_data()
    zip_bytes = gerar_fichas_lote_zip(df, only_at_risk=False, limit=10)
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        assert len(zf.namelist()) == 10
