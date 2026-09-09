# Testes para src/statistics_analysis.py — resumo textual (overview) dos dados.
from src.data_processing import get_processed_data
from src.statistics_analysis import generate_overview_summary


def test_generate_overview_summary_returns_non_empty_text():
    # O resumo deve ser sempre uma string não trivial (com conteúdo real).
    df = get_processed_data()
    summary = generate_overview_summary(df)
    assert isinstance(summary, str)
    assert len(summary) > 30


def test_generate_overview_summary_mentions_key_figures():
    # O resumo deve mencionar o número total de estudantes e pelo menos uma percentagem.
    df = get_processed_data()
    summary = generate_overview_summary(df)
    assert str(len(df)) in summary
    assert "%" in summary


def test_generate_overview_summary_changes_with_different_data():
    df = get_processed_data()
    summary_full = generate_overview_summary(df)
    summary_subset = generate_overview_summary(df.head(50))
    # Datasets diferentes (nº de estudantes muda) -> texto tem de refletir isso.
    assert summary_full != summary_subset
