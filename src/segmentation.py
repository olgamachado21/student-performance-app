"""
Segmentação de Perfis: agrupa estudantes em "perfis" comportamentais
semelhantes usando K-Means, com nomeação automática de cada grupo a partir
dos traços mais desviantes da média geral (não são nomes fixos/inventados,
são calculados a partir dos próprios dados).
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

# Variáveis usadas por omissão para calcular a semelhança entre estudantes.
SEGMENTATION_FEATURES = [
    "studytime", "absences", "failures", "G1", "G2", "G3",
    "famrel", "freetime", "goout", "Dalc", "Walc", "health", "traveltime",
]

# Para cada variável, o rótulo do traço quando está acima (alto) ou abaixo
# (baixo) da média geral — usado para nomear os grupos automaticamente.
TRAIT_LABELS = {
    "studytime": ("Dedicados ao Estudo", "Pouco Tempo de Estudo"),
    "absences": ("Muitas Faltas", "Assiduidade Elevada"),
    "failures": ("Histórico de Reprovações", "Sem Reprovações"),
    "G1": ("Bom Início de Ano", "Início de Ano Fraco"),
    "G2": ("Consistência a Meio do Ano", "Quebra a Meio do Ano"),
    "G3": ("Bom Desempenho Académico", "Desempenho Académico Fraco"),
    "famrel": ("Boa Relação Familiar", "Relação Familiar Distante"),
    "freetime": ("Muito Tempo Livre", "Pouco Tempo Livre"),
    "goout": ("Vida Social Ativa", "Pouco Convívio Social"),
    "Dalc": ("Consumo de Álcool em Dias Úteis", "Sem Consumo em Dias Úteis"),
    "Walc": ("Consumo de Álcool ao Fim de Semana", "Sem Consumo ao Fim de Semana"),
    "health": ("Boa Saúde", "Saúde Frágil"),
    "traveltime": ("Deslocação Longa até à Escola", "Escola Perto de Casa"),
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

# Uma sugestão concreta e acionável para cada traço possível (chave = o
# mesmo texto produzido por TRAIT_LABELS) — não é um conselho genérico
# tipo "estuda mais", é ligado diretamente ao traço mais desviante desse
# grupo em concreto.
MICRO_HABIT_SUGGESTIONS = {
    "Dedicados ao Estudo": "Mantém uma rotina fixa (mesmo horário e local) para não perderes o ritmo que já tens.",
    "Pouco Tempo de Estudo": "Começa por blocos curtos e fixos (15-20 min) todos os dias — mais fácil manter do que sessões longas irregulares.",
    "Muitas Faltas": "Identifica a causa mais comum das faltas (transporte, horário, motivação) e resolve-a primeiro.",
    "Assiduidade Elevada": "A tua assiduidade é um ponto forte — protege-a, sobretudo nas semanas antes de avaliações.",
    "Histórico de Reprovações": "Prioriza apoio extra (explicações, tutoria) nas disciplinas onde já reprovaste antes.",
    "Sem Reprovações": "Consolida o que já funciona: revê os teus métodos de estudo para os repetires noutras disciplinas.",
    "Bom Início de Ano": "Mantém o mesmo método que resultou no 1º período — não o abandones a meio do ano.",
    "Início de Ano Fraco": "Recupera terreno cedo: rever a matéria da semana no próprio fim de semana evita acumular dívidas.",
    "Consistência a Meio do Ano": "Continua a rever regularmente — a consistência entre períodos vale mais do que picos isolados.",
    "Quebra a Meio do Ano": "Revê o que mudou entre o 1º e o 2º período (rotina, disciplinas, hábitos) para perceberes a causa da quebra.",
    "Bom Desempenho Académico": "Regista o que tens feito bem — é mais fácil repetir uma rotina identificada do que adivinhar de novo.",
    "Desempenho Académico Fraco": "Foca-te primeiro numa ou duas disciplinas, em vez de tentar melhorar tudo ao mesmo tempo.",
    "Boa Relação Familiar": "Aproveita o apoio em casa: pede para reverem a matéria contigo ou ajudarem a fixar um horário de estudo.",
    "Relação Familiar Distante": "Procura um espaço de estudo tranquilo fora de casa (biblioteca, sala de estudo) se o ambiente não ajudar.",
    "Muito Tempo Livre": "Usa uma pequena parte do tempo livre para revisão espaçada — sessões curtas e frequentes.",
    "Pouco Tempo Livre": "Protege pelo menos um bloco fixo de descanso por semana — também afeta o desempenho.",
    "Vida Social Ativa": "Define um limite de saídas nas semanas antes de testes ou exames.",
    "Pouco Convívio Social": "Algum convívio social ajuda a gerir o stress — não precisa de ser eliminado por completo.",
    "Consumo de Álcool em Dias Úteis": "Reduzir o consumo em dias de semana está associado, nos dados analisados, a mais tempo de estudo efetivo.",
    "Sem Consumo em Dias Úteis": "Sem consumo relevante em dias úteis — não é um fator a trabalhar aqui.",
    "Consumo de Álcool ao Fim de Semana": "Vale a pena vigiar se o fim de semana está a comprometer o início da semana de estudo.",
    "Sem Consumo ao Fim de Semana": "Sem consumo relevante ao fim de semana — não é um fator a trabalhar aqui.",
    "Boa Saúde": "Mantém a rotina de sono e alimentação que já tens — sustenta a energia para estudar.",
    "Saúde Frágil": "Cuidar do sono e da alimentação tende a refletir-se na energia disponível para estudar.",
    "Deslocação Longa até à Escola": "Aproveita o tempo de deslocação para rever resumos ou ouvir gravações das aulas.",
    "Escola Perto de Casa": "Usa o tempo poupado na deslocação para uma rotina de estudo mais regular.",
}


# Variáveis mostradas no gráfico radar do Perfil do Estudante — um
# subconjunto de hábitos/estilo de vida (sem notas, que já têm o seu próprio
# gráfico de evolução G1->G2->G3 nessa página).
RADAR_FEATURES = ["studytime", "absences", "failures", "famrel", "freetime", "goout", "health"]
# Nomes amigáveis de cada variável do radar, mostrados na legenda do gráfico.
RADAR_LABELS = {
    "studytime": "Tempo de estudo",
    "absences": "Faltas",
    "failures": "Reprovações",
    "famrel": "Relação familiar",
    "freetime": "Tempo livre",
    "goout": "Sair com amigos",
    "health": "Saúde",
}


def radar_profile(df: pd.DataFrame, subgroup_mask: pd.Series) -> dict:
    """
    Médias de RADAR_FEATURES normalizadas (min-max, escala 0-100) para o
    subgrupo filtrado (Perfil do Estudante) vs a turma toda — pronto para um
    gráfico radar/spider no frontend. A normalização usa sempre os limites
    do dataset COMPLETO (não do subgrupo), para os eixos terem sempre a
    mesma escala, independentemente do filtro ativo.
    """
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
        "labels": [RADAR_LABELS[f] for f in RADAR_FEATURES],
        "subgroup_values": subgroup_values,
        "overall_values": overall_values,
        "n_subgroup": int(len(subgroup)),
    }


def _name_cluster(z_means: pd.Series, features: list[str]) -> tuple[str, list[str]]:
    """Escolhe os traços mais desviantes da média para nomear o grupo."""
    # Ordena as variáveis pelo valor absoluto do desvio (mais desviante primeiro).
    deviations = z_means.reindex(features).abs().sort_values(ascending=False)
    # Só considera os traços que ultrapassam o limiar mínimo, até ao máximo definido.
    salient = [f for f in deviations.index if deviations[f] >= Z_SCORE_THRESHOLD][:MAX_TRAITS_PER_GROUP]

    traits = []
    for feature in salient:
        high_label, low_label = TRAIT_LABELS[feature]
        # Escolhe o rótulo "alto" ou "baixo" consoante o sinal do desvio deste grupo.
        traits.append(high_label if z_means[feature] > 0 else low_label)

    if not traits:
        # Nenhum traço se destacou o suficiente — o grupo é "normal" em tudo.
        traits = ["Perfil Misto (sem traços muito acima da média geral)"]

    # Nome do grupo: combina os dois traços mais fortes, ou só um se for o único.
    name = " & ".join(traits[:2]) if len(traits) >= 2 else traits[0]
    return name, traits


def _suggest_micro_habits(traits: list[str]) -> list[str]:
    """Traduz os traços mais desviantes do grupo em sugestões concretas,
    uma por traço, até MAX_SUGGESTIONS_PER_GROUP — usa sempre os PRIMEIROS
    traços da lista, que já vêm ordenados por desvio (o mais característico
    do grupo primeiro)."""
    suggestions = []
    for trait in traits[:MAX_SUGGESTIONS_PER_GROUP]:
        suggestion = MICRO_HABIT_SUGGESTIONS.get(trait)
        if suggestion:
            suggestions.append(suggestion)
    return suggestions


def run_segmentation(df: pd.DataFrame, n_clusters: int = 4, features: list[str] | None = None) -> dict:
    """Agrupa os estudantes em `n_clusters` perfis, usando as variáveis indicadas (ou as por omissão)."""
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

        # Nome automático do grupo e os traços que o caracterizam.
        name, traits = _name_cluster(z_means, features)
        groups.append({
            "cluster_id": int(cluster_id),
            "name": name,
            "traits": traits,
            "suggestions": _suggest_micro_habits(traits),
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
