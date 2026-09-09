"""Testes para src/chatbot.py — assistente baseado em regras (sem LLM externo)."""
# pytest: framework de testes usado em todo o projeto.
import pytest

from src.chatbot import EXAMPLE_QUESTIONS, _extract_student_id, answer_question
from src.data_processing import get_processed_data


@pytest.fixture(scope="module")
def df():
    # Carrega o dataset processado uma única vez para todos os testes deste ficheiro
    # (scope="module"), em vez de recarregar a cada teste — mais rápido.
    return get_processed_data()


@pytest.fixture(scope="module")
def sample_student_id(df):
    # Um id de estudante válido qualquer, para testar perguntas sobre "um estudante".
    return int(df.iloc[0]["student_id"])


@pytest.fixture(scope="module")
def at_risk_student_id(df):
    # Um estudante em risco, necessário para testar o plano de recuperação
    # (o Otimizador só faz sentido testar com alguém que precise de melhorar).
    at_risk = df[df["at_risk"] == 1]
    if at_risk.empty:
        # Se por acaso o dataset atual não tiver ninguém em risco, salta este teste em vez de falhar.
        pytest.skip("Dataset atual não tem nenhum estudante em risco para testar.")
    return int(at_risk.iloc[0]["student_id"])


# ------------------------------------------------------------------
# Extração do id do estudante a partir da pergunta
# ------------------------------------------------------------------

def test_extract_student_id_with_keyword():
    # Casos em que o id aparece logo a seguir a uma palavra-chave ("aluno", "estudante", "id").
    assert _extract_student_id("como está o aluno 12?") == 12
    assert _extract_student_id("Estudante 45 está em risco?") == 45
    assert _extract_student_id("id 7") == 7


def test_extract_student_id_lone_number_with_alunowword():
    # Caso em que o número não está logo a seguir à palavra, mas ainda é o único número da frase.
    assert _extract_student_id("o aluno 9 vai bem?") == 9


def test_extract_student_id_no_keyword_no_number_returns_none():
    # Sem nenhuma palavra-chave nem número — não há id nenhum a extrair.
    assert _extract_student_id("qual é a taxa de aprovação?") is None


def test_extract_student_id_number_without_student_word_is_ignored():
    # "15" aqui é claramente uma nota-alvo, não haveria "aluno"/"estudante"
    # na frase — não deve ser confundido com um id.
    assert _extract_student_id("quero chegar a 15 valores") is None


# ------------------------------------------------------------------
# Perguntas gerais / ajuda
# ------------------------------------------------------------------

def test_empty_question_returns_fallback(df):
    # Pergunta vazia deve cair sempre no fallback, nunca dar erro.
    result = answer_question(df, "")
    assert result["intent"] == "fallback"


def test_help_intent(df):
    # Pedir ajuda deve devolver a lista completa de perguntas de exemplo.
    result = answer_question(df, "ajuda")
    assert result["intent"] == "help"
    for example in EXAMPLE_QUESTIONS:
        assert example in result["answer"]


def test_unrecognized_question_returns_fallback(df):
    # Pergunta totalmente fora do âmbito do chatbot deve cair no fallback.
    result = answer_question(df, "qual é a capital de Portugal?")
    assert result["intent"] == "fallback"


# ------------------------------------------------------------------
# Perguntas sobre um estudante específico
# ------------------------------------------------------------------

def test_student_status(df, sample_student_id):
    # Pergunta genérica sobre um estudante deve devolver o estado geral (student_status).
    result = answer_question(df, f"como está o aluno {sample_student_id}?")
    assert result["intent"] == "student_status"
    assert str(sample_student_id) in result["answer"]


def test_student_not_found(df):
    # Id que claramente não existe no dataset (999999) deve ser tratado como "não encontrado".
    result = answer_question(df, "como está o aluno 999999?")
    assert result["intent"] == "student_not_found"


def test_student_explain(df, sample_student_id):
    # Pergunta com "porque" deve acionar a explicação da previsão (student_explain).
    result = answer_question(df, f"porque é que o aluno {sample_student_id} está em risco?")
    assert result["intent"] == "student_explain"
    assert str(sample_student_id) in result["answer"]


def test_student_plan_already_above_target(df, sample_student_id):
    # Nota-alvo de 0 valores: qualquer estudante já a atinge, sem precisar de mudanças.
    result = answer_question(df, f"o que precisa o aluno {sample_student_id} para chegar a 0 valores?")
    assert result["intent"] == "student_plan"


def test_student_plan_with_target(df, at_risk_student_id):
    # Estudante em risco a tentar atingir 15 valores — testa o caminho "normal" do plano.
    result = answer_question(df, f"o que precisa o aluno {at_risk_student_id} para chegar a 15 valores?")
    assert result["intent"] == "student_plan"
    assert str(at_risk_student_id) in result["answer"]


def test_student_compare(df, sample_student_id):
    # Pergunta de comparação com a turma deve acionar student_compare.
    result = answer_question(df, f"como está o aluno {sample_student_id} comparado com a turma?")
    assert result["intent"] == "student_compare"


# ------------------------------------------------------------------
# Perguntas agregadas sobre o dataset
# ------------------------------------------------------------------

def test_pass_rate_question(df):
    # A resposta deve incluir uma percentagem (a taxa de aprovação).
    result = answer_question(df, "qual é a taxa de aprovação?")
    assert result["intent"] == "dataset_stats"
    assert "%" in result["answer"]


def test_risk_question(df):
    result = answer_question(df, "quantos estudantes estão em risco?")
    assert result["intent"] == "dataset_stats"


def test_average_grade_question(df):
    result = answer_question(df, "qual é a nota média?")
    assert result["intent"] == "dataset_stats"


def test_n_students_question(df):
    # A resposta deve mencionar o número exato de estudantes do dataset atual.
    result = answer_question(df, "quantos estudantes há no dataset?")
    assert result["intent"] == "dataset_stats"
    assert str(len(df)) in result["answer"]


def test_correlation_question(df):
    result = answer_question(df, "qual é o fator mais correlacionado com a nota final?")
    assert result["intent"] == "dataset_stats"


def test_summary_question(df):
    # O resumo automático (generate_overview_summary) deve devolver algum texto não vazio.
    result = answer_question(df, "dá-me um resumo geral da turma")
    assert result["intent"] == "dataset_stats"
    assert len(result["answer"]) > 0


# ------------------------------------------------------------------
# Ajuda a navegar a app
# ------------------------------------------------------------------

def test_navigation_help_export(df):
    # Pergunta sobre exportar deve referir CSV na resposta.
    result = answer_question(df, "como exporto os dados em csv?")
    assert result["intent"] == "navigation_help"
    assert "CSV" in result["answer"] or "csv" in result["answer"].lower()


def test_navigation_help_alerts(df):
    result = answer_question(df, "onde vejo os avisos?")
    assert result["intent"] == "navigation_help"


# ------------------------------------------------------------------
# Camada da API
# ------------------------------------------------------------------

def test_api_chatbot_ask_endpoint():
    # Testa o endpoint POST /chatbot/ask diretamente, chamando a função do FastAPI.
    from src.api import ChatQuestionInput, chatbot_ask

    result = chatbot_ask(ChatQuestionInput(question="qual é a taxa de aprovação?"))
    assert result["intent"] == "dataset_stats"


def test_api_chatbot_examples_endpoint():
    # Testa o endpoint GET /chatbot/examples — deve devolver exatamente a mesma lista de exemplos.
    from src.api import chatbot_examples

    result = chatbot_examples()
    assert result["examples"] == EXAMPLE_QUESTIONS
