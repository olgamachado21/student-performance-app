"""Testes para src/backup.py e os endpoints /backup em src/api.py — cópias de
segurança manuais e automáticas da base de dados SQLite. Cobre criar, listar,
restaurar, apagar, a política de retenção (só cópias automáticas/pré-restauro
são podadas, nunca as manuais) e o agendador em segundo plano."""
import os
import shutil
import time
from pathlib import Path

# Base de dados e pasta de backups isoladas em /tmp, para estes testes não
# afetarem os dados reais nem interferirem com outros ficheiros de teste.
os.environ.setdefault("SQLITE_DB_PATH", "/tmp/test_backup.db")
os.environ.setdefault("STUDENTPERFOMANCE_BACKUP_DIR", "/tmp/test_backup_dir")

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src import backup as backup_module
from src import config, database
from src.api import app

client = TestClient(app)


def _ensure_db_exists():
    """Garante que existe um ficheiro de BD válido para copiar (uma tabela simples)."""
    database.write_table(pd.DataFrame({"a": [1, 2, 3]}), "Backup_Test_Table")


def _clean_backup_dir():
    if config.BACKUP_DIR.exists():
        shutil.rmtree(config.BACKUP_DIR, ignore_errors=True)
    config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)


@pytest.fixture(autouse=True)
def _clean_state():
    """Garante que cada teste começa com a BD presente e a pasta de backups vazia,
    e que o agendador automático está sempre parado entre testes."""
    backup_module.stop_auto_backup()
    _ensure_db_exists()
    _clean_backup_dir()
    yield
    backup_module.stop_auto_backup()
    _clean_backup_dir()


# ---------------------------------------------------------------------------
# Módulo src/backup.py diretamente
# ---------------------------------------------------------------------------
def test_create_backup_manual():
    result = backup_module.create_backup(reason=backup_module.MANUAL_BACKUP_REASON)
    assert result["reason"] == "manual"
    assert (config.BACKUP_DIR / result["filename"]).exists()
    assert result["size_bytes"] > 0


def test_list_backups_empty_then_populated():
    assert backup_module.list_backups() == []
    backup_module.create_backup(reason=backup_module.MANUAL_BACKUP_REASON)
    backups = backup_module.list_backups()
    assert len(backups) == 1
    assert backups[0]["reason"] == "manual"


def test_list_backups_most_recent_first():
    backup_module.create_backup(reason=backup_module.MANUAL_BACKUP_REASON)
    time.sleep(1.1)  # garante um timestamp de ficheiro diferente
    backup_module.create_backup(reason=backup_module.AUTO_BACKUP_REASON)
    backups = backup_module.list_backups()
    assert len(backups) == 2
    assert backups[0]["reason"] == "automatico"
    assert backups[1]["reason"] == "manual"


def test_create_backup_without_existing_db_raises(monkeypatch):
    # Aponta temporariamente config.SQLITE_PATH para um caminho que nunca
    # existe, em vez de apagar o ficheiro real de /tmp/test_backup.db —
    # apagar e recriar esse ficheiro no meio da suite mostrou-se instável
    # neste sandbox (o mesmo problema de ficheiros sujeitos a
    # unlink()/reescrita já documentado noutros testes deste projeto).
    monkeypatch.setattr(config, "SQLITE_PATH", Path("/tmp/tmp_nao_existe_backup_test.db"))
    with pytest.raises(ValueError):
        backup_module.create_backup()


def test_restore_backup_brings_back_deleted_table():
    backup_module.create_backup(reason=backup_module.MANUAL_BACKUP_REASON)
    backup_id = backup_module.list_backups()[0]["id"]

    database.drop_table("Backup_Test_Table")
    assert not database.table_exists("Backup_Test_Table")

    backup_module.restore_backup(backup_id)
    assert database.table_exists("Backup_Test_Table")

    # o restauro deve ter criado automaticamente uma cópia de pré-restauro
    reasons = [b["reason"] for b in backup_module.list_backups()]
    assert "pre_restauro" in reasons


