"""
Segmentação de Perfis: agrupa estudantes em "perfis" comportamentais
semelhantes usando K-Means, com nomeação automática de cada grupo a partir
dos traços mais desviantes da média geral (não são nomes fixos/inventados,
são calculados a partir dos próprios dados).

i18n: os nomes de grupo, traços e sugestões de micro-hábitos são texto
gerado pelo backend e devolvido à API — por isso, ao contrário de um
dicionário simples PT->EN, os rótulos e as sugestões estão indexados por um
"código" estável (ex.: "studytime_high") em vez do próprio texto português,
que só existia como chave porque, antes desta funcionalidade, só havia um
idioma. Isto permite traduzir o texto sem partir a ligação entre um traço e
a sua sugestão. Ver src/i18n.py para o helper t()/plural_en() usado noutros
módulos — aqui optou-se por dicionários PT/EN completos (em vez de t() em
cada string) porque os rótulos são reutilizados em vários sítios (nome do
grupo, lista de traços, sugestões) e um dicionário evita repetir a mesma
tradução três vezes.
"""
from __future__ import annotations

# numpy: cálculos numéricos auxiliares.
import numpy as np
# pandas: para trabalhar com os dados como tabela.
import pandas as pd
# KMeans: algoritmo de clustering (agrupamento) usado para formar os perfis.
from sklearn.cluster import KMeans
# StandardScaler: normaliza as variáveis (média 0, desvio-padrão 1) antes do
# KMeans, para nenhuma variável dominar só por ter uma escala maior.
from sklearn.preprocessing import StandardScaler

from src import config
from src.i18n import normalize_lang

# Variáveis usadas por omissão para calcular a semelhança entre estudantes.
SEGMENTATION_FEATURES = [
    "studytime", "absences", "failures", "G1", "G2", "G3",
    "famrel", "freetime", "goout", "Dalc", "Walc", "health", "traveltime",
]

# Para cada variável, o código do traço quando está acima (alto) ou abaixo
# (baixo) da média geral — usado para nomear os grupos automaticamente e
# para ir buscar o rótulo/sugestão no idioma certo (ver TRAIT_CODE_LABELS e
# TRAIT_CODE_SUGGESTIONS abaixo).
TRAIT_CODES = {
    "studytime": ("studytime_high", "studytime_low"),
    "absences": ("absences_high", "absences_low"),
    "failures": ("failures_high", "failures_low"),
    "G1": ("G1_high", "G1_low"),
    "G2": ("G2_high", "G2_low"),
    "G3": ("G3_high", "G3_low"),
    "famrel": ("famrel_high", "famrel_low"),
    "freetime": ("freetime_high", "freetime_low"),
    "goout": ("goout_high", "goout_low"),
    "Dalc": ("Dalc_high", "Dalc_low"),
    "Walc": ("Walc_high", "Walc_low"),
    "health": ("health_high", "health_low"),
    "traveltime": ("traveltime_high", "traveltime_low"),
}

# Rótulo de cada código de traço, por idioma.
TRAIT_CODE_LABELS = {
    "pt": {
        "studytime_high": "Dedicados ao Estudo", "studytime_low": "Pouco Tempo de Estudo",
        "absences_high": "Muitas Faltas", "absences_low": "Assiduidade Elevada",
        "failures_high": "Histórico de Reprovações", "failures_low": "Sem Reprovações",
        "G1_high": "Bom Início de Ano", "G1_low": "Início de Ano Fraco",
        "G2_high": "Consistência a Meio do Ano", "G2_low": "Quebra a Meio do Ano",
        "G3_high": "Bom Desempenho Académico", "G3_low": "Desempenho Académico Fraco",
        "famrel_high": "Boa Relação Familiar", "famrel_low": "Relação Familiar Distante",
        "freetime_high": "Muito Tempo Livre", "freetime_low": "Pouco Tempo Livre",
        "goout_high": "Vida Social Ativa", "goout_low": "Pouco Convívio Social",
        "Dalc_high": "Consumo de Álcool em Dias Úteis", "Dalc_low": "Sem Consumo em Dias Úteis",
        "Walc_high": "Consumo de Álcool ao Fim de Semana", "Walc_low": "Sem Consumo ao Fim de Semana",
        "health_high": "Boa Saúde", "health_low": "Saúde Frágil",
        "traveltime_high": "Deslocação Longa até à Escola", "traveltime_low": "Escola Perto de Casa",
    },
    "en": {
        "studytime_high": "Study-Focused", "studytime_low": "Low Study Time",
        "absences_high": "Frequent Absences", "absences_low": "High Attendance",
        "failures_high": "History of Failures", "failures_low": "No Failures",
        "G1_high": "Strong Start to the Year", "G1_low": "Weak Start to the Year",
        "G2_high": "Consistent Mid-Year", "G2_low": "Mid-Year Dip",
        "G3_high": "Strong Academic Performance", "G3_low": "Weak Academic Performance",
        "famrel_high": "Strong Family Relationship", "famrel_low": "Distant Family Relationship",
        "freetime_high": "Lots of Free Time", "freetime_low": "Little Free Time",
        "goout_high": "Active Social Life", "goout_low": "Low Social Activity",
        "Dalc_high": "Weekday Alcohol Consumption", "Dalc_low": "No Weekday Consumption",
        "Walc_high": "Weekend Alcohol Consumption", "Walc_low": "No Weekend Consumption",
        "health_high": "Good Health", "health_low": "Fragile Health",
        "traveltime_high": "Long Commute to School", "traveltime_low": "School Close to Home",
    },
}

