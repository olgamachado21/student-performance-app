"""
Cópias de segurança da base de dados: permite criar uma cópia do ficheiro da
BD SQLite a qualquer momento (botão manual em Configurações) e também
periodicamente sem qualquer ação do utilizador (agendador em segundo plano,
ver start_auto_backup — arrancado uma vez no arranque da API em src/api.py).

Cada cópia fica guardada num ficheiro próprio dentro de BACKUP_DIR (ver
src/config.py), com data/hora e motivo no nome, para nunca se sobreporem.
As cópias AUTOMÁTICAS mais antigas são apagadas sozinhas passado um certo
número (ver MAX_AUTO_BACKUPS), para a pasta não crescer sem limite; as
cópias MANUAIS nunca são apagadas sozinhas — foram pedidas de propósito,
por isso ficam guardadas até o utilizador as apagar explicitamente.

Só funciona com SQLite (o motor por omissão da app) — com SQL Server
(DB_DRIVER="mssql") a base de dados já vive num servidor com as suas
próprias ferramentas de backup (SQL Server Management Studio, agentes de
manutenção, etc.), por isso aqui devolve-se sempre um erro claro em vez de
tentar copiar um ficheiro que nem existe localmente.
"""
from __future__ import annotations

# sqlite3: usa-se a própria API de backup do SQLite (Connection.backup()),
# que faz uma cópia segura mesmo com a aplicação a correr e a escrever ao
# mesmo tempo — ao contrário de copiar o ficheiro diretamente (shutil.copy),
# que podia apanhar uma escrita a meio e gravar uma cópia corrompida.
import sqlite3
# threading: o agendador automático corre numa thread em segundo plano,
# separada dos pedidos normais da API, para nunca bloquear a aplicação.
import threading
# datetime: para carimbar cada cópia com a data/hora de criação e calcular
# há quanto tempo foi a última cópia automática.
from datetime import datetime
from pathlib import Path

from src import config, database

# Cerca de duas semanas de cópias diárias — mais do que isso deixa de ser
# muito útil (dados demasiado antigos) e só ocupa espaço em disco à toa.
MAX_AUTO_BACKUPS = 14

# Intervalo por omissão entre cópias automáticas: 1 dia.
AUTO_BACKUP_INTERVAL_SECONDS = 24 * 60 * 60

AUTO_BACKUP_REASON = "automatico"
MANUAL_BACKUP_REASON = "manual"
PRE_RESTORE_REASON = "pre_restauro"

_FILENAME_TIME_FORMAT = "%Y%m%d_%H%M%S"
_FILENAME_PREFIX = "studentperfomance_"


def _require_sqlite():
    """As cópias de segurança só fazem sentido com um ficheiro local
    (SQLite) — sem isto, tentar copiar um ficheiro que não existe dava um
    erro confuso lá mais à frente em vez de uma explicação clara já aqui."""
    if config.DB_DRIVER != "sqlite":
        raise ValueError(
            "As cópias de segurança só estão disponíveis com a base de dados SQLite "
            "(a configuração atual usa SQL Server). Usa as ferramentas de backup do "
            "próprio SQL Server (SSMS ou um agente de manutenção) para este caso."
        )


def _backup_filename(reason: str) -> str:
    stamp = datetime.now().strftime(_FILENAME_TIME_FORMAT)
    # Filtra o motivo para só letras/números/traços — nunca é texto do
    # utilizador (só vem de constantes fixas neste módulo), mas mantém o
    # nome do ficheiro sempre previsível e seguro de qualquer forma.
    safe_reason = "".join(c for c in reason if c.isalnum() or c in ("-", "_")) or "backup"
    return f"{_FILENAME_PREFIX}{stamp}_{safe_reason}.db"


def _remove_file_robust(path: Path):
    """Tenta apagar um ficheiro; se o sistema de ficheiros recusar (raro,
    mas visto nalguns ambientes com pastas sincronizadas/de rede), tenta
    pelo menos tirá-lo do caminho renomeando-o — o mesmo padrão de
    tolerância a falhas usado em src/custom_dataset._clear_custom_models."""
    try:
        path.unlink()
    except OSError:
        try:
            path.replace(path.with_name(f"_stale_{path.name}"))
        except OSError:
            pass


