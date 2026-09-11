"""
Modo "Última Semana Antes do Exame": um checklist curto e priorizado do que
ainda vale a pena mudar quando só resta pouco tempo.

Ao contrário do Otimizador (optimizer.py — procura a combinação de mudanças
para atingir uma nota-alvo, o que pode implicar várias semanas de mudança
gradual), aqui cada item é UM único passo realista para os próximos dias,
ordenado pelo ganho estimado que esse passo teria na previsão do modelo — a
pergunta não é "o que preciso para tirar 15?", é "de tudo o que ainda dá
para mudar esta semana, o que vale mais a pena fazer primeiro?".

Reaproveita as mesmas "alavancas" do Otimizador (estudo, sair, faltas,
álcool) porque são hábitos que podem mudar de um dia para o outro — ao
contrário de, por exemplo, reprovações anteriores (já aconteceram, não há
nada a fazer sobre isso agora) ou o desejo de seguir para o ensino superior
(não é uma ação com efeito imediato).
"""
from __future__ import annotations

# get_defaults: valores típicos para preencher hábitos não indicados.
# predict_grade: usa o modelo de ML para prever a nota a partir dos hábitos.
from src.predict import get_defaults, predict_grade
from src.i18n import t, plural_en, normalize_lang

# Mesmo texto explicativo por alavanca, para o checklist ser concreto em vez
# de só dizer "melhora X" — diz exatamente de que valor para que valor.
# Cada valor é uma função (lambda) que recebe o idioma, o valor atual e o
# novo valor, e devolve a frase de ação correspondente nesse idioma.
ACTION_TEMPLATES = {
    "studytime": lambda lang, frm, to: t(
        lang,
        f"Aumenta o tempo de estudo esta semana (nível {int(frm)} → {int(to)}).",
        f"Increase your study time this week (level {int(frm)} → {int(to)}).",
    ),
    "goout": lambda lang, frm, to: t(
        lang,
        f"Reduz um pouco as saídas com amigos esta semana (nível {int(frm)} → {int(to)}).",
        f"Cut back a little on going out with friends this week (level {int(frm)} → {int(to)}).",
    ),
    "absences": lambda lang, frm, to: t(
        lang,
        "Evita faltar às próximas aulas — cada falta a menos ajuda.",
        "Avoid missing the next classes — every absence less helps.",
    ),
    "Dalc": lambda lang, frm, to: t(
        lang,
        f"Reduz o consumo de álcool em dias úteis (nível {int(frm)} → {int(to)}).",
        f"Reduce weekday alcohol consumption (level {int(frm)} → {int(to)}).",
    ),
    "Walc": lambda lang, frm, to: t(
        lang,
        f"Reduz o consumo de álcool ao fim de semana (nível {int(frm)} → {int(to)}).",
        f"Reduce weekend alcohol consumption (level {int(frm)} → {int(to)}).",
    ),
}

# Nomes amigáveis de cada alavanca, mostrados no checklist, por idioma.
QUICK_WIN_LABELS = {
    "pt": {
        "studytime": "Tempo de estudo semanal",
        "goout": "Sair com amigos",
        "absences": "Faltas",
        "Dalc": "Álcool (dias úteis)",
        "Walc": "Álcool (fim de semana)",
    },
    "en": {
        "studytime": "Weekly study time",
        "goout": "Going out with friends",
        "absences": "Absences",
        "Dalc": "Alcohol (weekdays)",
        "Walc": "Alcohol (weekend)",
    },
}

# Mesmas alavancas e limites do optimizer.py (LEVERS) — não duplicam por
# coincidência, é deliberado: são as variáveis que a app já trata como
# realisticamente ajustáveis a curto prazo em qualquer sítio da app.
# "step": quanto cada passo muda o valor (positivo = aumentar, negativo = diminuir).
# "bound": o limite que não pode ser ultrapassado (ex.: faltas não pode passar de 0 para baixo).
QUICK_WIN_LEVERS = [
    {"column": "studytime", "step": 1, "bound": 4},
    {"column": "goout", "step": -1, "bound": 1},
    {"column": "absences", "step": -1, "bound": 0},
    {"column": "Dalc", "step": -1, "bound": 1},
    {"column": "Walc", "step": -1, "bound": 1},
]

