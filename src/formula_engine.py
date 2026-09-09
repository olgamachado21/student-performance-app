"""
Motor de fórmulas personalizadas: permite ao utilizador escrever a sua
própria expressão (ex.: "G1*0.3 + G2*0.3 + G3*0.4" ou "media(G3) onde
studytime >= 3") sobre o Dataset Personalizado, e devolve ou uma coluna nova
(um valor por linha) ou um resultado único, consoante a fórmula.

Nunca se usa eval()/exec() sobre o texto do utilizador — a fórmula é primeiro
interpretada como uma árvore de sintaxe (ast.parse), e só depois percorrida
nó a nó por _eval(), que só sabe lidar com uma lista fechada de construções
(números, nomes de colunas, operadores aritméticos/comparação, e um punhado
de funções conhecidas). Qualquer outra coisa — acesso a atributos, chamadas a
funções desconhecidas, lambdas, importações, etc. — é sempre rejeitada antes
de qualquer cálculo acontecer. Isto é o que torna seguro aceitar texto livre
de um utilizador sem correr o risco de executar código arbitrário.
"""
from __future__ import annotations

import ast
import operator
import re
import unicodedata

import numpy as np
import pandas as pd


class FormulaError(ValueError):
    """Erro de fórmula (sintaxe inválida, coluna/função desconhecida, etc.) — sempre com mensagem em português, pronta a mostrar ao utilizador."""


# --- Limites de segurança/desempenho ----------------------------------------
# Sem estes limites, uma fórmula maliciosa ou só mal escrita (ex.: um
# expoente gigante) poderia consumir memória/CPU a mais para uma app local.
MAX_EXPR_LEN = 300
MAX_NODES = 120
MAX_EXPONENT = 12

# --- Operadores permitidos ---------------------------------------------------
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
    ast.Pow: operator.pow,
}
_CMP_OPS = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}

# Funções agregadas: reduzem uma coluna inteira a um único número (ignorando
# nulos). "contar" tem tratamento especial porque também aceita zero
# argumentos (nº de linhas do dataset, ou do subconjunto filtrado por "onde").
_AGG_FUNCS = {
    "soma": "sum",
    "media": "mean",
    "mediana": "median",
    "minimo": "min",
    "maximo": "max",
    "desvio": "std",
}
FUNCTION_NAMES = sorted(list(_AGG_FUNCS) + ["contar", "absoluto", "arredondar", "se"])