# A partir de que desvio-padrão (z-score) um traço é considerado
# suficientemente desviante para caracterizar o grupo.
Z_SCORE_THRESHOLD = 0.35
# Número máximo de traços usados para descrever cada grupo.
MAX_TRAITS_PER_GROUP = 4

# Quantas sugestões de micro-hábitos mostrar por grupo, no máximo — os
# traços mais desviantes (os primeiros de `traits`) são os que melhor
# caracterizam o grupo, por isso só se usam os primeiros.
MAX_SUGGESTIONS_PER_GROUP = 3

# Uma sugestão concreta e acionável para cada código de traço possível — não
# é um conselho genérico tipo "estuda mais", é ligado diretamente ao traço
# mais desviante desse grupo em concreto.
TRAIT_CODE_SUGGESTIONS = {
    "pt": {
        "studytime_high": "Mantém uma rotina fixa (mesmo horário e local) para não perderes o ritmo que já tens.",
        "studytime_low": "Começa por blocos curtos e fixos (15-20 min) todos os dias — mais fácil manter do que sessões longas irregulares.",
        "absences_high": "Identifica a causa mais comum das faltas (transporte, horário, motivação) e resolve-a primeiro.",
        "absences_low": "A tua assiduidade é um ponto forte — protege-a, sobretudo nas semanas antes de avaliações.",
        "failures_high": "Prioriza apoio extra (explicações, tutoria) nas disciplinas onde já reprovaste antes.",
        "failures_low": "Consolida o que já funciona: revê os teus métodos de estudo para os repetires noutras disciplinas.",
        "G1_high": "Mantém o mesmo método que resultou no 1º período — não o abandones a meio do ano.",
        "G1_low": "Recupera terreno cedo: rever a matéria da semana no próprio fim de semana evita acumular dívidas.",
        "G2_high": "Continua a rever regularmente — a consistência entre períodos vale mais do que picos isolados.",
        "G2_low": "Revê o que mudou entre o 1º e o 2º período (rotina, disciplinas, hábitos) para perceberes a causa da quebra.",
        "G3_high": "Regista o que tens feito bem — é mais fácil repetir uma rotina identificada do que adivinhar de novo.",
        "G3_low": "Foca-te primeiro numa ou duas disciplinas, em vez de tentar melhorar tudo ao mesmo tempo.",
        "famrel_high": "Aproveita o apoio em casa: pede para reverem a matéria contigo ou ajudarem a fixar um horário de estudo.",
        "famrel_low": "Procura um espaço de estudo tranquilo fora de casa (biblioteca, sala de estudo) se o ambiente não ajudar.",
        "freetime_high": "Usa uma pequena parte do tempo livre para revisão espaçada — sessões curtas e frequentes.",
        "freetime_low": "Protege pelo menos um bloco fixo de descanso por semana — também afeta o desempenho.",
        "goout_high": "Define um limite de saídas nas semanas antes de testes ou exames.",
        "goout_low": "Algum convívio social ajuda a gerir o stress — não precisa de ser eliminado por completo.",
        "Dalc_high": "Reduzir o consumo em dias de semana está associado, nos dados analisados, a mais tempo de estudo efetivo.",
        "Dalc_low": "Sem consumo relevante em dias úteis — não é um fator a trabalhar aqui.",
        "Walc_high": "Vale a pena vigiar se o fim de semana está a comprometer o início da semana de estudo.",
        "Walc_low": "Sem consumo relevante ao fim de semana — não é um fator a trabalhar aqui.",
        "health_high": "Mantém a rotina de sono e alimentação que já tens — sustenta a energia para estudar.",
        "health_low": "Cuidar do sono e da alimentação tende a refletir-se na energia disponível para estudar.",
        "traveltime_high": "Aproveita o tempo de deslocação para rever resumos ou ouvir gravações das aulas.",
        "traveltime_low": "Usa o tempo poupado na deslocação para uma rotina de estudo mais regular.",
    },
    "en": {
        "studytime_high": "Stick to a fixed routine (same time and place) so you don't lose the rhythm you already have.",
        "studytime_low": "Start with short, fixed blocks (15-20 min) every day — easier to keep up than long, irregular sessions.",
        "absences_high": "Identify the most common cause of the absences (transport, schedule, motivation) and address it first.",
        "absences_low": "Your attendance is a strong point — protect it, especially in the weeks before assessments.",
        "failures_high": "Prioritize extra support (tutoring, extra classes) in the subjects you've failed before.",
        "failures_low": "Consolidate what already works: review your study methods so you can repeat them in other subjects.",
        "G1_high": "Keep the same method that worked in the 1st term — don't drop it halfway through the year.",
        "G1_low": "Catch up early: reviewing the week's material over the weekend avoids piling up gaps.",
        "G2_high": "Keep reviewing regularly — consistency between terms matters more than isolated peaks.",
        "G2_low": "Review what changed between the 1st and 2nd term (routine, subjects, habits) to understand the cause of the dip.",
        "G3_high": "Write down what's been working — it's easier to repeat a known routine than to guess again.",
        "G3_low": "Focus on one or two subjects first, instead of trying to improve everything at once.",
        "famrel_high": "Make the most of support at home: ask someone to review material with you or help set a study schedule.",
        "famrel_low": "Look for a quiet study space outside the house (library, study room) if the home environment doesn't help.",
        "freetime_high": "Use a small part of your free time for spaced review — short, frequent sessions.",
        "freetime_low": "Protect at least one fixed block of rest per week — it also affects performance.",
        "goout_high": "Set a limit on going out in the weeks before tests or exams.",
        "goout_low": "Some social time helps manage stress — it doesn't need to be eliminated entirely.",
        "Dalc_high": "Cutting back on weekday consumption is associated, in the data analyzed, with more effective study time.",
        "Dalc_low": "No significant weekday consumption — not a factor to work on here.",
        "Walc_high": "Worth keeping an eye on whether the weekend is affecting the start of your study week.",
        "Walc_low": "No significant weekend consumption — not a factor to work on here.",
        "health_high": "Keep the sleep and eating routine you already have — it sustains the energy needed to study.",
        "health_low": "Taking care of sleep and diet tends to be reflected in the energy available for studying.",
        "traveltime_high": "Use the commute time to review summaries or listen to class recordings.",
        "traveltime_low": "Use the time saved on commuting for a more regular study routine.",
    },
}


