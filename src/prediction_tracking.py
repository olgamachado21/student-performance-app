"""
Comparação Antes/Depois: guarda uma "fotografia" da previsão do modelo no
momento em que o estudante decide mudar algum hábito (ex.: aumentar o tempo
de estudo), e permite mais tarde registar a nota REAL obtida — fechando o
ciclo entre "o modelo previu isto" e "foi isto que realmente aconteceu",
em vez de a previsão do Simulador ficar só como um número que se esquece.

Serve também para validar o próprio modelo com dados reais do utilizador,
não só com as métricas medidas no dataset histórico.
"""
from __future__ import annotations

# json: para guardar o dicionário de hábitos como texto dentro da base de dados.
import json
# datetime: para registar quando cada previsão/nota real foi guardada.
from datetime import datetime

# pandas: para trabalhar com o histórico de previsões como tabela.
import pandas as pd

from src import database
from src.i18n import t, plural_en, normalize_lang

# Nome da tabela na base de dados onde ficam guardadas as previsões "fotografadas".
SNAPSHOT_TABLE = "Prediction_Snapshots"
# Colunas dessa tabela.
SNAPSHOT_COLUMNS = [
    "id", "label", "habits", "predicted_grade", "model_variant",
    "actual_grade", "actual_recorded_at", "created_at",
]

# Diferença mínima (em valores) para se considerar "melhor" ou "pior" do
# que a previsão, em vez de "como previsto" — evita que uma diferença de
# 0.1 valores (ruído normal) seja apresentada como uma surpresa.
STATUS_TOLERANCE = 0.5


def _load() -> pd.DataFrame:
    """Lê a tabela de previsões guardadas (vazia se ainda não existir nenhuma)."""
    if not database.table_exists(SNAPSHOT_TABLE):
        return pd.DataFrame(columns=SNAPSHOT_COLUMNS)
    return database.read_table(SNAPSHOT_TABLE)


def _next_id(df: pd.DataFrame) -> int:
    """Calcula o próximo id disponível: o maior id existente + 1, ou 1 se ainda não houver nenhum."""
    return int(df["id"].max()) + 1 if not df.empty else 1


def _row_to_dict(row: pd.Series) -> dict:
    """Converte uma linha da tabela (formato da base de dados) num dicionário pronto a devolver na API."""
    d = row.to_dict()
    d["id"] = int(d["id"])
    # Os hábitos foram guardados como texto JSON — converte de volta para dicionário.
    habits = d.get("habits")
    d["habits"] = json.loads(habits) if isinstance(habits, str) and habits else {}
    d["predicted_grade"] = float(d["predicted_grade"])
    # A nota real pode ainda não ter sido registada (string vazia na BD) — nesse caso fica None.
    d["actual_grade"] = float(d["actual_grade"]) if d.get("actual_grade") not in (None, "") else None
    d["actual_recorded_at"] = d.get("actual_recorded_at") or None
    d["label"] = d.get("label") or ""

    if d["actual_grade"] is not None:
        # Já há nota real: calcula a diferença face à previsão e classifica o resultado.
        diff = round(d["actual_grade"] - d["predicted_grade"], 2)
        d["diff"] = diff
        if diff > STATUS_TOLERANCE:
            d["status"] = "melhor_que_previsto"
        elif diff < -STATUS_TOLERANCE:
            d["status"] = "pior_que_previsto"
        else:
            d["status"] = "como_previsto"
    else:
        # Ainda não há nota real registada — fica pendente.
        d["diff"] = None
        d["status"] = "pendente"
    return d


def save_snapshot(prediction_result: dict, habits: dict, label: str = "", lang: str | None = None) -> dict:
    """
    Guarda uma previsão como ponto de partida para comparação futura.
    Usa a previsão "completa" (com G1/G2) quando disponível, senão a de
    hábitos — a mesma prioridade de leitura já usada no ecrã do Simulador.
    """
    lang = normalize_lang(lang)
    # Escolhe qual variante da previsão usar, com a mesma prioridade do Simulador.
    if "nota_prevista_completa" in prediction_result:
        predicted = prediction_result["nota_prevista_completa"]
    elif "nota_prevista_habitos" in prediction_result:
        predicted = prediction_result["nota_prevista_habitos"]
    else:
        raise ValueError(t(
            lang,
            "Resultado de previsão inválido: falta 'nota_prevista_habitos' ou 'nota_prevista_completa'.",
            "Invalid prediction result: missing 'nota_prevista_habitos' or 'nota_prevista_completa'.",
        ))

    df = _load()
    # Novo registo, ainda sem nota real (fica preenchida mais tarde, quando disponível).
    new_row = {
        "id": _next_id(df),
        "label": (label or "").strip(),
        # Converte o dicionário de hábitos para texto, para poder ser guardado numa célula da tabela.
        "habits": json.dumps(habits, ensure_ascii=False, default=str),
        "predicted_grade": predicted["predicted_grade"],
        "model_variant": predicted["model_variant"],
        "actual_grade": "",
        "actual_recorded_at": "",
        "created_at": datetime.now().isoformat(),
    }
    # Junta o novo registo aos já existentes e grava tudo de novo na base de dados.
    combined = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    database.write_table(combined, SNAPSHOT_TABLE, if_exists="replace")
    return _row_to_dict(pd.Series(new_row))


def get_snapshots() -> list[dict]:
    """Histórico de previsões guardadas, da mais recente para a mais antiga."""
    df = _load()
    if df.empty:
        return []
    items = [_row_to_dict(row) for _, row in df.iterrows()]
    # Ordena pela data de criação, mais recente primeiro.
    return sorted(items, key=lambda i: i["created_at"], reverse=True)


