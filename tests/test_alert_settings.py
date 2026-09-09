# Testes para os limiares de alerta configuráveis em src/settings.py e o
# seu efeito em src/alerts.py (generate_alerts).
import pytest

from src import settings
from src.alerts import generate_alerts
from src.data_processing import get_processed_data


def test_default_alert_settings():
    # Sem configuração guardada, os limiares de alerta devem ter os valores por omissão.
    current = settings.get_settings()
    assert current["alert_risk_threshold"] == settings.DEFAULT_ALERT_RISK_THRESHOLD
    assert current["alert_min_absences"] == settings.DEFAULT_ALERT_MIN_ABSENCES


def test_save_and_read_alert_risk_threshold():
    # Guardar o limiar de taxa de risco deve ficar persistido.
    updated = settings.save_settings(alert_risk_threshold=0.15)
    assert updated["alert_risk_threshold"] == 0.15
    assert settings.get_settings()["alert_risk_threshold"] == 0.15


def test_save_and_read_alert_min_absences():
    # Guardar o limiar mínimo de faltas deve ficar persistido.
    updated = settings.save_settings(alert_min_absences=12)
    assert updated["alert_min_absences"] == 12
    assert settings.get_settings()["alert_min_absences"] == 12


def test_reset_alert_min_absences_with_sentinel():
    # O valor sentinela -1 deve repor o limiar de faltas para "sem limite" (None).
    settings.save_settings(alert_min_absences=20)
    assert settings.get_settings()["alert_min_absences"] == 20
    reset = settings.save_settings(alert_min_absences=-1)
    assert reset["alert_min_absences"] is None
    assert settings.get_settings()["alert_min_absences"] is None


def test_save_settings_rejects_out_of_range_risk_threshold():
    # O limiar de risco tem de estar entre 0 (exclusivo) e 1 (exclusivo/inclusivo, conforme regra).
    with pytest.raises(ValueError):
        settings.save_settings(alert_risk_threshold=1.5)
    with pytest.raises(ValueError):
        settings.save_settings(alert_risk_threshold=0.0)


def test_save_settings_rejects_negative_min_absences():
    # Um número negativo de faltas (que não seja o sentinela -1) não é válido.
    with pytest.raises(ValueError):
        settings.save_settings(alert_min_absences=-5)


def test_generate_alerts_respects_custom_risk_rate_threshold():
    df = get_processed_data()
    # Um limiar muito baixo (1%) deve disparar sempre o aviso de taxa de risco.
    alerts_low_threshold = generate_alerts(df, risk_rate_threshold=0.01)
    assert any(a["id"] == "risk_rate_high" for a in alerts_low_threshold)

    # Um limiar muito alto (99%) não deve disparar (a menos que quase toda a
    # turma esteja em risco, o que não acontece neste dataset).
    alerts_high_threshold = generate_alerts(df, risk_rate_threshold=0.99)
    assert not any(a["id"] == "risk_rate_high" for a in alerts_high_threshold)


def test_generate_alerts_respects_custom_min_absences():
    df = get_processed_data()
    # Um limiar de faltas muito alto (acima do máximo do dataset) não deve
    # sinalizar ninguém.
    max_absences = int(df["absences"].max())
    alerts_high = generate_alerts(df, min_absences=max_absences + 100)
    assert not any(a["id"] == "high_absences" for a in alerts_high)

    # Um limiar de faltas muito baixo (0) deve sinalizar quase toda a gente
    # com pelo menos 1 falta.
    alerts_low = generate_alerts(df, min_absences=0)
    high_absences_alert = next((a for a in alerts_low if a["id"] == "high_absences"), None)
    assert high_absences_alert is not None


def test_generate_alerts_uses_saved_settings_when_no_override_given():
    # Sem parâmetros explícitos, generate_alerts deve ler os limiares gravados em settings.
    df = get_processed_data()
    settings.save_settings(alert_risk_threshold=0.01)
    alerts_default_call = generate_alerts(df)
    assert any(a["id"] == "risk_rate_high" for a in alerts_default_call)
    # repor para não afetar outros testes que corram a seguir
    settings.save_settings(alert_risk_threshold=settings.DEFAULT_ALERT_RISK_THRESHOLD)
