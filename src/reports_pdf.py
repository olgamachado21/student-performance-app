"""
Fichas de Desempenho: gera um PDF individual por estudante, com um resumo
das notas e uma recomendação personalizada baseada em comparações reais
entre grupos de estudantes (nunca texto inventado).
"""
from __future__ import annotations

# io: para construir o PDF em memória (sem gravar ficheiro temporário em disco).
import io
# zipfile: para juntar várias fichas PDF num único ficheiro ZIP (geração em lote).
import zipfile

# pandas: para trabalhar com os dados como tabela.
import pandas as pd
# reportlab: biblioteca usada para gerar ficheiros PDF programaticamente.
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (Paragraph, SimpleDocTemplate, Spacer, Table,
                                 TableStyle)

from src.i18n import t, plural_en, normalize_lang

# Tamanho mínimo de um grupo para as suas estatísticas serem consideradas
# fiáveis o suficiente para entrar na recomendação (evita comparar com
# grupos com muito poucos estudantes, pouco representativos).
MIN_GROUP_SIZE = 5
# Descrição em texto de cada nível da escala de tempo de estudo (1 a 4), por idioma.
STUDYTIME_LABELS = {
    "pt": {1: "menos de 2h/semana", 2: "2 a 5h/semana", 3: "5 a 10h/semana", 4: "mais de 10h/semana"},
    "en": {1: "less than 2h/week", 2: "2 to 5h/week", 3: "5 to 10h/week", 4: "more than 10h/week"},
}


def gerar_insight_personalizado(df: pd.DataFrame, student_id: int, lang: str | None = None) -> str:
    """
    Compara o estudante com o grupo do mesmo nível de tempo de estudo, e com
    o grupo um nível acima (se existir e tiver amostra suficiente), para
    gerar uma recomendação baseada em dados reais — nunca um texto genérico.
    """
    lang = normalize_lang(lang)
    studytime_labels = STUDYTIME_LABELS[lang]
    student = df[df["student_id"] == student_id]
    if student.empty:
        return t(lang, "Estudante não encontrado.", "Student not found.")
    student = student.iloc[0]

    # Grupo de comparação: todos os estudantes com o mesmo nível de tempo de estudo.
    own_group = df[df["studytime"] == student["studytime"]]
    own_avg = own_group["G3"].mean()

    # Diferença entre a nota do estudante e a média do seu grupo.
    diff_own = student["G3"] - own_avg
    above_own = diff_own >= 0
    parts = [
        t(
            lang,
            f"A nota final deste estudante ({student['G3']:.0f} valores) está "
            f"{'acima' if above_own else 'abaixo'} da média do grupo com o mesmo "
            f"tempo de estudo ({studytime_labels.get(int(student['studytime']), '')}, "
            f"média de {own_avg:.1f} valores), uma diferença de {abs(diff_own):.1f} valores.",
            f"This student's final grade ({student['G3']:.0f} points) is "
            f"{'above' if above_own else 'below'} the average of the group with the same "
            f"study time ({studytime_labels.get(int(student['studytime']), '')}, "
            f"average of {own_avg:.1f} points), a difference of {abs(diff_own):.1f} points.",
        )
    ]

    # Se existir um nível de tempo de estudo acima (a escala vai até 4), compara
    # também com esse grupo, para sugerir um caminho de melhoria concreto.
    next_level = int(student["studytime"]) + 1
    if next_level <= 4:
        higher_group = df[df["studytime"] == next_level]
        # Só usa esta comparação se ambos os grupos tiverem amostra suficiente.
        if len(own_group) >= MIN_GROUP_SIZE and len(higher_group) >= MIN_GROUP_SIZE:
            higher_avg = higher_group["G3"].mean()
            gain = higher_avg - own_avg
            if gain > 0:
                parts.append(t(
                    lang,
                    f"Estudantes com um nível de estudo acima "
                    f"({studytime_labels.get(next_level, '')}) têm, em média, "
                    f"{higher_avg:.1f} valores — uma diferença de +{gain:.1f} valores "
                    f"face ao grupo atual, com base em {len(higher_group)} estudantes "
                    f"nesse grupo.",
                    f"Students with one study level above "
                    f"({studytime_labels.get(next_level, '')}) score, on average, "
                    f"{higher_avg:.1f} points — a difference of +{gain:.1f} points "
                    f"compared to the current group, based on {len(higher_group)} students "
                    f"in that group.",
                ))

    # Menciona reprovações anteriores, se existirem — fator com maior impacto negativo conhecido.
    if student["failures"] >= 1:
        parts.append(t(
            lang,
            f"Este estudante já teve {int(student['failures'])} reprovação(ões) anterior(es), "
            f"o fator com maior impacto negativo identificado na análise estatística "
            f"deste dataset (~-1,98 valores por reprovação, em média).",
            f"This student has had {int(student['failures'])} prior "
            f"{plural_en(int(student['failures']), 'failure')}, the factor with the largest "
            f"known negative impact identified in this dataset's statistical analysis "
            f"(~-1.98 points per failure, on average).",
        ))

    # Menciona faltas acima da média, se for o caso.
    if student["absences"] > df["absences"].mean():
        parts.append(t(
            lang,
            f"O número de faltas ({int(student['absences'])}) está acima da média geral "
            f"({df['absences'].mean():.1f}), fator associado a notas mais baixas.",
            f"The number of absences ({int(student['absences'])}) is above the overall average "
            f"({df['absences'].mean():.1f}), a factor associated with lower grades.",
        ))

    return " ".join(parts)


