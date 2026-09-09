# Testes para src/exam_week.py — checklist de última semana antes dos exames
# (sugere as mudanças de hábito com maior ganho estimado de nota).
import pytest

from src.exam_week import gerar_checklist_ultima_semana


# Hábitos no pior cenário possível (muito espaço para melhorar em tudo).
WORST_CASE_HABITS = {
    "studytime": 1, "absences": 5, "failures": 0, "goout": 5,
    "Dalc": 5, "Walc": 5, "internet": "yes", "higher": "yes",
    "schoolsup": "no", "romantic": "no",
}

# Hábitos já no melhor valor possível (sem margem de melhoria).
BEST_CASE_HABITS = {
    "studytime": 4, "absences": 0, "failures": 0, "goout": 1,
    "Dalc": 1, "Walc": 1,
}


def test_checklist_has_items_when_room_to_improve():
    # Com hábitos no pior cenário, deve haver itens sugeridos para melhorar.
    result = gerar_checklist_ultima_semana(WORST_CASE_HABITS)
    assert len(result["items"]) > 0
    assert "baseline_grade" in result


def test_checklist_items_sorted_by_estimated_gain_descending():
    # Os itens devem vir ordenados do maior para o menor ganho estimado.
    result = gerar_checklist_ultima_semana(WORST_CASE_HABITS)
    gains = [item["estimated_gain"] for item in result["items"]]
    assert gains == sorted(gains, reverse=True)


def test_checklist_items_all_have_positive_gain():
    # Só devem aparecer sugestões que realmente melhorem a nota estimada.
    result = gerar_checklist_ultima_semana(WORST_CASE_HABITS)
    for item in result["items"]:
        assert item["estimated_gain"] > 0


def test_checklist_respects_limit():
    # O parâmetro limit deve limitar o número de itens devolvidos.
    result = gerar_checklist_ultima_semana(WORST_CASE_HABITS, limit=2)
    assert len(result["items"]) <= 2


def test_checklist_empty_when_already_at_best_values():
    # Já nos melhores valores possíveis, não há nada a sugerir.
    result = gerar_checklist_ultima_semana(BEST_CASE_HABITS)
    assert result["items"] == []
    assert "Não há mudanças rápidas" in result["message"]


def test_checklist_respects_absences_lower_bound():
    # Com absences já em 0 (o mínimo possível), não deve sugerir reduzir mais faltas.
    habits = {**WORST_CASE_HABITS, "absences": 0}
    result = gerar_checklist_ultima_semana(habits)
    assert all(item["feature"] != "absences" for item in result["items"])


def test_checklist_respects_studytime_upper_bound():
    # Com studytime já no máximo (4), não deve sugerir aumentar mais.
    habits = {**WORST_CASE_HABITS, "studytime": 4}
    result = gerar_checklist_ultima_semana(habits)
    assert all(item["feature"] != "studytime" for item in result["items"])


def test_checklist_item_action_text_mentions_from_and_to_for_studytime():
    # O texto da ação deve mencionar tanto o valor atual como o valor sugerido.
    habits = {**WORST_CASE_HABITS, "studytime": 1}
    result = gerar_checklist_ultima_semana(habits)
    studytime_item = next((i for i in result["items"] if i["feature"] == "studytime"), None)
    assert studytime_item is not None
    assert "1" in studytime_item["action"] and "2" in studytime_item["action"]


def test_checklist_uses_defaults_for_missing_habits():
    # Sem "studytime"/"goout"/etc. no dicionário, deve usar os valores por
    # omissão do dataset (get_defaults) em vez de rebentar.
    result = gerar_checklist_ultima_semana({})
    assert "baseline_grade" in result
    assert isinstance(result["items"], list)


def test_checklist_message_reflects_item_count():
    # A mensagem final deve referir o número de itens sugeridos.
    result = gerar_checklist_ultima_semana(WORST_CASE_HABITS)
    assert str(len(result["items"])) in result["message"]


# ------------------------------------------------------------------
# Camada da API
# ------------------------------------------------------------------

def test_api_exam_week_checklist_endpoint():
    # O endpoint deve aceitar um StudentInput completo e devolver a mesma estrutura.
    from src.api import StudentInput, exam_week_checklist

    payload = StudentInput(**WORST_CASE_HABITS)
    result = exam_week_checklist(payload)
    assert "items" in result
    assert "baseline_grade" in result


def test_api_exam_week_checklist_endpoint_with_partial_input():
    # O endpoint também deve funcionar com um input parcial (campos em falta usam defaults).
    from src.api import StudentInput, exam_week_checklist

    payload = StudentInput(studytime=1, absences=3)
    result = exam_week_checklist(payload)
    assert "items" in result