def record_actual_grade(snapshot_id: int, actual_grade: float, lang: str | None = None) -> dict:
    """Regista a nota real obtida, associando-a a uma previsão guardada anteriormente."""
    lang = normalize_lang(lang)
    # Valida que a nota está dentro da escala válida (0-20).
    if not (0 <= actual_grade <= 20):
        raise ValueError(t(lang, "A nota real tem de estar entre 0 e 20.", "The actual grade must be between 0 and 20."))
    df = _load()
    # Verifica que a previsão indicada realmente existe antes de tentar atualizá-la.
    if df.empty or snapshot_id not in set(df["id"]):
        raise ValueError(t(
            lang,
            f"Previsão {snapshot_id} não encontrada.",
            f"Prediction {snapshot_id} not found.",
        ))
    # Encontra a linha correspondente a este id e atualiza-a.
    idx = df.index[df["id"] == snapshot_id][0]
    df.at[idx, "actual_grade"] = actual_grade
    df.at[idx, "actual_recorded_at"] = datetime.now().isoformat()
    database.write_table(df, SNAPSHOT_TABLE, if_exists="replace")
    return _row_to_dict(df.loc[idx])


def get_validation_summary(lang: str | None = None) -> dict:
    """
    Valida o modelo com dados REAIS do próprio utilizador, não só com o
    dataset histórico de treino: agrega todas as previsões guardadas que já
    têm nota real registada (ver record_actual_grade) e calcula o erro
    médio real "em produção" — desfechos que aconteceram de verdade, para
    além do MAE medido uma vez no conjunto de teste separado no treino
    (ver get_model_mae em predict.py). Sem isto, a única prova de qualidade
    do modelo eram métricas calculadas sobre dados históricos; isto fecha o
    ciclo com previsões e resultados reais deste utilizador.
    """
    lang = normalize_lang(lang)
    # Só interessam as previsões que já têm nota real registada.
    validated = [s for s in get_snapshots() if s["actual_grade"] is not None]
    if not validated:
        return {
            "n_validated": 0,
            "has_data": False,
            "message": t(
                lang,
                "Ainda não há previsões guardadas com nota real registada — guarda uma "
                "previsão no Simulador e regista a nota real mais tarde para começares a "
                "validar o modelo com dados próprios.",
                "There are no saved predictions with a recorded actual grade yet — save a "
                "prediction in the Simulator and record the actual grade later to start "
                "validating the model with your own data.",
            ),
        }

    # Erro absoluto de cada previsão validada (diferença entre real e previsto, sem sinal).
    errors = [abs(s["actual_grade"] - s["predicted_grade"]) for s in validated]
    # MAE (Mean Absolute Error): média dos erros absolutos.
    mae = round(sum(errors) / len(errors), 2)
    # RMSE (Root Mean Squared Error): penaliza mais os erros grandes do que o MAE.
    rmse = round((sum(e ** 2 for e in errors) / len(errors)) ** 0.5, 2)

    # Conta quantas previsões ficaram em cada categoria (melhor/pior/como previsto).
    status_counts = {"melhor_que_previsto": 0, "pior_que_previsto": 0, "como_previsto": 0}
    for s in validated:
        status_counts[s["status"]] = status_counts.get(s["status"], 0) + 1

    return {
        "n_validated": len(validated),
        "has_data": True,
        "real_world_mae": mae,
        "real_world_rmse": rmse,
        "status_counts": status_counts,
        "message": t(
            lang,
            f"{len(validated)} previsão(ões) validada(s) com nota real — erro médio real "
            f"de {mae} valores nesta amostra.",
            f"{len(validated)} {plural_en(len(validated), 'prediction')} validated with an actual "
            f"grade — real-world average error of {mae} points in this sample.",
        ),
    }


def get_accuracy_over_time() -> dict:
    """
    Acompanha a precisão do modelo ao longo do tempo: para cada previsão já
    validada (com nota real registada — ver record_actual_grade), ordenadas
    pela data em que a nota real foi registada, calcula o erro absoluto
    médio (MAE) acumulado até esse ponto. Em vez de um único número
    "de sempre" (ver get_validation_summary), isto mostra se a precisão do
    modelo se mantém estável, melhora ou piora à medida que mais resultados
    reais vão sendo registados.
    """
    validated = [s for s in get_snapshots() if s["actual_grade"] is not None]
    # Ordena da mais antiga para a mais recente, pela data em que a nota real foi registada.
    validated.sort(key=lambda s: s["actual_recorded_at"] or "")

    # Um ponto por cada previsão validada, com o MAE acumulado até esse ponto.
    points = []
    cumulative_errors: list[float] = []
    for s in validated:
        error = round(abs(s["actual_grade"] - s["predicted_grade"]), 2)
        cumulative_errors.append(error)
        # MAE calculado sobre todos os erros vistos até agora (inclusive este).
        cumulative_mae = round(sum(cumulative_errors) / len(cumulative_errors), 2)
        points.append({
            "recorded_at": s["actual_recorded_at"],
            "label": s["label"],
            "predicted_grade": s["predicted_grade"],
            "actual_grade": s["actual_grade"],
            "error": error,
            "cumulative_mae": cumulative_mae,
            "n_so_far": len(cumulative_errors),
        })

    return {
        "n_validated": len(points),
        # Só faz sentido mostrar uma "evolução" com pelo menos 2 pontos.
        "has_data": len(points) >= 2,
        "points": points,
    }


def delete_snapshot(snapshot_id: int) -> bool:
    """Remove uma previsão guardada. Devolve True se encontrou e removeu, False se não existia."""
    df = _load()
    if df.empty or snapshot_id not in set(df["id"]):
        return False
    # Grava de novo a tabela, excluindo a linha com este id.
    database.write_table(df[df["id"] != snapshot_id], SNAPSHOT_TABLE, if_exists="replace")
    return True
