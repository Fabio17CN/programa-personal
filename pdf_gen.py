import os
import json
from datetime import datetime
from PIL import Image as PILImage

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepTogether
)

BASE_DIR = os.path.dirname(__file__)
LOGO_PADRAO = os.path.join(BASE_DIR, "static", "icon-192.png")

# Paleta baseada no modelo enviado pelo cliente (cabeçalho escuro / faixas azuis)
DARK = colors.HexColor("#0F172A")
DARK_2 = colors.HexColor("#1E293B")
PRIMARY = colors.HexColor("#3B82F6")
PRIMARY_LIGHT = colors.HexColor("#60A5FA")
SUBTEXT = colors.HexColor("#64748B")
ALERT = colors.HexColor("#B91C1C")
LINE = colors.HexColor("#CBD5E1")
ROW_BG = colors.HexColor("#F1F5F9")
WHITE = colors.white

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TituloRel", fontSize=17, textColor=WHITE, fontName="Helvetica-Bold", leading=20))
styles.add(ParagraphStyle(name="SubtituloRel", fontSize=9.5, textColor=colors.HexColor("#CBD5E1"), fontName="Helvetica-Oblique"))
styles.add(ParagraphStyle(name="ContatoRel", fontSize=8.5, textColor=colors.HexColor("#94A3B8"), alignment=TA_CENTER))
styles.add(ParagraphStyle(name="SecaoRel", fontSize=11, textColor=WHITE, fontName="Helvetica-Bold", spaceBefore=0, spaceAfter=0))
styles.add(ParagraphStyle(name="AlertaRel", fontSize=9, textColor=ALERT, spaceBefore=4, spaceAfter=4))
styles.add(ParagraphStyle(name="OkRel", fontSize=9, textColor=colors.HexColor("#059669"), spaceBefore=2, spaceAfter=2))
styles.add(ParagraphStyle(name="LeveRel", fontSize=9, textColor=colors.HexColor("#B45309"), spaceBefore=2, spaceAfter=2))
styles.add(ParagraphStyle(name="ModeradaRel", fontSize=9, textColor=colors.HexColor("#C2410C"), spaceBefore=2, spaceAfter=2))
styles.add(ParagraphStyle(name="ResumoRel", fontSize=9.5, textColor=DARK, fontName="Helvetica-Bold", spaceBefore=6, spaceAfter=2))
styles.add(ParagraphStyle(name="TextoNormal", fontSize=9.5, textColor=DARK, leading=13))
styles.add(ParagraphStyle(name="LegendaFoto", fontSize=11, textColor=DARK, fontName="Helvetica-Bold", spaceBefore=4))
styles.add(ParagraphStyle(name="BadgeTexto", fontSize=13, textColor=WHITE, fontName="Helvetica-Bold", alignment=TA_CENTER))
styles.add(ParagraphStyle(name="BadgeLegenda", fontSize=7.5, textColor=WHITE, alignment=TA_CENTER))
styles.add(ParagraphStyle(name="MedidaChip", fontSize=8, textColor=SUBTEXT))
styles.add(ParagraphStyle(name="SubtituloItalico", fontSize=7.5, textColor=SUBTEXT, fontName="Helvetica-Oblique", leading=10))
styles.add(ParagraphStyle(name="CelulaExercicio", fontSize=9, textColor=DARK, leading=12))

COR_OK = colors.HexColor("#059669")
COR_LEVE = colors.HexColor("#B45309")
COR_MODERADA = colors.HexColor("#C2410C")
COR_ACENTUADA = colors.HexColor("#B91C1C")


def _cor_classificacao(rotulo):
    """Cor consistente pra qualquer classificação (IMC, % gordura, RCQ) —
    verde quando está dentro do esperado, laranja de atenção, vermelho de risco.
    Devolve string hex (#RRGGBB) pra usar direto em markup de Paragraph."""
    if not rotulo:
        return "#64748B"
    r = rotulo.lower()
    if any(p in r for p in ["normal", "atlético", "bom", "baixo risco", "dentro do esperado"]):
        return "#059669"
    if any(p in r for p in ["sobrepeso", "aceitável", "moderad", "muito baixo", "leve"]):
        return "#B45309"
    return "#B91C1C"  # obesidade, elevado, risco alto, acentuada...


def _cor_gravidade_pdf(gravidade):
    return {"dentro do esperado": COR_OK, "leve": COR_LEVE, "moderada": COR_MODERADA,
            "acentuada": COR_ACENTUADA}.get(gravidade, SUBTEXT)


def _selo_placar(pontuacao, gravidade_geral):
    """Selo colorido (verde/amarelo/laranja/vermelho) com o placar de 0-100,
    em vez de um texto solto — dá um acabamento bem mais profissional."""
    cor = _cor_gravidade_pdf(gravidade_geral)
    rotulos = {"dentro do esperado": "DENTRO DO ESPERADO", "leve": "ASSIMETRIA LEVE",
               "moderada": "ASSIMETRIA MODERADA", "acentuada": "ASSIMETRIA ACENTUADA"}
    selo = Table([[Paragraph(f"{pontuacao}/100", styles["BadgeTexto"])],
                  [Paragraph(rotulos.get(gravidade_geral, ""), styles["BadgeLegenda"])]],
                 colWidths=[4.2 * cm])
    selo.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), cor),
        ("TOPPADDING", (0, 0), (-1, 0), 8), ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
        ("TOPPADDING", (0, 1), (-1, 1), 0), ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    return selo


