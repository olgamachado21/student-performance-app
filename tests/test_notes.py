# Testes para src/notes.py — comentários curtos ligados a um estudante,
# opcionalmente associados ao alerta que os motivou.
import pytest

from src import notes


def test_add_note_returns_saved_fields():
    saved = notes.add_note(1, "Falei com ele, vai melhorar a assiduidade.")
    assert saved["student_id"] == 1
    assert saved["text"] == "Falei com ele, vai melhorar a assiduidade."
    assert saved["context"] is None
    assert saved["created_at"]
    assert isinstance(saved["id"], int)


def test_add_note_strips_text_and_context():
    saved = notes.add_note(2, "   Com espaços à volta.   ", context="  Risco combinado  ")
    assert saved["text"] == "Com espaços à volta."
    assert saved["context"] == "Risco combinado"


def test_add_note_rejects_empty_text():
    with pytest.raises(ValueError, match="vazio"):
        notes.add_note(1, "")
    with pytest.raises(ValueError, match="vazio"):
        notes.add_note(1, "    ")


def test_get_notes_filters_by_student_and_orders_most_recent_first():
    notes.add_note(3, "Primeiro comentário.")
    second = notes.add_note(3, "Segundo comentário.")
    notes.add_note(4, "Comentário de outro estudante.")

    student3_notes = notes.get_notes(student_id=3)
    assert all(n["student_id"] == 3 for n in student3_notes)
    assert student3_notes[0]["id"] == second["id"]  # o mais recente primeiro


def test_get_notes_without_student_id_returns_all():
    notes.add_note(5, "Nota A.")
    notes.add_note(6, "Nota B.")
    all_notes = notes.get_notes()
    ids = {n["id"] for n in all_notes}
    student_ids = {n["student_id"] for n in all_notes}
    assert 5 in student_ids and 6 in student_ids
    assert len(ids) == len(all_notes)


def test_get_notes_for_student_with_no_notes_is_empty_list():
    assert notes.get_notes(student_id=999_999) == []


def test_delete_note_removes_it():
    saved = notes.add_note(7, "Para apagar.")
    assert notes.delete_note(saved["id"]) is True
    remaining = notes.get_notes(student_id=7)
    assert all(n["id"] != saved["id"] for n in remaining)


def test_delete_note_not_found_returns_false():
    assert notes.delete_note(9_999_999) is False


def test_note_with_alert_context_round_trips():
    saved = notes.add_note(
        8,
        "Faltas a subir depois do alerta.",
        context="Risco combinado: faltas altas e reprovação anterior",
    )
    reloaded = next(n for n in notes.get_notes(student_id=8) if n["id"] == saved["id"])
    assert reloaded["context"] == "Risco combinado: faltas altas e reprovação anterior"
