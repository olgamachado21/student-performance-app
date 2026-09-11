"""
Internacionalização (i18n) do texto gerado pelo backend — PT/EN.

Contexto: o frontend já é bilingue desde a Fase 2 (ver web/js/i18n.js), mas
só para o texto fixo da interface. Muito do texto que a pessoa vê vem do
backend já pronto (alertas, sugestões de hábitos, mensagens do otimizador,
respostas do chatbot, PDFs, CSV) — construído com f-strings que misturam
dados reais (contagens, médias, percentagens) com frases em português. Por
isso a tradução tem de acontecer aqui, no sítio onde a frase é montada, e
não no frontend (que só recebe o resultado final já em texto corrido).

Padrão escolhido — diferente do dicionário central usado em i18n.js — para
evitar que vários ficheiros/tarefas em paralelo tenham de editar o mesmo
ficheiro gigante: cada string fica ao lado do código que a usa, com t()
como pequeno helper de escolha + formatação. Uso típico:

    from src.i18n import t

    t(lang, "Sem avisos de momento", "No alerts right now")

    t(
        lang,
        f"{n} estudante(s) têm mais de {limiar:.0f} faltas.",
        f"{n} student(s) have more than {limiar:.0f} absences.",
    )

Para frases com plural que muda a palavra toda (não só um "s" no fim, como
em português "previsão"/"previsões"), construir os dois textos completos
com condição prévia e passá-los já prontos a t() — ver exemplos em
prediction_tracking.py e optimizer.py.

lang vem sempre de um parâmetro de query da API (ver src/api.py, `lang`),
propagado desde o pedido do frontend (que o envia com getLanguage() — ver
web/js/api.js). Quando não é passado (pedidos antigos, scripts, testes),
normalize_lang() assume "pt" — o idioma original da aplicação — por isso
nada parte para quem já usava a API sem se preocupar com idiomas.
"""
from __future__ import annotations

DEFAULT_LANG = "pt"
SUPPORTED_LANGS = ("pt", "en")


def normalize_lang(lang: str | None) -> str:
    """Qualquer valor que não seja exatamente "en" cai em "pt" (omissão segura)."""
    return "en" if lang == "en" else "pt"


def t(lang: str | None, pt: str, en: str) -> str:
    """
    Escolhe o texto PT ou EN consoante lang. Os dois textos já devem vir
    completos (incluindo quaisquer valores interpolados via f-string do lado
    de quem chama) — t() não faz .format(), só escolhe.
    """
    return en if normalize_lang(lang) == "en" else pt


def plural_en(n: float | int, singular: str, plural: str | None = None) -> str:
    """
    Escolhe singular/plural em inglês consoante n (1 -> singular, resto ->
    plural). Ajuda a espelhar construções portuguesas tipo "estudante(s)"
    sem ter de escrever a condição à mão em cada sítio. Se plural não for
    dado, assume singular + "s" (regra regular, cobre a maioria dos casos
    usados neste projeto: student(s), prediction(s), change(s), point(s)...).
    """
    if plural is None:
        plural = singular + "s"
    return singular if n == 1 else plural
