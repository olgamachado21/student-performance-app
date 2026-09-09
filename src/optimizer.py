"""
Otimizador de Estudo: calcula a mudança mínima de hábitos necessária para um
estudante atingir uma nota-alvo, usando um algoritmo guloso (hill-climbing)
sobre o modelo de regressão já treinado (variante "completo").

Em cada iteração, testa um passo em cada "alavanca" ajustável (tempo de
estudo, sair com amigos, faltas, álcool) e aplica sempre a que mais aumenta
a nota prevista, até atingir a meta ou esgotar as iterações.
"""
from __future__ import annotations

# pandas: para trabalhar com o dataset como tabela.
import pandas as pd

from src import config
from src.predict import predict_grade

# Número máximo de passos que o algoritmo guloso pode dar antes de desistir
# (evita loops infinitos caso a meta seja impossível de atingir).
MAX_ITERATIONS = 80

# Alavancas ajustáveis: coluna, direção do passo "de melhoria", e limite.
LEVERS = [
    {"column": "studytime", "step": 1, "bound": 4, "label": "Tempo de estudo"},
    {"column": "goout", "step": -1, "bound": 1, "label": "Sair com amigos"},
    {"column": "absences", "step": -1, "bound": 0, "label": "Faltas"},
    {"column": "Dalc", "step": -1, "bound": 1, "label": "Álcool (dias úteis)"},
    {"column": "Walc", "step": -1, "bound": 1, "label": "Álcool (fim de semana)"},
]

# Acesso rápido a uma alavanca pelo nome da coluna (em vez de percorrer a lista LEVERS sempre).
_LEVERS_BY_COLUMN = {lever["column"]: lever for lever in LEVERS}

# Limites reais (não só o "bound de melhoria" de LEVERS) de cada variável —
# usados para "clampar" o simulador em lote, que aceita deltas em qualquer
# direção (positivo ou negativo), ao contrário do hill-climbing acima, que só
# anda sempre na direção que melhora a nota.
COHORT_VALUE_LIMITS = {
    "studytime": (1, 4),
    "goout": (1, 5),
    "absences": (0, 93),
    "Dalc": (1, 5),
    "Walc": (1, 5),
}


def _within_bounds(value: float, lever: dict) -> bool:
    """Verifica se ainda é possível dar mais um passo nesta alavanca sem ultrapassar o limite."""
    if lever["step"] > 0:
        return value < lever["bound"]
    return value > lever["bound"]


def otimizar_plano_estudo(df: pd.DataFrame, student_id: int, target_grade: float) -> dict:
    """Calcula, passo a passo, a combinação mínima de mudanças de hábitos para um estudante atingir a nota-alvo."""
    # Localiza o estudante pelo id, e valida que existe.
    student_rows = df[df["student_id"] == student_id]
    if student_rows.empty:
        raise ValueError(f"Estudante {student_id} não encontrado.")
    student = student_rows.iloc[0]
    student_id = int(student_id)
    # Todos os dados do estudante, usados como base para cada previsão (só as alavancas mudam).
    base_input = student.to_dict()

    # Converter para tipos nativos do Python (não numpy) para serem serializáveis em JSON.
    working = {lever["column"]: int(student[lever["column"]]) for lever in LEVERS}

    def predict(habits: dict) -> float:
        # Junta os hábitos alterados aos restantes dados do estudante (que não mudam), e prevê.
        merged = {**base_input, **habits}
        return predict_grade(merged, use_previous_grades=True)["predicted_grade"]

    # Nota prevista com os hábitos atuais, sem qualquer mudança ainda.
    initial_grade = predict(working)
    grade = initial_grade
    # Lista de mudanças aplicadas, passo a passo (preenchida no ciclo abaixo).
    changes: list[dict] = []

    if grade >= target_grade:
        # Já cumpre a meta sem precisar de mudar nada.
        return {
            "student_id": student_id,
            "initial_grade": round(initial_grade, 2),
            "target_grade": target_grade,
            "final_grade": round(initial_grade, 2),
            "achieved": True,
            "changes": [],
            "message": (
                f"Este estudante já tem uma nota prevista ({initial_grade:.1f} valores) "
                f"igual ou superior à meta ({target_grade} valores) — não é necessária "
                f"nenhuma mudança de hábitos."
            ),
        }

    # Algoritmo guloso (hill-climbing): em cada iteração, testa um passo em
    # cada alavanca e aplica sempre a que mais melhora a nota prevista.
    for _ in range(MAX_ITERATIONS):
        if grade >= target_grade:
            break

        # Melhor alavanca encontrada nesta iteração (começa "vazia").
        best_lever, best_gain, best_new_value, best_new_grade = None, 0.0, None, grade
        for lever in LEVERS:
            col = lever["column"]
            # Salta esta alavanca se já estiver no limite (não há mais margem para melhorar).
            if not _within_bounds(working[col], lever):
                continue
            # Testa UM passo desta alavanca, mantendo as restantes iguais.
            candidate = dict(working)
            candidate[col] = working[col] + lever["step"]
            new_grade = predict(candidate)
            gain = new_grade - grade
            # Guarda esta alavanca se for a que dá o maior ganho até agora.
            if gain > best_gain:
                best_lever, best_gain = lever, gain
                best_new_value, best_new_grade = candidate[col], new_grade

        if best_lever is None:
            # Nenhuma alavanca melhora a nota — não há mais nada a fazer.
            break

        # Aplica o melhor passo encontrado e regista a mudança.
        changes.append({
            "label": best_lever["label"],
            "from": working[best_lever["column"]],
            "to": best_new_value,
        })
        working[best_lever["column"]] = best_new_value
        grade = best_new_grade

    achieved = grade >= target_grade
    # Junta passos consecutivos da mesma alavanca numa única entrada, mais legível.
    consolidated = _consolidate_changes(changes)
    has_prior_failures = int(student["failures"]) >= 1
    return {
        "student_id": student_id,
        "initial_grade": round(initial_grade, 2),
        "target_grade": target_grade,
        "final_grade": round(grade, 2),
        "achieved": achieved,
        "changes": consolidated,
        "message": _format_message(achieved, initial_grade, grade, target_grade, consolidated, has_prior_failures),
    }


