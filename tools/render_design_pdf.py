"""Render the current design Markdown to a CJK PDF and verify document links."""
from pathlib import Path
import argparse
import hashlib
import html
import json
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Preformatted,
)
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'


def inline(text):
    # Escape source prose before introducing controlled ReportLab markup.
    text = html.escape(text)
    def link(match):
        label, target = match.groups()
        if target.startswith(('https://', 'http://')):
            return f'<a href="{target}" color="#205E83">{label}</a>'
        return label
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', link, text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    return re.sub(r'`([^`]+)`', r'\1', text)


def run(preview_dir=None):
    source = DOCS / 'CyberArm_设计文档.md'
    target = source.with_suffix('.pdf')
    text = source.read_text(encoding='utf-8')
    pdfmetrics.registerFont(TTFont('CJK', 'C:/Windows/Fonts/simhei.ttf'))
    pdfmetrics.registerFontFamily('CJK', normal='CJK', bold='CJK', italic='CJK', boldItalic='CJK')
    base = dict(fontName='CJK', wordWrap='CJK', alignment=TA_LEFT)
    body = ParagraphStyle('Body', fontSize=10, leading=16, spaceAfter=7, **base)
    title = ParagraphStyle('Title', fontSize=21, leading=29, spaceAfter=14, textColor=colors.HexColor('#16394D'), **base)
    heading = ParagraphStyle('Heading', fontSize=13, leading=20, spaceBefore=12, spaceAfter=7, keepWithNext=True, textColor=colors.HexColor('#16394D'), **base)
    cell = ParagraphStyle('Cell', fontSize=8.4, leading=12.6, **base)
    code_style = ParagraphStyle('Code', fontName='CJK', fontSize=8.5, leading=14, backColor=colors.HexColor('#F1F5F7'), borderPadding=8, spaceAfter=10)
    story = []
    lines = text.splitlines()
    width = A4[0] - 84
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line.startswith('```'):
            block = []
            i += 1
            while i < len(lines) and not lines[i].startswith('```'):
                block.append(lines[i])
                i += 1
            story.append(Preformatted('\n'.join(block), code_style))
        elif line.startswith('|'):
            rows = []
            while i < len(lines) and lines[i].startswith('|'):
                values = [v.strip() for v in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?', v) for v in values):
                    rows.append([Paragraph(inline(v), cell) for v in values])
                i += 1
            n = len(rows[0])
            proportions = {3: [0.20, 0.34, 0.46], 4: [0.20, 0.35, 0.30, 0.15], 5: [0.06, 0.16, 0.14, 0.53, 0.11]}.get(n, [1 / n] * n)
            table = Table(rows, colWidths=[width * p for p in proportions], repeatRows=1, hAlign='LEFT')
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#DCEAF0')),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F6F8FA')]),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 6),
                ('RIGHTPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 7),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
                ('LINEBELOW', (0, 0), (-1, 0), 0.7, colors.HexColor('#A5BEC9')),
            ]))
            story.extend([table, Spacer(1, 10)])
            continue
        elif line.startswith('# '):
            story.append(Paragraph(inline(line[2:]), title))
        elif line.startswith('## '):
            story.append(Paragraph(inline(line[3:]), heading))
        else:
            story.append(Paragraph(inline(line), body))
        i += 1

    def page(canvas, doc):
        canvas.saveState()
        canvas.setFont('CJK', 8)
        canvas.setFillColor(colors.HexColor('#5D7480'))
        canvas.drawString(42, 24, 'CyberArm  |  设计基线 2.0  |  2026-09-14')
        canvas.drawRightString(A4[0] - 42, 24, str(doc.page))
        canvas.restoreState()

    doc = SimpleDocTemplate(str(target), pagesize=A4, rightMargin=42, leftMargin=42,
                            topMargin=40, bottomMargin=44, title='CyberArm 机械臂系统设计文档 2.0', author='CyberArm')
    doc.build(story, onFirstPage=page, onLaterPages=page)
    reader = PdfReader(str(target))
    extracted = '\n'.join(p.extract_text() or '' for p in reader.pages)
    assert '条件可达' in extracted and '固件方案摘要' in extracted and '文档与交付' in extracted
    active_docs = [source, DOCS/'K230D_SYSTEM_DESIGN.md', DOCS/'固件实现方案.md', DOCS/'技术决策与问题记录.md']
    broken = []
    stale = []
    for path in active_docs:
        content = path.read_text(encoding='utf-8')
        for label, url in re.findall(r'\[([^\]]+)\]\(([^)]+)\)', content):
            if not url.startswith(('http://', 'https://', '#')):
                resolved = (path.parent / url.split('#')[0]).resolve()
                if not resolved.exists():
                    broken.append({'file':path.name, 'target':url})
        for term in ['四个运动关节', '五路 MG90S', '4 个关节 + 1 个夹爪', '水平半径 ≥15']:
            if term in content:
                stale.append({'file':path.name, 'term':term})
    assert not broken, broken
    assert not stale, stale
    report = {'design_version':'2.0', 'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
              'pdf_sha256':hashlib.sha256(target.read_bytes()).hexdigest(), 'pages':len(reader.pages),
              'checked_documents':[p.name for p in active_docs], 'broken_local_links':broken,
              'stale_configuration_terms':stale, 'pdf_text_checks':'passed',
              'scope':'Documentation synchronization only; no robot software or hardware tests performed.'}
    (DOCS/'文档同步检查.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    if preview_dir:
        import pypdfium2 as pdfium
        from PIL import Image
        out = Path(preview_dir)
        out.mkdir(parents=True, exist_ok=True)
        pdf = pdfium.PdfDocument(str(target))
        indices = sorted(set([0, len(pdf)//2, len(pdf)-1]))
        images = [pdf[k].render(scale=1).to_pil().convert('RGB') for k in indices]
        canvas = Image.new('RGB', (sum(im.width for im in images), max(im.height for im in images)), 'white')
        x = 0
        for im in images:
            canvas.paste(im, (x, 0))
            x += im.width
        canvas.save(out/'design_v2_preview.png')
        report['preview_pages'] = [k+1 for k in indices]
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--preview-dir')
    run(parser.parse_args().preview_dir)
