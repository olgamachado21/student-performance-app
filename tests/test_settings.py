# Testes para src/settings.py — temas, fonte e limiares de alerta configuráveis.
import pytest

from src import settings


def test_default_settings():
    # Sem nenhuma configuração guardada ainda, deve devolver os valores por omissão.
    current = settings.get_settings()
    assert current["theme"] == settings.DEFAULT_THEME
    assert current["font"] == settings.DEFAULT_FONT


def test_list_themes_returns_all_with_colors():
    # Cada tema listado deve ter todos os campos necessários para o seletor da interface.
    themes = settings.list_themes()
    assert len(themes) == len(settings.THEMES)
    for theme in themes:
        assert "id" in theme and "name" in theme and "mode" in theme and "colors" in theme
        assert theme["mode"] in ("claro", "escuro")


def test_save_settings_persists_theme_and_font():
    # Guardar um tema/fonte deve ficar persistido — lido de novo dá o mesmo valor.
    updated = settings.save_settings(theme="oceano", font="Georgia")
    assert updated["theme"] == "oceano"
    assert updated["font"] == "Georgia"
    current = settings.get_settings()
    assert current["theme"] == "oceano"
    assert current["font"] == "Georgia"


def test_save_settings_partial_update_keeps_other_field():
    # Atualizar só o tema não deve apagar a fonte guardada anteriormente.
    settings.save_settings(theme="floresta", font="Roboto")
    updated = settings.save_settings(theme="ametista")
    assert updated["theme"] == "ametista"
    assert updated["font"] == "Roboto"


def test_save_settings_rejects_invalid_theme():
    # Um id de tema inexistente deve ser rejeitado.
    with pytest.raises(ValueError):
        settings.save_settings(theme="tema-que-nao-existe")


def test_save_settings_rejects_invalid_font():
    # Uma fonte fora da lista permitida deve ser rejeitada.
    with pytest.raises(ValueError):
        settings.save_settings(font="Fonte Fake")