# Número máximo de itens mostrados no checklist, por omissão.
DEFAULT_LIMIT = 5


def _within_bounds(value: float, lever: dict) -> bool:
    """Verifica se ainda é possível dar mais um passo nesta alavanca sem ultrapassar o limite."""
    if lever["step"] > 0:
        # Alavancas que aumentam (ex.: tempo de estudo): só é válido se o
        # valor atual ainda estiver abaixo do limite máximo.
        return value < lever["bound"]
    # Alavancas que diminuem (ex.: faltas, álcool): só é válido se o valor
    # atual ainda estiver acima do limite mínimo.
    return value > lever["bound"]


def gerar_checklist_ultima_semana(habits: dict, limit: int = DEFAULT_LIMIT, lang: str | None = None) -> dict:
    """
    Para cada alavanca ainda dentro dos limites (ex.: já não pode reduzir
    mais faltas se já estiver em 0), testa UM passo de melhoria e mede o
    ganho imediato na nota prevista do modelo (mantendo tudo o resto igual)
    — depois ordena do maior para o menor ganho, mostrando só o que
    realmente vale a pena priorizar primeiro.
    """
    lang = normalize_lang(lang)
    # Valores típicos do dataset, para preencher hábitos que não tenham sido indicados.
    defaults = get_defaults()
    # Nota prevista com os hábitos atuais, sem qualquer mudança — ponto de
    # partida para comparar o ganho de cada alavanca testada a seguir.
    baseline = predict_grade(habits, use_previous_grades=False)["predicted_grade"]

    # Lista de itens do checklist, construída passo a passo abaixo.
    items = []
    for lever in QUICK_WIN_LEVERS:
        col = lever["column"]
        # Valor atual do hábito, ou o valor típico do dataset se não tiver sido indicado.
        current = habits.get(col)
        if current is None:
            current = defaults.get(col)
        # Se mesmo assim não há valor disponível, esta alavanca não pode ser testada.
        if current is None:
            continue
        current = float(current)
        # Se já está no limite (ex.: faltas já em 0), não há mais nada a melhorar aqui.
        if not _within_bounds(current, lever):
            continue

        # Simula UM passo de melhoria nesta alavanca, mantendo tudo o resto igual.
        new_value = current + lever["step"]
        candidate = {**habits, col: new_value}
        # Recalcula a previsão do modelo com o valor alterado.
        new_grade = predict_grade(candidate, use_previous_grades=False)["predicted_grade"]
        # Ganho estimado: quanto a nota prevista sobe com este passo (arredondado a 2 casas).
        gain = round(new_grade - baseline, 2)
        # Só inclui no checklist se realmente houver um ganho positivo.
        if gain <= 0:
            continue

        items.append({
            "feature": col,
            "label": QUICK_WIN_LABELS[lang][col],
            "from": current,
            "to": new_value,
            "estimated_gain": gain,
            "action": ACTION_TEMPLATES[col](lang, current, new_value),
        })

    # Ordena do maior para o menor ganho estimado, e mantém só os "limit" primeiros.
    items.sort(key=lambda i: i["estimated_gain"], reverse=True)
    items = items[:limit]

    # Mensagem de resumo, diferente consoante haja ou não itens a mostrar.
    if items:
        message = t(
            lang,
            f"{len(items)} ação(ões) prioritária(s) para os próximos dias, ordenadas pelo impacto estimado.",
            f"{len(items)} priority {plural_en(len(items), 'action')} for the next few days, ordered by estimated impact.",
        )
    else:
        message = t(
            lang,
            "Não há mudanças rápidas com impacto relevante identificadas nesta previsão — os valores atuais já estão perto do limite considerado ajustável.",
            "No quick changes with meaningful impact were identified for this prediction — the current values are already close to the limit considered adjustable.",
        )

    return {
        "baseline_grade": baseline,
        "items": items,
        "message": message,
    }