def gerar_ficha_pdf(df: pd.DataFrame, student_id: int, lang: str | None = None) -> bytes:
    """Gera o PDF da ficha de desempenho de um estudante e devolve os bytes."""
    lang = normalize_lang(lang)
    studytime_labels = STUDYTIME_LABELS[lang]
    student_rows = df[df["student_id"] == student_id]
    if student_rows.empty:
        raise ValueError(t(
            lang,
            f"Estudante {student_id} não encontrado.",
            f"Student {student_id} not found.",
        ))
    student = student_rows.iloc[0]

    # Cria o PDF em memória (buffer), em vez de gravar num ficheiro temporário em disco.
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm,
    )

    # Estilos de texto: título, cabeçalhos de secção, e corpo de texto normal.
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleCustom", parent=styles["Title"], textColor=colors.HexColor("#4F46E5"), fontSize=20,
    )
    heading_style = ParagraphStyle(
        "HeadingCustom", parent=styles["Heading2"], textColor=colors.HexColor("#1E293B"), spaceBefore=14,
    )
    body_style = ParagraphStyle(
        "BodyCustom", parent=styles["BodyText"], leading=16, spaceAfter=6,
    )

    # Lista de elementos que vão compor o PDF, na ordem em que aparecem.
    elements = []
    elements.append(Paragraph(t(lang, "Ficha de Desempenho do Estudante", "Student Performance Report"), title_style))
    elements.append(Paragraph(t(lang, f"Estudante Nº {int(student['student_id'])}", f"Student No. {int(student['student_id'])}"), body_style))
    elements.append(Spacer(1, 0.4 * cm))

    aprovado_txt = t(lang, "Aprovado", "Passed") if student["aprovado"] == 1 else t(lang, "Reprovado", "Failed")
    risk_txt = t(lang, "Em risco", "At risk") if student["at_risk"] == 1 else t(lang, "Sem sinais de risco", "No risk signs")

    # Tabela-resumo com os dados principais do estudante, em 4 colunas (etiqueta/valor x2).
    resumo_data = [
        [t(lang, "Sexo", "Sex"), str(student["sex"]), t(lang, "Idade", "Age"), str(int(student["age"]))],
        [t(lang, "Tempo de estudo", "Study time"), studytime_labels.get(int(student["studytime"]), "-"), t(lang, "Faltas", "Absences"), str(int(student["absences"]))],
        [t(lang, "Reprovações anteriores", "Prior failures"), str(int(student["failures"])), t(lang, "Situação", "Status"), aprovado_txt],
        [t(lang, "Nota 1º período (G1)", "Grade 1st period (G1)"), f"{student['G1']:.0f}", t(lang, "Nota 2º período (G2)", "Grade 2nd period (G2)"), f"{student['G2']:.0f}"],
        [t(lang, "Nota final (G3)", "Final grade (G3)"), f"{student['G3']:.0f} / 20", t(lang, "Estado de risco", "Risk status"), risk_txt],
    ]
    table = Table(resumo_data, colWidths=[4.5 * cm, 3.5 * cm, 4.5 * cm, 3.5 * cm])
    # Estilo visual da tabela: colunas de etiqueta com fundo colorido e negrito,
    # bordas finas, texto verticalmente centrado, e algum espaçamento interno.
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EEF0FF")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#EEF0FF")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E7E9EE")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(table)

    elements.append(Paragraph(t(lang, "Recomendação personalizada", "Personalized recommendation"), heading_style))
    elements.append(Paragraph(gerar_insight_personalizado(df, student_id, lang=lang), body_style))

    elements.append(Paragraph(t(lang, "Nota metodológica", "Methodological note"), heading_style))
    elements.append(Paragraph(
        t(
            lang,
            "Esta recomendação é gerada automaticamente a partir de comparações "
            "estatísticas reais entre grupos de estudantes deste dataset, e não "
            "constitui um diagnóstico individual. Consulta a aplicação para mais "
            "detalhes sobre os fatores que influenciam o desempenho académico.",
            "This recommendation is generated automatically from real statistical "
            "comparisons between groups of students in this dataset, and does not "
            "constitute an individual diagnosis. See the application for more "
            "details on the factors influencing academic performance.",
        ),
        ParagraphStyle("Note", parent=body_style, textColor=colors.HexColor("#64748B"), fontSize=8.5),
    ))

    # Monta o documento final a partir da lista de elementos, e devolve os bytes do PDF.
    doc.build(elements)
    return buffer.getvalue()