def _nome_arquivo_logo(personal):
    caminho = (personal or {}).get("logo_path")
    if caminho and os.path.exists(caminho):
        return caminho
    if os.path.exists(LOGO_PADRAO):
        return LOGO_PADRAO
    return None


def _cabecalho(titulo, personal, extra_direita=""):
    """Monta a barra escura de topo com logo + título + nome do personal + contato,
    igual ao modelo (fundo #0F172A, logo à esquerda, texto à direita)."""
    logo_path = _nome_arquivo_logo(personal)
    nome_personal = personal.get("nome_exibicao") or personal.get("usuario") or "Personal Trainer"

    if logo_path:
        logo_cell = Image(logo_path, width=2.4 * cm, height=2.4 * cm)
    else:
        logo_cell = Paragraph("", styles["TextoNormal"])

    texto_cell = [
        Paragraph(titulo.upper(), styles["TituloRel"]),
        Paragraph(f"Personal: {nome_personal}" + (f"  |  CREF: {personal['cref']}" if personal.get("cref") else ""),
                   styles["SubtituloRel"]),
    ]
    if extra_direita:
        texto_cell.append(Paragraph(extra_direita, styles["SubtituloRel"]))

    tabela = Table([[logo_cell, texto_cell]], colWidths=[3 * cm, 13 * cm])
    tabela.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), DARK),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, 0), "CENTER"),
        ("LEFTPADDING", (0, 0), (0, 0), 10),
        ("LEFTPADDING", (1, 0), (1, 0), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))

    linhas = [tabela]

    contatos = []
    if personal.get("telefone"):
        contatos.append(f'<font color="#94A3B8">WhatsApp: {personal["telefone"]}</font>')
    if personal.get("instagram"):
        arroba = personal["instagram"] if personal["instagram"].startswith("@") else f"@{personal['instagram']}"
        contatos.append(f'<font color="#60A5FA"><b>Instagram: {arroba}</b></font>')
    slogan = personal.get("slogan") or "Treinamento personalizado, resultado de verdade."

    rodape_txt = "  •  ".join(contatos) if contatos else ""
    faixa = Table([[Paragraph(f'<i>{slogan}</i>', styles["ContatoRel"])],
                    [Paragraph(rodape_txt, styles["ContatoRel"])] if rodape_txt else [Paragraph("", styles["ContatoRel"])]],
                   colWidths=[16 * cm])
    faixa.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), DARK_2),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    linhas.append(faixa)
    return linhas


def _faixa_secao(titulo):
    t = Table([[Paragraph(titulo, styles["SecaoRel"])]], colWidths=[17 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PRIMARY),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
    ]))
    return t


def _faixa_secao_com_selo(letra, titulo):
    """Faixa de seção com um selo quadrado destacando a letra do treino
    (A, B, C...) à esquerda — dá mais identidade visual pra cada dia."""
    selo = Table([[Paragraph(f"<b>{letra}</b>", styles["BadgeTexto"])]], colWidths=[1.1 * cm], rowHeights=[1.1 * cm])
    selo.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), DARK),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    faixa = Table([[Paragraph(titulo, styles["SecaoRel"])]], colWidths=[15.9 * cm], rowHeights=[1.1 * cm])
    faixa.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PRIMARY),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
    ]))
    linha = Table([[selo, faixa]], colWidths=[1.1 * cm, 15.9 * cm])
    linha.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return linha


GIFS_DIR = os.path.join(os.path.dirname(__file__), "static", "exercicios", "gifs")
GIFS_CACHE_DIR = os.path.join(os.path.dirname(__file__), "uploads", "_gifs_exercicios_cache")


def _obter_frame_gif_exercicio(nome_gif):
    """Pega o primeiro quadro do GIF de demonstração do exercício (biblioteca
    pública MIT — github.com/mohamedatef90/exercise-library, já embutida no
    projeto em static/exercicios/gifs) e devolve o caminho de uma imagem
    estática pra usar no PDF. Guarda em cache pra não converter de novo toda
    vez. Se o arquivo não existir, devolve None silenciosamente — o PDF sai
    normal, só sem a imagem desse exercício."""
    if not nome_gif:
        return None
    try:
        caminho_gif = os.path.join(GIFS_DIR, nome_gif)
        if not os.path.exists(caminho_gif):
            return None

        os.makedirs(GIFS_CACHE_DIR, exist_ok=True)
        nome_base = os.path.splitext(os.path.basename(nome_gif))[0]
        caminho_png = os.path.join(GIFS_CACHE_DIR, f"{nome_base}.png")
        if os.path.exists(caminho_png):
            return caminho_png

        with PILImage.open(caminho_gif) as img:
            img.seek(0)  # primeiro quadro do GIF animado
            img.convert("RGB").save(caminho_png)
        return caminho_png
    except (OSError, ValueError) as e:
        print(f"Aviso: não foi possível processar o GIF do exercício '{nome_gif}': {e}")
        return None


