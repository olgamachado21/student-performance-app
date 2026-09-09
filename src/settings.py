"""
Configurações gerais da aplicação: tema de cores e fonte, guardados
como preferência única (linha) na base de dados, para se manterem entre
sessões independentemente de a app correr como página web ou janela nativa.
"""
from __future__ import annotations

# pandas: para guardar as configurações como uma tabela de uma só linha.
import pandas as pd

from src import database

# Nome da tabela na base de dados onde fica guardada a única linha de configurações.
SETTINGS_TABLE = "App_Settings"
# Colunas dessa tabela.
SETTINGS_COLUMNS = ["theme", "font", "alert_risk_threshold", "alert_min_absences"]

# Tema e fonte usados por omissão, antes de o utilizador escolher outros.
DEFAULT_THEME = "indigo"
DEFAULT_FONT = "Inter"

# Limiares por omissão dos avisos automáticos (ver src/alerts.py) — o
# utilizador pode personalizá-los em Configurações. alert_min_absences=None
# significa "cálculo automático" (média de faltas + 2 desvios-padrão sobre o
# dataset atual), em vez de um número fixo.
DEFAULT_ALERT_RISK_THRESHOLD = 0.30
DEFAULT_ALERT_MIN_ABSENCES = None

# Tipos de letra disponíveis para escolha em Configurações.
FONT_OPTIONS = ["Inter", "Georgia", "Roboto", "Courier New"]

# Cada tema define as variáveis CSS que substituem a paleta por omissão.
# "mode" indica se é um tema claro ou escuro (para o seletor agrupar os dois).
# "--surface-2" é o fundo de botões pequenos/campos de formulário/etiquetas
# que ficam "em cima" de um cartão (ex.: inputs, textareas, os botões da
# barra de ferramentas do Esquema Mental) — antes disto existir, esses
# elementos tinham um branco fixo no CSS, por isso no tema escuro ficavam
# com texto/ícones claros (var(--text-main)) sobre um fundo branco também
# fixo, impossível de ler. Cada tema escuro usa aqui um cinzento-escuro um
# pouco mais claro que "--card-bg", para se distinguir do cartão à volta.
#
# Todos os temas seguem a mesma estrutura: "name" (nome mostrado ao
# utilizador), "mode" ("claro" ou "escuro") e "colors" (as variáveis CSS
# reais: cor principal, fundo, texto, bordas, etc.).
THEMES = {
    "indigo": {
        "name": "Índigo (padrão)", "mode": "claro",
        "colors": {"--primary": "#4F46E5", "--primary-dark": "#4338CA", "--primary-light": "#EEF0FF",
                   "--bg": "#F7F8FA", "--card-bg": "#FFFFFF", "--surface-2": "#FBFBFD",
                   "--text-main": "#1E293B", "--text-muted": "#64748B", "--border": "#E7E9EE"},
    },
    "oceano": {
        "name": "Azul Oceano", "mode": "claro",
        "colors": {"--primary": "#0284C7", "--primary-dark": "#0369A1", "--primary-light": "#E0F2FE",
                   "--bg": "#F5F9FC", "--card-bg": "#FFFFFF", "--surface-2": "#FBFDFE",
                   "--text-main": "#0F172A", "--text-muted": "#64748B", "--border": "#E1EBF2"},
    },
    "floresta": {
        "name": "Verde Floresta", "mode": "claro",
        "colors": {"--primary": "#059669", "--primary-dark": "#047857", "--primary-light": "#DCFCE7",
                   "--bg": "#F6FAF7", "--card-bg": "#FFFFFF", "--surface-2": "#FBFDFC",
                   "--text-main": "#14291F", "--text-muted": "#5B7A6B", "--border": "#DDEBE2"},
    },
    "ametista": {
        "name": "Roxo Ametista", "mode": "claro",
        "colors": {"--primary": "#7C3AED", "--primary-dark": "#6D28D9", "--primary-light": "#F1E8FE",
                   "--bg": "#F9F7FC", "--card-bg": "#FFFFFF", "--surface-2": "#FCFBFD",
                   "--text-main": "#241B2F", "--text-muted": "#6B637A", "--border": "#E8E0F2"},
    },
    "coral": {
        "name": "Rosa Coral", "mode": "claro",
        "colors": {"--primary": "#DB2777", "--primary-dark": "#BE185D", "--primary-light": "#FCE7F3",
                   "--bg": "#FCF7F9", "--card-bg": "#FFFFFF", "--surface-2": "#FDFBFC",
                   "--text-main": "#2B1620", "--text-muted": "#7A5C68", "--border": "#F2DEE7"},
    },
    "neutro": {
        "name": "Cinza Neutro", "mode": "claro",
        "colors": {"--primary": "#475569", "--primary-dark": "#334155", "--primary-light": "#E2E8F0",
                   "--bg": "#F8FAFC", "--card-bg": "#FFFFFF", "--surface-2": "#FBFBFD",
                   "--text-main": "#1E293B", "--text-muted": "#64748B", "--border": "#E2E8F0"},
    },
    "escuro_indigo": {
        "name": "Escuro Índigo", "mode": "escuro",
        "colors": {"--primary": "#818CF8", "--primary-dark": "#6366F1", "--primary-light": "#312E81",
                   "--bg": "#111827", "--card-bg": "#1F2937", "--surface-2": "#2B3648",
                   "--text-main": "#F1F5F9", "--text-muted": "#94A3B8", "--border": "#374151"},
    },
    "escuro_verde": {
        "name": "Escuro Esmeralda", "mode": "escuro",
        "colors": {"--primary": "#34D399", "--primary-dark": "#10B981", "--primary-light": "#064E3B",
                   "--bg": "#0F1A17", "--card-bg": "#1B2A25", "--surface-2": "#243830",
                   "--text-main": "#ECFDF5", "--text-muted": "#9CA89F", "--border": "#2E4038"},
    },
    "escuro_ambar": {
        "name": "Escuro Âmbar", "mode": "escuro",
        "colors": {"--primary": "#FBBF24", "--primary-dark": "#F59E0B", "--primary-light": "#78350F",
                   "--bg": "#1C1917", "--card-bg": "#292524", "--surface-2": "#34302D",
                   "--text-main": "#FDF6E3", "--text-muted": "#A8A29E", "--border": "#44403C"},
    },
    "escuro_contraste": {
        "name": "Escuro Alto Contraste", "mode": "escuro",
        "colors": {"--primary": "#60A5FA", "--primary-dark": "#3B82F6", "--primary-light": "#1E3A8A",
                   "--bg": "#000000", "--card-bg": "#161616", "--surface-2": "#242424",
                   "--text-main": "#FFFFFF", "--text-muted": "#B0B0B0", "--border": "#3A3A3A"},
    },
}


