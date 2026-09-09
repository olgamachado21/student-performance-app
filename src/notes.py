"""
Comentários/notas ligados a um estudante: um espaço curto para o utilizador
registar as suas próprias observações — ex.: "falei com ele, vai melhorar a
assiduidade" — associadas a um estudante específico e, opcionalmente, ao
alerta que motivou o comentário (ex.: "Risco combinado: faltas altas e
reprovação anterior").

Ao contrário de um bloco de notas livre e independente (que existiu numa
fase anterior do projeto como "Central de Notas" e foi removido por estar
fora do âmbito de gestão de dados de estudantes), este módulo mantém sempre
o comentário agarrado a um estudante real do dataset — continua a servir o
propósito da app (acompanhar estudantes), só que acrescenta uma camada
humana à informação estruturada.
"""
from __future__ import annotations

# datetime: para registar quando cada comentário foi criado.
from datetime import datetime

# pandas: para trabalhar com os comentários guardados como tabela.
import pandas as pd

from src import database

# Nome da tabela na base de dados onde ficam guardados os comentários.
NOTES_TABLE = "Student_Notes"
# Colunas dessa tabela.
NOTES_COLUMNS = ["id", "student_id", "text", "context", "created_at"]


def _load() -> pd.DataFrame:
    """Lê a tabela de comentários (vazia se ainda não existir nenhum)."""
    if not database.table_exists(NOTES_TABLE):
        return pd.DataFrame(columns=NOTES_COLUMNS)
    return database.read_table(NOTES_TABLE)


def _next_id(df: pd.DataFrame) -> int:
    """Calcula o próximo id disponível: o maior id existente + 1, ou 1 se ainda não houver nenhum."""
    return int(df["id"].max()) + 1 if not df.empty else 1


def _row_to_dict(row: pd.Series) -> dict:
    """Converte uma linha da tabela (formato da base de dados) num dicionário pronto a devolver na API."""
    d = row.to_dict()
    d["id"] = int(d["id"])
    d["student_id"] = int(d["student_id"])
    d["text"] = d.get("text") or ""
    # O contexto é opcional (ex.: título do alerta que motivou o comentário).
    d["context"] = d.get("context") or None
    return d


def add_note(student_id: int, text: str, context: str | None = None) -> dict:
    """
    Regista um novo comentário associado a um estudante. O texto não pode
    ficar vazio (só espaços em branco também conta como vazio); o contexto
    é opcional — usado quando o comentário nasce a partir de um alerta
    específico em vez de ser escrito livremente no Perfil do Estudante.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("O comentário não pode ficar vazio.")

    df = _load()
    new_row = {
        "id": _next_id(df),
        "student_id": int(student_id),
        "text": text,
        "context": (context or "").strip(),
        "created_at": datetime.now().isoformat(),
    }
    combined = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    database.write_table(combined, NOTES_TABLE, if_exists="replace")
    return _row_to_dict(pd.Series(new_row))


def get_notes(student_id: int | None = None) -> list[dict]:
    """
    Lista os comentários guardados, da mais recente para o mais antigo.
    Se student_id for indicado, devolve só os comentários desse estudante
    (uso normal, no Perfil do Estudante e nos Avisos e Alertas); sem
    student_id, devolve todos (uso administrativo/depuração).
    """
    df = _load()
    if df.empty:
        return []
    if student_id is not None:
        df = df[df["student_id"] == int(student_id)]
        if df.empty:
            return []
    items = [_row_to_dict(row) for _, row in df.iterrows()]
    return sorted(items, key=lambda i: i["created_at"], reverse=True)


def delete_note(note_id: int) -> bool:
    """Remove um comentário. Devolve True se encontrou e removeu, False se não existia."""
    df = _load()
    if df.empty or note_id not in set(df["id"]):
        return False
    database.write_table(df[df["id"] != note_id], NOTES_TABLE, if_exists="replace")
    return True
