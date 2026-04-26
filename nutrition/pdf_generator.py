import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Brand colours ──────────────────────────────────────────────────────────────
GREEN       = colors.HexColor('#16a34a')
GREEN_DARK  = colors.HexColor('#15803d')
GREEN_LIGHT = colors.HexColor('#dcfce7')
GREEN_MID   = colors.HexColor('#86efac')
GREEN_BG    = colors.HexColor('#f0fdf4')
GREEN_SOFT  = colors.HexColor('#bbf7d0')
GRAY_900    = colors.HexColor('#111827')
GRAY_700    = colors.HexColor('#374151')
GRAY_500    = colors.HexColor('#6b7280')
GRAY_200    = colors.HexColor('#e5e7eb')
GRAY_100    = colors.HexColor('#f3f4f6')
GRAY_50     = colors.HexColor('#f9fafb')
WHITE       = colors.white

PAGE_W, PAGE_H = A4
MARGIN     = 18 * mm
BOTTOM_MGN = 22 * mm
CONTENT_W  = PAGE_W - 2 * MARGIN


def _styles():
    return {
        'title': ParagraphStyle(
            'title', fontName='Helvetica-Bold', fontSize=22,
            textColor=WHITE, leading=26,
        ),
        'subtitle': ParagraphStyle(
            'subtitle', fontName='Helvetica', fontSize=10,
            textColor=GREEN_SOFT, leading=14,
        ),
        'kcal_big': ParagraphStyle(
            'kcal_big', fontName='Helvetica-Bold', fontSize=24,
            textColor=WHITE, leading=26, alignment=TA_RIGHT,
        ),
        'kcal_label': ParagraphStyle(
            'kcal_label', fontName='Helvetica', fontSize=9,
            textColor=GREEN_SOFT, alignment=TA_RIGHT,
        ),
        'section': ParagraphStyle(
            'section', fontName='Helvetica-Bold', fontSize=13,
            textColor=GRAY_900, leading=16,
        ),
        'meal_name': ParagraphStyle(
            'meal_name', fontName='Helvetica-Bold', fontSize=12,
            textColor=GRAY_900, leading=14,
        ),
        'meal_meta': ParagraphStyle(
            'meal_meta', fontName='Helvetica', fontSize=8.5,
            textColor=GRAY_500, leading=11,
        ),
        'meal_kcal': ParagraphStyle(
            'meal_kcal', fontName='Helvetica-Bold', fontSize=11,
            textColor=GREEN_DARK, alignment=TA_RIGHT, leading=13,
        ),
        'body': ParagraphStyle(
            'body', fontName='Helvetica', fontSize=9,
            textColor=GRAY_700, leading=13,
        ),
        'small': ParagraphStyle(
            'small', fontName='Helvetica', fontSize=8,
            textColor=GRAY_500, leading=11,
        ),
        'disclaimer': ParagraphStyle(
            'disclaimer', fontName='Helvetica-Oblique', fontSize=8,
            textColor=GRAY_500, alignment=TA_CENTER, leading=11,
        ),
    }