def _load() -> pd.DataFrame:
    """Lê a tabela de configurações da base de dados (vazia se ainda não existir)."""
    if not database.table_exists(SETTINGS_TABLE):
        return pd.DataFrame(columns=SETTINGS_COLUMNS)
    return database.read_table(SETTINGS_TABLE)


def get_settings() -> dict:
    """Devolve as configurações atuais, com valores por omissão para o que ainda não foi definido."""
    df = _load()
    if df.empty:
        # Ainda não existe nenhuma configuração guardada — devolve tudo por omissão.
        return {
            "theme": DEFAULT_THEME, "font": DEFAULT_FONT,
            "alert_risk_threshold": DEFAULT_ALERT_RISK_THRESHOLD,
            "alert_min_absences": DEFAULT_ALERT_MIN_ABSENCES,
        }
    # Só existe uma linha na tabela (é uma configuração única, não uma lista).
    row = df.iloc[0]
    theme = row.get("theme") or DEFAULT_THEME
    font = row.get("font") or DEFAULT_FONT
    # Proteção extra: se o valor guardado já não for válido (ex.: tema
    # removido numa atualização futura), volta ao valor por omissão em vez de falhar.
    if theme not in THEMES:
        theme = DEFAULT_THEME
    if font not in FONT_OPTIONS:
        font = DEFAULT_FONT

    # Limiar de taxa de risco: usa o valor guardado, ou o valor por omissão
    # se estiver em falta/inválido (NaN pode acontecer ao ler de uma base de dados).
    risk_threshold = row.get("alert_risk_threshold")
    risk_threshold = (
        DEFAULT_ALERT_RISK_THRESHOLD if risk_threshold is None or pd.isna(risk_threshold)
        else float(risk_threshold)
    )

    # Número mínimo de faltas para gerar aviso: idem, com fallback para None
    # (o que significa "cálculo automático" em src/alerts.py).
    min_absences = row.get("alert_min_absences")
    min_absences = (
        DEFAULT_ALERT_MIN_ABSENCES if min_absences is None or pd.isna(min_absences)
        else int(min_absences)
    )

    return {
        "theme": theme, "font": font,
        "alert_risk_threshold": risk_threshold,
        "alert_min_absences": min_absences,
    }


def save_settings(
    theme: str | None = None,
    font: str | None = None,
    alert_risk_threshold: float | None = None,
    alert_min_absences: int | None = None,
) -> dict:
    """
    Atualização parcial: só os parâmetros explicitamente passados são
    alterados, os restantes mantêm o valor guardado anteriormente.

    alert_min_absences aceita um truque especial: -1 significa "voltar ao
    cálculo automático" (limpar a personalização), já que None já está
    reservado para "não alterar este campo" nesta chamada.
    """
    # Parte das configurações atuais, e só substitui os campos indicados.
    current = get_settings()
    if theme is not None:
        if theme not in THEMES:
            raise ValueError(f"Tema inválido: {theme}.")
        current["theme"] = theme
    if font is not None:
        if font not in FONT_OPTIONS:
            raise ValueError(f"Fonte inválida: {font}.")
        current["font"] = font
    if alert_risk_threshold is not None:
        # Valida que o limiar está num intervalo percentual razoável (1% a 99%).
        if not (0.01 <= alert_risk_threshold <= 0.99):
            raise ValueError("O limiar de taxa de risco deve estar entre 1% e 99%.")
        current["alert_risk_threshold"] = float(alert_risk_threshold)
    if alert_min_absences is not None:
        if alert_min_absences == -1:
            # Valor especial -1: volta ao cálculo automático (remove a personalização).
            current["alert_min_absences"] = None
        elif alert_min_absences < 0:
            raise ValueError("O número mínimo de faltas não pode ser negativo.")
        else:
            current["alert_min_absences"] = int(alert_min_absences)
    # Grava a configuração completa (uma só linha), substituindo a anterior.
    database.write_table(pd.DataFrame([current]), SETTINGS_TABLE, if_exists="replace")
    return current


def list_themes() -> list[dict]:
    """Lista todos os temas disponíveis, cada um com o seu id incluído (para o seletor de temas)."""
    return [{"id": theme_id, **info} for theme_id, info in THEMES.items()]