def gerar_relatorio_turma_pdf(df: pd.DataFrame, lang: str | None = None) -> bytes:
    """
    Relatório agregado de turma: KPIs gerais, um resumo da segmentação de
    perfis (K-Means) e a lista dos estudantes em risco mais prioritários —
    para partilhar uma visão do conjunto sem ter de abrir a aplicação, tal
    como gerar_ficha_pdf já faz para um único estudante.
    """
    from src.segmentation import run_segmentation  # import tardio: evita import circular

    lang = normalize_lang(lang)
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleCustom", parent=styles["Title"], textColor=colors.HexColor("#4F46E5"), fontSize=20,
    )
    heading_style = ParagraphStyle(
        "HeadingCustom", parent=styles["Heading2"], textColor=colors.HexColor("#1E293B"), spaceBefore=14,
    )
    body_style = ParagraphStyle(
        "BodyCustom", parent=styles["BodyText"], leading=16, spaceAfter=6,
    )
    note_style = ParagraphStyle(
        "Note", parent=body_style, textColor=colors.HexColor("#64748B"), fontSize=8.5,
    )

    elements = []
    elements.append(Paragraph(t(lang, "Relatório de Turma", "Class Report"), title_style))
    elements.append(Paragraph(
        t(
            lang,
            f"{len(df)} estudantes analisados (inclui estudantes adicionados manualmente).",
            f"{len(df)} {plural_en(len(df), 'student')} analyzed (includes manually added students).",
        ),
        body_style,
    ))
    elements.append(Spacer(1, 0.4 * cm))

    # Tabela de indicadores-chave (KPIs) gerais da turma.
    kpi_data = [
        [t(lang, "Nota média (G3)", "Average grade (G3)"), f"{df['G3'].mean():.2f} / 20", t(lang, "Taxa de aprovação", "Pass rate"), f"{df['aprovado'].mean() * 100:.1f}%"],
        [t(lang, "Estudantes em risco", "Students at risk"), f"{int(df['at_risk'].sum())} ({df['at_risk'].mean() * 100:.1f}%)", t(lang, "Faltas médias", "Average absences"), f"{df['absences'].mean():.1f}"],
        [t(lang, "Tempo de estudo médio (nível)", "Average study time (level)"), f"{df['studytime'].mean():.2f}", t(lang, "Reprovações médias", "Average failures"), f"{df['failures'].mean():.2f}"],
    ]
    # colWidths somam 16.6cm — a área útil da página é 17cm (21cm A4 menos
    # 2cm de margem de cada lado); a soma tinha 17.4cm antes (excedia por
    # 4mm), o que podia empurrar a tabela ligeiramente para além da margem
    # direita consoante o motor de PDF. Reduz-se as colunas de VALOR (2ª/4ª,
    # que só têm números curtos, ex. "84.7%") em vez das de etiqueta (1ª/3ª),
    # para etiquetas mais compridas como "Tempo de estudo médio (nível)"
    # continuarem a ter espaço confortável antes do valor seguinte.
    kpi_table = Table(kpi_data, colWidths=[5 * cm, 3.3 * cm, 5 * cm, 3.3 * cm])
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#EEF0FF")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#EEF0FF")),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E7E9EE")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    elements.append(kpi_table)

    elements.append(Paragraph(t(lang, "Perfis de estudantes (segmentação automática)", "Student profiles (automatic segmentation)"), heading_style))
    try:
        # Corre a segmentação em tempo real (4 grupos), para o relatório refletir sempre o estado atual.
        segmentation = run_segmentation(df, n_clusters=4, lang=lang)
        # Estilo próprio para o nome do perfil dentro da tabela: os nomes são
        # gerados automaticamente (ex.: "Consumo de Álcool ao Fim de Semana &
        # Consumo de Álcool em Dias Úteis") e podem ser bastante compridos. Uma
        # string simples numa célula do Table NÃO quebra linha — quando não
        # cabia na largura da coluna (7cm), o texto continuava para além dela e
        # ficava sobreposto aos números da coluna seguinte ("Estudantes"). Um
        # Paragraph, ao contrário de uma string simples, quebra automaticamente
        # linha dentro da largura da coluna, resolvendo a sobreposição.
        seg_name_style = ParagraphStyle(
            "SegName", parent=body_style, fontSize=8.5, leading=11, spaceAfter=0,
        )
        seg_rows = [[
            t(lang, "Perfil", "Profile"), t(lang, "Estudantes", "Students"),
            t(lang, "Nota média", "Average grade"), t(lang, "Taxa de risco", "Risk rate"),
        ]]
        for group in segmentation["groups"]:
            seg_rows.append([
                Paragraph(group["name"], seg_name_style), f"{group['size']} ({group['size_pct']}%)",
                f"{group['avg_grade']:.1f}", f"{group['risk_pct']}%",
            ])
        seg_table = Table(seg_rows, colWidths=[7 * cm, 3.5 * cm, 3 * cm, 3 * cm])
        # Cabeçalho da tabela com fundo colorido e texto branco, para se destacar das linhas de dados.
        seg_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#4F46E5")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E7E9EE")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        elements.append(seg_table)
    except ValueError:
        # A segmentação pode falhar com datasets muito pequenos — mostra uma mensagem em vez de rebentar.
        elements.append(Paragraph(t(lang, "Segmentação não disponível para este conjunto de dados.", "Segmentation not available for this dataset."), body_style))

    elements.append(Paragraph(t(lang, "Estudantes em risco prioritários", "Priority at-risk students"), heading_style))
    # Lista os 20 estudantes em risco com nota mais baixa (os mais urgentes primeiro).
    at_risk = df[df["at_risk"] == 1].sort_values("G3").head(20)
    if at_risk.empty:
        elements.append(Paragraph(t(lang, "Sem estudantes em risco no conjunto de dados atual.", "No at-risk students in the current dataset."), body_style))
    else:
        risk_rows = [[
            t(lang, "Nº", "No."), t(lang, "Sexo", "Sex"), t(lang, "Estudo", "Study"),
            t(lang, "Faltas", "Absences"), t(lang, "Reprovações", "Failures"), "G3",
        ]]
        for _, s in at_risk.iterrows():
            risk_rows.append([
                int(s["student_id"]), str(s["sex"]), int(s["studytime"]),
                int(s["absences"]), int(s["failures"]), f"{s['G3']:.0f}",
            ])
        risk_table = Table(risk_rows, colWidths=[2.3 * cm] * 6)
        # Cabeçalho em vermelho, para transmitir visualmente a urgência desta lista.
        risk_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#DC2626")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E7E9EE")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(risk_table)
        # Se houver mais de 20 estudantes em risco, avisa que a lista foi limitada.
        n_at_risk_total = int(df["at_risk"].sum())
        if n_at_risk_total > 20:
            elements.append(Paragraph(
                t(
                    lang,
                    f"Mostra os 20 estudantes em risco com nota mais baixa, de um total de {n_at_risk_total}.",
                    f"Showing the 20 lowest-grade at-risk students, out of a total of {n_at_risk_total}.",
                ),
                note_style,
            ))

    elements.append(Paragraph(t(lang, "Nota metodológica", "Methodological note"), heading_style))
    elements.append(Paragraph(
        t(
            lang,
            "Este relatório é gerado automaticamente a partir do estado atual do conjunto de dados. "
            "A segmentação agrupa estudantes por K-Means sobre 13 variáveis de hábitos e notas; "
            "\"em risco\" significa nota final abaixo de 10, pelo menos uma reprovação anterior, ou "
            "mais de 15 faltas.",
            "This report is generated automatically from the current state of the dataset. "
            "Segmentation groups students using K-Means over 13 habit and grade variables; "
            "\"at risk\" means a final grade below 10, at least one prior failure, or "
            "more than 15 absences.",
        ),
        note_style,
    ))

    doc.build(elements)
    return buffer.getvalue()


