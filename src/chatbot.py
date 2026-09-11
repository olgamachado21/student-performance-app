"""
Assistente da StudentPerfomance — chatbot baseado em regras, não num LLM externo:
reconhece o tipo de pergunta por palavras-chave e responde chamando as
mesmas funções já usadas pela API REST (estatísticas, alertas, explicação
da previsão, otimizador de estudo, correlações). Mantém a app 100% local,
sem chave de API nem ligação à internet — só entende o conjunto de
perguntas listado em EXAMPLE_QUESTIONS, mas responde sempre com dados
reais e atuais do dataset, nunca inventados.

i18n: `lang` controla só o IDIOMA DA RESPOSTA (texto devolvido em "answer"),
nunca o reconhecimento da pergunta. A deteção de intenção (que função
chamar) compara a pergunta com palavras-chave em PT E em EN ao mesmo tempo,
independentemente de `lang` — uma pessoa com a app em inglês pode perfeitamente
escrever a pergunta em português (ou vice-versa), por isso cada lista de
palavras-chave abaixo tem as duas variantes lado a lado, em vez de escolher
consoante `lang`. As listas PT originais nunca foram alteradas (só
acrescentadas), para não haver qualquer regressão nos testes/perguntas já
reconhecidas.
"""
from __future__ import annotations

# re: expressões regulares, usadas para procurar números/palavras-chave na pergunta.
import re
# Optional: indica que uma função pode devolver None em vez de um valor.
from typing import Optional

# pandas: para trabalhar com o dataset como tabela.
import pandas as pd

# Reaproveita as mesmas funções já usadas pela API REST — o chatbot nunca
# calcula nada por conta própria, só interpreta a pergunta e chama a função certa.
from src.optimizer import otimizar_plano_estudo
from src.predict import EXPLAIN_FEATURES, explain_prediction
from src.statistics_analysis import generate_overview_summary
from src.i18n import t, plural_en, normalize_lang

# Perguntas de exemplo mostradas quando se pede ajuda ou quando a pergunta
# não é reconhecida — o frontend usa a mesma lista para sugerir perguntas
# clicáveis (ver web/js/pages/chat.js — ATENÇÃO: essa lista está duplicada
# manualmente lá, sincronizar as duas ao editar), para nunca haver duas
# listas diferentes de "o que o chatbot sabe fazer" dentro do backend. Esta
# constante (PT) é a usada por omissão e por todo o código já existente —
# ver EXAMPLE_QUESTIONS_EN e example_questions(lang) abaixo para a versão
# inglesa, usada só quando lang="en".
EXAMPLE_QUESTIONS = [
    "Como está o aluno 12?",
    "Porque é que o aluno 12 está em risco?",
    "Qual é a taxa de aprovação?",
    "Quantos estudantes estão em risco?",
    "Qual é o fator mais correlacionado com a nota final?",
    "O que precisa o aluno 12 para chegar a 15 valores?",
    "Como está o aluno 12 comparado com a turma?",
    "Como exporto os dados em CSV?",
]

EXAMPLE_QUESTIONS_EN = [
    "How is student 12 doing?",
    "Why is student 12 at risk?",
    "What is the pass rate?",
    "How many students are at risk?",
    "What is the factor most correlated with the final grade?",
    "What does student 12 need to reach 15 points?",
    "How does student 12 compare to the class?",
    "How do I export the data as CSV?",
]


def example_questions(lang: str | None = None) -> list[str]:
    """Lista de perguntas de exemplo no idioma pedido (ver EXAMPLE_QUESTIONS acima)."""
    return EXAMPLE_QUESTIONS_EN if normalize_lang(lang) == "en" else EXAMPLE_QUESTIONS