# Variáveis mostradas no gráfico radar do Perfil do Estudante — um
# subconjunto de hábitos/estilo de vida (sem notas, que já têm o seu próprio
# gráfico de evolução G1->G2->G3 nessa página).
RADAR_FEATURES = ["studytime", "absences", "failures", "famrel", "freetime", "goout", "health"]
# Nomes amigáveis de cada variável do radar, mostrados na legenda do gráfico, por idioma.
RADAR_LABELS = {
    "pt": {
        "studytime": "Tempo de estudo",
        "absences": "Faltas",
        "failures": "Reprovações",
        "famrel": "Relação familiar",
        "freetime": "Tempo livre",
        "goout": "Sair com amigos",
        "health": "Saúde",
    },
    "en": {
        "studytime": "Study time",
        "absences": "Absences",
        "failures": "Failures",
        "famrel": "Family relationship",
        "freetime": "Free time",
        "goout": "Going out with friends",
        "health": "Health",
    },
}


def radar_profile(df: pd.DataFrame, subgroup_mask: pd.Series, lang: str | None = None) -> dict:
    """
    Médias de RADAR_FEATURES normalizadas (min-max, escala 0-100) para o
    subgrupo filtrado (Perfil do Estudante) vs a turma toda — pronto para um
    gráfico radar/spider no frontend. A normalização usa sempre os limites
    do dataset COMPLETO (não do subgrupo), para os eixos terem sempre a
    mesma escala, independentemente do filtro ativo.
    """
    lang = normalize_lang(lang)
    # Filtra o dataset pelo subgrupo indicado (ex.: só estudantes de uma escola).
    subgroup = df[subgroup_mask]
    # Uma lista de valores (0-100) por eixo do radar, para o subgrupo e para a turma toda.
    subgroup_values, overall_values = [], []

    for feature in RADAR_FEATURES:
        # Mínimo e máximo desta variável em TODO o dataset (não só no subgrupo),
        # para a escala do gráfico ser sempre a mesma independentemente do filtro.
        lo, hi = float(df[feature].min()), float(df[feature].max())
        span = hi - lo

        def normalize(value: float) -> float:
            # Normalização min-max: converte o valor para uma escala de 0 a 100.
            if span == 0:
                # Sem variação nos dados — evita divisão por zero, usa o ponto médio.
                return 50.0
            return round((value - lo) / span * 100, 1)

        # Se o subgrupo estiver vazio, usa 0 em vez de tentar calcular a média de nada.
        subgroup_values.append(normalize(float(subgroup[feature].mean())) if len(subgroup) else 0.0)
        overall_values.append(normalize(float(df[feature].mean())))

    return {
        "features": RADAR_FEATURES,
        "labels": [RADAR_LABELS[lang][f] for f in RADAR_FEATURES],
        "subgroup_values": subgroup_values,
        "overall_values": overall_values,
        "n_subgroup": int(len(subgroup)),
    }


