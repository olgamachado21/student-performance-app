"""
Adicionar Dados: permite adicionar um novo estudante ao dataset através de
um formulário simplificado. A nota final (G3) nunca é inserida manualmente —
é sempre prevista automaticamente pelo modelo de regressão já treinado
(variante "completo", que usa G1/G2 e os restantes hábitos).
"""
from __future__ import annotations

# pandas: para construir e combinar tabelas de dados (DataFrame).
import pandas as pd

from src import database
# Lê os estudantes já adicionados anteriormente (para os juntar ao novo).
from src.data_processing import load_added_students
# get_defaults: valores típicos do dataset, usados nos campos não preenchidos.
# predict_grade: usa o modelo de ML para calcular a nota G3 prevista.
from src.predict import get_defaults, predict_grade

# Nome da tabela na base de dados onde ficam guardados os estudantes
# adicionados manualmente (separada da tabela dos dados originais).
ADDED_STUDENTS_TABLE = "Students_Added"

# Esquema igual ao dos dados originais (Students_Raw), para que os
# estudantes adicionados se possam juntar de forma transparente ao dataset.
RAW_COLUMNS = [
    "school", "sex", "age", "address", "famsize", "Pstatus", "Medu", "Fedu",
    "Mjob", "Fjob", "reason", "guardian", "traveltime", "studytime", "failures",
    "schoolsup", "famsup", "paid", "activities", "nursery", "higher", "internet",
    "romantic", "famrel", "freetime", "goout", "Dalc", "Walc", "health",
    "absences", "G1", "G2", "G3",
]

# Campos que o formulário "Adicionar Dados" pede explicitamente ao utilizador
# (os restantes usam valores por omissão razoáveis, calculados a partir do dataset atual).
FORM_FIELDS = ["school", "sex", "age", "studytime", "absences", "failures", "G1", "G2"]

# Metadados de organização/identificação (nome do estudante, disciplina, ano
# escolar) — todos opcionais, guardados junto do registo mas NUNCA passados
# ao modelo de previsão: não fazem parte do dataset original (Students_Raw),
# por isso get_processed_data() ignora-os automaticamente ao juntar os
# estudantes adicionados ao resto do dataset (só junta colunas em comum).
EXTRA_COLUMNS = ["nome", "disciplina", "ano"]
# Lista completa de colunas guardadas na tabela Students_Added.
ALL_COLUMNS = RAW_COLUMNS + EXTRA_COLUMNS


def add_student(fields: dict) -> dict:
    """
    Adiciona um estudante ao dataset. `fields` deve conter pelo menos os
    campos de FORM_FIELDS; os restantes são preenchidos automaticamente.
    Devolve o registo adicionado (incluindo a nota G3 prevista).
    """
    # Valores típicos (médias/modas) do dataset atual, usados para preencher
    # qualquer campo que o utilizador não tenha indicado.
    defaults = get_defaults()
    # Constrói a linha do novo estudante: usa o valor recebido em `fields` se
    # existir, senão usa o valor por omissão — nunca inclui G3 aqui (é calculado a seguir).
    row = {col: fields.get(col, defaults.get(col)) for col in RAW_COLUMNS if col != "G3"}

    # Usa o modelo de Machine Learning para prever a nota final a partir dos
    # restantes campos (use_previous_grades=True porque G1/G2 estão preenchidos).
    prediction = predict_grade(row, use_previous_grades=True)
    # Arredonda a previsão (número inteiro, como as notas reais do dataset).
    predicted_grade = round(prediction["predicted_grade"])
    # Garante que a nota final fica sempre dentro do intervalo válido 0-20.
    row["G3"] = int(max(0, min(20, predicted_grade)))

    # Nome/disciplina/ano: guardados tal como escritos (só espaços a mais
    # removidos), nunca obrigatórios — ficam "" se não forem indicados.
    for col in EXTRA_COLUMNS:
        row[col] = str(fields.get(col) or "").strip()

    # Converte o dicionário numa tabela de uma só linha, com as colunas pela
    # ordem definida em ALL_COLUMNS.
    row_df = pd.DataFrame([row])[ALL_COLUMNS]

    # Vai buscar todos os estudantes adicionados anteriormente, para juntar o novo.
    existing = load_added_students()
    if existing.empty:
        # Ainda não havia nenhum estudante adicionado — este é o primeiro.
        combined = row_df
    else:
        # Registos adicionados antes de existirem estas colunas não as têm —
        # reindex preenche-as com "" em vez de a junção falhar.
        existing = existing.reindex(columns=ALL_COLUMNS, fill_value="")
        # Junta os estudantes já existentes com o novo, numa só tabela.
        combined = pd.concat([existing[ALL_COLUMNS], row_df], ignore_index=True)

    # Grava a tabela completa (antigos + novo) na base de dados, substituindo
    # a versão anterior da tabela Students_Added.
    database.write_table(combined, ADDED_STUDENTS_TABLE, if_exists="replace")

    # Devolve o registo adicionado, qual modelo foi usado na previsão, e o
    # total acumulado de estudantes adicionados até agora.
    return {
        "added_student": row,
        "model_used": prediction["model_used"],
        "total_added_so_far": int(len(combined)),
    }