# Respostas fixas de ajuda a navegar a app — por palavras-chave, não é
# preciso nenhum pedido à API para responder a isto.
# Cada entrada é (lista de palavras-chave PT+EN, resposta PT, resposta EN) —
# as palavras-chave misturam os dois idiomas de propósito (ver nota de i18n
# no topo do ficheiro): reconhece a pergunta em qualquer um dos idiomas,
# só a resposta depende de `lang`. As palavras-chave PT originais nunca
# foram alteradas, só foram acrescentadas as equivalentes em inglês.
NAV_FAQ = [
    (["exportar", "csv", "download", "descarregar", "export"],
     'Vai à página "Dados", aplica os filtros que quiseres (opcional) e clica em "Exportar CSV" — descarrega logo o ficheiro com os estudantes filtrados.',
     'Go to the "Data" page, apply any filters you want (optional), and click "Export CSV" — it downloads the file with the filtered students right away.'),
    (["importar", "carregar ficheiro", "lote", "import", "upload file", "batch"],
     'Na página "Adicionar Dados", desce até "Importar vários estudantes de uma vez (CSV)", escolhe o ficheiro e clica em "Importar CSV".',
     'On the "Add Data" page, scroll down to "Import multiple students at once (CSV)", choose the file, and click "Import CSV".'),
    (["alertas", "avisos", "notifica", "alerts", "notifications"],
     'A página "Avisos e Alertas" mostra os sinais mais urgentes calculados a partir do dataset atual, e também os estudantes em risco.',
     'The "Alerts" page shows the most urgent signals calculated from the current dataset, along with the students at risk.'),
    (["segmenta", "perfis", "clusters", "grupos de alunos", "segmentation", "profiles", "student groups"],
     'A página "Segmentação de Perfis" agrupa os estudantes por hábitos semelhantes (k-means) — podes escolher o número de grupos e as variáveis usadas.',
     'The "Profile Segmentation" page groups students by similar habits (k-means) — you can choose the number of groups and the variables used.'),
    (["ficha", "pdf", "relatório individual", "relatorio individual", "report card", "individual report"],
     'Em "Fichas de Desempenho" consegues gerar um PDF individual por estudante, ou várias fichas de uma vez em lote.',
     'In "Performance Reports" you can generate an individual PDF per student, or several report cards at once in batch.'),
]


def _extract_student_id(question: str) -> Optional[int]:
    """
    Procura primeiro um número logo a seguir a "aluno"/"estudante"/"id"/"student"
    (ex.: "aluno 12" / "student 12"). Se não encontrar mas a pergunta ainda
    assim mencionar um aluno/estudante e só tiver um número lá dentro, assume
    que é esse (ex.: "o 12 está em risco?"). Nunca assume um número como id só
    porque aparece na frase — isso confundiria facilmente uma nota-alvo com um id.
    """
    # Caso principal: "aluno 12", "estudante 12", "id 12", "student 12" (até 5 caracteres entre a palavra e o número).
    match = re.search(r"\b(?:aluno|estudante|id|student)\D{0,5}(\d+)", question, re.IGNORECASE)
    if match:
        return int(match.group(1))
    # Caso alternativo: a pergunta menciona "aluno"/"estudante"/"student" mas o
    # número está noutro sítio da frase — só assume se houver exatamente UM número (sem ambiguidade).
    if re.search(r"\b(aluno|estudante|student)\b", question, re.IGNORECASE):
        numbers = re.findall(r"\d+", question)
        if len(numbers) == 1:
            return int(numbers[0])
    return None


def _get_student_row(df: pd.DataFrame, student_id: int) -> Optional[pd.Series]:
    """Procura o estudante pelo id no dataset. Devolve None se não existir."""
    rows = df[df["student_id"] == student_id]
    return rows.iloc[0] if not rows.empty else None


def _fmt(value, decimals: int = 1) -> str:
    """Formata um número com casas decimais fixas, para as respostas ficarem consistentes."""
    return f"{float(value):.{decimals}f}"