def _name_cluster(z_means: pd.Series, features: list[str], lang: str) -> tuple[str, list[str]]:
    """Escolhe os traços mais desviantes da média para nomear o grupo. Devolve
    o nome do grupo e a lista de RÓTULOS (já traduzidos para `lang`) dos
    traços — a lista de códigos usada para procurar as sugestões é calculada
    à parte (ver _trait_codes), para não se perder a ligação traço<->sugestão
    quando o rótulo muda de idioma."""
    codes = _trait_codes(z_means, features)
    labels = TRAIT_CODE_LABELS[lang]

    if not codes:
        # Nenhum traço se destacou o suficiente — o grupo é "normal" em tudo.
        mixed = (
            "Perfil Misto (sem traços muito acima da média geral)" if lang == "pt"
            else "Mixed Profile (no traits far above the general average)"
        )
        return mixed, [mixed]

    traits = [labels[code] for code in codes]
    # Nome do grupo: combina os dois traços mais fortes, ou só um se for o único.
    name = " & ".join(traits[:2]) if len(traits) >= 2 else traits[0]
    return name, traits


def _trait_codes(z_means: pd.Series, features: list[str]) -> list[str]:
    """Códigos (independentes de idioma) dos traços mais desviantes da
    média, ordenados do mais para o menos desviante — usados tanto para
    montar os rótulos como para procurar as sugestões de micro-hábitos."""
    # Ordena as variáveis pelo valor absoluto do desvio (mais desviante primeiro).
    deviations = z_means.reindex(features).abs().sort_values(ascending=False)
    # Só considera os traços que ultrapassam o limiar mínimo, até ao máximo definido.
    salient = [f for f in deviations.index if deviations[f] >= Z_SCORE_THRESHOLD][:MAX_TRAITS_PER_GROUP]

    codes = []
    for feature in salient:
        high_code, low_code = TRAIT_CODES[feature]
        # Escolhe o código "alto" ou "baixo" consoante o sinal do desvio deste grupo.
        codes.append(high_code if z_means[feature] > 0 else low_code)
    return codes