def _header_table(diet_plan, styles):
    """Faixa verde com título, objetivo, data e calorias diárias."""
    goal = diet_plan.goal_description or 'Plano personalizado'
    kcal = diet_plan.total_calories
    date = diet_plan.created_at.strftime('%d/%m/%Y') if diet_plan.created_at else '—'

    if isinstance(kcal, int):
        kcal_str = f'{kcal:,}'.replace(',', '.')
    else:
        kcal_str = str(kcal) if kcal else '—'

    left_col = [
        Paragraph('Seu Plano Alimentar', styles['title']),
        Spacer(1, 6),
        Paragraph(f'Gerado por Inteligência Artificial &bull; {date}',
                  styles['subtitle']),
        Spacer(1, 3),
        Paragraph(f'Objetivo: <b>{goal}</b>', styles['subtitle']),
    ]
    right_col = [
        Spacer(1, 4),
        Paragraph(kcal_str, styles['kcal_big']),
        Paragraph('kcal por dia', styles['kcal_label']),
    ]

    tbl = Table(
        [[left_col, right_col]],
        colWidths=[CONTENT_W - 55 * mm, 55 * mm],
    )
    tbl.setStyle(TableStyle([
        ('BACKGROUND',     (0, 0), (-1, -1), GREEN),
        ('ROUNDEDCORNERS', [8]),
        ('TOPPADDING',     (0, 0), (-1, -1), 18),
        ('BOTTOMPADDING',  (0, 0), (-1, -1), 18),
        ('LEFTPADDING',    (0, 0), (-1, -1), 20),
        ('RIGHTPADDING',   (0, 0), (-1, -1), 20),
        ('VALIGN',         (0, 0), (-1, -1), 'TOP'),
    ]))
    return tbl


def _macros_table(macros, total_kcal):
    """Painel verde-claro com proteína / carboidratos / gordura + % das calorias."""
    if not macros:
        return None

    def _pct(grams_key, kcal_per_g):
        try:
            grams = float(macros.get(grams_key) or 0)
            tot   = float(total_kcal or 0)
            if grams and tot:
                return f'{round(grams * kcal_per_g / tot * 100)}% das calorias'
        except (TypeError, ValueError):
            pass
        return ''

    def _cell(label, grams, pct):
        value = f'{grams}g' if grams not in (None, '', '—') else '—'
        return [
            Paragraph(label, ParagraphStyle(
                'm_label', fontName='Helvetica-Bold', fontSize=8,
                textColor=GREEN_DARK, alignment=TA_CENTER, spaceAfter=3)),
            Paragraph(f'<b>{value}</b>', ParagraphStyle(
                'm_val', fontName='Helvetica-Bold', fontSize=16,
                textColor=GRAY_900, alignment=TA_CENTER, leading=18)),
            Paragraph(pct or '&nbsp;', ParagraphStyle(
                'm_pct', fontName='Helvetica', fontSize=7.5,
                textColor=GRAY_500, alignment=TA_CENTER)),
        ]

    data = [[
        _cell('PROTEÍNA',     macros.get('protein_g', '—'), _pct('protein_g', 4)),
        _cell('CARBOIDRATOS', macros.get('carbs_g',   '—'), _pct('carbs_g',   4)),
        _cell('GORDURA',      macros.get('fat_g',     '—'), _pct('fat_g',     9)),
    ]]

    tbl = Table(data, colWidths=[CONTENT_W / 3] * 3)
    tbl.setStyle(TableStyle([
        ('BACKGROUND',     (0, 0), (-1, -1), GREEN_BG),
        ('ROUNDEDCORNERS', [8]),
        ('TOPPADDING',     (0, 0), (-1, -1), 14),
        ('BOTTOMPADDING',  (0, 0), (-1, -1), 14),
        ('LINEAFTER',      (0, 0), (1, 0), 0.5, GREEN_MID),
        ('VALIGN',         (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return tbl


def _section_title(text, styles):
    """Título de seção com barrinha verde como acento à esquerda."""
    bar = Table([['']], colWidths=[3], rowHeights=[16])
    bar.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), GREEN)]))

    holder = Table(
        [[bar, Paragraph(text, styles['section'])]],
        colWidths=[6, CONTENT_W - 6],
    )
    holder.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING',   (0, 0), (0, 0), 0),
        ('RIGHTPADDING',  (0, 0), (0, 0), 8),
        ('LEFTPADDING',   (1, 0), (1, 0), 6),
        ('RIGHTPADDING',  (1, 0), (1, 0), 0),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    return holder


