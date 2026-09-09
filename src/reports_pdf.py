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

# Tamanho mínimo de um grupo para as suas estatísticas serem consideradas
# fiáveis o suficiente para entrar na recomendação (evita comparar com
# grupos com muito poucos estudantes, pouco representativos).
MIN_GROUP_SIZE = 5
# Descrição em texto de cada nível da escala de tempo de estudo (1 a 4).
STUDYTIME_LABELS = {1: "menos de 2h/semana", 2: "2 a 5h/semana", 3: "5 a 10h/semana", 4: "mais de 10h/semana"}


def gerar_insight_personalizado(df: pd.DataFrame, student_id: int) -> str:
    """
    Compara o estudante com o grupo do mesmo nível de tempo de estudo, e com
    o grupo um nível acima (se existir e tiver amostra suficiente), para
    gerar uma recomendação baseada em dados reais — nunca um texto genérico.
    """
    student = df[df["student_id"] == student_id]
    if student.empty:
        return "Estudante não encontrado."
    student = student.iloc[0]

    # Grupo de comparação: todos os estudantes com o mesmo nível de tempo de estudo.
    own_group = df[df["studytime"] == student["studytime"]]
    own_avg = own_group["G3"].mean()

    # Diferença entre a nota do estudante e a média do seu grupo.
    diff_own = student["G3"] - own_avg
    parts = [
        f"A nota final deste estudante ({student['G3']:.0f} valores) está "
        f"{'acima' if diff_own >= 0 else 'abaixo'} da média do grupo com o mesmo "
        f"tempo de estudo ({STUDYTIME_LABELS.get(int(student['studytime']), '')}, "
        f"média de {own_avg:.1f} valores), uma diferença de {abs(diff_own):.1f} valores."
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
                parts.append(
                    f"Estudantes com um nível de estudo acima "
                    f"({STUDYTIME_LABELS.get(next_level, '')}) têm, em média, "
                    f"{higher_avg:.1f} valores — uma diferença de +{gain:.1f} valores "
                    f"face ao grupo atual, com base em {len(higher_group)} estudantes "
                    f"nesse grupo."
                )

    # Menciona reprovações anteriores, se existirem — fator com maior impacto negativo conhecido.
    if student["failures"] >= 1:
        parts.append(
            f"Este estudante já teve {int(student['failures'])} reprovação(ões) anterior(es), "
            f"o fator com maior impacto negativo identificado na análise estatística "
            f"deste dataset (~-1,98 valores por reprovação, em média)."
        )

    # Menciona faltas acima da média, se for o caso.
    if student["absences"] > df["absences"].mean():
        parts.append(
            f"O número de faltas ({int(student['absences'])}) está acima da média geral "
            f"({df['absences'].mean():.1f}), fator associado a notas mais baixas."
        )

    return " ".join(parts)


def gerar_ficha_pdf(df: pd.DataFrame, student_id: int) -> bytes:
    """Gera o PDF da ficha de desempenho de um estudante e devolve os bytes."""
    student_rows = df[df["student_id"] == student_id]
    if student_rows.empty:
        raise ValueError(f"Estudante {student_id} não encontrado.")
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
    elements.append(Paragraph("Ficha de Desempenho do Estudante", title_style))
    elements.append(Paragraph(f"Estudante Nº {int(student['student_id'])}", body_style))
    elements.append(Spacer(1, 0.4 * cm))

    aprovado_txt = "Aprovado" if student["aprovado"] == 1 else "Reprovado"
    risk_txt = "Em risco" if student["at_risk"] == 1 else "Sem sinais de risco"

    # Tabela-resumo com os dados principais do estudante, em 4 colunas (etiqueta/valor x2).
    resumo_data = [
        ["Sexo", str(student["sex"]), "Idade", str(int(student["age"]))],
        ["Tempo de estudo", STUDYTIME_LABELS.get(int(student["studytime"]), "-"), "Faltas", str(int(student["absences"]))],
        ["Reprovações anteriores", str(int(student["failures"])), "Situação", aprovado_txt],
        ["Nota 1º período (G1)", f"{student['G1']:.0f}", "Nota 2º período (G2)", f"{student['G2']:.0f}"],
        ["Nota final (G3)", f"{student['G3']:.0f} / 20", "Estado de risco", risk_txt],
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

    elements.append(Paragraph("Recomendação personalizada", heading_style))
    elements.append(Paragraph(gerar_insight_personalizado(df, student_id), body_style))

    elements.append(Paragraph("Nota metodológica", heading_style))
    elements.append(Paragraph(
        "Esta recomendação é gerada automaticamente a partir de comparações "
        "estatísticas reais entre grupos de estudantes deste dataset, e não "
        "constitui um diagnóstico individual. Consulta a aplicação para mais "
        "detalhes sobre os fatores que influenciam o desempenho académico.",
        ParagraphStyle("Note", parent=body_style, textColor=colors.HexColor("#64748B"), fontSize=8.5),
    ))

    # Monta o documento final a partir da lista de elementos, e devolve os bytes do PDF.
    doc.build(elements)
    return buffer.getvalue()


def gerar_relatorio_turma_pdf(df: pd.DataFrame) -> bytes:
    """
    Relatório agregado de turma: KPIs gerais, um resumo da segmentação de
    perfis (K-Means) e a lista dos estudantes em risco mais prioritários —
    para partilhar uma visão do conjunto sem ter de abrir a aplicação, tal
    como gerar_ficha_pdf já faz para um único estudante.
    """
    from src.segmentation import run_segmentation  # import tardio: evita import circular

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
    elements.append(Paragraph("Relatório de Turma", title_style))
    elements.append(Paragraph(f"{len(df)} estudantes analisados (inclui estudantes adicionados manualmente).", body_style))
    elements.append(Spacer(1, 0.4 * cm))

    # Tabela de indicadores-chave (KPIs) gerais da turma.
    kpi_data = [
        ["Nota média (G3)", f"{df['G3'].mean():.2f} / 20", "Taxa de aprovação", f"{df['aprovado'].mean() * 100:.1f}%"],
        ["Estudantes em risco", f"{int(df['at_risk'].sum())} ({df['at_risk'].mean() * 100:.1f}%)", "Faltas médias", f"{df['absences'].mean():.1f}"],
        ["Tempo de estudo médio (nível)", f"{df['studytime'].mean():.2f}", "Reprovações médias", f"{df['failures'].mean():.2f}"],
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

    elements.append(Paragraph("Perfis de estudantes (segmentação automática)", heading_style))
    try:
        # Corre a segmentação em tempo real (4 grupos), para o relatório refletir sempre o estado atual.
        segmentation = run_segmentation(df, n_clusters=4)
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
        seg_rows = [["Perfil", "Estudantes", "Nota média", "Taxa de risco"]]
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
        elements.append(Paragraph("Segmentação não disponível para este conjunto de dados.", body_style))

    elements.append(Paragraph("Estudantes em risco prioritários", heading_style))
    # Lista os 20 estudantes em risco com nota mais baixa (os mais urgentes primeiro).
    at_risk = df[df["at_risk"] == 1].sort_values("G3").head(20)
    if at_risk.empty:
        elements.append(Paragraph("Sem estudantes em risco no conjunto de dados atual.", body_style))
    else:
        risk_rows = [["Nº", "Sexo", "Estudo", "Faltas", "Reprovações", "G3"]]
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
                f"Mostra os 20 estudantes em risco com nota mais baixa, de um total de {n_at_risk_total}.",
                note_style,
            ))

    elements.append(Paragraph("Nota metodológica", heading_style))
    elements.append(Paragraph(
        "Este relatório é gerado automaticamente a partir do estado atual do conjunto de dados. "
        "A segmentação agrupa estudantes por K-Means sobre 13 variáveis de hábitos e notas; "
        "\"em risco\" significa nota final abaixo de 10, pelo menos uma reprovação anterior, ou "
        "mais de 15 faltas.",
        note_style,
    ))

    doc.build(elements)
    return buffer.getvalue()


def gerar_fichas_lote_zip(df: pd.DataFrame, only_at_risk: bool = True, limit: int = 200) -> bytes:
    """
    Gera um ficheiro ZIP com a ficha de desempenho PDF de vários estudantes
    de uma vez, reaproveitando gerar_ficha_pdf por estudante — por omissão,
    todos os estudantes em risco (até `limit`, começando pelos de nota mais
    baixa), para descarregar de uma vez as fichas de quem precisa de mais
    atenção, em vez de gerar uma a uma.
    """
    # Filtra só os estudantes em risco (se pedido), ordena pela nota mais baixa, e limita a quantidade.
    subset = df[df["at_risk"] == 1] if only_at_risk else df
    subset = subset.sort_values("G3").head(limit)
    if subset.empty:
        raise ValueError("Nenhum estudante corresponde aos critérios para gerar fichas em lote.")

    # Constrói o ZIP em memória, adicionando uma ficha PDF por estudante.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for _, student in subset.iterrows():
            student_id = int(student["student_id"])
            pdf_bytes = gerar_ficha_pdf(df, student_id)
            zf.writestr(f"ficha_estudante_{student_id}.pdf", pdf_bytes)
    return buffer.getvalue()
