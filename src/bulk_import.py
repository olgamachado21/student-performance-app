"""
Importação em lote de estudantes a partir de um ficheiro CSV — em vez de
adicionar um estudante de cada vez no formulário, permite carregar vários de
uma só vez. Reaproveita a mesma lógica de valores por omissão e previsão de
nota final do formulário normal (ver add_student.py), mas valida todas as
linhas primeiro e escreve tudo na base de dados de uma só vez, em vez de um
pedido por estudante.
"""
from __future__ import annotations

# io: permite tratar o texto do CSV como se fosse um ficheiro, para o pandas o ler.
import io

# pandas: para ler o CSV e trabalhar com os dados como tabela.
import pandas as pd

from src import database
# Reaproveita constantes e listas já definidas no formulário normal, para
# nunca haver duas definições diferentes do mesmo esquema de colunas.
from src.add_student import ADDED_STUDENTS_TABLE, ALL_COLUMNS, EXTRA_COLUMNS, FORM_FIELDS, RAW_COLUMNS
from src.data_processing import load_added_students
from src.predict import get_defaults, predict_grade

# Intervalos válidos para os campos numéricos — os mesmos limites aplicados
# no formulário normal (ver NewStudentInput em src/api.py).
NUMERIC_BOUNDS = {
    "age": (15, 22),
    "studytime": (1, 4),
    "absences": (0, 93),
    "failures": (0, 4),
    "G1": (0, 20),
    "G2": (0, 20),
}


def parse_csv(file_bytes: bytes) -> pd.DataFrame:
    """
    Lê o CSV (deteta automaticamente se o separador é ',' ou ';', para lidar
    bem com ficheiros exportados do Excel em português) e devolve um
    DataFrame cru, tal como veio do ficheiro — sem validação de conteúdo.
    """
    try:
        # Descodifica os bytes do ficheiro como texto UTF-8 (o "-sig" remove
        # o BOM que o Excel costuma adicionar no início do ficheiro).
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        # Ficheiro não é texto válido (ex.: enviaram um .xlsx em vez de .csv).
        raise ValueError(f"Não foi possível ler o ficheiro como texto (UTF-8): {exc}") from exc
    try:
        # sep=None + engine="python": deteta automaticamente o separador
        # (vírgula ou ponto-e-vírgula), útil porque o Excel em português
        # exporta CSV com ";" em vez de ",".
        df = pd.read_csv(io.StringIO(text), sep=None, engine="python")
    except Exception as exc:
        raise ValueError(f"Não foi possível interpretar o ficheiro como CSV: {exc}") from exc
    # Remove espaços a mais à volta dos nomes das colunas (erros comuns ao exportar do Excel).
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _coerce_row(raw_row: dict) -> tuple[dict, list[str]]:
    """Converte e valida uma linha crua do CSV. Devolve (campos válidos, lista de erros)."""
    # Lista de mensagens de erro encontradas nesta linha (fica vazia se tudo estiver bem).
    errors: list[str] = []
    # Campos já convertidos e validados desta linha.
    fields: dict = {}

    for col in FORM_FIELDS:
        # Salta colunas que não existem no CSV ou que estão vazias/em falta.
        if col not in raw_row or pd.isna(raw_row[col]) or str(raw_row[col]).strip() == "":
            continue
        raw_value = raw_row[col]

        if col in NUMERIC_BOUNDS:
            # Campo numérico: tenta converter para número inteiro.
            try:
                value = int(float(raw_value))
            except (TypeError, ValueError):
                errors.append(f"'{col}' devia ser um número, veio '{raw_value}'")
                continue
            # Verifica se o valor está dentro do intervalo permitido para este campo.
            low, high = NUMERIC_BOUNDS[col]
            if not (low <= value <= high):
                errors.append(f"'{col}' fora do intervalo esperado ({low}-{high}): {value}")
                continue
        elif col == "school":
            # Escola: só aceita "GP" ou "MS" (maiúsculas, tal como no dataset original).
            value = str(raw_value).strip().upper()
            if value not in ("GP", "MS"):
                errors.append(f"'school' devia ser 'GP' ou 'MS', veio '{raw_value}'")
                continue
        elif col == "sex":
            # Sexo: só aceita "F" ou "M".
            value = str(raw_value).strip().upper()
            if value not in ("F", "M"):
                errors.append(f"'sex' devia ser 'F' ou 'M', veio '{raw_value}'")
                continue
        else:
            # Qualquer outro campo: usa o valor tal como veio, sem conversão.
            value = raw_value

        fields[col] = value

    # Campos extra (nome, disciplina, ano) não são validados, só limpos de espaços.
    for col in EXTRA_COLUMNS:
        if col in raw_row and not pd.isna(raw_row[col]):
            fields[col] = str(raw_row[col]).strip()

    return fields, errors