def normalize_text(text: str) -> str:
    """Remove acentos e baixa para minúsculas — usado para comparar nomes de
    colunas e de funções de forma tolerante (ex.: "Média"/"media"/"MEDIA" e
    "Nota Final" só correspondem se o utilizador escrever o nome técnico da
    coluna; os acentos das FUNÇÕES é que são sempre tolerados)."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text.strip().lower()


def _call_absoluto(x):
    return x.abs() if isinstance(x, pd.Series) else abs(x)


def _call_arredondar(x, casas=0):
    try:
        casas = int(casas)
    except (TypeError, ValueError):
        raise FormulaError("O segundo argumento de 'arredondar' tem de ser um número inteiro de casas decimais.")
    if isinstance(x, pd.Series):
        return x.round(casas)
    return round(float(x), casas)


def _call_se(cond, a, b):
    """Equivalente ao SE()/IF() do Excel: se(condição, valor_se_verdadeiro, valor_se_falso)."""
    if isinstance(cond, pd.Series):
        return pd.Series(np.where(cond, a, b), index=cond.index)
    return a if cond else b


def _split_filter(expr: str) -> tuple[str, str | None]:
    """Separa a fórmula principal de uma cláusula de filtro opcional
    introduzida por "onde"/"where" (ex.: "media(G3) onde studytime >= 3" ->
    ("media(G3)", "studytime >= 3"))."""
    m = re.search(r"\b(onde|where)\b", expr, flags=re.IGNORECASE)
    if not m:
        return expr.strip(), None
    main = expr[: m.start()].strip()
    filt = expr[m.end():].strip()
    if not main:
        raise FormulaError("Falta a expressão principal antes de 'onde'.")
    if not filt:
        raise FormulaError("Falta a condição depois de 'onde'.")
    return main, filt


def _normalize_equals(expr: str) -> str:
    """Troca um "=" isolado (não colado a <, >, =, !) por "==", para aceitar
    uma sintaxe mais parecida com o Excel (ex.: "sexo = 'F'")."""
    return re.sub(r"(?<![<>=!])=(?!=)", "==", expr)


def _parse(expr: str) -> ast.AST:
    if len(expr) > MAX_EXPR_LEN:
        raise FormulaError(f"Fórmula demasiado longa (máximo {MAX_EXPR_LEN} caracteres).")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise FormulaError(f"Fórmula com erro de sintaxe: {exc.msg}") from exc
    if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
        raise FormulaError("Fórmula demasiado complexa — tenta simplificá-la.")
    return tree


def _eval(node: ast.AST, df: pd.DataFrame, columns_lookup: dict):
    """Avalia recursivamente um nó da árvore de sintaxe. Devolve uma
    pd.Series (quando o resultado é "uma coisa por linha") ou um valor
    escalar (número/booleano/texto) — o autor da fórmula não precisa de
    distinguir os dois casos: os operadores fazem a coisa certa em ambos,
    graças ao próprio pandas (Series + número = Series; número + número =
    número)."""
    if isinstance(node, ast.Expression):
        return _eval(node.body, df, columns_lookup)

    if isinstance(node, ast.Constant):
        if node.value is None or isinstance(node.value, (int, float, bool, str)):
            return node.value
        raise FormulaError("Tipo de valor não suportado na fórmula.")

    if isinstance(node, ast.Name):
        key = normalize_text(node.id)
        if key in columns_lookup:
            return df[columns_lookup[key]]
        disponiveis = ", ".join(sorted(columns_lookup.values()))
        raise FormulaError(f"Coluna desconhecida: '{node.id}'. Colunas disponíveis: {disponiveis}.")

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _BIN_OPS:
            raise FormulaError("Operador aritmético não suportado na fórmula.")
        left = _eval(node.left, df, columns_lookup)
        right = _eval(node.right, df, columns_lookup)
        if op_type is ast.Pow and not isinstance(right, pd.Series) and right is not None:
            # A conversão para float pode falhar sem ser por causa da
            # grandeza do expoente (ex.: texto) — só essa exceção é
            # apanhada aqui; o FormulaError do expoente grande tem de
            # propagar-se sempre (nunca é capturado pelo "except" abaixo,
            # já que FormulaError também é um ValueError).
            try:
                exp_magnitude = abs(float(right))
            except (TypeError, ValueError):
                exp_magnitude = None
            if exp_magnitude is not None and exp_magnitude > MAX_EXPONENT:
                raise FormulaError(f"Expoente demasiado grande (máximo {MAX_EXPONENT}).")
        try:
            return _BIN_OPS[op_type](left, right)
        except ZeroDivisionError:
            raise FormulaError("Divisão por zero na fórmula.")
        except FormulaError:
            raise
        except Exception as exc:
            raise FormulaError(f"Não foi possível calcular a fórmula: {exc}") from exc

    if isinstance(node, ast.UnaryOp):
        operand = _eval(node.operand, df, columns_lookup)
        if isinstance(node.op, ast.USub):
            return -operand
        if isinstance(node.op, ast.UAdd):
            return +operand
        if isinstance(node.op, ast.Not):
            return (~operand) if isinstance(operand, pd.Series) else (not operand)
        raise FormulaError("Operador unário não suportado na fórmula.")

    if isinstance(node, ast.BoolOp):
        values = [_eval(v, df, columns_lookup) for v in node.values]
        is_series = any(isinstance(v, pd.Series) for v in values)
        result = values[0]
        for v in values[1:]:
            if isinstance(node.op, ast.And):
                result = (result & v) if is_series else (result and v)
            else:
                result = (result | v) if is_series else (result or v)
        return result

    if isinstance(node, ast.Compare):
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise FormulaError("Só é suportada uma comparação de cada vez (ex.: 'idade > 15').")
        op_type = type(node.ops[0])
        if op_type not in _CMP_OPS:
            raise FormulaError("Comparador não suportado (usa ==, !=, <, <=, > ou >=).")
        left = _eval(node.left, df, columns_lookup)
        right = _eval(node.comparators[0], df, columns_lookup)
        return _CMP_OPS[op_type](left, right)

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise FormulaError("Só são permitidas chamadas a funções conhecidas (ex.: media(G3)).")
        if node.keywords:
            raise FormulaError("Argumentos com nome (ex.: 'casas=2') não são suportados — usa apenas a ordem.")
        fname = normalize_text(node.func.id)
        args = [_eval(a, df, columns_lookup) for a in node.args]

        if fname == "contar":
            if len(args) == 0:
                return int(len(df))
            if len(args) == 1 and isinstance(args[0], pd.Series):
                return int(args[0].dropna().count())
            raise FormulaError("A função 'contar' espera 0 ou 1 argumento (uma coluna).")

        if fname in _AGG_FUNCS:
            if len(args) != 1:
                raise FormulaError(f"A função '{node.func.id}' espera exatamente 1 argumento (uma coluna) — ex.: {node.func.id}(G3).")
            series = args[0]
            if not isinstance(series, pd.Series):
                raise FormulaError(f"A função '{node.func.id}' só pode ser usada sobre uma coluna, não sobre um número.")
            clean = series.dropna()
            if clean.empty:
                return None
            value = getattr(clean, _AGG_FUNCS[fname])()
            return None if pd.isna(value) else float(value)

        if fname == "absoluto":
            if len(args) != 1:
                raise FormulaError("A função 'absoluto' espera exatamente 1 argumento.")
            return _call_absoluto(args[0])

        if fname == "arredondar":
            if len(args) not in (1, 2):
                raise FormulaError("A função 'arredondar' espera 1 ou 2 argumentos: arredondar(valor) ou arredondar(valor, casas).")
            return _call_arredondar(args[0], args[1] if len(args) == 2 else 0)

        if fname == "se":
            if len(args) != 3:
                raise FormulaError("A função 'se' espera 3 argumentos: se(condição, valor_se_verdadeiro, valor_se_falso).")
            return _call_se(*args)

        raise FormulaError(f"Função desconhecida: '{node.func.id}'. Funções disponíveis: {', '.join(FUNCTION_NAMES)}.")

    raise FormulaError("A fórmula contém uma construção não suportada (só são permitidos números, colunas, operadores e as funções da lista de ajuda).")


def _clean_value(v):
    """Converte um valor (possivelmente de tipo numpy/pandas) num valor
    nativo do Python, seguro para serializar em JSON (None em vez de NaN)."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, np.floating):
        return round(float(v), 4)
    if isinstance(v, np.integer):
        return int(v)
    if isinstance(v, float):
        return round(v, 4)
    return v


