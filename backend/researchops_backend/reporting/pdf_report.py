from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from io import BytesIO
from html import escape
import textwrap

from reportlab.graphics.shapes import Drawing, Rect, Line, String
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
)


CHART_COLORS=[colors.HexColor('#2563EB'),colors.HexColor('#64748B'),colors.HexColor('#16A34A')]

def _title(drawing,title):
    drawing.add(String(12,drawing.height-18,title,fontName='ResearchOpsSans-Bold',fontSize=11))

def _forecast_chart(forecast):
    if not forecast or not forecast.get('available'):return None
    series=[]
    if forecast.get('method')=='evidence-based-scenario':
        series=[(name.title(),[(p['year'],p['value']) for p in obj.get('series',[])]) for name,obj in forecast.get('scenarios',{}).items()]
    elif forecast.get('method')=='ridge-log-trend-ml':
        rows=forecast.get('forecast',[])
        series=[(name,[(r['year'],r[key]) for r in rows]) for name,key in [('Predicted','predicted'),('P10','p10'),('P90','p90')]]
    series=[(name,points) for name,points in series if points]
    if not series:return None
    d=Drawing(460,225);_title(d,'Forecast summary')
    plot=LinePlot();plot.x=62;plot.y=48;plot.width=380;plot.height=132
    plot.data=[points for _,points in series]
    plot.xValueAxis.labelTextFormat=lambda value:str(int(value))
    plot.xValueAxis.labels.fontName=plot.yValueAxis.labels.fontName='ResearchOpsSans'
    plot.xValueAxis.labels.fontSize=plot.yValueAxis.labels.fontSize=7
    plot.yValueAxis.valueMin=0
    for i,(name,_) in enumerate(series):
        plot.lines[i].strokeColor=CHART_COLORS[i%3];plot.lines[i].strokeWidth=1.7
        d.add(Line(62+i*120,16,78+i*120,16,strokeColor=CHART_COLORS[i%3],strokeWidth=2))
        d.add(String(82+i*120,13,name,fontName='ResearchOpsSans',fontSize=8))
    d.add(plot)
    d.add(String(240,32,'Year' if forecast.get('method')=='ridge-log-trend-ml' else 'Years from baseline',fontName='ResearchOpsSans',fontSize=8,textAnchor='middle'))
    return d

def _bars(labels,values,title,maximum,width=460):
    height=66+len(labels)*30;d=Drawing(width,height);_title(d,title)
    left=225;bar_width=width-left-36
    for i,(label,value) in enumerate(zip(labels,values)):
        y=height-47-i*30
        d.add(String(12,y+3,textwrap.shorten(label,width=36,placeholder='...'),fontName='ResearchOpsSans',fontSize=8))
        d.add(Rect(left,y,bar_width,13,fillColor=colors.HexColor('#E2E8F0'),strokeColor=None))
        d.add(Rect(left,y,bar_width*max(0,min(maximum,value))/maximum,13,fillColor=CHART_COLORS[0],strokeColor=None))
        d.add(String(width-29,y+3,f'{value:.0f}',fontName='ResearchOpsSans',fontSize=8))
    d.add(String(left,12,f'Score / {maximum}',fontName='ResearchOpsSans',fontSize=8))
    return d

def _risk_chart(risk):
    rows=(risk or {}).get('risks',[])[:8]
    if not rows:return None
    return _bars([r.get('text','Risk') for r in rows],[r.get('score',0) for r in rows],'Priority risk summary',25)

def _quality_chart(quality):
    if not quality:return None
    return _bars(['Verification','Source quality','Domain diversity','Evidence coverage'],[
        quality.get('verification_rate',0),quality.get('average_source_quality',0)*100,
        quality.get('domain_diversity_score',0),quality.get('evidence_coverage_score',0)],'Research quality indicators',100)