def _linha_tabela(label, valor, sufixo=""):
    if valor in (None, ""):
        return [label, "-"]
    return [label, f"{valor}{sufixo}"]


def _grafico_evolucao(avaliacoes, campo, titulo, caminho_saida):
    datas, valores = [], []
    for a in avaliacoes:
        if a.get(campo) is not None:
            datas.append(a["data"][:10])
            valores.append(a[campo])
    if len(valores) < 1:
        return None
    plt.figure(figsize=(6, 2.6))
    plt.plot(datas, valores, marker="o", color="#3B82F6", linewidth=2)
    plt.title(titulo, fontsize=10, color="#0F172A")
    plt.xticks(rotation=30, ha="right", fontsize=7)
    plt.yticks(fontsize=7)
    plt.grid(alpha=0.25)
    plt.tight_layout()
    plt.savefig(caminho_saida, dpi=150)
    plt.close()
    return caminho_saida


def _grafico_composicao(massa_magra, massa_gorda, bf, sexo, caminho_saida):
    """Gráfico de composição corporal em estilo 'donut', com o percentual real
    de gordura no centro, a classificação (que é diferente para homem e mulher)
    e os valores reais de massa magra/gorda em kg na legenda — bem mais
    informativo e estiloso que uma pizza simples."""
    if bf is None:
        return None
    import calculos
    gordura_pct = float(bf)
    magra_pct = max(0.0, 100 - gordura_pct)
    classificacao = calculos.classificar_bf(gordura_pct, sexo) or ""

    cor_gordura, cor_magra = "#F97316", "#3B82F6"
    fig, ax = plt.subplots(figsize=(3.6, 3.6))
    wedges, _ = ax.pie(
        [gordura_pct, magra_pct], colors=[cor_gordura, cor_magra], startangle=90,
        wedgeprops={"width": 0.38, "edgecolor": "white", "linewidth": 2.5},
    )
    ax.text(0, 0.12, f"{gordura_pct:.1f}%", ha="center", va="center",
            fontsize=20, fontweight="bold", color="#0F172A")
    ax.text(0, -0.14, "GORDURA CORPORAL", ha="center", va="center",
            fontsize=6.5, color="#64748B", fontweight="bold")
    if classificacao:
        ax.text(0, -0.32, classificacao.upper(), ha="center", va="center",
                fontsize=7.5, color=cor_gordura, fontweight="bold")
    ax.axis("equal")

    if massa_magra is not None and massa_gorda is not None:
        plt.figtext(0.5, 0.06, f"Massa Magra: {massa_magra:.1f} kg  |  Massa Gorda: {massa_gorda:.1f} kg",
                     ha="center", fontsize=7.3, color="#334155", fontweight="bold")

    plt.subplots_adjust(bottom=0.16)
    plt.savefig(caminho_saida, dpi=170, transparent=True, bbox_inches="tight")
    plt.close()
    return caminho_saida