def _consolidate_changes(changes: list[dict]) -> list[dict]:
    """Junta passos consecutivos da mesma alavanca (ex.: 3x 'Tempo de estudo')
    numa única entrada, mostrando o valor inicial e final combinados."""
    consolidated: list[dict] = []
    for change in changes:
        # Se a última entrada já é da mesma alavanca, só atualiza o valor final.
        if consolidated and consolidated[-1]["label"] == change["label"]:
            consolidated[-1]["to"] = change["to"]
        else:
            consolidated.append(dict(change))
    return consolidated


def _format_message(achieved, initial, final, target, changes, has_prior_failures=False) -> str:
    """Constrói a mensagem final explicando o resultado do plano de recuperação."""
    if not changes:
        return "Não foi possível identificar mudanças de hábitos que melhorassem a nota prevista."

    if achieved:
        base = (
            f"Com {len(changes)} mudança(s) de hábitos, a nota prevista passaria de "
            f"{initial:.1f} para {final:.1f} valores, atingindo a meta de {target} valores."
        )
    else:
        base = (
            f"Mesmo aplicando todas as mudanças de hábitos possíveis dentro dos limites "
            f"considerados, a nota prevista chegaria a {final:.1f} valores (partindo de "
            f"{initial:.1f}), sem atingir a meta de {target} valores. Pode ser necessário "
            f"apoio adicional (explicações, acompanhamento pedagógico) além da mudança de hábitos."
        )

    # Acrescenta uma nota de calibração, se aplicável (ver função abaixo).
    return base + _studytime_calibration_note(changes, has_prior_failures)


def _studytime_calibration_note(changes, has_prior_failures) -> str:
    """
    Nota de calibração: o modelo de regressão usado aqui (variante
    "completo") é linear e não tem termo de interação entre tempo de
    estudo e reprovações anteriores — por isso estima sempre o mesmo ganho
    por nível de tempo de estudo, independentemente de o estudante já ter
    reprovado ou não. Nos dados reais isso não é verdade: o efeito do
    tempo de estudo é bem mais fraco (e deixa de ser estatisticamente
    significativo, n=100) em quem já reprovou pelo menos uma vez, contra um
    efeito forte e significativo em quem nunca reprovou (ver
    studytime_regression_no_failures/with_failures em /statistical-tests).

    Sem este aviso, o plano de recuperação prometeria o mesmo ganho a
    todos por igual, o que não é honesto para quem já reprovou.
    """
    # Só mostra a nota se o plano incluir mudar o tempo de estudo E o
    # estudante já tiver reprovações anteriores (caso em que o aviso se aplica).
    studytime_in_plan = any(c["label"] == "Tempo de estudo" for c in changes)
    if not (has_prior_failures and studytime_in_plan):
        return ""
    return (
        " Nota: como este estudante já tem reprovações anteriores, o ganho estimado ao "
        "aumentar o tempo de estudo tende a ser otimista — nos dados analisados, esse "
        "efeito é bem mais fraco (e deixa de ser estatisticamente significativo) em quem já "
        "reprovou, o que pode refletir lacunas que só mais tempo de estudo não resolve. "
        "Vale a pena considerar também apoio adicional (explicações, acompanhamento "
        "pedagógico)."
    )


