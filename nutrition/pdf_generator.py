import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Brand colours ──────────────────────────────────────────────────────────────
GREEN       = colors.HexColor('#16a34a')
GREEN_LIGHT = colors.HexColor('#dcfce7')
GREEN_MID   = colors.HexColor('#86efac')
GRAY_900    = colors.HexColor('#111827')
GRAY_700    = colors.HexColor('#374151')
GRAY_500    = colors.HexColor('#6b7280')
GRAY_200    = colors.HexColor('#e5e7eb')
GRAY_50     = colors.HexColor('#f9fafb')
WHITE       = colors.white

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm


def _styles():
    base = getSampleStyleSheet()
    return {
        'title': ParagraphStyle(
            'title',
            fontName='Helvetica-Bold',
            fontSize=22,
            textColor=WHITE,
            leading=28,
        ),
        'subtitle': ParagraphStyle(
            'subtitle',
            fontName='Helvetica',
            fontSize=10,
            textColor=colors.HexColor('#bbf7d0'),
            leading=14,
        ),
        'section': ParagraphStyle(
            'section',
            fontName='Helvetica-Bold',
            fontSize=13,
            textColor=GRAY_900,
            spaceBefore=10,
            spaceAfter=6,
        ),
        'meal_name': ParagraphStyle(
            'meal_name',
            fontName='Helvetica-Bold',
            fontSize=11,
            textColor=GRAY_900,
        ),
        'meal_meta': ParagraphStyle(
            'meal_meta',
            fontName='Helvetica',
            fontSize=9,
            textColor=GRAY_500,
        ),
        'body': ParagraphStyle(
            'body',
            fontName='Helvetica',
            fontSize=9,
            textColor=GRAY_700,
            leading=13,
        ),
        'small': ParagraphStyle(
            'small',
            fontName='Helvetica',
            fontSize=8,
            textColor=GRAY_500,
            leading=11,
        ),
        'footer': ParagraphStyle(
            'footer',
            fontName='Helvetica',
            fontSize=8,
            textColor=GRAY_500,
            alignment=1,
        ),
    }


def _header_table(diet_plan, user_name: str, styles: dict):
    """Faixa verde do topo com nome do usuário, objetivo e data."""
    goal  = diet_plan.goal_description or 'Plano personalizado'
    kcal  = diet_plan.total_calories or '—'
    date  = diet_plan.created_at.strftime('%d/%m/%Y') if diet_plan.created_at else '—'

    title_para    = Paragraph('Seu Plano Alimentar', styles['title'])
    subtitle_para = Paragraph(
        f'Gerado por Inteligência Artificial &bull; {date}',
        styles['subtitle'],
    )
    goal_para   = Paragraph(f'Objetivo: <b>{goal}</b>', styles['subtitle'])
    kcal_para   = Paragraph(f'<b>{kcal:,}</b> kcal / dia'.replace(',', '.'), styles['subtitle'])

    left_col  = [title_para, Spacer(1, 4), subtitle_para, Spacer(1, 2), goal_para]
    right_col = [Spacer(1, 10), kcal_para]

    tbl = Table(
        [[left_col, right_col]],
        colWidths=[PAGE_W - 2 * MARGIN - 60 * mm, 60 * mm],
    )
    tbl.setStyle(TableStyle([
        ('BACKGROUND',  (0, 0), (-1, -1), GREEN),
        ('ROUNDEDCORNERS', [6]),
        ('TOPPADDING',  (0, 0), (-1, -1), 14),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 14),
        ('LEFTPADDING', (0, 0), (-1, -1), 16),
        ('RIGHTPADDING', (0, 0), (-1, -1), 16),
        ('VALIGN',      (0, 0), (-1, -1), 'TOP'),
        ('ALIGN',       (1, 0), (1, 0), 'RIGHT'),
    ]))
    return tbl