def _match_nav_faq(question_lower: str, lang: str | None = None) -> Optional[str]:
    """Procura na lista NAV_FAQ se alguma palavra-chave (PT ou EN) aparece na pergunta, e devolve a resposta no idioma pedido."""
    lang = normalize_lang(lang)
    for keywords, answer_pt, answer_en in NAV_FAQ:
        if any(k in question_lower for k in keywords):
            return answer_en if lang == "en" else answer_pt
    return None


def _student_not_found(student_id: int, lang: str | None = None) -> dict:
    """Resposta padrão quando o id de estudante indicado não existe no dataset atual."""
    return {
        "intent": "student_not_found",
        "answer": t(
            lang,
            f"Não encontrei nenhum estudante com o número {student_id} no dataset atual.",
            f"I couldn't find any student with number {student_id} in the current dataset.",
        ),
    }


def _fallback(lang: str | None = None) -> dict:
    """Resposta padrão quando nenhum tipo de pergunta conhecido foi reconhecido."""
    examples = example_questions(lang)
    return {
        "intent": "fallback",
        "answer": t(
            lang,
            "Não percebi bem a pergunta. Podes perguntar, por exemplo:\n",
            "I didn't quite understand the question. You could ask, for example:\n",
        ) + "\n".join(f"• {e}" for e in examples),
    }


def _help(lang: str | None = None) -> dict:
    """Resposta ao pedir ajuda (ex.: "o que sabes fazer?"), com exemplos de perguntas."""
    examples = example_questions(lang)
    return {
        "intent": "help",
        "answer": (
            t(
                lang,
                "Posso responder a perguntas sobre um estudante específico, sobre o dataset todo, "
                "ou ajudar a navegar a app. Por exemplo:\n",
                "I can answer questions about a specific student, about the whole dataset, "
                "or help you navigate the app. For example:\n",
            ) + "\n".join(f"• {e}" for e in examples)
        ),
    }


def _answer_student_explain(df: pd.DataFrame, student_id: int, lang: str | None = None) -> dict:
    """Responde a "porque está o aluno X em risco/com esta nota?" usando explain_prediction."""
    row = _get_student_row(df, student_id)
    if row is None:
        return _student_not_found(student_id, lang)
    # Constrói o dicionário de entrada para o modelo a partir dos dados reais deste estudante.
    user_input = {feat: row[feat] for feat in EXPLAIN_FEATURES if feat in row}
    result = explain_prediction(user_input, lang=lang)
    if not result["contributions"]:
        # Nenhum fator se destacou — os valores deste estudante estão todos perto do típico.
        return {
            "intent": "student_explain",
            "answer": t(
                lang,
                f"Para o estudante {student_id}, os valores indicados estão perto do típico do "
                f"dataset — nenhum fator isolado se destaca na previsão ({_fmt(result['baseline_grade'])} valores).",
                f"For student {student_id}, the values provided are close to the dataset's typical "
                f"values — no single factor stands out in the prediction ({_fmt(result['baseline_grade'])} points).",
            ),
        }
    # Mostra só os 3 fatores com maior impacto (positivo ou negativo).
    top = result["contributions"][:3]
    lines = [
        t(
            lang,
            f"• {c['label']}: {'ajuda' if c['impact'] > 0 else 'prejudica'} a previsão em "
            f"{abs(c['impact']):.2f} valores (valor do aluno: {c['student_value']}, típico: {c['typical_value']})",
            f"• {c['label']}: {'helps' if c['impact'] > 0 else 'hurts'} the prediction by "
            f"{abs(c['impact']):.2f} points (student's value: {c['student_value']}, typical: {c['typical_value']})",
        )
        for c in top
    ]
    return {
        "intent": "student_explain",
        "answer": (
            t(
                lang,
                f"Nota prevista para o estudante {student_id}: {_fmt(result['baseline_grade'])} valores. "
                "Os fatores que mais pesam:\n",
                f"Predicted grade for student {student_id}: {_fmt(result['baseline_grade'])} points. "
                "The factors that weigh most:\n",
            ) + "\n".join(lines)
        ),
    }