def build_pdf_report(result: dict) -> bytes:
    font_dir = Path(__file__).with_name('fonts')
    if 'ResearchOpsSans' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('ResearchOpsSans', str(font_dir / 'DejaVuSans.ttf')))
        pdfmetrics.registerFont(TTFont('ResearchOpsSans-Bold', str(font_dir / 'DejaVuSans-Bold.ttf')))
        pdfmetrics.registerFontFamily('ResearchOpsSans',normal='ResearchOpsSans',bold='ResearchOpsSans-Bold',italic='ResearchOpsSans',boldItalic='ResearchOpsSans-Bold')
    out = BytesIO()
    doc = SimpleDocTemplate(
        out, pagesize=A4, rightMargin=42, leftMargin=42, topMargin=46, bottomMargin=42,
        title='ResearchOps Decision Research Report'
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='TitleCenter', parent=styles['Title'], alignment=TA_CENTER, fontName='ResearchOpsSans-Bold', fontSize=20, leading=24, textColor=colors.black, spaceAfter=12))
    styles.add(ParagraphStyle(name='H2Black', parent=styles['Heading2'], fontName='ResearchOpsSans-Bold', fontSize=13, leading=16, textColor=colors.black, spaceBefore=10, spaceAfter=6))
    styles.add(ParagraphStyle(name='BodyBlack', parent=styles['BodyText'], fontName='ResearchOpsSans', fontSize=9.4, leading=13, textColor=colors.black, spaceAfter=6))
    styles.add(ParagraphStyle(name='SmallBlack', parent=styles['BodyText'], fontName='ResearchOpsSans', fontSize=7.6, leading=10, textColor=colors.black, spaceAfter=4))
    styles.add(ParagraphStyle(name='Callout', parent=styles['BodyText'], fontName='ResearchOpsSans-Bold', fontSize=10, leading=14, textColor=colors.black, borderColor=colors.HexColor('#CBD5E1'), borderWidth=0.7, borderPadding=8, backColor=colors.HexColor('#F8FAFC'), spaceAfter=10))

    story = [
        Paragraph('ResearchOps Decision Research Report', styles['TitleCenter']),
        Paragraph(f"<b>Problem statement:</b> {escape(result.get('question',''))}", styles['BodyBlack']),
    ]
    opts = result.get('request_options', {})
    sweep = result.get('research_sweep', {})
    story.append(Paragraph(
        f"<b>Forecast horizon:</b> {opts.get('forecast_years', 5)} year(s) &nbsp;&nbsp; "
        f"<b>Research depth:</b> {escape(str(opts.get('research_mode', sweep.get('mode','Deep'))))} &nbsp;&nbsp; "
        f"<b>Processing:</b> {escape(result.get('mapreduce',{}).get('engine',''))}",
        styles['BodyBlack']))
    if sweep:
        story.append(Paragraph(
            f"Adaptive web sweep: <b>{sweep.get('queries_executed',0)} queries</b>, "
            f"<b>{sweep.get('unique_sources',0)} unique sources</b>, "
            f"<b>{sweep.get('unique_domains',0)} domains</b>. Stop reason: {escape(str(sweep.get('stop_reason','completed')).replace('-', ' '))}.",
            styles['SmallBlack']))

    quality = result.get('research_quality', {})
    if quality:
        data = [
            ['Decision readiness', 'Verified findings', 'Unique domains', 'Avg. source quality'],
            [Paragraph(escape(f"{quality.get('readiness_score',0)}/100 ({quality.get('band','')})"), styles['SmallBlack']), str(result.get('metrics',{}).get('verified_findings',0)), str(quality.get('unique_domains',0)), f"{quality.get('average_source_quality',0)*100:.0f}%"]
        ]
        table = Table(data, colWidths=[1.6*inch, 1.4*inch, 1.35*inch, 1.6*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#EEF2F7')),
            ('TEXTCOLOR',(0,0),(-1,-1),colors.black),
            ('FONTNAME',(0,0),(-1,0),'ResearchOpsSans-Bold'),
            ('FONTNAME',(0,1),(-1,-1),'ResearchOpsSans'),
            ('FONTSIZE',(0,0),(-1,-1),8),
            ('GRID',(0,0),(-1,-1),0.4,colors.HexColor('#CBD5E1')),
            ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
            ('ALIGN',(0,0),(-1,-1),'CENTER'),
            ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),
        ]))
        story += [Spacer(1, 6), table, Spacer(1, 10)]
        qchart = _quality_chart(quality)
        if qchart: story += [qchart, Spacer(1, 8)]

    syn = result.get('synthesis', {})
    story += [Paragraph('Executive Summary', styles['H2Black']), Paragraph(escape(syn.get('executive_summary','No executive summary available.')), styles['BodyBlack'])]

    advice = result.get('decision_suggestion') or {}
    if advice.get('enabled'):
        story += [Paragraph('AI Decision Suggestion', styles['H2Black'])]
        story.append(Paragraph(
            f"<b>{escape(advice.get('stance',''))}</b> &nbsp; | &nbsp; Confidence: {advice.get('confidence',0)}%<br/>{escape(advice.get('summary',''))}",
            styles['Callout']))
        for r in advice.get('reasons', []):
            refs = ', '.join(r.get('source_ids', []))
            story.append(Paragraph(f"• {escape(r.get('text',''))} <font size='7'>[{escape(refs)}]</font>", styles['BodyBlack']))
        if advice.get('conditions'):
            story.append(Paragraph('<b>Conditions before acting</b>', styles['BodyBlack']))
            for x in advice['conditions']:
                story.append(Paragraph(f"• {escape(x)}", styles['BodyBlack']))
        if advice.get('action_plan'):
            story.append(Paragraph('<b>Recommended action plan</b>', styles['BodyBlack']))
            for x in advice['action_plan']:
                refs = ', '.join(x.get('source_ids', []))
                detail = f"<b>{escape(x.get('priority','Next'))}: {escape(x.get('action',''))}</b>"
                if x.get('timeframe'):
                    detail += f" — {escape(x.get('timeframe',''))}"
                if x.get('why'):
                    detail += f"<br/>Why: {escape(x.get('why',''))}"
                if x.get('expected_effect'):
                    detail += f"<br/>Expected effect: {escape(x.get('expected_effect',''))}"
                if refs:
                    detail += f" <font size='7'>[{escape(refs)}]</font>"
                story.append(Paragraph('• ' + detail, styles['BodyBlack']))
        elif advice.get('next_actions'):
            story.append(Paragraph('<b>Recommended next actions</b>', styles['BodyBlack']))
            for x in advice['next_actions']:
                story.append(Paragraph(f"• {escape(x)}", styles['BodyBlack']))
        if advice.get('success_metrics'):
            story.append(Paragraph('<b>Success metrics</b>', styles['BodyBlack']))
            for x in advice['success_metrics']:
                story.append(Paragraph(f"• {escape(x)}", styles['BodyBlack']))
        if advice.get('reconsider_if'):
            story.append(Paragraph('<b>Reconsider if</b>', styles['BodyBlack']))
            for x in advice['reconsider_if']:
                story.append(Paragraph(f"• {escape(x)}", styles['BodyBlack']))
        story.append(Paragraph(escape(advice.get('note','')), styles['SmallBlack']))

    conflicts = result.get('evidence_conflicts', [])
    coverage = result.get('research_coverage', {})
    if conflicts:
        story += [Paragraph('Evidence Conflicts', styles['H2Black'])]
        for x in conflicts:
            story.append(Paragraph(
                f"• <b>{escape(str(x.get('severity','medium')).title())} — {escape(x.get('topic','Conflict'))}</b>: {escape(x.get('description',''))}<br/>Resolution needed: {escape(x.get('resolution_needed',''))}",
                styles['BodyBlack']))
    if coverage.get('tasks'):
        coverage_block = [Paragraph('Research Coverage', styles['H2Black'])]
        for x in coverage['tasks']:
            coverage_block.append(Paragraph(
                f"• <b>{escape(x.get('task_id',''))} — {escape(x.get('topic',''))}</b>: {escape(x.get('status',''))}; {x.get('sources_found',0)} sources; {x.get('verified_findings',0)} verified findings.",
                styles['BodyBlack']))
        story += [KeepTogether(coverage_block)] if len(coverage['tasks']) <= 8 else coverage_block

    story += [Paragraph('Verified Findings', styles['H2Black'])]
    if not result.get('verified_findings'):
        story.append(Paragraph('No claim passed the evidence checks.', styles['BodyBlack']))
    for f in result.get('verified_findings', []):
        refs = ', '.join(f.get('source_ids', []))
        story.append(Paragraph(f"• {escape(f.get('claim',''))} <font size='7'>[{escape(refs)}]</font>", styles['BodyBlack']))

    story += [Paragraph('Business Opportunities', styles['H2Black'])]
    if not syn.get('opportunities'):
        story.append(Paragraph('No sufficiently supported opportunity was identified.', styles['BodyBlack']))
    for x in syn.get('opportunities', []):
        story.append(Paragraph(f"• <b>{escape(x.get('text',''))}</b> - {escape(x.get('rationale',''))}", styles['BodyBlack']))

    risk = result.get('risk_assessment', {})
    story += [Paragraph('Risk Analysis', styles['H2Black']), Paragraph(f"Aggregate risk score: <b>{str(risk.get('overall_score'))+'/100' if risk.get('overall_score') is not None else 'Not assessed'} - {escape(str(risk.get('band','Unknown')))}</b>", styles['BodyBlack'])]
    rchart = _risk_chart(risk)
    if rchart: story += [rchart, Spacer(1, 8)]
    for x in risk.get('risks', []):
        story.append(Paragraph(
            f"• <b>{escape(x.get('text',''))}</b> - likelihood {x.get('likelihood',0)}/5, impact {x.get('impact',0)}/5, score {x.get('score',0)}/25. Mitigation: {escape(x.get('mitigation',''))}",
            styles['BodyBlack']))

    forecast = result.get('forecast', {})
    forecast_block = [Paragraph('Forecast', styles['H2Black']), Paragraph(escape(forecast.get('warning') or forecast.get('message','')), styles['BodyBlack'])]
    fchart = _forecast_chart(forecast)
    if fchart: forecast_block += [fchart, Spacer(1, 8)]
    if forecast.get('method') == 'evidence-based-scenario':
        rows = [['Scenario', 'Annual rate', 'End value']]
        for name, obj in forecast.get('scenarios', {}).items():
            series = obj.get('series', [])
            rows.append([name.title(), f"{obj.get('annual_rate',0)*100:.2f}%", f"{series[-1]['value']:.2f}" if series else '-'])
        t = Table(rows, colWidths=[1.8*inch, 1.8*inch, 1.8*inch], repeatRows=1)
        t.setStyle(TableStyle([('TEXTCOLOR',(0,0),(-1,-1),colors.black),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#EEF2F7')),('FONTNAME',(0,0),(-1,-1),'ResearchOpsSans'),('FONTNAME',(0,0),(-1,0),'ResearchOpsSans-Bold'),('GRID',(0,0),(-1,-1),0.35,colors.HexColor('#CBD5E1')),('FONTSIZE',(0,0),(-1,-1),8),('ALIGN',(1,1),(-1,-1),'RIGHT')]))
        forecast_block.append(t)
    elif forecast.get('method') == 'ridge-log-trend-ml':
        rows = [['Year', 'Predicted', 'P10', 'P90']] + [[str(r['year']), f"{r['predicted']:.2f}", f"{r['p10']:.2f}", f"{r['p90']:.2f}"] for r in forecast.get('forecast', [])]
        t = Table(rows, colWidths=[1.2*inch,1.4*inch,1.4*inch,1.4*inch], repeatRows=1)
        t.setStyle(TableStyle([('TEXTCOLOR',(0,0),(-1,-1),colors.black),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#EEF2F7')),('FONTNAME',(0,0),(-1,-1),'ResearchOpsSans'),('FONTNAME',(0,0),(-1,0),'ResearchOpsSans-Bold'),('GRID',(0,0),(-1,-1),0.35,colors.HexColor('#CBD5E1')),('FONTSIZE',(0,0),(-1,-1),8),('ALIGN',(1,1),(-1,-1),'RIGHT')]))
        forecast_block.append(t)
    story += [KeepTogether(forecast_block)]

    story += [Paragraph('Decision Questions', styles['H2Black'])]
    if not syn.get('decision_questions'):
        story.append(Paragraph('No additional decision question was produced.', styles['BodyBlack']))
    for x in syn.get('decision_questions', []):
        story.append(Paragraph(f"• {escape(str(x))}", styles['BodyBlack']))

    story += [Paragraph('Limitations', styles['H2Black'])]
    for x in syn.get('limitations', []):
        story.append(Paragraph(f"• {escape(str(x))}", styles['BodyBlack']))
    story.append(Paragraph(escape(result.get('verification_note','')), styles['SmallBlack']))

    story += [Paragraph('Source Register', styles['H2Black'])]
    for s in result.get('source_catalog', []):
        url = escape(s.get('url',''), quote=True)
        title = escape(s.get('title','Untitled'))
        domain = escape(s.get('domain',''))
        sid = escape(s.get('source_id',''))
        story.append(Paragraph(f"<b>{sid}</b> - {title} - {domain}<br/><link href='{url}' color='black'>{url}</link>", styles['SmallBlack']))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont('ResearchOpsSans', 7)
        canvas.setFillColor(colors.HexColor('#64748B'))
        canvas.drawString(42, 24, 'ResearchOps • Evidence and scenario estimates require review')
        canvas.drawRightString(A4[0]-42, 24, str(document.page))
        canvas.restoreState()
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return out.getvalue()