def gerar_fichas_lote_zip(df: pd.DataFrame, only_at_risk: bool = True, limit: int = 200, lang: str | None = None) -> bytes:
    """
    Gera um ficheiro ZIP com a ficha de desempenho PDF de vários estudantes
    de uma vez, reaproveitando gerar_ficha_pdf por estudante — por omissão,
    todos os estudantes em risco (até `limit`, começando pelos de nota mais
    baixa), para descarregar de uma vez as fichas de quem precisa de mais
    atenção, em vez de gerar uma a uma.
    """
    lang = normalize_lang(lang)
    # Filtra só os estudantes em risco (se pedido), ordena pela nota mais baixa, e limita a quantidade.
    subset = df[df["at_risk"] == 1] if only_at_risk else df
    subset = subset.sort_values("G3").head(limit)
    if subset.empty:
        raise ValueError(t(
            lang,
            "Nenhum estudante corresponde aos critérios para gerar fichas em lote.",
            "No students match the criteria for generating reports in bulk.",
        ))

    # Constrói o ZIP em memória, adicionando uma ficha PDF por estudante.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for _, student in subset.iterrows():
            student_id = int(student["student_id"])
            pdf_bytes = gerar_ficha_pdf(df, student_id, lang=lang)
            zf.writestr(f"ficha_estudante_{student_id}.pdf", pdf_bytes)
    return buffer.getvalue()