def _answer_student_plan(df: pd.DataFrame, student_id: int, question_lower: str, lang: str | None = None) -> dict:
    """Responde a "o que precisa o aluno X para chegar a Y valores?" usando o Otimizador."""
    # Procura números na pergunta (a nota-alvo) — aceita tanto vírgula como ponto decimal.
    numbers = [float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", question_lower)]
    # Ignora o próprio id do estudante e valores fora da escala de notas (0-20); usa o último número válido.
    candidates = [n for n in numbers if n != student_id and 0 <= n <= 20]
    # Se não encontrar uma nota-alvo explícita na pergunta, assume 14 valores por omissão.
    target_grade = candidates[-1] if candidates else 14.0

    try:
        plan = otimizar_plano_estudo(df, student_id, target_grade, lang=lang)
    except ValueError:
        return _student_not_found(student_id, lang)

    if plan["achieved"] and not plan["changes"]:
        # Já cumpre a meta sem precisar de mudar nada.
        return {"intent": "student_plan", "answer": plan["message"]}
    if not plan["changes"]:
        # Não foi encontrada nenhuma combinação de mudanças que ajude.
        return {
            "intent": "student_plan",
            "answer": t(
                lang,
                f"Não encontrei uma combinação de mudanças realistas que leve o estudante "
                f"{student_id} a {target_grade:g} valores. A melhor previsão possível com estas "
                f"alavancas fica perto de {_fmt(plan['final_grade'])} valores.",
                f"I couldn't find a combination of realistic changes that gets student "
                f"{student_id} to {target_grade:g} points. The best possible prediction with these "
                f"levers is close to {_fmt(plan['final_grade'])} points.",
            ),
        }
    # Lista as mudanças de hábitos sugeridas, uma por linha.
    lines = [
        t(lang, f"• {c['label']}: de {c['from']} para {c['to']}", f"• {c['label']}: from {c['from']} to {c['to']}")
        for c in plan["changes"]
    ]
    status = t(
        lang,
        "consegue chegar a" if plan["achieved"] else "aproxima-se de (mas não chega totalmente a)",
        "can reach" if plan["achieved"] else "gets close to (but doesn't fully reach)",
    )
    return {
        "intent": "student_plan",
        "answer": (
            t(
                lang,
                f"Com estas mudanças, o estudante {student_id} {status} {target_grade:g} valores "
                f"(previsão final: {_fmt(plan['final_grade'])}):\n",
                f"With these changes, student {student_id} {status} {target_grade:g} points "
                f"(final prediction: {_fmt(plan['final_grade'])}):\n",
            ) + "\n".join(lines)
        ),
    }


def _answer_student_compare(df: pd.DataFrame, student_id: int, lang: str | None = None) -> dict:
    """Responde a "como está o aluno X comparado com a turma?" — compara com colegas do mesmo perfil de estudo."""
    row = _get_student_row(df, student_id)
    if row is None:
        return _student_not_found(student_id, lang)
    # Grupo de comparação: colegas com o mesmo nível de tempo de estudo.
    peers = df[df["studytime"] == row["studytime"]]
    if len(peers) <= 1:
        # Só o próprio estudante está neste grupo — não há ninguém para comparar.
        return {
            "intent": "student_compare",
            "answer": t(
                lang,
                f"Não há estudantes suficientes com o mesmo perfil de tempo de estudo para comparar com o estudante {student_id}.",
                f"There aren't enough students with the same study-time profile to compare with student {student_id}.",
            ),
        }
    peer_avg = peers["G3"].mean()
    peer_pass = peers["aprovado"].mean()
    diff = row["G3"] - peer_avg
    direction = t(lang, "acima", "above") if diff >= 0 else t(lang, "abaixo", "below")
    return {
        "intent": "student_compare",
        "answer": t(
            lang,
            f"O estudante {student_id} tem {_fmt(row['G3'])} valores, {abs(diff):.1f} valores "
            f"{direction} da média de {len(peers)} estudantes com o mesmo tempo de estudo "
            f"({_fmt(peer_avg)} valores, {peer_pass * 100:.0f}% de taxa de aprovação).",
            f"Student {student_id} has {_fmt(row['G3'])} points, {abs(diff):.1f} points "
            f"{direction} the average of {len(peers)} students with the same study time "
            f"({_fmt(peer_avg)} points, {peer_pass * 100:.0f}% pass rate).",
        ),
    }


def _answer_student_status(df: pd.DataFrame, student_id: int, lang: str | None = None) -> dict:
    """Resposta por omissão a uma pergunta sobre um estudante concreto: um resumo geral do seu estado."""
    row = _get_student_row(df, student_id)
    if row is None:
        return _student_not_found(student_id, lang)
    risk_text = t(
        lang,
        "está sinalizado como em risco" if row["at_risk"] else "não está sinalizado como em risco",
        "is flagged as at risk" if row["at_risk"] else "is not flagged as at risk",
    )
    return {
        "intent": "student_status",
        "answer": t(
            lang,
            f"Estudante {student_id}: nota final {_fmt(row['G3'])} valores ({row['perf_band']}), "
            f"{risk_text}. Tempo de estudo: nível {int(row['studytime'])}, faltas: {int(row['absences'])}, "
            f"reprovações anteriores: {int(row['failures'])}.",
            f"Student {student_id}: final grade {_fmt(row['G3'])} points ({row['perf_band']}), "
            f"{risk_text}. Study time: level {int(row['studytime'])}, absences: {int(row['absences'])}, "
            f"prior failures: {int(row['failures'])}.",
        ),
    }


def answer_question(df: pd.DataFrame, question: str, lang: str | None = None) -> dict:
    """
    Responde a uma pergunta em texto livre, dentro do conjunto de tipos de
    pergunta reconhecidos (ver EXAMPLE_QUESTIONS). Devolve sempre
    {"intent": ..., "answer": ...} — "intent" identifica que tipo de
    pergunta foi reconhecido (útil para testes e para o frontend).

    `lang` só decide o idioma da resposta — a pergunta em si é reconhecida
    tanto em português como em inglês, independentemente de `lang` (ver nota
    de i18n no topo do ficheiro).
    """
    question = (question or "").strip()
    if not question:
        return _fallback(lang)

    # Versão em minúsculas, usada em todas as comparações de palavras-chave abaixo.
    ql = question.lower()

    # Pedido de ajuda / saudação — responde sempre com a lista de exemplos.
    if any(w in ql for w in [
        "ajuda", "o que podes fazer", "o que sabes fazer", "ajudar-me", "olá", "ola", "bom dia", "boa tarde",
        "help", "what can you do", "hello", "hi ", "good morning", "good afternoon",
    ]):
        return _help(lang)

    # Tenta identificar se a pergunta é sobre um estudante específico.
    student_id = _extract_student_id(ql)

    if student_id is not None:
        # Dentro de uma pergunta sobre um estudante, distingue o tipo exato pela intenção das palavras usadas.
        if any(w in ql for w in [
            "porque", "por que", "pesa", "explica", "razão", "razao",
            "why", "explain", "reason",
        ]):
            return _answer_student_explain(df, student_id, lang)
        if any(w in ql for w in [
            "chegar a", "atingir", "preciso", "precisa", "meta", "alvo",
            "reach", "achieve", "need", "needs", "target", "goal",
        ]):
            return _answer_student_plan(df, student_id, ql, lang)
        if any(w in ql for w in [
            "compar", "turma", "pares", "média da turma", "media da turma",
            "compare", "class", "peers", "class average",
        ]):
            return _answer_student_compare(df, student_id, lang)
        # Nenhuma palavra-chave específica reconhecida — devolve o estado geral do estudante.
        return _answer_student_status(df, student_id, lang)

    # A partir daqui, a pergunta é sobre o dataset como um todo (não sobre um estudante específico).

    if any(w in ql for w in [
        "taxa de aprovação", "taxa de aprovacao", "aprovados", "quantos passam",
        "pass rate", "passing rate", "how many pass",
    ]):
        pass_rate = df["aprovado"].mean()
        return {
            "intent": "dataset_stats",
            "answer": t(
                lang,
                f"A taxa de aprovação atual do dataset é {pass_rate * 100:.1f}% ({int(df['aprovado'].sum())} de {len(df)} estudantes).",
                f"The current pass rate of the dataset is {pass_rate * 100:.1f}% ({int(df['aprovado'].sum())} out of {len(df)} students).",
            ),
        }

    if "risco" in ql or "at risk" in ql or "at-risk" in ql:
        n_risk = int(df["at_risk"].sum())
        return {
            "intent": "dataset_stats",
            "answer": t(
                lang,
                f"Há {n_risk} estudante(s) em risco em {len(df)} ({n_risk / len(df) * 100:.1f}%).",
                f"There {plural_en(n_risk, 'is', 'are')} {n_risk} {plural_en(n_risk, 'student', 'students')} at risk out of {len(df)} ({n_risk / len(df) * 100:.1f}%).",
            ),
        }

    if any(w in ql for w in [
        "nota média", "nota media", "média das notas", "media das notas",
        "average grade", "mean grade", "average score",
    ]):
        return {
            "intent": "dataset_stats",
            "answer": t(
                lang,
                f"A nota média (G3) do dataset é {_fmt(df['G3'].mean())} valores, numa escala de 0 a 20.",
                f"The average grade (G3) of the dataset is {_fmt(df['G3'].mean())} points, on a scale of 0 to 20.",
            ),
        }

    if any(w in ql for w in [
        "quantos estudantes", "quantos alunos", "tamanho do dataset", "número de estudantes", "numero de estudantes",
        "how many students", "dataset size", "number of students",
    ]):
        return {
            "intent": "dataset_stats",
            "answer": t(
                lang,
                f"O dataset tem atualmente {len(df)} estudantes.",
                f"The dataset currently has {len(df)} students.",
            ),
        }

    if any(w in ql for w in [
        "correlacionad", "correlação", "correlacao", "mais afeta", "influencia mais",
        "correlated", "correlation", "most affects", "most influences",
    ]):
        # Calcula a correlação de todas as variáveis numéricas com a nota final, em tempo real.
        numeric_cols = [c for c in df.select_dtypes("number").columns if c != "G3"]
        if not numeric_cols:
            return {
                "intent": "dataset_stats",
                "answer": t(lang, "Não foi possível calcular as correlações.", "It wasn't possible to calculate the correlations."),
            }
        corr = df[numeric_cols + ["G3"]].corr()["G3"].drop("G3")
        # A variável com maior correlação em valor absoluto (positiva ou negativa).
        top_col = corr.abs().sort_values(ascending=False).index[0]
        return {
            "intent": "dataset_stats",
            "answer": t(
                lang,
                f'A variável mais correlacionada com a nota final é "{top_col}" '
                f"(correlação de {corr[top_col]:.2f}). Correlação não é o mesmo que causalidade.",
                f'The variable most correlated with the final grade is "{top_col}" '
                f"(correlation of {corr[top_col]:.2f}). Correlation is not the same as causation.",
            ),
        }

    if any(w in ql for w in [
        "resumo", "panorama", "como está a turma", "como esta a turma",
        "summary", "overview", "how is the class",
    ]):
        # Reaproveita o mesmo resumo automático mostrado no topo da Visão Geral.
        return {"intent": "dataset_stats", "answer": generate_overview_summary(df, lang=lang)}

    # Última tentativa: verifica se a pergunta é sobre como usar/navegar a app.
    nav_answer = _match_nav_faq(ql, lang)
    if nav_answer:
        return {"intent": "navigation_help", "answer": nav_answer}

    # Nenhum tipo de pergunta foi reconhecido.
    return _fallback(lang)