def _meal_badge(n):
    """Quadrado arredondado verde com o número da refeição em branco."""
    p = Paragraph(
        f'<font color="white"><b>{n}</b></font>',
        ParagraphStyle('badge', fontName='Helvetica-Bold',
                       fontSize=11, alignment=TA_CENTER, leading=12),
    )
    t = Table([[p]], colWidths=[9 * mm], rowHeights=[9 * mm])
    t.setStyle(TableStyle([
        ('BACKGROUND',     (0, 0), (-1, -1), GREEN),
        ('ROUNDEDCORNERS', [4.5]),
        ('VALIGN',         (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',     (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING',  (0, 0), (-1, -1), 0),
        ('LEFTPADDING',    (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',   (0, 0), (-1, -1), 0),
    ]))
    return t


def _meal_block(index, meal_name, calories, raw_meal, styles):
    """Bloco completo de refeição (cabeçalho + tabela de alimentos)."""
    time_text = (raw_meal.get('time_suggestion') or '') if raw_meal else ''
    meta_parts = [f'REFEIÇÃO {index + 1}']
    if time_text:
        meta_parts.append(time_text)
    meta_text = '  •  '.join(meta_parts)

    head_left = [
        Paragraph(meta_text, styles['meal_meta']),
        Spacer(1, 2),
        Paragraph(meal_name, styles['meal_name']),
    ]
    head = Table(
        [[_meal_badge(index + 1), head_left, Paragraph(f'{calories} kcal', styles['meal_kcal'])]],
        colWidths=[12 * mm, CONTENT_W - 12 * mm - 30 * mm, 30 * mm],
    )
    head.setStyle(TableStyle([
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))

    elements = [head, Spacer(1, 8)]

    foods = raw_meal.get('foods', []) if raw_meal else []
    if foods:
        th_style = ParagraphStyle(
            'th', fontName='Helvetica-Bold', fontSize=7,
            textColor=GRAY_500, leading=9,
        )
        rows = [[
            Paragraph('ALIMENTO',   ParagraphStyle('thl', parent=th_style, alignment=TA_LEFT)),
            Paragraph('QUANTIDADE', ParagraphStyle('thc', parent=th_style, alignment=TA_CENTER)),
            Paragraph('KCAL',       ParagraphStyle('thr', parent=th_style, alignment=TA_RIGHT)),
        ]]
        for f in foods:
            qty = f.get('quantity') or f'{f.get("quantity_g", "—")}g'
            rows.append([
                Paragraph(f.get('name', '—'), styles['body']),
                Paragraph(str(qty), ParagraphStyle(
                    'qty', fontName='Helvetica', fontSize=9,
                    textColor=GRAY_700, alignment=TA_CENTER)),
                Paragraph(str(f.get('calories', '—')), ParagraphStyle(
                    'fk', fontName='Helvetica-Bold', fontSize=9,
                    textColor=GREEN_DARK, alignment=TA_RIGHT)),
            ])

        tbl = Table(rows, colWidths=[CONTENT_W * 0.55, CONTENT_W * 0.25, CONTENT_W * 0.20])
        tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0), GRAY_50),
            ('LINEBELOW',     (0, 0), (-1, 0), 0.6, GRAY_200),
            ('LINEBELOW',     (0, 1), (-1, -1), 0.3, GRAY_200),
            ('TOPPADDING',    (0, 0), (-1, 0), 7),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 7),
            ('TOPPADDING',    (0, 1), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
            ('LEFTPADDING',   (0, 0), (-1, -1), 8),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(tbl)
    else:
        elements.append(Paragraph('Detalhes não disponíveis.', styles['small']))

    elements.append(Spacer(1, 14))
    return KeepTogether(elements)


def _notes_card(notes, styles):
    """Caixa verde-clara com as observações."""
    tbl = Table([[Paragraph(notes, styles['body'])]], colWidths=[CONTENT_W])
    tbl.setStyle(TableStyle([
        ('BACKGROUND',     (0, 0), (-1, -1), GREEN_BG),
        ('ROUNDEDCORNERS', [6]),
        ('LEFTPADDING',    (0, 0), (-1, -1), 14),
        ('RIGHTPADDING',   (0, 0), (-1, -1), 14),
        ('TOPPADDING',     (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING',  (0, 0), (-1, -1), 12),
    ]))
    return tbl


def _draw_decoration(canvas, doc):
    """Linha + branding + número de página no rodapé de cada página."""
    canvas.saveState()
    canvas.setStrokeColor(GRAY_200)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN, 14 * mm, PAGE_W - MARGIN, 14 * mm)

    canvas.setFont('Helvetica-Bold', 8)
    canvas.setFillColor(GREEN_DARK)
    canvas.drawString(MARGIN, 9 * mm, 'MyNutri AI')
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(GRAY_500)
    canvas.drawString(MARGIN + 18 * mm, 9 * mm, '· mynutriai.app')
    canvas.drawRightString(PAGE_W - MARGIN, 9 * mm, f'Página {doc.page}')
    canvas.restoreState()


def generate_diet_pdf(diet_plan) -> bytes:
    """
    Gera o PDF de um DietPlan e retorna os bytes.
    Parâmetro: instância de DietPlan com meals pré-carregadas (prefetch_related).
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=MARGIN,
        bottomMargin=BOTTOM_MGN,
        title='Meu Plano Alimentar — MyNutri AI',
        author='MyNutri AI',
    )

    styles    = _styles()
    raw       = diet_plan.raw_response or {}
    macros    = raw.get('macros')
    notes     = raw.get('notes', '')
    meals_raw = raw.get('meals', [])

    story = []

    # ── Cabeçalho ─────────────────────────────────────────────────────────────
    story.append(_header_table(diet_plan, styles))
    story.append(Spacer(1, 16))

    # ── Macros ────────────────────────────────────────────────────────────────
    macros_tbl = _macros_table(macros, diet_plan.total_calories)
    if macros_tbl:
        story.append(macros_tbl)
        story.append(Spacer(1, 22))

    # ── Refeições ─────────────────────────────────────────────────────────────
    story.append(_section_title('Refeições do Dia', styles))
    story.append(Spacer(1, 12))

    meals = list(diet_plan.meals.order_by('order'))
    for i, meal in enumerate(meals):
        raw_meal = meals_raw[i] if i < len(meals_raw) else {}
        story.append(_meal_block(i, meal.meal_name, meal.calories, raw_meal, styles))

    # ── Observações ───────────────────────────────────────────────────────────
    if notes:
        story.append(Spacer(1, 4))
        story.append(_section_title('Observações', styles))
        story.append(Spacer(1, 10))
        story.append(_notes_card(notes, styles))
        story.append(Spacer(1, 16))

    # ── Substituições ─────────────────────────────────────────────────────────
    substitutions = raw.get('substitutions', [])
    if substitutions:
        story.append(_section_title('Substituições Sugeridas', styles))
        story.append(Spacer(1, 10))
        for sub in substitutions:
            alts = ', '.join(sub.get('alternatives', []))
            story.append(Paragraph(
                f'<font color="#15803d"><b>{sub.get("food", "")}</b></font>'
                f' &nbsp;→&nbsp; <font color="#374151">{alts}</font>',
                styles['body'],
            ))
            story.append(Spacer(1, 6))
        story.append(Spacer(1, 8))

    # ── Disclaimer final ──────────────────────────────────────────────────────
    generated_at = datetime.now().strftime('%d/%m/%Y às %H:%M')
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width='100%', thickness=0.5, color=GRAY_200))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        f'Plano gerado em {generated_at}. Este documento é informativo e não '
        f'substitui a avaliação de um profissional de saúde.',
        styles['disclaimer'],
    ))

    doc.build(
        story,
        onFirstPage=_draw_decoration,
        onLaterPages=_draw_decoration,
    )
    return buffer.getvalue()