def _suggest_micro_habits(codes: list[str], lang: str) -> list[str]:
    """Traduz os códigos de traço mais desviantes do grupo em sugestões
    concretas, uma por traço, até MAX_SUGGESTIONS_PER_GROUP — usa sempre os
    PRIMEIROS códigos da lista, que já vêm ordenados por desvio (o mais
    característico do grupo primeiro)."""
    suggestions_by_code = TRAIT_CODE_SUGGESTIONS[lang]
    suggestions = []
    for code in codes[:MAX_SUGGESTIONS_PER_GROUP]:
        suggestion = suggestions_by_code.get(code)
        if suggestion:
            suggestions.append(suggestion)
    return suggestions


def run_segmentation(
    df: pd.DataFrame,
    n_clusters: int = 4,
    features: list[str] | None = None,
    lang: str | None = None,
) -> dict:
    """Agrupa os estudantes em `n_clusters` perfis, usando as variáveis indicadas (ou as por omissão)."""
    lang = normalize_lang(lang)
    # Restringe o número de clusters a um intervalo razoável (nem poucos
    # demais para não ter significado, nem tantos que fiquem grupos minúsculos).
    n_clusters = max(3, min(8, n_clusters))

    # Por omissão usa-se o conjunto completo de 13 variáveis; o utilizador
    # pode escolher um subconjunto (mín. 2) na página de Segmentação para
    # ver como os perfis mudam ao focar só em certas dimensões (ex.: só
    # hábitos de estudo, sem envolver as notas).
    if features is None:
        features = SEGMENTATION_FEATURES
    else:
        # Valida que todas as variáveis pedidas são conhecidas e que há pelo menos 2.
        invalid = [f for f in features if f not in SEGMENTATION_FEATURES]
        if invalid:
            raise ValueError(f"Variáveis desconhecidas: {', '.join(invalid)}")
        if len(features) < 2:
            raise ValueError("É preciso escolher pelo menos 2 variáveis.")

    # Extrai só as colunas escolhidas, como números.
    X = df[features].astype(float)
    # Normaliza cada variável (média 0, desvio-padrão 1), para nenhuma
    # dominar o cálculo de distância só por ter uma escala maior (ex.: faltas 0-93 vs notas 0-20).
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Corre o K-Means: agrupa os estudantes em n_clusters grupos, com uma
    # semente aleatória fixa (reprodutibilidade) e 10 tentativas (n_init)
    # para escolher o melhor resultado.
    kmeans = KMeans(n_clusters=n_clusters, random_state=config.RANDOM_STATE, n_init=10)
    labels = kmeans.fit_predict(X_scaled)

    df = df.copy()
    # Adiciona a coluna com o grupo atribuído a cada estudante.
    df["_cluster"] = labels

    # médias padronizadas (z-score) de cada variável, por grupo, face à média geral
    z_df = pd.DataFrame(X_scaled, columns=features, index=df.index)
    z_df["_cluster"] = labels

    # Constrói a descrição de cada grupo, um a um.
    groups = []
    for cluster_id in sorted(df["_cluster"].unique()):
        subset = df[df["_cluster"] == cluster_id]
        # Média (já normalizada) de cada variável, só para os estudantes deste grupo.
        z_means = z_df[z_df["_cluster"] == cluster_id][features].mean()

        # Códigos dos traços mais desviantes (independentes de idioma),
        # nome e rótulos já traduzidos para `lang`.
        codes = _trait_codes(z_means, features)
        name, traits = _name_cluster(z_means, features, lang)
        groups.append({
            "cluster_id": int(cluster_id),
            "name": name,
            "traits": traits,
            "suggestions": _suggest_micro_habits(codes, lang),
            "size": int(len(subset)),
            "size_pct": round(len(subset) / len(df) * 100, 1),
            "avg_grade": round(float(subset["G3"].mean()), 2),
            "risk_pct": round(float(subset["at_risk"].mean()) * 100, 1),
            "avg_studytime": round(float(subset["studytime"].mean()), 2),
            "avg_absences": round(float(subset["absences"].mean()), 1),
            # IDs dos estudantes deste grupo — permite ao frontend mostrar a
            # lista concreta de estudantes ao clicar num cartão de perfil,
            # em vez de ficar só com as médias agregadas.
            "student_ids": [int(v) for v in subset["student_id"].tolist()],
        })

    # Ordena os grupos pela nota média, do melhor para o pior desempenho.
    groups.sort(key=lambda g: g["avg_grade"], reverse=True)
    return {
        "n_clusters": n_clusters,
        "n_students": int(len(df)),
        "features": features,
        "groups": groups,
    }
