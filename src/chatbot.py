"""
Assistente da StudentPerfomance — chatbot baseado em regras, não num LLM externo:
reconhece o tipo de pergunta por palavras-chave e responde chamando as
mesmas funções já usadas pela API REST (estatísticas, alertas, explicação
da previsão, otimizador de estudo, correlações). Mantém a app 100% local,
sem chave de API nem ligação à internet — só entende o conjunto de
perguntas listado em EXAMPLE_QUESTIONS, mas responde sempre com dados
reais e atuais do dataset, nunca inventados.
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

# Perguntas de exemplo mostradas quando se pede ajuda ou quando a pergunta
# não é reconhecida — o frontend usa a mesma lista para sugerir perguntas
# clicáveis (ver web/js/pages/chat.js), para nunca haver duas listas
# diferentes de "o que o chatbot sabe fazer".
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

# Respostas fixas de ajuda a navegar a app — por palavras-chave, não é
# preciso nenhum pedido à API para responder a isto.
# Cada entrada é (lista de palavras-chave, resposta a dar se alguma delas aparecer na pergunta).
NAV_FAQ = [
    (["exportar", "csv", "download", "descarregar"],
    'Vai à página "Dados", aplica os filtros que quiseres (opcional) e clica em "Exportar CSV" — descarrega logo o ficheiro com os estudantes filtrados.'),
    (["importar", "carregar ficheiro", "lote"],
    'Na página "Adicionar Dados", desce até "Importar vários estudantes de uma vez (CSV)", escolhe o ficheiro e clica em "Importar CSV".'),
    (["alertas", "avisos", "notifica"],
    'A página "Avisos e Alertas" mostra os sinais mais urgentes calculados a partir do dataset atual, e também os estudantes em risco.'),
    (["segmenta", "perfis", "clusters", "grupos de alunos"],
    'A página "Segmentação de Perfis" agrupa os estudantes por hábitos semelhantes (k-means) — podes escolher o número de grupos e as variáveis usadas.'),
    (["ficha", "pdf", "relatório individual", "relatorio individual"],
    'Em "Fichas de Desempenho" consegues gerar um PDF individual por estudante, ou várias fichas de uma vez em lote.'),
]


def _extract_student_id(question: str) -> Optional[int]:
    """
    Procura primeiro um número logo a seguir a "aluno"/"estudante"/"id"
    (ex.: "aluno 12"). Se não encontrar mas a pergunta ainda assim mencionar
    um aluno/estudante e só tiver um número lá dentro, assume que é esse
    (ex.: "o 12 está em risco?"). Nunca assume um número como id só porque
    aparece na frase — isso confundiria facilmente uma nota-alvo com um id.
    """
    # Caso principal: "aluno 12", "estudante 12", "id 12" (com até 5 caracteres entre a palavra e o número).
    match = re.search(r"\b(?:aluno|estudante|id)\D{0,5}(\d+)", question, re.IGNORECASE)
    if match:
        return int(match.group(1))
    # Caso alternativo: a pergunta menciona "aluno"/"estudante" mas o número
    # está noutro sítio da frase — só assume se houver exatamente UM número (sem ambiguidade).
    if re.search(r"\b(aluno|estudante)\b", question, re.IGNORECASE):
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


def _match_nav_faq(question_lower: str) -> Optional[str]:
    """Procura na lista NAV_FAQ se alguma palavra-chave aparece na pergunta, e devolve a resposta correspondente."""
    for keywords, answer in NAV_FAQ:
        if any(k in question_lower for k in keywords):
            return answer
    return None


def _student_not_found(student_id: int) -> dict:
    """Resposta padrão quando o id de estudante indicado não existe no dataset atual."""
    return {
        "intent": "student_not_found",
        "answer": f"Não encontrei nenhum estudante com o número {student_id} no dataset atual.",
    }


def _fallback() -> dict:
    """Resposta padrão quando nenhum tipo de pergunta conhecido foi reconhecido."""
    return {
        "intent": "fallback",
        "answer": "Não percebi bem a pergunta. Podes perguntar, por exemplo:\n" + "\n".join(f"• {e}" for e in EXAMPLE_QUESTIONS),
    }


def _help() -> dict:
    """Resposta ao pedir ajuda (ex.: "o que sabes fazer?"), com exemplos de perguntas."""
    return {
        "intent": "help",
        "answer": (
            "Posso responder a perguntas sobre um estudante específico, sobre o dataset todo, "
            "ou ajudar a navegar a app. Por exemplo:\n" + "\n".join(f"• {e}" for e in EXAMPLE_QUESTIONS)
        ),
    }


def _answer_student_explain(df: pd.DataFrame, student_id: int) -> dict:
    """Responde a "porque está o aluno X em risco/com esta nota?" usando explain_prediction."""
    row = _get_student_row(df, student_id)
    if row is None:
        return _student_not_found(student_id)
    # Constrói o dicionário de entrada para o modelo a partir dos dados reais deste estudante.
    user_input = {feat: row[feat] for feat in EXPLAIN_FEATURES if feat in row}
    result = explain_prediction(user_input)
    if not result["contributions"]:
        # Nenhum fator se destacou — os valores deste estudante estão todos perto do típico.
        return {
            "intent": "student_explain",
            "answer": (
                f"Para o estudante {student_id}, os valores indicados estão perto do típico do "
                f"dataset — nenhum fator isolado se destaca na previsão ({_fmt(result['baseline_grade'])} valores)."
            ),
        }
    # Mostra só os 3 fatores com maior impacto (positivo ou negativo).
    top = result["contributions"][:3]
    lines = [
        f"• {c['label']}: {'ajuda' if c['impact'] > 0 else 'prejudica'} a previsão em "
        f"{abs(c['impact']):.2f} valores (valor do aluno: {c['student_value']}, típico: {c['typical_value']})"
        for c in top
    ]
    return {
        "intent": "student_explain",
        "answer": (
            f"Nota prevista para o estudante {student_id}: {_fmt(result['baseline_grade'])} valores. "
            "Os fatores que mais pesam:\n" + "\n".join(lines)
        ),
    }


def _answer_student_plan(df: pd.DataFrame, student_id: int, question_lower: str) -> dict:
    """Responde a "o que precisa o aluno X para chegar a Y valores?" usando o Otimizador."""
    # Procura números na pergunta (a nota-alvo) — aceita tanto vírgula como ponto decimal.
    numbers = [float(n.replace(",", ".")) for n in re.findall(r"\d+(?:[.,]\d+)?", question_lower)]
    # Ignora o próprio id do estudante e valores fora da escala de notas (0-20); usa o último número válido.
    candidates = [n for n in numbers if n != student_id and 0 <= n <= 20]
    # Se não encontrar uma nota-alvo explícita na pergunta, assume 14 valores por omissão.
    target_grade = candidates[-1] if candidates else 14.0

    try:
        plan = otimizar_plano_estudo(df, student_id, target_grade)
    except ValueError:
        return _student_not_found(student_id)

    if plan["achieved"] and not plan["changes"]:
        # Já cumpre a meta sem precisar de mudar nada.
        return {"intent": "student_plan", "answer": plan["message"]}
    if not plan["changes"]:
        # Não foi encontrada nenhuma combinação de mudanças que ajude.
        return {
            "intent": "student_plan",
            "answer": (
                f"Não encontrei uma combinação de mudanças realistas que leve o estudante "
                f"{student_id} a {target_grade:g} valores. A melhor previsão possível com estas "
                f"alavancas fica perto de {_fmt(plan['final_grade'])} valores."
            ),
        }
    # Lista as mudanças de hábitos sugeridas, uma por linha.
    lines = [f"• {c['label']}: de {c['from']} para {c['to']}" for c in plan["changes"]]
    status = "consegue chegar a" if plan["achieved"] else "aproxima-se de (mas não chega totalmente a)"
    return {
        "intent": "student_plan",
        "answer": (
            f"Com estas mudanças, o estudante {student_id} {status} {target_grade:g} valores "
            f"(previsão final: {_fmt(plan['final_grade'])}):\n" + "\n".join(lines)
        ),
    }


def _answer_student_compare(df: pd.DataFrame, student_id: int) -> dict:
    """Responde a "como está o aluno X comparado com a turma?" — compara com colegas do mesmo perfil de estudo."""
    row = _get_student_row(df, student_id)
    if row is None:
        return _student_not_found(student_id)
    # Grupo de comparação: colegas com o mesmo nível de tempo de estudo.
    peers = df[df["studytime"] == row["studytime"]]
    if len(peers) <= 1:
        # Só o próprio estudante está neste grupo — não há ninguém para comparar.
        return {
            "intent": "student_compare",
            "answer": f"Não há estudantes suficientes com o mesmo perfil de tempo de estudo para comparar com o estudante {student_id}.",
        }
    peer_avg = peers["G3"].mean()
    peer_pass = peers["aprovado"].mean()
    diff = row["G3"] - peer_avg
    direction = "acima" if diff >= 0 else "abaixo"
    return {
        "intent": "student_compare",
        "answer": (
            f"O estudante {student_id} tem {_fmt(row['G3'])} valores, {abs(diff):.1f} valores "
            f"{direction} da média de {len(peers)} estudantes com o mesmo tempo de estudo "
            f"({_fmt(peer_avg)} valores, {peer_pass * 100:.0f}% de taxa de aprovação)."
        ),
    }


def _answer_student_status(df: pd.DataFrame, student_id: int) -> dict:
    """Resposta por omissão a uma pergunta sobre um estudante concreto: um resumo geral do seu estado."""
    row = _get_student_row(df, student_id)
    if row is None:
        return _student_not_found(student_id)
    risk_text = "está sinalizado como em risco" if row["at_risk"] else "não está sinalizado como em risco"
    return {
        "intent": "student_status",
        "answer": (
            f"Estudante {student_id}: nota final {_fmt(row['G3'])} valores ({row['perf_band']}), "
            f"{risk_text}. Tempo de estudo: nível {int(row['studytime'])}, faltas: {int(row['absences'])}, "
            f"reprovações anteriores: {int(row['failures'])}."
        ),
    }


def answer_question(df: pd.DataFrame, question: str) -> dict:
    """
    Responde a uma pergunta em texto livre, dentro do conjunto de tipos de
    pergunta reconhecidos (ver EXAMPLE_QUESTIONS). Devolve sempre
    {"intent": ..., "answer": ...} — "intent" identifica que tipo de
    pergunta foi reconhecido (útil para testes e para o frontend).
    """
    question = (question or "").strip()
    if not question:
        return _fallback()

    # Versão em minúsculas, usada em todas as comparações de palavras-chave abaixo.
    ql = question.lower()

    # Pedido de ajuda / saudação — responde sempre com a lista de exemplos.
    if any(w in ql for w in ["ajuda", "o que podes fazer", "o que sabes fazer", "ajudar-me", "olá", "ola", "bom dia", "boa tarde"]):
        return _help()

    # Tenta identificar se a pergunta é sobre um estudante específico.
    student_id = _extract_student_id(ql)

    if student_id is not None:
        # Dentro de uma pergunta sobre um estudante, distingue o tipo exato pela intenção das palavras usadas.
        if any(w in ql for w in ["porque", "por que", "pesa", "explica", "razão", "razao"]):
            return _answer_student_explain(df, student_id)
        if any(w in ql for w in ["chegar a", "atingir", "preciso", "precisa", "meta", "alvo"]):
            return _answer_student_plan(df, student_id, ql)
        if any(w in ql for w in ["compar", "turma", "pares", "média da turma", "media da turma"]):
            return _answer_student_compare(df, student_id)
        # Nenhuma palavra-chave específica reconhecida — devolve o estado geral do estudante.
        return _answer_student_status(df, student_id)

    # A partir daqui, a pergunta é sobre o dataset como um todo (não sobre um estudante específico).

    if any(w in ql for w in ["taxa de aprovação", "taxa de aprovacao", "aprovados", "quantos passam"]):
        pass_rate = df["aprovado"].mean()
        return {
            "intent": "dataset_stats",
            "answer": f"A taxa de aprovação atual do dataset é {pass_rate * 100:.1f}% ({int(df['aprovado'].sum())} de {len(df)} estudantes).",
        }

    if "risco" in ql:
        n_risk = int(df["at_risk"].sum())
        return {
            "intent": "dataset_stats",
            "answer": f"Há {n_risk} estudante(s) em risco em {len(df)} ({n_risk / len(df) * 100:.1f}%).",
        }

    if any(w in ql for w in ["nota média", "nota media", "média das notas", "media das notas"]):
        return {
            "intent": "dataset_stats",
            "answer": f"A nota média (G3) do dataset é {_fmt(df['G3'].mean())} valores, numa escala de 0 a 20.",
        }

    if any(w in ql for w in ["quantos estudantes", "quantos alunos", "tamanho do dataset", "número de estudantes", "numero de estudantes"]):
        return {"intent": "dataset_stats", "answer": f"O dataset tem atualmente {len(df)} estudantes."}

    if any(w in ql for w in ["correlacionad", "correlação", "correlacao", "mais afeta", "influencia mais"]):
        # Calcula a correlação de todas as variáveis numéricas com a nota final, em tempo real.
        numeric_cols = [c for c in df.select_dtypes("number").columns if c != "G3"]
        if not numeric_cols:
            return {"intent": "dataset_stats", "answer": "Não foi possível calcular as correlações."}
        corr = df[numeric_cols + ["G3"]].corr()["G3"].drop("G3")
        # A variável com maior correlação em valor absoluto (positiva ou negativa).
        top_col = corr.abs().sort_values(ascending=False).index[0]
        return {
            "intent": "dataset_stats",
            "answer": (
                f'A variável mais correlacionada com a nota final é "{top_col}" '
                f"(correlação de {corr[top_col]:.2f}). Correlação não é o mesmo que causalidade."
            ),
        }

    if any(w in ql for w in ["resumo", "panorama", "como está a turma", "como esta a turma"]):
        # Reaproveita o mesmo resumo automático mostrado no topo da Visão Geral.
        return {"intent": "dataset_stats", "answer": generate_overview_summary(df)}

    # Última tentativa: verifica se a pergunta é sobre como usar/navegar a app.
    nav_answer = _match_nav_faq(ql)
    if nav_answer:
        return {"intent": "navigation_help", "answer": nav_answer}

    # Nenhum tipo de pergunta foi reconhecido.
    return _fallback()