def add_students_bulk(file_bytes: bytes) -> dict:
    """
    Lê um CSV com uma linha por estudante (colunas iguais às do formulário
    "Adicionar Dados": school, sex, age, studytime, absences, failures, G1,
    G2, nome, disciplina, ano — todas opcionais, tal como no formulário),
    valida cada linha e adiciona ao dataset as que forem válidas. Linhas
    inválidas são reportadas (com o nº da linha e o motivo) mas não impedem
    as restantes de serem adicionadas.
    """
    # Lê o CSV para um DataFrame cru (sem validação ainda) — sem limite de
    # linhas: o ficheiro é sempre processado por inteiro, seja qual for o
    # seu tamanho.
    raw_df = parse_csv(file_bytes)

    # Valores típicos do dataset, para preencher campos não indicados em cada linha.
    defaults = get_defaults()
    # Linhas que passaram na validação e vão ser adicionadas ao dataset.
    added_rows = []
    # Linhas com erros, reportadas ao utilizador mas não adicionadas.
    row_errors = []

    # Percorre cada linha do CSV, uma a uma.
    for i, raw_row in enumerate(raw_df.to_dict(orient="records")):
        # Número da linha no ficheiro original, como o utilizador o vê no Excel:
        # +1 porque "i" começa em 0, +1 porque a linha 1 é o cabeçalho.
        line_no = i + 2
        # Converte e valida os campos desta linha.
        fields, errors = _coerce_row(raw_row)
        if errors:
            # Linha inválida: regista o erro e passa à seguinte, sem adicionar.
            row_errors.append({"line": line_no, "errors": errors})
            continue

        # Constrói o registo completo do estudante, tal como no formulário normal:
        # usa o valor do CSV se existir, senão o valor típico do dataset.
        row = {col: fields.get(col, defaults.get(col)) for col in RAW_COLUMNS if col != "G3"}
        # Prevê a nota final (G3) com o modelo de Machine Learning, tal como no formulário normal.
        prediction = predict_grade(row, use_previous_grades=True)
        predicted_grade = round(prediction["predicted_grade"])
        # Garante que a nota fica sempre entre 0 e 20.
        row["G3"] = int(max(0, min(20, predicted_grade)))
        # Preenche os campos extra (nome, disciplina, ano), vazios se não indicados.
        for col in EXTRA_COLUMNS:
            row[col] = str(fields.get(col) or "").strip()
        added_rows.append(row)

    if added_rows:
        # Há pelo menos uma linha válida: junta-as todas ao que já existia
        # na base de dados, e grava tudo de uma só vez.
        new_df = pd.DataFrame(added_rows)[ALL_COLUMNS]
        existing = load_added_students()
        if existing.empty:
            combined = new_df
        else:
            # Garante que os estudantes já existentes têm as mesmas colunas
            # (preenche com "" se faltar alguma), antes de juntar com os novos.
            existing = existing.reindex(columns=ALL_COLUMNS, fill_value="")
            combined = pd.concat([existing[ALL_COLUMNS], new_df], ignore_index=True)
        database.write_table(combined, ADDED_STUDENTS_TABLE, if_exists="replace")
        total_added_so_far = int(len(combined))
    else:
        # Nenhuma linha foi válida — o total mantém-se igual ao que já existia.
        total_added_so_far = int(len(load_added_students()))

    # Resumo final: quantos foram adicionados, quantos falharam, e os detalhes dos erros.
    return {
        "added_count": len(added_rows),
        "error_count": len(row_errors),
        "errors": row_errors,
        "total_added_so_far": total_added_so_far,
    }