def evaluate(df: pd.DataFrame, formula: str, page: int = 1, page_size: int = 20) -> dict:
    """
    Ponto de entrada principal: avalia "formula" sobre "df" e devolve um
    dicionário pronto a serializar como JSON. Duas formas possíveis:
      - {"type": "column", ...}: a fórmula produziu um valor por linha
        (ex.: "G1*0.3 + G2*0.3 + G3*0.4") — paginado, tal como as Previsões.
      - {"type": "scalar", ...}: a fórmula reduziu-se a um único resultado
        (ex.: "media(G3) onde studytime >= 3").
    """
    if not formula or not formula.strip():
        raise FormulaError("Escreve uma fórmula antes de calcular.")
    if page_size < 1:
        page_size = 20

    main_raw, filter_raw = _split_filter(formula.strip())

    columns_lookup = {normalize_text(c): c for c in df.columns}
    work_df = df
    if filter_raw:
        filter_tree = _parse(_normalize_equals(filter_raw))
        mask = _eval(filter_tree, df, columns_lookup)
        if not isinstance(mask, pd.Series) or not pd.api.types.is_bool_dtype(mask):
            raise FormulaError("A condição depois de 'onde' tem de ser uma comparação sobre uma coluna (ex.: 'idade > 15' ou 'sexo == \"F\"').")
        work_df = df[mask]
        if work_df.empty:
            raise FormulaError("Nenhuma linha do dataset corresponde à condição indicada depois de 'onde'.")

    work_lookup = {normalize_text(c): c for c in work_df.columns}
    main_tree = _parse(_normalize_equals(main_raw))
    result = _eval(main_tree, work_df, work_lookup)

    if isinstance(result, pd.Series):
        id_col = (
            work_df["row_id"] if "row_id" in work_df.columns
            else pd.Series(range(1, len(work_df) + 1), index=work_df.index)
        )
        rows_df = pd.DataFrame({"row_id": id_col, "resultado": result}).reset_index(drop=True)

        total = len(rows_df)
        total_pages = max(1, -(-total // page_size))
        page = min(max(page, 1), total_pages)
        start = (page - 1) * page_size
        page_rows = rows_df.iloc[start:start + page_size]

        numeric = pd.to_numeric(rows_df["resultado"], errors="coerce").dropna()
        summary = None
        if not numeric.empty:
            summary = {
                "mean": round(float(numeric.mean()), 4),
                "min": round(float(numeric.min()), 4),
                "max": round(float(numeric.max()), 4),
            }

        return {
            "type": "column",
            "n_rows": total,
            "n_rows_total_dataset": int(len(df)),
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "rows": [
                {"row_id": _clean_value(r.row_id), "resultado": _clean_value(r.resultado)}
                for r in page_rows.itertuples(index=False)
            ],
            "summary": summary,
        }

    return {
        "type": "scalar",
        "result": _clean_value(result),
        "n_rows_considered": int(len(work_df)),
        "n_rows_total_dataset": int(len(df)),
    }