def create_backup(reason: str = MANUAL_BACKUP_REASON) -> dict:
    """Cria uma cópia de segurança do ficheiro da base de dados atual."""
    _require_sqlite()
    if not config.SQLITE_PATH.exists():
        raise ValueError("Ainda não existe nenhuma base de dados para copiar.")

    config.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    dest_path = config.BACKUP_DIR / _backup_filename(reason)

    src_conn = sqlite3.connect(str(config.SQLITE_PATH))
    try:
        dest_conn = sqlite3.connect(str(dest_path))
        try:
            src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        src_conn.close()

    if reason in (AUTO_BACKUP_REASON, PRE_RESTORE_REASON):
        _enforce_retention()

    return _describe_backup(dest_path)


def list_backups() -> list[dict]:
    """Lista as cópias de segurança existentes, mais recente primeiro."""
    if not config.BACKUP_DIR.exists():
        return []
    files = sorted(
        config.BACKUP_DIR.glob(f"{_FILENAME_PREFIX}*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return [_describe_backup(p) for p in files]


def _describe_backup(path: Path) -> dict:
    stat = path.stat()
    return {
        "id": path.name,
        "filename": path.name,
        "size_bytes": stat.st_size,
        "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "reason": _reason_from_filename(path.name),
    }


def _reason_from_filename(filename: str) -> str:
    # "studentperfomance_20260821_103000_manual.db" -> "manual"
    # "studentperfomance_20260821_103000_pre_restauro.db" -> "pre_restauro"
    # (o motivo em si pode ter "_" lá dentro, ex.: PRE_RESTORE_REASON =
    # "pre_restauro" — por isso junta-se TUDO depois do prefixo fixo
    # "studentperfomance_<data>_<hora>_", em vez de assumir que é só o último pedaço.
    stem = Path(filename).stem
    parts = stem.split("_")
    return "_".join(parts[3:]) if len(parts) >= 4 else "desconhecido"


def _resolve_backup_path(backup_id: str) -> Path:
    # backup_id é sempre o próprio nome do ficheiro (ver _describe_backup) —
    # usar só o ".name" impede escapar da pasta de backups (ex.: um id como
    # "../../ficheiro_qualquer") mesmo que o valor venha de fora (API).
    candidate = config.BACKUP_DIR / Path(backup_id).name
    if not candidate.name.startswith(_FILENAME_PREFIX) or not candidate.exists():
        raise ValueError(f"Cópia de segurança não encontrada: '{backup_id}'.")
    return candidate


def restore_backup(backup_id: str) -> dict:
    """
    Substitui a base de dados atual pelo conteúdo desta cópia de segurança.

    Faz sempre, antes de restaurar, um backup automático do estado atual
    (motivo "pre_restauro") — para nunca perder dados sem hipótese de voltar
    atrás, mesmo que o próprio restauro tenha sido um engano.
    """
    _require_sqlite()
    backup_path = _resolve_backup_path(backup_id)

    if config.SQLITE_PATH.exists():
        try:
            create_backup(reason=PRE_RESTORE_REASON)
        except ValueError:
            pass  # nunca bloquear o restauro só porque este backup de segurança falhou

    # Fecha as ligações ativas antes de substituir o ficheiro, para o
    # SQLAlchemy não continuar a apontar para um ficheiro/estado já
    # substituído por baixo (mais relevante no Windows, onde um ficheiro
    # aberto por um processo pode nem deixar ser substituído por outro).
    database.get_engine().dispose()

    config.SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
    src_conn = sqlite3.connect(str(backup_path))
    try:
        dest_conn = sqlite3.connect(str(config.SQLITE_PATH))
        try:
            src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        src_conn.close()

    # Garante que os próximos pedidos abrem ligações novas ao ficheiro
    # acabado de restaurar, em vez de reaproveitarem alguma ligação em cache
    # apontada para o estado anterior.
    database.get_engine().dispose()

    return {"restored": True, "from": backup_path.name}


def delete_backup(backup_id: str) -> dict:
    """Apaga uma cópia de segurança específica (o utilizador pediu explicitamente)."""
    path = _resolve_backup_path(backup_id)
    _remove_file_robust(path)
    return {"deleted": True, "filename": path.name}


def _enforce_retention():
    """Mantém só as MAX_AUTO_BACKUPS cópias AUTOMÁTICAS (ou de pré-restauro)
    mais recentes, apagando as mais antigas - nunca toca em cópias manuais."""
    auto_backups = [b for b in list_backups() if b["reason"] in (AUTO_BACKUP_REASON, PRE_RESTORE_REASON)]
    for old in auto_backups[MAX_AUTO_BACKUPS:]:
        _remove_file_robust(config.BACKUP_DIR / old["filename"])


# --- Agendador automático -------------------------------------------------
# Thread única, em segundo plano, que corre enquanto a aplicação estiver
# aberta e faz uma cópia de segurança sozinha de vez em quando — arrancada
# uma única vez no arranque da API (ver evento "startup" em src/api.py).
_scheduler_thread: threading.Thread | None = None
_scheduler_stop_event = threading.Event()


def _seconds_since_last_auto_backup() -> float | None:
    """Devolve há quanto tempo foi a última cópia automática (ou de
    pré-restauro, que também conta como "recente o suficiente"), ou None se
    nunca tiver havido nenhuma."""
    autos = [b for b in list_backups() if b["reason"] in (AUTO_BACKUP_REASON, PRE_RESTORE_REASON)]
    if not autos:
        return None
    latest = datetime.fromisoformat(autos[0]["created_at"])
    return (datetime.now() - latest).total_seconds()


def _run_scheduler_loop(interval_seconds: float):
    # Se a última cópia automática já tem mais tempo do que o intervalo (ou
    # nunca houve nenhuma), faz uma logo ao arrancar — assim o utilizador não
    # depende de deixar a app aberta ininterruptamente durante um dia
    # inteiro só para a primeira cópia automática acontecer (ex.: se abre a
    # app todos os dias por umas horas e depois fecha).
    try:
        elapsed = _seconds_since_last_auto_backup()
        if elapsed is None or elapsed >= interval_seconds:
            create_backup(reason=AUTO_BACKUP_REASON)
    except Exception:
        # Um backup automático falhado (ex.: disco cheio, BD ainda não
        # existe na primeira execução) nunca deve impedir a aplicação de
        # arrancar nem derrubar esta thread — tenta-se de novo no próximo intervalo.
        pass

    while not _scheduler_stop_event.wait(interval_seconds):
        try:
            create_backup(reason=AUTO_BACKUP_REASON)
        except Exception:
            pass


def start_auto_backup(interval_seconds: float = AUTO_BACKUP_INTERVAL_SECONDS):
    """Arranca o agendador de backups automáticos (thread daemon, uma única
    vez) — chamado no arranque da API. Não faz nada se já estiver a correr,
    para permitir chamar em segurança mais do que uma vez."""
    global _scheduler_thread
    if _scheduler_thread is not None and _scheduler_thread.is_alive():
        return
    _scheduler_stop_event.clear()
    _scheduler_thread = threading.Thread(
        target=_run_scheduler_loop, args=(interval_seconds,), daemon=True
    )
    _scheduler_thread.start()


def stop_auto_backup():
    """Para o agendador automático — usado nos testes, para nunca deixar
    threads em segundo plano penduradas depois de um teste terminar."""
    global _scheduler_thread
    _scheduler_stop_event.set()
    if _scheduler_thread is not None:
        _scheduler_thread.join(timeout=2)
    _scheduler_thread = None


def is_auto_backup_running() -> bool:
    """Indica se o agendador automático está atualmente a correr — usado em
    /backup/status para a interface mostrar se o backup automático está ativo."""
    return _scheduler_thread is not None and _scheduler_thread.is_alive()