def _rodape(canvas, doc):
    """Rodapé profissional: linha fina + numeração de página em todas as folhas."""
    canvas.saveState()
    largura, altura = A4
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(0.6)
    canvas.line(1.6 * cm, 1.3 * cm, largura - 1.6 * cm, 1.3 * cm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(SUBTEXT)
    canvas.drawString(1.6 * cm, 0.9 * cm, "Documento gerado digitalmente — uso exclusivo do aluno e do profissional.")
    canvas.drawRightString(largura - 1.6 * cm, 0.9 * cm, f"Página {doc.page}")
    # friso superior fino, dá um acabamento de "capa" em todas as páginas
    canvas.setFillColor(PRIMARY)
    canvas.rect(0, altura - 0.18 * cm, largura, 0.18 * cm, stroke=0, fill=1)
    canvas.restoreState()


def gerar_pdf_avaliacao(caminho_pdf, personal, aluno, avaliacao, historico, fotos, anamnese, tmp_dir):
    doc = SimpleDocTemplate(caminho_pdf, pagesize=A4,
                             topMargin=0, bottomMargin=1.9 * cm, leftMargin=1.6 * cm, rightMargin=1.6 * cm)
    story = []

    gerado_em = datetime.now().strftime("%d/%m/%Y %H:%M")
    story.extend(_cabecalho(
        "Relatório de Avaliação Física", personal,
        extra_direita=f"Protocolo Digital &nbsp;|&nbsp; Gerado em: {gerado_em}"
    ))
    story.append(Spacer(1, 10))

    story.append(_faixa_secao(f"DADOS DO ALUNO: {(aluno.get('nome') or '-').upper()}"))
    dados_aluno = [
        ["Idade", str(aluno.get("idade") or "-"), "Sexo", aluno.get("sexo") or "-", "Telefone", aluno.get("telefone") or "-"],
        ["Cidade", aluno.get("cidade") or "-", "Região", aluno.get("regiao") or "-", "Academia", aluno.get("academia") or "-"],
        ["Objetivo", aluno.get("objetivo") or "-", "", "", "", ""],
    ]
    t = Table(dados_aluno, colWidths=[2.2 * cm, 4.3 * cm, 2.2 * cm, 3.3 * cm, 2.2 * cm, 3.0 * cm])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), PRIMARY), ("TEXTCOLOR", (2, 0), (2, -1), PRIMARY), ("TEXTCOLOR", (4, 0), (4, -1), PRIMARY),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTNAME", (4, 0), (4, -1), "Helvetica-Bold"),
        ("SPAN", (1, 2), (5, 2)),
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))

    observacoes_anamnese = []
    if anamnese and anamnese.get("respostas_json"):
        respostas = json.loads(anamnese["respostas_json"])
        if respostas:
            story.append(_faixa_secao("ANAMNESE"))
            linhas = [[r["pergunta"], r["resposta"]] for r in respostas]
            for r in respostas:
                obs = (r.get("observacao") or "").strip()
                if obs:
                    observacoes_anamnese.append(f"{r['pergunta']} → {r['resposta']}: {obs}")
            ta = Table(linhas, colWidths=[12 * cm, 5 * cm])
            ta.setStyle(TableStyle([
                ("FONTSIZE", (0, 0), (-1, -1), 8.3),
                ("GRID", (0, 0), (-1, -1), 0.3, LINE),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, ROW_BG]),
            ]))
            story.append(ta)
            if anamnese.get("observacoes"):
                observacoes_anamnese.insert(0, anamnese["observacoes"])
            story.append(Spacer(1, 10))

    # ---- Indicadores de composição corporal (com classificação técnica ao lado de cada valor) ----
    import calculos
    story.append(_faixa_secao("INDICADORES DE COMPOSIÇÃO CORPORAL"))
    sexo_aluno = aluno.get("sexo")
    imc_val = avaliacao.get("imc")
    bf_val = avaliacao.get("bf")
    rcq_val = calculos.calcular_rcq(avaliacao.get("cintura"), avaliacao.get("quadril"))
    rcest_val = calculos.calcular_rcest(avaliacao.get("cintura"), avaliacao.get("altura"))
    ic_val = calculos.calcular_indice_conicidade(avaliacao.get("peso"), avaliacao.get("altura"), avaliacao.get("cintura"))
    tmb_val = calculos.calcular_tmb(avaliacao.get("peso"), avaliacao.get("altura"), aluno.get("idade"), sexo_aluno)
    peso_ideal_val = calculos.calcular_peso_ideal(avaliacao.get("altura"), sexo_aluno)
    classe_imc = calculos.classificar_imc(imc_val)
    classe_bf = calculos.classificar_bf(bf_val, sexo_aluno)
    classe_rcq = calculos.classificar_rcq(rcq_val, sexo_aluno)
    classe_rcest = calculos.classificar_rcest(rcest_val)
    classe_ic = calculos.classificar_indice_conicidade(ic_val, sexo_aluno)

    def _celula_indicador(rotulo, valor, classe=None):
        linhas_html = [f'<font size="7.5" color="#64748B">{rotulo}</font>',
                        f'<font size="12"><b>{valor}</b></font>']
        if classe:
            cor = _cor_classificacao(classe)
            linhas_html.append(f'<font size="6.8" color="{cor}"><b>{classe.upper()}</b></font>')
        return Paragraph("<br/>".join(linhas_html), ParagraphStyle("cel", alignment=TA_CENTER, leading=11))

    indicadores = [[
        _celula_indicador("PESO", f"{avaliacao.get('peso') or '-'} kg"),
        _celula_indicador("ALTURA", f"{avaliacao.get('altura') or '-'} m"),
        _celula_indicador("IMC", imc_val or "-", classe_imc),
        _celula_indicador("GORDURA", f"{bf_val}%" if bf_val is not None else "-", classe_bf),
        _celula_indicador("M. MAGRA", f"{avaliacao.get('massa_magra') or '-'} kg"),
        _celula_indicador("RCQ", rcq_val or "-", classe_rcq),
    ]]
    ti = Table(indicadores, colWidths=[2.83 * cm] * 6)
    ti.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#DBEAFE")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, WHITE),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(ti)
    story.append(Spacer(1, 4))

    indicadores_extra_pdf = [[
        _celula_indicador("RCEST", rcest_val or "-", classe_rcest),
        _celula_indicador("CONICIDADE", ic_val or "-", classe_ic),
        _celula_indicador("TMB", f"{tmb_val} kcal/d" if tmb_val else "-"),
        _celula_indicador("PESO REF.", f"{peso_ideal_val} kg" if peso_ideal_val else "-"),
    ]]
    tie = Table(indicadores_extra_pdf, colWidths=[4.25 * cm] * 4)
    tie.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#DBEAFE")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, WHITE),
        ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(tie)
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "RCQ = Relação Cintura-Quadril · RCEst = Relação Cintura-Estatura · Índice de Conicidade complementa "
        "a leitura de distribuição de gordura · TMB = Taxa Metabólica Basal (Mifflin-St Jeor) · Peso de "
        "referência é um parâmetro clássico (fórmula de Lorentz), não uma meta rígida. Classificações seguem "
        "parâmetros de referência e diferem entre homens e mulheres.",
        styles["SubtituloItalico"]))
    story.append(Spacer(1, 10))

    # ---- Dobras cutâneas + gráfico de pizza lado a lado ----
    dobras = [
        ("Subscapular", avaliacao.get("dobra_subescapular")), ("Tríceps", avaliacao.get("dobra_triceps")),
        ("Bicipital", avaliacao.get("dobra_bicipital")), ("Peitoral", avaliacao.get("dobra_peitoral")),
        ("Axilar", avaliacao.get("dobra_axilar")), ("Abdominal", avaliacao.get("dobra_abdominal")),
        ("Suprailíaca", avaliacao.get("dobra_suprailiaca")), ("Coxa", avaliacao.get("dobra_coxa")),
    ]
    grafico_pizza = None
    if avaliacao.get("bf") is not None:
        grafico_pizza = _grafico_composicao(avaliacao.get("massa_magra"), avaliacao.get("massa_gorda"),
                                             avaliacao.get("bf"), aluno.get("sexo"), os.path.join(tmp_dir, "pizza.png"))

    if any(v is not None for _, v in dobras) or grafico_pizza:
        linhas_dobras = []
        for i in range(0, len(dobras), 2):
            par = dobras[i:i + 2]
            linha = []
            for nome, valor in par:
                linha += [nome, "-" if valor is None else f"{valor} mm"]
            if len(linha) < 4:
                linha += ["", ""]
            linhas_dobras.append(linha)
        td = Table(linhas_dobras, colWidths=[2.6 * cm, 1.6 * cm, 2.6 * cm, 1.6 * cm])
        td.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 8.3),
            ("GRID", (0, 0), (-1, -1), 0.3, LINE),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
            ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        bloco_esq = [Paragraph("DOBRAS CUTÂNEAS (mm)", styles["LegendaFoto"]), Spacer(1, 4), td]
        bloco_dir = [Image(grafico_pizza, width=6.8 * cm, height=6.8 * cm)] if grafico_pizza else [Paragraph("", styles["TextoNormal"])]
        combinado = Table([[bloco_esq, bloco_dir]], colWidths=[9.5 * cm, 7.5 * cm])
        combinado.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story.append(combinado)
        story.append(Spacer(1, 10))

    # ---- Perímetros / antropometria ----
    perimetros = [
        ["Ombro", avaliacao.get("ombro"), "cm", "Peito", avaliacao.get("peito"), "cm"],
        ["Cintura", avaliacao.get("cintura"), "cm", "Abdome", avaliacao.get("abdome"), "cm"],
        ["Quadril", avaliacao.get("quadril"), "cm", "Braço D.", avaliacao.get("braco_d"), "cm"],
        ["Braço E.", avaliacao.get("braco_e"), "cm", "Coxa D.", avaliacao.get("coxa_d"), "cm"],
        ["Coxa E.", avaliacao.get("coxa_e"), "cm", "Pant. D.", avaliacao.get("panturrilha_d"), "cm"],
        ["Pant. E.", avaliacao.get("panturrilha_e"), "cm", "", "", ""],
    ]
    if any(v not in (None, "") for linha in perimetros for v in [linha[1], linha[4]]):
        story.append(_faixa_secao("PERÍMETROS E ANTROPOMETRIA (cm)"))
        linhas_perim = []
        for a, va, ua, b, vb, ub in perimetros:
            col_a = f"{a}: {va if va not in (None, '') else '-'}{ua if va not in (None, '') else ''}"
            col_b = f"{b}: {vb if vb not in (None, '') else '-'}{ub if vb not in (None, '') else ''}" if b else ""
            linhas_perim.append([col_a, col_b])
        tp = Table(linhas_perim, colWidths=[8.5 * cm, 8.5 * cm])
        tp.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.3, LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, ROW_BG]),
        ]))
        story.append(tp)
        story.append(Spacer(1, 10))

    story.append(_faixa_secao("OBSERVAÇÕES E ANAMNESE"))
    story.append(Spacer(1, 4))
    texto_obs_avaliacao = (avaliacao.get("observacoes") or "").strip()
    if texto_obs_avaliacao:
        story.append(Paragraph(texto_obs_avaliacao, styles["TextoNormal"]))
        story.append(Spacer(1, 4))
    if observacoes_anamnese:
        for linha_obs in observacoes_anamnese:
            story.append(Paragraph(f"• {linha_obs}", styles["TextoNormal"]))
    elif not texto_obs_avaliacao:
        story.append(Paragraph("Nenhuma observação registrada.", styles["TextoNormal"]))

    if len(historico) >= 2:
        story.append(Spacer(1, 12))
        story.append(_faixa_secao("EVOLUÇÃO REAL DO ALUNO"))
        story.append(Spacer(1, 6))
        for campo, titulo in [("peso", "Peso (kg)"), ("bf", "% Gordura (BF)"), ("imc", "IMC")]:
            png = os.path.join(tmp_dir, f"graf_{campo}.png")
            if _grafico_evolucao(historico, campo, titulo, png):
                story.append(Image(png, width=15 * cm, height=6.2 * cm))
                story.append(Spacer(1, 6))

    # ---- Avaliação postural com foto + linha traçada pela IA ----
    if fotos:
        story.append(PageBreak())
        story.extend(_cabecalho("Avaliação Postural com IA", personal))
        story.append(Spacer(1, 10))
        story.append(Paragraph(
            "As linhas sobre as fotos mostram o alinhamento de ombros e quadril identificado "
            "automaticamente (por visão computacional) e/ou marcado manualmente pelo profissional. "
            "É um apoio visual de acompanhamento — não substitui uma avaliação clínica.",
            styles["TextoNormal"]))
        story.append(Spacer(1, 10))

        import postural as _postural_mod
        fotos_com_diagnostico = []
        for f in fotos:
            if f.get("diagnostico_json"):
                fotos_com_diagnostico.append({
                    "tipo": f.get("tipo"),
                    "diagnostico": json.loads(f["diagnostico_json"]),
                    "pontuacao": f.get("pontuacao"),
                })
        if len(fotos_com_diagnostico) >= 2:
            parecer = _postural_mod.gerar_parecer_postural_completo(fotos_com_diagnostico)
            if parecer:
                hex_por_gravidade = {"dentro do esperado": "#05966922", "leve": "#B4530922",
                                      "moderada": "#C2410C22", "acentuada": "#B91C1C22"}
                cor_fundo = hex_por_gravidade.get(parecer["gravidade_final"], "#64748B22")
                estilo_parecer = ParagraphStyle("parecer_geral", parent=styles["TextoNormal"],
                                                 fontSize=9.5, leading=13, textColor=colors.HexColor("#0F172A"),
                                                 backColor=colors.HexColor(cor_fundo, hasAlpha=True), borderPadding=8)
                story.append(Paragraph(f"<b>Parecer geral da IA ({len(parecer['vistas_analisadas'])} vistas combinadas):</b> "
                                        f"{parecer['veredito']}", estilo_parecer))
                story.append(Spacer(1, 10))

        nomes_tipo = {"frontal": "Vista Frontal", "lateral": "Vista Lateral",
                      "lateral_direita": "Lado Direito", "lateral_esquerda": "Lado Esquerdo",
                      "costas": "Vista de Costas"}
        blocos_foto = []
        for f in fotos:
            caminho = f.get("caminho_anotado") or f.get("caminho_original")
            if not (caminho and os.path.exists(caminho)):
                continue

            legenda = nomes_tipo.get(f.get("tipo"), (f.get("tipo") or "").capitalize())
            coluna_foto = [Image(caminho, width=6.6 * cm, height=8.8 * cm)]

            coluna_texto = [Paragraph(legenda, styles["LegendaFoto"]), Spacer(1, 4)]
            if f.get("pontuacao") is not None:
                coluna_texto.append(_selo_placar(f["pontuacao"], f.get("gravidade_geral")))
                coluna_texto.append(Spacer(1, 8))

            medidas_chip = []
            if f.get("angulo_ombro") is not None:
                medidas_chip.append(f"Ombro {f['angulo_ombro']}°")
            if f.get("angulo_quadril") is not None:
                medidas_chip.append(f"Quadril {f['angulo_quadril']}°")
            if f.get("angulo_cabeca") is not None:
                medidas_chip.append(f"Cabeça {f['angulo_cabeca']}°")
            if f.get("desvio_tronco_pct") is not None:
                medidas_chip.append(f"Tronco {f['desvio_tronco_pct']}%")
            if medidas_chip:
                coluna_texto.append(Paragraph(" · ".join(medidas_chip), styles["MedidaChip"]))
                coluna_texto.append(Spacer(1, 8))

            if f.get("diagnostico_json"):
                try:
                    pontos = json.loads(f["diagnostico_json"])
                except (TypeError, ValueError):
                    pontos = []
                for ponto in pontos:
                    if not isinstance(ponto, dict):
                        coluna_texto.append(Paragraph(f"• {ponto}", styles["TextoNormal"]))
                        continue
                    gravidade = ponto.get("gravidade")
                    texto = ponto.get("texto", "")
                    if gravidade in ("resumo", "aviso"):
                        continue  # já aparece no selo / no rodapé do card
                    cor = _cor_gravidade_pdf(gravidade)
                    linha_estilo = ParagraphStyle(f"pt_{gravidade}_{len(coluna_texto)}", parent=styles["TextoNormal"],
                                                   textColor=cor, fontSize=8.7, leading=11.5)
                    coluna_texto.append(Paragraph(f"● {texto}", linha_estilo))
                    coluna_texto.append(Spacer(1, 3))

            if f.get("observacao_profissional"):
                coluna_texto.append(Spacer(1, 6))
                estilo_obs = ParagraphStyle("obs_profissional", parent=styles["TextoNormal"],
                                             fontSize=8.8, leading=11.5, textColor=colors.HexColor("#F8FAFC"),
                                             backColor=colors.HexColor("#1E293B"), borderPadding=6)
                coluna_texto.append(Paragraph(
                    f"<b>Observação do profissional:</b> {f['observacao_profissional']}", estilo_obs))

            coluna_texto.append(Spacer(1, 4))
            coluna_texto.append(Paragraph(
                "Apoio visual por IA a partir de uma foto 2D — não é um diagnóstico médico.",
                styles["SubtituloItalico"]))

            card = Table([[coluna_foto, coluna_texto]], colWidths=[7.1 * cm, 9.4 * cm])
            card.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BOX", (0, 0), (-1, -1), 0.7, LINE),
                ("LEFTPADDING", (0, 0), (0, 0), 6), ("TOPPADDING", (0, 0), (0, 0), 6), ("BOTTOMPADDING", (0, 0), (0, 0), 6),
                ("LEFTPADDING", (1, 0), (1, 0), 10), ("RIGHTPADDING", (1, 0), (1, 0), 8),
                ("TOPPADDING", (1, 0), (1, 0), 8), ("BOTTOMPADDING", (1, 0), (1, 0), 8),
            ]))
            blocos_foto.append(KeepTogether([card, Spacer(1, 14)]))
        story.extend(blocos_foto)

    # ---- Parecer técnico final, no padrão de um laudo assinado pelo profissional ----
    pontuacoes = [f["pontuacao"] for f in fotos if f.get("pontuacao") is not None]
    media_postural = round(sum(pontuacoes) / len(pontuacoes)) if pontuacoes else None
    parecer = calculos.gerar_parecer_tecnico(aluno, avaliacao, media_postural)
    if parecer:
        story.append(PageBreak())
        story.append(_faixa_secao("PARECER TÉCNICO"))
        story.append(Spacer(1, 8))
        story.append(Paragraph(parecer, styles["TextoNormal"]))
        story.append(Spacer(1, 40))

        nome_personal = personal.get("nome_exibicao") or personal.get("usuario") or "Personal Trainer"
        linha_assinatura = f"{nome_personal}"
        if personal.get("cref"):
            linha_assinatura += f" — CREF: {personal['cref']}"
        assinatura = Table([
            [Paragraph("_" * 42, styles["TextoNormal"])],
            [Paragraph(f"<b>{linha_assinatura}</b>", styles["TextoNormal"])],
            [Paragraph("Profissional responsável pela avaliação", styles["SubtituloItalico"])],
        ], colWidths=[9 * cm])
        assinatura.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
        story.append(assinatura)

    doc.build(story, onFirstPage=_rodape, onLaterPages=_rodape)
    return caminho_pdf