def _macros_table(macros: dict, styles: dict):
    """Caixa horizontal com proteína / carboidratos / gordura."""
    if not macros:
        return None

    def _cell(label, value, unit='g'):
        return [
            Paragraph(f'<b>{value}{unit}</b>', ParagraphStyle(
                'mv', fontName='Helvetica-Bold', fontSize=14,
                textColor=GREEN, alignment=1,
            )),
            Paragraph(label, ParagraphStyle(
                'ml', fontName='Helvetica', fontSize=8,
                textColor=GRAY_500, alignment=1,
            )),
        ]

    data = [[
        _cell('Proteína',     macros.get('protein_g', '—')),
        _cell('Carboidratos', macros.get('carbs_g',   '—')),
        _cell('Gordura',      macros.get('fat_g',     '—')),
    ]]

    tbl = Table(data, colWidths=[(PAGE_W - 2 * MARGIN) / 3] * 3)
    tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), GREEN_LIGHT),
        ('ROUNDEDCORNERS', [6]),
        ('TOPPADDING',    (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LINEAFTER',     (0, 0), (1, 0), 1, GREEN_MID),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    return tbl


def _meal_block(index: int, meal_name: str, calories: int,
                raw_meal: dict, styles: dict) -> list:
    """Retorna lista de flowables para uma refeição."""
    emojis = ['🌅', '🥗', '🍽️', '🥤', '🌙', '🍎', '🥑', '🫐']
    emoji  = emojis[index % len(emojis)]

    time_text = raw_meal.get('time_suggestion', '') if raw_meal else ''
    meta_text = f'{emoji}  Refeição {index + 1}'
    if time_text:
        meta_text += f'  •  {time_text}'

    elements = [
        Paragraph(meta_text, styles['meal_meta']),
        Spacer(1, 2),
        Paragraph(f'{meal_name}  —  <font color="#16a34a"><b>{calories} kcal</b></font>',
                  styles['meal_name']),
        Spacer(1, 6),
    ]

    foods = raw_meal.get('foods', []) if raw_meal else []

    if foods:
        header_row = [
            Paragraph('<b>Alimento</b>', ParagraphStyle(
                'th', fontName='Helvetica-Bold', fontSize=8, textColor=GRAY_500)),
            Paragraph('<b>Quantidade</b>', ParagraphStyle(
                'th', fontName='Helvetica-Bold', fontSize=8, textColor=GRAY_500, alignment=1)),
            Paragraph('<b>Kcal</b>', ParagraphStyle(
                'th', fontName='Helvetica-Bold', fontSize=8, textColor=GRAY_500, alignment=2)),
        ]
        rows = [header_row]
        for f in foods:
            qty = f.get('quantity') or (f'{f.get("quantity_g", "—")}g')
            rows.append([
                Paragraph(f.get('name', '—'), styles['body']),
                Paragraph(str(qty), ParagraphStyle(
                    'qty', fontName='Helvetica', fontSize=9,
                    textColor=GRAY_700, alignment=1)),
                Paragraph(str(f.get('calories', '—')), ParagraphStyle(
                    'kcal', fontName='Helvetica-Bold', fontSize=9,
                    textColor=GREEN, alignment=2)),
            ])

        col_w = PAGE_W - 2 * MARGIN
        tbl = Table(rows, colWidths=[col_w * 0.55, col_w * 0.25, col_w * 0.20])
        tbl.setStyle(TableStyle([
            ('BACKGROUND',    (0, 0), (-1, 0), GRAY_50),
            ('LINEBELOW',     (0, 0), (-1, 0), 0.5, GRAY_200),
            ('LINEBELOW',     (0, 1), (-1, -1), 0.3, GRAY_200),
            ('TOPPADDING',    (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING',   (0, 0), (-1, -1), 6),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 6),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(tbl)
    else:
        # fallback: descrição em texto corrido
        description = ''
        # Será preenchido pelo chamador se disponível
        elements.append(Paragraph('Detalhes não disponíveis.', styles['small']))

    elements.append(Spacer(1, 10))
    elements.append(HRFlowable(
        width='100%', thickness=0.5, color=GRAY_200, spaceAfter=10))
    return elements


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
        bottomMargin=MARGIN,
        title='Meu Plano Alimentar — MyNutri AI',
        author='MyNutri AI',
    )

    styles   = _styles()
    raw      = diet_plan.raw_response or {}
    macros   = raw.get('macros')
    notes    = raw.get('notes', '')
    meals_raw = raw.get('meals', [])

    story = []

    # ── Cabeçalho verde ────────────────────────────────────────────────────────
    story.append(_header_table(diet_plan, '', styles))
    story.append(Spacer(1, 14))

    # ── Macros ─────────────────────────────────────────────────────────────────
    macros_tbl = _macros_table(macros, styles)
    if macros_tbl:
        story.append(macros_tbl)
        story.append(Spacer(1, 18))

    # ── Refeições ──────────────────────────────────────────────────────────────
    story.append(Paragraph('Refeições do Dia', styles['section']))
    story.append(Spacer(1, 4))

    meals = list(diet_plan.meals.order_by('order'))
    for i, meal in enumerate(meals):
        raw_meal = meals_raw[i] if i < len(meals_raw) else {}
        story.extend(_meal_block(i, meal.meal_name, meal.calories, raw_meal, styles))

    # ── Notas ──────────────────────────────────────────────────────────────────
    if notes:
        story.append(Paragraph('Observações', styles['section']))
        story.append(Spacer(1, 4))
        story.append(Paragraph(notes, styles['body']))
        story.append(Spacer(1, 14))

    # ── Substituições ──────────────────────────────────────────────────────────
    substitutions = raw.get('substitutions', [])
    if substitutions:
        story.append(Paragraph('Substituições Sugeridas', styles['section']))
        story.append(Spacer(1, 4))
        for sub in substitutions:
            alts = ', '.join(sub.get('alternatives', []))
            story.append(Paragraph(
                f'<b>{sub.get("food", "")}</b> → {alts}',
                styles['body'],
            ))
            story.append(Spacer(1, 4))
        story.append(Spacer(1, 10))

    # ── Rodapé ─────────────────────────────────────────────────────────────────
    story.append(HRFlowable(width='100%', thickness=0.5, color=GRAY_200, spaceBefore=10))
    story.append(Spacer(1, 6))
    generated_at = datetime.now().strftime('%d/%m/%Y às %H:%M')
    story.append(Paragraph(
        f'Gerado pelo MyNutri AI em {generated_at} &bull; mynutriai.app',
        styles['footer'],
    ))

    doc.build(story)
    return buffer.getvalue()