def test_restore_unknown_backup_raises():
    with pytest.raises(ValueError):
        backup_module.restore_backup("nao_existe.db")


def test_restore_rejects_path_traversal():
    with pytest.raises(ValueError):
        backup_module.restore_backup("../../etc/passwd")


def test_delete_backup():
    result = backup_module.create_backup(reason=backup_module.MANUAL_BACKUP_REASON)
    backup_id = result["id"]
    assert len(backup_module.list_backups()) == 1

    backup_module.delete_backup(backup_id)
    assert backup_module.list_backups() == []


def test_delete_unknown_backup_raises():
    with pytest.raises(ValueError):
        backup_module.delete_backup("nao_existe.db")


def test_retention_keeps_manual_backups_forever():
    """Cópias manuais nunca são podadas pela política de retenção, mesmo
    quando há muito mais cópias automáticas do que o limite."""
    backup_module.create_backup(reason=backup_module.MANUAL_BACKUP_REASON)
    original_max = backup_module.MAX_AUTO_BACKUPS
    backup_module.MAX_AUTO_BACKUPS = 2
    try:
        for _ in range(4):
            backup_module.create_backup(reason=backup_module.AUTO_BACKUP_REASON)
            time.sleep(1.05)
        backups = backup_module.list_backups()
        manual_count = sum(1 for b in backups if b["reason"] == "manual")
        auto_count = sum(1 for b in backups if b["reason"] == "automatico")
        assert manual_count == 1
        assert auto_count == 2
    finally:
        backup_module.MAX_AUTO_BACKUPS = original_max


# ---------------------------------------------------------------------------
# Agendador automático
# ---------------------------------------------------------------------------
def test_start_and_stop_auto_backup():
    assert backup_module.is_auto_backup_running() is False
    backup_module.start_auto_backup(interval_seconds=3600)
    time.sleep(0.3)
    assert backup_module.is_auto_backup_running() is True
    # deve ter feito logo uma cópia automática ao arrancar (catch-up), já
    # que ainda não existia nenhuma
    backups = backup_module.list_backups()
    assert any(b["reason"] == "automatico" for b in backups)

    backup_module.stop_auto_backup()
    assert backup_module.is_auto_backup_running() is False


def test_start_auto_backup_is_idempotent():
    backup_module.start_auto_backup(interval_seconds=3600)
    time.sleep(0.2)
    first_thread = backup_module._scheduler_thread
    backup_module.start_auto_backup(interval_seconds=3600)  # não deve arrancar uma segunda thread
    assert backup_module._scheduler_thread is first_thread


# ---------------------------------------------------------------------------
# Endpoints da API
# ---------------------------------------------------------------------------
def test_api_backup_status():
    res = client.get("/backup/status")
    assert res.status_code == 200
    body = res.json()
    assert body["sqlite_supported"] is True
    assert "auto_backup_running" in body
    assert "n_backups" in body


def test_api_create_and_list_backup():
    res = client.post("/backup")
    assert res.status_code == 200
    assert res.json()["reason"] == "manual"

    res = client.get("/backup")
    assert res.status_code == 200
    backups = res.json()["backups"]
    assert len(backups) == 1


def test_api_restore_and_delete_backup():
    create_res = client.post("/backup")
    backup_id = create_res.json()["id"]

    restore_res = client.post(f"/backup/{backup_id}/restore")
    assert restore_res.status_code == 200
    assert restore_res.json()["restored"] is True

    delete_res = client.delete(f"/backup/{backup_id}")
    assert delete_res.status_code == 200
    assert delete_res.json()["deleted"] is True


def test_api_restore_unknown_backup_returns_400():
    res = client.post("/backup/nao_existe.db/restore")
    assert res.status_code == 400


def test_api_delete_unknown_backup_returns_404():
    res = client.delete("/backup/nao_existe.db")
    assert res.status_code == 404