def _normalizar_dias_treino(treino):
    """Aceita tanto o formato novo (dias com letra/dia_semana/exercicios) quanto o
    formato antigo (lista simples de exercícios) e devolve sempre a lista de dias."""
    bruto = json.loads(treino.get("exercicios_json") or "[]")
    if bruto and isinstance(bruto, list) and isinstance(bruto[0], dict) and "exercicios" in bruto[0]:
        return bruto
    # formato antigo: lista simples de exercícios -> vira um único dia "A"
    if bruto:
        return [{"letra": "A", "dia_semana": "", "exercicios": bruto}]
    return []


def gerar_pdf_treino(caminho_pdf, personal, aluno, treino):
    doc = SimpleDocTemplate(caminho_pdf, pagesize=A4,
                             topMargin=0, bottomMargin=1.9 * cm, leftMargin=1.6 * cm, rightMargin=1.6 * cm)
    story = []

    dias = _normalizar_dias_treino(treino)

    story.extend(_cabecalho("Ficha de Treino", personal))
    story.append(Spacer(1, 10))

    # ---- Faixa dos dias da semana (Segunda a Domingo), igual ao modelo ----
    mapa_letra_por_dia = {d.get("dia_semana"): d.get("letra") for d in dias if d.get("dia_semana")}
    dias_semana_completos = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    linha_letras = []
    for dia in dias_semana_completos:
        if mapa_letra_por_dia.get(dia):
            linha_letras.append(f'"{mapa_letra_por_dia.get(dia)}"')
        elif dia == "Sábado":
            linha_letras.append("Supletivo")
        else:
            linha_letras.append("Descanso")
    tsem = Table([dias_semana_completos, linha_letras], colWidths=[2.28 * cm] * 7)
    tsem.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY_LIGHT),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("GRID", (0, 0), (-1, -1), 0.5, WHITE),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(tsem)
    story.append(Spacer(1, 10))

    # ---- Resumo rápido da semana (dá um acabamento mais profissional) ----
    dias_com_treino = [d for d in dias if d.get("exercicios")]
    total_exercicios = sum(len(d.get("exercicios") or []) for d in dias_com_treino)
    if dias_com_treino:
        resumo_semana = Table([[
            f"{len(dias_com_treino)} DIA(S) DE TREINO NA SEMANA", f"{total_exercicios} EXERCÍCIOS NO TOTAL"
        ]], colWidths=[8.5 * cm, 8.5 * cm])
        resumo_semana.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#DBEAFE")),
            ("TEXTCOLOR", (0, 0), (-1, -1), DARK),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.5, WHITE),
            ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))
        story.append(resumo_semana)
        story.append(Spacer(1, 10))

    dados_aluno = [
        ["Aluno", aluno.get("nome") or "-", "Data", treino["data"][:10]],
        ["Cidade", aluno.get("cidade") or "-", "Gênero", aluno.get("sexo") or "-"],
        ["Academia", aluno.get("academia") or "-", "", ""],
    ]
    t = Table(dados_aluno, colWidths=[2.6 * cm, 6.4 * cm, 2.6 * cm, 4.4 * cm])
    t.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), PRIMARY), ("TEXTCOLOR", (2, 0), (2, -1), PRIMARY),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"), ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("SPAN", (1, 2), (3, 2)),
        ("GRID", (0, 0), (-1, -1), 0.3, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))

    # Resumo composição corporal (se vier junto do treino — opcional)
    if treino.get("bf") or treino.get("massa_magra"):
        resumo = Table([[f"PERCENTUAL DE GORDURA: {treino.get('bf')}%", f"MASSA MAGRA: {treino.get('massa_magra')}kg"]],
                        colWidths=[8 * cm, 8 * cm])
        resumo.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), DARK),
            ("BACKGROUND", (1, 0), (1, 0), PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, -1), WHITE),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9.5),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 8), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(resumo)
        story.append(Spacer(1, 10))

    for dia in dias:
        letra = dia.get("letra") or "A"
        exercicios = dia.get("exercicios") or []
        if not exercicios:
            continue
        titulo_dia = ""
        if dia.get("dia_semana"):
            titulo_dia += dia["dia_semana"].upper()
        if dia.get("grupo_muscular"):
            titulo_dia += f" — {dia['grupo_muscular']}" if titulo_dia else dia["grupo_muscular"]
        if not titulo_dia:
            titulo_dia = f'TREINO "{letra}"'

        tem_gif_no_dia = any(ex.get("gif") for ex in exercicios)
        cabecalho = ["", "EXERCÍCIO", "SÉRIES/REPS", "CARGA"] if tem_gif_no_dia else ["EXERCÍCIO", "SÉRIES/REPS", "CARGA"]
        linhas = [cabecalho]
        for ex in exercicios:
            series_reps = ex.get("series", "")
            if ex.get("reps"):
                series_reps = f"{ex.get('series', '')}x{ex.get('reps', '')}" if ex.get("series") else ex.get("reps")
            nome_cel = ex.get("nome", "")
            if ex.get("video"):
                nome_cel = (f'{ex.get("nome", "")}<br/>'
                            f'<link href="{ex["video"]}" color="#2563EB"><font size="7.5">▶ Ver vídeo do exercício</font></link>')
            linha_tabela = [Paragraph(nome_cel, styles["CelulaExercicio"]), series_reps, ex.get("obs", "")]
            if tem_gif_no_dia:
                caminho_frame = _obter_frame_gif_exercicio(ex.get("gif")) if ex.get("gif") else None
                celula_img = Image(caminho_frame, width=1.6 * cm, height=1.6 * cm) if caminho_frame else ""
                linha_tabela = [celula_img] + linha_tabela
            linhas.append(linha_tabela)

        col_widths = [1.9 * cm, 5.8 * cm, 4.3 * cm, 5 * cm] if tem_gif_no_dia else [7.5 * cm, 4.5 * cm, 5 * cm]
        tb = Table(linhas, colWidths=col_widths)
        tb.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), ROW_BG),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.4, LINE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, ROW_BG]),
        ]))
        bloco = [_faixa_secao_com_selo(letra, titulo_dia), Spacer(1, 0), tb, Spacer(1, 12)]
        story.append(KeepTogether(bloco))

    if treino.get("observacoes"):
        story.append(_faixa_secao("OBSERVAÇÕES"))
        story.append(Spacer(1, 4))
        story.append(Paragraph(treino["observacoes"], styles["TextoNormal"]))
        story.append(Spacer(1, 10))

    if dias_com_treino:
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            f"Bons treinos, {(aluno.get('nome') or '').split(' ')[0] or 'aluno'}! Qualquer dúvida na execução "
            "dos exercícios, chama o personal antes de seguir.", styles["ResumoRel"]))

    doc.build(story, onFirstPage=_rodape, onLaterPages=_rodape)
    return caminho_pdf


def gerar_pdf_relatorio_completo(caminho_pdf, personal, aluno, avaliacao, historico, fotos, anamnese,
                                  treino, tmp_dir):
    """Junta a Avaliação Física completa (com fotos + análise postural por IA) e a
    Ficha de Treino da semana em um único PDF — o "relatório completo do aluno"."""
    from pypdf import PdfWriter, PdfReader

    caminho_aval = os.path.join(tmp_dir, "parte_avaliacao.pdf")
    gerar_pdf_avaliacao(caminho_aval, personal, aluno, avaliacao, historico, fotos, anamnese, tmp_dir)

    writer = PdfWriter()
    for pagina in PdfReader(caminho_aval).pages:
        writer.add_page(pagina)

    if treino:
        caminho_treino = os.path.join(tmp_dir, "parte_treino.pdf")
        gerar_pdf_treino(caminho_treino, personal, aluno, treino)
        for pagina in PdfReader(caminho_treino).pages:
            writer.add_page(pagina)

    with open(caminho_pdf, "wb") as f:
        writer.write(f)
    return caminho_pdf