def simular_intervencao_turma(df: pd.DataFrame, deltas: dict) -> dict:
    """
    Simulador em lote, ao nível da turma: em vez de otimizar um estudante de
    cada vez (ver otimizar_plano_estudo acima), aplica a MESMA alteração
    hipotética de hábitos a TODOS os estudantes em risco (at_risk == 1) de
    uma só vez — ex.: "e se todos os estudantes em risco estudassem mais 1
    nível por semana e faltassem menos 2 vezes?" — e mede o impacto agregado
    na taxa de aprovação desse grupo.

    `deltas` é um dicionário {coluna: delta}, com colunas entre as de LEVERS
    (studytime, goout, absences, Dalc, Walc). Ao contrário de LEVERS, aceita
    deltas em qualquer direção (não só a "de melhoria"), mas o valor final de
    cada estudante é sempre "clampado" aos limites reais dessa variável no
    dataset (ver COHORT_VALUE_LIMITS), para nunca gerar hábitos impossíveis
    (ex.: tempo de estudo nível 6, que não existe na escala 1-4).
    """
    if not deltas:
        raise ValueError("Indica pelo menos uma alteração de hábito para simular.")

    # Valida que só foram indicadas colunas conhecidas (uma das alavancas definidas acima).
    invalid = [col for col in deltas if col not in _LEVERS_BY_COLUMN]
    if invalid:
        valid = ", ".join(_LEVERS_BY_COLUMN)
        raise ValueError(f"Variáveis inválidas: {', '.join(invalid)}. Escolhe entre: {valid}")

    # A simulação só se aplica ao grupo de estudantes em risco.
    at_risk_df = df[df["at_risk"] == 1]
    if at_risk_df.empty:
        return {
            "n_students": 0,
            "deltas_applied": deltas,
            "n_passing_before": 0,
            "n_passing_after": 0,
            "newly_passing": 0,
            "pass_rate_before": 0.0,
            "pass_rate_after": 0.0,
            "avg_grade_before": 0.0,
            "avg_grade_after": 0.0,
            "message": "Não há estudantes em risco no conjunto de dados atual — nada para simular.",
        }

    # Contadores e listas de notas, antes e depois da alteração hipotética.
    passing_before = 0
    passing_after = 0
    grades_before = []
    grades_after = []

    for _, student in at_risk_df.iterrows():
        base_input = student.to_dict()
        # Previsão com os hábitos reais atuais (sem alteração).
        before_grade = predict_grade(base_input, use_previous_grades=True)["predicted_grade"]

        # Aplica os deltas indicados, sempre dentro dos limites reais da variável.
        habits = {}
        for col, delta in deltas.items():
            lo, hi = COHORT_VALUE_LIMITS[col]
            habits[col] = max(lo, min(hi, float(student[col]) + delta))

        # Previsão com os hábitos alterados (hipotéticos).
        after_input = {**base_input, **habits}
        after_grade = predict_grade(after_input, use_previous_grades=True)["predicted_grade"]

        grades_before.append(before_grade)
        grades_after.append(after_grade)
        if before_grade >= config.PASS_THRESHOLD:
            passing_before += 1
        if after_grade >= config.PASS_THRESHOLD:
            passing_after += 1

    n = len(at_risk_df)
    avg_before = sum(grades_before) / n
    avg_after = sum(grades_after) / n
    newly_passing = passing_after - passing_before

    return {
        "n_students": n,
        "deltas_applied": deltas,
        "n_passing_before": passing_before,
        "n_passing_after": passing_after,
        "newly_passing": newly_passing,
        "pass_rate_before": round(passing_before / n, 4),
        "pass_rate_after": round(passing_after / n, 4),
        "avg_grade_before": round(avg_before, 2),
        "avg_grade_after": round(avg_after, 2),
        "message": _format_cohort_message(n, passing_before, passing_after, avg_before, avg_after),
    }


def _format_cohort_message(n: int, before: int, after: int, avg_before: float, avg_after: float) -> str:
    """Constrói a mensagem final resumindo o efeito da simulação em lote."""
    diff = after - before
    if diff <= 0:
        # A nota média pode subir, mas se ninguém passar de reprovado a aprovado, é dito claramente.
        return (
            f"Com esta alteração aplicada aos {n} estudantes em risco, a nota média passaria de "
            f"{avg_before:.1f} para {avg_after:.1f} valores, mas o número de estudantes a atingir a "
            f"aprovação não aumentaria ({after} em {n})."
        )
    # Concordância singular/plural na frase final, consoante o número de novos aprovados.
    plural = "s" if diff != 1 else ""
    return (
        f"Com esta alteração aplicada a todo o grupo em risco ({n} estudantes), a nota média passaria "
        f"de {avg_before:.1f} para {avg_after:.1f} valores, e o número de estudantes que atingiria a "
        f"aprovação (nota final ≥ {config.PASS_THRESHOLD}) subiria de {before} para {after} — "
        f"mais {diff} estudante{plural} aprovado{plural}."
    )
