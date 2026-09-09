"""
Sugestão de valores prováveis para o formulário "Adicionar Dados".

Hoje, um campo deixado em branco é preenchido com a mediana/moda de TODO o
dataset (ver predict.get_defaults()) — um valor "médio" razoável, mas o
mesmo para toda a gente, independentemente do que o utilizador já escreveu
nos outros campos. Este módulo faz uma estimativa mais informada: procura,
no dataset já processado, os estudantes mais parecidos com o que já foi
indicado no formulário (mesma escola/sexo, tempo de estudo semelhante, etc.)
e sugere os valores típicos DESSE grupo mais restrito para os campos ainda
por preencher — texto preditivo com base em casos reais semelhantes, não
uma média genérica.
"""
from __future__ import annotations

# numpy: cálculos numéricos (distâncias, comparações vetorizadas).
import numpy as np
# pandas: para trabalhar com o dataset como tabela (DataFrame).
import pandas as pd

# Lista oficial dos campos do formulário "Adicionar Dados".
from src.add_student import FORM_FIELDS

# Campos numéricos do formulário, usados no cálculo de distância euclidiana.
NUMERIC_FORM_FIELDS = ["age", "studytime", "absences", "failures", "G1", "G2"]
# Campos categóricos do formulário (texto/categorias), tratados de forma diferente na distância.
CATEGORICAL_FORM_FIELDS = ["school", "sex"]

# Nº de estudantes mais semelhantes a considerar para calcular a sugestão.
# Pequeno o suficiente para a sugestão ser moldada pelo perfil indicado,
# grande o suficiente para não deixar 1 ou 2 estudantes atípicos dominarem.
K_NEIGHBORS = 15

# Quantos desses estudantes semelhantes mostrar ao utilizador quando pede
# para ver em que casos a sugestão se baseou (transparência do algoritmo,
# não é preciso mostrar os 15 todos — os mais próximos já ilustram o padrão).
N_SIMILAR_TO_SHOW = 6

# Penalização (em desvios-padrão equivalentes) por não coincidir num campo
# categórico ao calcular a distância entre estudantes. Alta o suficiente
# para preferir sempre estudantes da mesma escola/sexo quando existem,
# sem ser absoluta: se quase ninguém coincidir, ainda aparecem os
# estudantes mais próximos nos restantes campos.
CATEGORICAL_MISMATCH_PENALTY = 2.5


def suggest_field_values(df: pd.DataFrame, known_fields: dict) -> dict:
    """
    `known_fields` é um subconjunto (pode ser vazio) dos campos do
    formulário já preenchidos pelo utilizador — ver add_student.FORM_FIELDS.
    Valores None ou fora desse conjunto são ignorados.

    Devolve um dicionário com:
      - "suggestions": valores sugeridos para os campos do formulário AINDA
        não preenchidos (dict, pode estar vazio se já estiver tudo preenchido);
      - "n_similar": quantos estudantes do dataset foram usados para calcular
        a sugestão (todo o dataset, se nenhum campo tiver sido indicado ainda);
      - "based_on": em que campos já preenchidos a semelhança foi calculada.
    """
    # Mantém só os campos válidos do formulário que realmente têm valor
    # (ignora None, string vazia, ou campos que não pertencem ao formulário).
    known_fields = {
        k: v for k, v in known_fields.items() if k in FORM_FIELDS and v is not None and v != ""
    }

    # Campos do formulário que ainda faltam preencher — são os únicos para
    # os quais faz sentido gerar sugestões.
    remaining = [f for f in FORM_FIELDS if f not in known_fields]
    if not remaining:
        # Já está tudo preenchido — não há nada a sugerir.
        return {"suggestions": {}, "n_similar": 0, "based_on": list(known_fields.keys()), "similar_students": []}

    # Só faz sentido procurar "vizinhos" (k-NN) se já houver pelo menos um
    # campo preenchido para basear a semelhança.
    is_knn = bool(known_fields)
    if not is_knn:
        # Sem nenhum campo preenchido ainda não há por onde procurar
        # semelhança — a sugestão cai de volta ao valor típico de todo o
        # dataset (o mesmo comportamento que já existia antes desta função).
        neighbors = df
        ordered_neighbors = df
    else:
        # Separa os campos já preenchidos em numéricos e categóricos, para
        # calcular a distância de forma diferente em cada caso.
        numeric_known = {k: v for k, v in known_fields.items() if k in NUMERIC_FORM_FIELDS}
        categorical_known = {k: v for k, v in known_fields.items() if k in CATEGORICAL_FORM_FIELDS}

        # Começa com distância zero para todos os estudantes, e vai somando
        # a contribuição de cada campo conhecido.
        distance = pd.Series(0.0, index=df.index)
        for col, value in numeric_known.items():
            # Desvio-padrão da coluna, usado para normalizar a diferença
            # (senão colunas com escalas maiores, como "absences", dominariam a distância).
            std = df[col].std()
            if not std or np.isnan(std):
                continue
            # Distância euclidiana normalizada: soma o quadrado da diferença
            # normalizada de cada campo numérico.
            distance = distance + ((df[col] - value) / std) ** 2
        for col, value in categorical_known.items():
            # Para campos categóricos: penalização fixa se o valor for
            # diferente, zero se for igual.
            mismatch = np.where(df[col] == value, 0.0, CATEGORICAL_MISMATCH_PENALTY)
            distance = distance + mismatch ** 2

        # Nº de vizinhos a usar (não pode ser maior que o total de estudantes disponíveis).
        k = min(K_NEIGHBORS, len(df))
        # Índices dos k estudantes com menor distância (mais parecidos).
        nearest_idx = distance.nsmallest(k).index
        neighbors = df.loc[nearest_idx]
        # Ordenados do mais para o menos parecido, para quando o utilizador
        # pedir para ver "em que casos a sugestão se baseou".
        ordered_neighbors = df.loc[distance.loc[nearest_idx].sort_values().index]

    # Para cada campo ainda por preencher, calcula a sugestão a partir do
    # grupo de estudantes semelhantes (ou de todo o dataset, se is_knn for False).
    suggestions: dict = {}
    for field in remaining:
        if field in CATEGORICAL_FORM_FIELDS:
            # Campo categórico: sugere o valor mais frequente (moda) no grupo.
            mode = neighbors[field].mode()
            if not mode.empty:
                suggestions[field] = mode.iloc[0]
        else:
            # Campo numérico: sugere a mediana do grupo, arredondada a inteiro.
            median = neighbors[field].median()
            if pd.notna(median):
                suggestions[field] = int(round(median))

    # Lista de exemplos concretos de estudantes semelhantes, para mostrar ao
    # utilizador em que casos reais a sugestão se baseou.
    similar_students = []
    if is_knn:
        # Só mostra as colunas do formulário que existem no dataset.
        preview_cols = [c for c in FORM_FIELDS if c in ordered_neighbors.columns]
        # Mostra só os N_SIMILAR_TO_SHOW mais próximos (já estão ordenados).
        for _, row in ordered_neighbors.head(N_SIMILAR_TO_SHOW).iterrows():
            student = {}
            for col in preview_cols:
                value = row[col]
                # Converte campos numéricos para int (evita mostrar "17.0" em vez de "17").
                student[col] = int(value) if col in NUMERIC_FORM_FIELDS else value
            similar_students.append(student)

    return {
        "suggestions": suggestions,
        "n_similar": int(len(neighbors)),
        "based_on": list(known_fields.keys()),
        "similar_students": similar_students,
    }
