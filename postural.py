"""
Avaliação postural assistida por IA.

- Desenho MANUAL das linhas é feito no navegador (canvas): o próprio celular
  já envia a foto com as linhas desenhadas por cima. Esse módulo cuida da
  parte AUTOMÁTICA (detecção por IA dos pontos do corpo).
- A análise roda pontos de: ombros, quadril, cabeça (orelhas), alinhamento
  vertical do tronco (fio de prumo) e, em fotos de frente/costas, alinhamento
  dos joelhos — cobrindo as vistas anterior, posterior e lateral de forma
  parecida com uma ficha de avaliação postural profissional.

IMPORTANTE (limite ético/de segurança do próprio recurso):
Isso é um apoio visual para o profissional, NÃO um diagnóstico médico. Uma
foto 2D não confirma condições clínicas (ex.: escoliose, pé plano, genu
valgo) — essas exigem exame presencial. A IA aqui identifica ASSIMETRIAS e
DESALINHAMENTOS VISUAIS e sugere pontos de atenção, sempre recomendando
encaminhar casos relevantes a um profissional de saúde.
"""
import os
import math

MODEL_PATH = os.path.join(os.path.dirname(__file__), "instance", "models", "pose_landmarker.task")

# Índices padrão do MediaPipe Pose
LEFT_SHOULDER, RIGHT_SHOULDER = 11, 12
LEFT_ELBOW, RIGHT_ELBOW = 13, 14
LEFT_WRIST, RIGHT_WRIST = 15, 16
LEFT_HIP, RIGHT_HIP = 23, 24
LEFT_EAR, RIGHT_EAR = 7, 8
LEFT_KNEE, RIGHT_KNEE = 25, 26
LEFT_ANKLE, RIGHT_ANKLE = 27, 28

# Limiares em graus / porcentagem para cada nível de gravidade.
NIVEIS_ANGULO = [(2.5, "dentro do esperado"), (5.0, "leve"), (9.0, "moderada")]  # acima do último = "acentuada"
NIVEIS_DESVIO_PCT = [(3.0, "dentro do esperado"), (6.0, "leve"), (10.0, "moderada")]

COR_OK = (16, 185, 129)
COR_LEVE = (245, 158, 11)
COR_MODERADA = (249, 115, 22)
COR_ACENTUADA = (239, 68, 68)


def modelo_disponivel():
    return os.path.exists(MODEL_PATH)


def _angulo_em_relacao_horizontal(p1, p2):
    """
    Ângulo de UMA linha (ex: ombro-a-ombro) em relação à horizontal.
    Sempre devolve o desvio AGUDO (0° = perfeitamente nivelado, até 90° =
    totalmente vertical) — não importa se p1/p2 vêm na ordem esquerda→direita
    ou direita→esquerda. Sem essa normalização, quando os dois pontos ficam
    "invertidos" no eixo X (comum em foto de frente, já que o lado esquerdo
    do corpo aparece do lado direito da imagem), o cálculo cru dava um
    ângulo obtuso perto de 180° em vez do valor real perto de 0°.
    """
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    ang = abs(math.degrees(math.atan2(dy, dx)))
    if ang > 90:
        ang = 180 - ang
    return ang


# Tipos de vista lateral aceitos — tratados com as mesmas regras de "lateral"
# nos cálculos, mas guardados/rotulados separadamente para dar as 4 vistas
# completas (frontal, lado direito, lado esquerdo, costas).
TIPOS_LATERAIS = ("lateral", "lateral_direita", "lateral_esquerda")


def _ponto_medio(p1, p2):
    return ((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2)


def _ponto_na_linha(p_de, p_para, fracao):
    """Ponto a uma fração (0 a 1) do caminho entre dois pontos."""
    return (p_de[0] + (p_para[0] - p_de[0]) * fracao, p_de[1] + (p_para[1] - p_de[1]) * fracao)


def _classificar(valor, niveis):
    for limite, rotulo in niveis:
        if valor <= limite:
            return rotulo
    return "acentuada"


def _cor_por_gravidade(rotulo):
    return {"dentro do esperado": COR_OK, "leve": COR_LEVE, "moderada": COR_MODERADA, "acentuada": COR_ACENTUADA}.get(rotulo, COR_OK)


def _pontuacao_alinhamento(gravidades):
    """Converte os rótulos de gravidade num placar de 0 a 100 (didático, não clínico)."""
    peso = {"dentro do esperado": 0, "leve": 8, "moderada": 18, "acentuada": 30}
    penalidade = sum(peso.get(g, 0) for g in gravidades)
    return max(0, 100 - penalidade)


def gerar_diagnostico(tipo, medidas):
    """
    Gera pontos de atenção em linguagem profissional, organizados como uma
    ficha de avaliação postural (vista anterior/posterior/lateral conforme
    o tipo da foto). Retorna (lista_de_pontos, lista_de_gravidades, resumo_geral).
    """
    pontos = []
    gravidades = []

    def registrar(rotulo_medida, valor, unidade, niveis, texto_alerta, texto_ok):
        g = _classificar(valor, niveis)
        gravidades.append(g)
        if g == "dentro do esperado":
            pontos.append({"categoria": rotulo_medida, "gravidade": g, "texto": texto_ok.format(valor=valor, unidade=unidade)})
        else:
            pontos.append({"categoria": rotulo_medida, "gravidade": g, "texto": texto_alerta.format(valor=valor, unidade=unidade, gravidade=g)})

    if medidas.get("angulo_ombro") is not None:
        v = medidas["angulo_ombro"]
        registrar("Nível dos ombros", v, "°", NIVEIS_ANGULO,
                   "Assimetria {gravidade} na linha dos ombros ({value:.1f}°) — sugere observar tensão/encurtamento "
                   "do trapézio superior do lado mais elevado e priorizar mobilidade + fortalecimento contralateral."
                   .replace("{value:.1f}", "{valor:.1f}"),
                   "Linha dos ombros bem nivelada ({valor:.1f}°).")

    if medidas.get("angulo_quadril") is not None:
        v = medidas["angulo_quadril"]
        registrar("Nível do quadril", v, "°", NIVEIS_ANGULO,
                   "Assimetria {gravidade} no nível do quadril ({valor:.1f}°) — vale avaliar comprimento aparente "
                   "das pernas, ativação de glúteo médio e mobilidade lombopélvica.",
                   "Quadril bem nivelado ({valor:.1f}°).")

    if medidas.get("angulo_cabeca") is not None:
        v = medidas["angulo_cabeca"]
        registrar("Alinhamento da cabeça", v, "°", NIVEIS_ANGULO,
                   "Inclinação lateral {gravidade} da cabeça ({valor:.1f}°) — observar tensão cervical e "
                   "equilíbrio da musculatura dos dois lados do pescoço.",
                   "Cabeça bem alinhada na horizontal ({valor:.1f}°).")

    if medidas.get("desvio_tronco_pct") is not None:
        v = medidas["desvio_tronco_pct"]
        registrar("Alinhamento do tronco (linha de prumo ombro → quadril)", v, "%", NIVEIS_DESVIO_PCT,
                   "Desvio lateral {gravidade} do tronco — o centro dos ombros não está alinhado com o centro "
                   "do quadril ({valor:.1f}% da largura do ombro) — vale reforçar o core e observar a "
                   "distribuição de peso entre os dois lados.",
                   "Tronco bem centrado — linha de prumo ombro → quadril alinhada ({valor:.1f}%).")

    if tipo in TIPOS_LATERAIS and medidas.get("cabeca_projetada_pct") is not None:
        v = medidas["cabeca_projetada_pct"]
        registrar("Postura da cabeça (vista lateral)", v, "%", NIVEIS_DESVIO_PCT,
                   "Cabeça aparenta projeção {gravidade} à frente do ombro ({valor:.1f}%) — comum em quem passa "
                   "muito tempo sentado; pode valer trabalhar fortalecimento de cervical profunda e alongamento peitoral.",
                   "Cabeça bem alinhada sobre o ombro, sem projeção anterior relevante.")

    if tipo in ("frontal", "costas") and medidas.get("diferenca_cotovelos_pct") is not None:
        v = medidas["diferenca_cotovelos_pct"]
        registrar("Alinhamento dos braços (cotovelos)", v, "%", NIVEIS_DESVIO_PCT,
                   "Diferença de altura {gravidade} entre os cotovelos ({valor:.1f}%) — pode indicar assimetria "
                   "de ombro/escápula ou tensão desigual entre os lados; vale observar o padrão em exercícios "
                   "unilaterais e bilaterais.",
                   "Cotovelos na mesma altura, braços simétricos ({valor:.1f}%).")

    if tipo in ("frontal", "costas") and medidas.get("diferenca_pulsos_pct") is not None:
        v = medidas["diferenca_pulsos_pct"]
        registrar("Alinhamento dos braços (punhos)", v, "%", NIVEIS_DESVIO_PCT,
                   "Diferença de altura {gravidade} entre os punhos ({valor:.1f}%) — reforça observar a "
                   "simetria de tronco superior junto com o ponto dos cotovelos.",
                   "Punhos na mesma altura, braços simétricos ({valor:.1f}%).")

    if tipo in TIPOS_LATERAIS and medidas.get("cotovelo_projetado_pct") is not None:
        v = medidas["cotovelo_projetado_pct"]
        registrar("Postura do braço (vista lateral)", v, "%", NIVEIS_DESVIO_PCT,
                   "Cotovelo aparenta projeção {gravidade} à frente da linha do ombro ({valor:.1f}%) — comum "
                   "junto com postura de ombros protraídos; vale observar mobilidade torácica e fortalecimento "
                   "de romboides/trapézio médio.",
                   "Braço bem alinhado sob a linha do ombro, sem projeção anterior relevante.")

    if tipo in ("frontal", "costas") and medidas.get("dif_comprimento_bracos_pct") is not None:
        v = medidas["dif_comprimento_bracos_pct"]
        lado = medidas.get("lado_braco_maior", "")
        registrar("Comprimento aparente dos braços", v, "%", NIVEIS_DESVIO_PCT,
                   "Diferença {gravidade} no comprimento aparente dos braços" + (f" (braço {lado} parece mais longo)" if lado else "") +
                   " ({valor:.1f}%) — pode ser efeito de pequena rotação do corpo na foto, ou merecer um olhar "
                   "mais de perto na postura do ombro/escápula desse lado.",
                   "Braços com comprimento aparente semelhante nos dois lados ({valor:.1f}%).")

    if tipo in ("frontal", "costas") and medidas.get("dif_comprimento_pernas_pct") is not None:
        v = medidas["dif_comprimento_pernas_pct"]
        lado = medidas.get("lado_perna_maior", "")
        registrar("Comprimento aparente das pernas", v, "%", NIVEIS_DESVIO_PCT,
                   "Diferença {gravidade} no comprimento aparente das pernas" + (f" (perna {lado} parece mais longa)" if lado else "") +
                   " ({valor:.1f}%) — pode ser efeito de apoio de peso desigual ou leve rotação do corpo na foto; "
                   "se for consistente em várias fotos, vale investigar dismetria de membros com um profissional.",
                   "Pernas com comprimento aparente semelhante nos dois lados ({valor:.1f}%).")

    # ---- Rastreio visual de possível escoliose (frontal/costas) ----
    # Não é diagnóstico: é a mesma lógica de uma triagem postural básica —
    # combina o nível dos ombros, o nível do quadril e o desvio lateral do
    # tronco. Quando pelo menos dois desses três sinais aparecem alterados
    # ao mesmo tempo, é um padrão clássico de alerta pra investigar melhor.
    if tipo in ("frontal", "costas"):
        sinais_relevantes = [
            _classificar(medidas.get("angulo_ombro", 0), NIVEIS_ANGULO),
            _classificar(medidas.get("angulo_quadril", 0), NIVEIS_ANGULO),
            _classificar(medidas.get("desvio_tronco_pct", 0), NIVEIS_DESVIO_PCT),
        ]
        n_alterados = sum(1 for g in sinais_relevantes if g in ("moderada", "acentuada"))
        n_acentuados = sum(1 for g in sinais_relevantes if g == "acentuada")
        if n_acentuados >= 2 or n_alterados >= 2:
            pontos.append({
                "categoria": "Rastreio de possível escoliose", "gravidade": "acentuada" if n_acentuados >= 2 else "moderada",
                "texto": ("Sinais visuais combinados (ombro, quadril e/ou tronco) compatíveis com possível "
                          "assimetria de coluna — recomenda-se avaliação presencial com fisioterapeuta ou "
                          "ortopedista para investigar melhor.")
            })
        elif n_alterados == 1:
            pontos.append({
                "categoria": "Rastreio de possível escoliose", "gravidade": "leve",
                "texto": ("Foi identificado um sinal isolado de assimetria (ombro, quadril ou tronco) — sozinho, "
                          "não é padrão característico de escoliose, mas vale manter no acompanhamento.")
            })
        else:
            pontos.append({
                "categoria": "Rastreio de possível escoliose", "gravidade": "dentro do esperado",
                "texto": "Sem sinais visuais combinados que sugiram assimetria de coluna nesta foto."
            })

    pontuacao = _pontuacao_alinhamento(gravidades)
    if pontuacao >= 90:
        resumo = f"Placar de alinhamento: {pontuacao}/100 — postura geral dentro do esperado nesta vista."
    elif pontuacao >= 70:
        resumo = f"Placar de alinhamento: {pontuacao}/100 — assimetrias leves detectadas, vale acompanhar ao longo do tempo."
    elif pontuacao >= 50:
        resumo = f"Placar de alinhamento: {pontuacao}/100 — assimetrias moderadas; recomenda-se atenção redobrada e reavaliação periódica."
    else:
        resumo = f"Placar de alinhamento: {pontuacao}/100 — assimetrias mais acentuadas; recomenda-se avaliação com um profissional de saúde (fisioterapeuta/ortopedista)."

    pontos.append({"categoria": "Resumo geral", "gravidade": "resumo", "texto": resumo})
    pontos.append({
        "categoria": "Aviso",
        "gravidade": "aviso",
        "texto": "Isso é um apoio visual por IA a partir de uma foto 2D, não um diagnóstico médico. "
                 "Assimetrias persistentes ou que gerem dor devem ser encaminhadas a um profissional de saúde."
    })
    return pontos, gravidades, pontuacao


def gerar_parecer_postural_completo(fotos):
    """
    Junta o diagnóstico das 4 vistas (frontal, lado direito, lado esquerdo,
    costas) numa conclusão só. Isso é mais sensível do que olhar cada foto
    isolada: um sinal leve que aparece sozinho na frontal pode não bater o
    critério de alerta ali, mas se o MESMO sinal (ex.: ombro mais alto de
    um lado) aparece de novo nas costas, é uma corroboração — duas fotos
    independentes concordando é um sinal mais forte do que uma só.

    `fotos` é uma lista de dicts com pelo menos: tipo, diagnostico (lista
    de pontos, como retornado por gerar_diagnostico) e pontuacao.
    Retorna um dict com o parecer final.
    """
    por_tipo = {f["tipo"]: f for f in fotos if f.get("diagnostico")}
    if not por_tipo:
        return None

    def gravidade_de(tipo_foto, categoria):
        foto = por_tipo.get(tipo_foto)
        if not foto:
            return None
        for p in foto["diagnostico"]:
            if p["categoria"] == categoria:
                return p["gravidade"]
        return None

    sinais = {
        "ombro": [gravidade_de("frontal", "Nível dos ombros"), gravidade_de("costas", "Nível dos ombros")],
        "quadril": [gravidade_de("frontal", "Nível do quadril"), gravidade_de("costas", "Nível do quadril")],
        "tronco": [gravidade_de("frontal", "Alinhamento do tronco (linha de prumo ombro → quadril)"),
                   gravidade_de("costas", "Alinhamento do tronco (linha de prumo ombro → quadril)")],
        "pernas": [gravidade_de("frontal", "Comprimento aparente das pernas"),
                   gravidade_de("costas", "Comprimento aparente das pernas")],
        "cabeca_lateral": [gravidade_de("lateral_direita", "Postura da cabeça (vista lateral)"),
                            gravidade_de("lateral_esquerda", "Postura da cabeça (vista lateral)")],
    }

    ALTERADO = ("leve", "moderada", "acentuada")
    FORTE = ("moderada", "acentuada")

    # Corroborado = o MESMO sinal apareceu alterado em pelo menos 2 vistas
    # independentes (ex.: ombro desnivelado na frontal E nas costas) — é
    # isso que dá mais confiança do que julgar uma foto isolada.
    corroborados = []
    isolados = []
    for nome, gravs in sinais.items():
        vistos = [g for g in gravs if g in ALTERADO]
        if len(vistos) >= 2:
            pior = "acentuada" if "acentuada" in vistos else ("moderada" if "moderada" in vistos else "leve")
            corroborados.append((nome, pior))
        elif len(vistos) == 1:
            isolados.append((nome, vistos[0]))

    n_fortes_corroborados = sum(1 for _, g in corroborados if g in FORTE)
    n_corroborados = len(corroborados)

    nomes_pt = {"ombro": "nível dos ombros", "quadril": "nível do quadril", "tronco": "alinhamento do tronco",
                "pernas": "comprimento aparente das pernas", "cabeca_lateral": "postura da cabeça (vista lateral)"}

    if n_fortes_corroborados >= 2 or (n_corroborados >= 1 and n_fortes_corroborados >= 1 and n_corroborados >= 2):
        gravidade_final = "acentuada"
    elif n_corroborados >= 2 or n_fortes_corroborados >= 1:
        gravidade_final = "moderada"
    elif n_corroborados >= 1 or len(isolados) >= 2:
        gravidade_final = "leve"
    else:
        gravidade_final = "dentro do esperado"

    pontuacoes = [f.get("pontuacao") for f in fotos if f.get("pontuacao") is not None]
    pontuacao_media = round(sum(pontuacoes) / len(pontuacoes)) if pontuacoes else None
    vistas_analisadas = sorted(por_tipo.keys())

    if gravidade_final in ("acentuada", "moderada"):
        itens = ", ".join(nomes_pt[n] for n, _ in corroborados) or ", ".join(nomes_pt[n] for n, _ in isolados)
        veredito = (
            f"Combinando as {len(vistas_analisadas)} vistas enviadas, os sinais de assimetria em "
            f"{itens} aparecem em mais de uma foto de forma consistente. Isso é compatível com um padrão "
            "de desvio postural — incluindo possível escoliose — mas fotos não confirmam isso sozinhas: "
            "a confirmação exige avaliação presencial com um profissional de saúde (fisioterapeuta ou "
            "ortopedista), que pode incluir exame físico e, se necessário, radiografia. Recomendo "
            "fortemente encaminhar para essa avaliação."
        )
    elif gravidade_final == "leve":
        veredito = (
            f"Combinando as {len(vistas_analisadas)} vistas enviadas, foram encontrados sinais leves e "
            "isolados (não confirmados em mais de uma foto). Isoladamente não formam um padrão característico "
            "de escoliose, mas vale manter no acompanhamento nas próximas avaliações."
        )
    else:
        veredito = (
            f"Combinando as {len(vistas_analisadas)} vistas enviadas, não foram encontrados sinais visuais "
            "consistentes de assimetria de coluna. Isso não é um exame médico e não substitui avaliação "
            "profissional, mas dentro do que dá pra observar em fotos, o aluno aparenta alinhamento dentro do esperado."
        )

    return {
        "vistas_analisadas": vistas_analisadas,
        "gravidade_final": gravidade_final,
        "pontuacao_media": pontuacao_media,
        "sinais_corroborados": [{"sinal": nomes_pt[n], "gravidade": g} for n, g in corroborados],
        "sinais_isolados": [{"sinal": nomes_pt[n], "gravidade": g} for n, g in isolados],
        "veredito": veredito,
    }


def detectar_postura_automatica(caminho_imagem, caminho_saida, tipo="frontal"):
    """
    Roda a detecção de pontos do corpo na foto, desenha as linhas (ombros,
    quadril, cabeça, fio de prumo do tronco e, quando aplicável, joelhos),
    calcula os ângulos/desvios e monta um relatório com níveis de gravidade
    e um placar geral de alinhamento. Retorna dict com 'erro' se a IA ainda
    não estiver instalada ou não detectar corpo na foto.
    """
    if not modelo_disponivel():
        return {
            "erro": "modelo_ausente",
            "mensagem": (
                "Detecção automática ainda não instalada neste servidor. "
                "Rode 'python baixar_modelo_ia.py' na pasta do sistema (uma vez só) "
                "e reinicie o site. A linha manual continua funcionando normalmente."
            ),
        }

    from PIL import Image, ImageDraw, ImageFont
    import mediapipe as mp
    from mediapipe.tasks.python import vision
    from mediapipe.tasks.python.core.base_options import BaseOptions

    options = vision.PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=MODEL_PATH),
        running_mode=vision.RunningMode.IMAGE,
    )
    with vision.PoseLandmarker.create_from_options(options) as landmarker:
        mp_image = mp.Image.create_from_file(caminho_imagem)
        resultado = landmarker.detect(mp_image)

        if not resultado.pose_landmarks:
            return {"erro": "sem_deteccao", "mensagem": "Não foi possível identificar o corpo nessa foto. Tente uma foto com corpo inteiro visível, bem iluminada e de preferência com fundo neutro."}

        landmarks = resultado.pose_landmarks[0]
        img = Image.open(caminho_imagem).convert("RGB")
        w, h = img.size

        def ponto(idx):
            lm = landmarks[idx]
            return (lm.x * w, lm.y * h)

        ombro_e, ombro_d = ponto(LEFT_SHOULDER), ponto(RIGHT_SHOULDER)
        cotovelo_e, cotovelo_d = ponto(LEFT_ELBOW), ponto(RIGHT_ELBOW)
        pulso_e, pulso_d = ponto(LEFT_WRIST), ponto(RIGHT_WRIST)
        quadril_e, quadril_d = ponto(LEFT_HIP), ponto(RIGHT_HIP)
        orelha_e, orelha_d = ponto(LEFT_EAR), ponto(RIGHT_EAR)
        joelho_e, joelho_d = ponto(LEFT_KNEE), ponto(RIGHT_KNEE)
        tornozelo_e, tornozelo_d = ponto(LEFT_ANKLE), ponto(RIGHT_ANKLE)

        # --- checagem de plausibilidade da detecção ---
        # Em fotos de frente/costas, a distância entre os ombros deve ser uma fração
        # razoável da altura da pessoa na foto. Quando a IA "confunde" os pontos do
        # corpo (o que pode acontecer em fotos com braços colados ao corpo, ângulo
        # de câmera ruim, roupa/objetos no caminho etc.), os ombros aparecem quase
        # colados um no outro e todos os cálculos saem sem sentido — em vez de
        # devolver números fantasiosos, é melhor avisar que a foto não deu pra
        # confiar e pedir uma nova tentativa.
        if tipo in ("frontal", "costas"):
            largura_ombro_bruta = abs(ombro_d[0] - ombro_e[0])
            altura_corpo_px = abs(((tornozelo_e[1] + tornozelo_d[1]) / 2) - ((orelha_e[1] + orelha_d[1]) / 2))
            razao_ombro_altura = (largura_ombro_bruta / altura_corpo_px) if altura_corpo_px else 0
            if razao_ombro_altura < 0.09:
                return {
                    "erro": "deteccao_pouco_confiavel",
                    "mensagem": (
                        "A IA identificou um corpo na foto, mas não conseguiu localizar os ombros com "
                        "confiança suficiente (provavelmente por causa do ângulo, iluminação ou pose na "
                        "foto) — os números dariam um resultado sem sentido, então preferi não mostrar. "
                        "Tente tirar a foto de novo com a pessoa de frente/costas bem retas, braços "
                        "levemente afastados do corpo, corpo inteiro visível e boa iluminação."
                    ),
                }

        def _dist(p1, p2):
            return math.hypot(p2[0] - p1[0], p2[1] - p1[1])

        medidas = {}
        if tipo in ("frontal", "costas"):
            medidas["angulo_ombro"] = _angulo_em_relacao_horizontal(ombro_e, ombro_d)
            medidas["angulo_quadril"] = _angulo_em_relacao_horizontal(quadril_e, quadril_d)
            medidas["angulo_cabeca"] = _angulo_em_relacao_horizontal(orelha_e, orelha_d)

        ombro_medio = _ponto_medio(ombro_e, ombro_d)
        quadril_medio = _ponto_medio(quadril_e, quadril_d)
        largura_ombro = max(1.0, abs(ombro_d[0] - ombro_e[0]))
        altura_tronco = max(1.0, abs(quadril_medio[1] - ombro_medio[1]))

        # Desvio do tronco = o quanto o centro dos ombros está deslocado
        # lateralmente em relação ao centro do quadril (a mesma ideia da
        # "linha de prumo" usada em triagem postural: num corpo bem
        # alinhado, um fio de prumo cai do meio dos ombros até o meio do
        # quadril; se a coluna tem uma curva, esse fio "escapa" pro lado).
        # IMPORTANTE: antes essa métrica usava um ponto interpolado a 12%
        # do caminho quadril→ombro pra simular a cintura — só que esse
        # ponto, por estar matematicamente EM CIMA da própria reta
        # ombro→quadril, deixava o valor sempre pertinho de zero (~12% do
        # sinal real), mascarando desvios verdadeiros. Comparar ombro
        # direto com quadril é o que realmente captura o desvio.
        # SÓ faz sentido em frontal/costas: numa foto de lado, ombro esquerdo
        # e direito ficam quase colados no eixo X (é a mesma pessoa vista de
        # perfil), então "largura do ombro" vira quase zero e qualquer
        # cálculo em cima disso explode (ex.: 194% de desvio) — por isso
        # essa métrica é pulada em vista lateral.
        if tipo in ("frontal", "costas"):
            medidas["desvio_tronco_pct"] = abs(ombro_medio[0] - quadril_medio[0]) / largura_ombro * 100

            # Braços: compara a altura (Y) de cotovelos e punhos dos dois lados —
            # uma boa aproximação de simetria de ombro/escápula sem precisar de
            # um protocolo clínico de "ângulo de carregamento".
            medidas["diferenca_cotovelos_pct"] = abs(cotovelo_e[1] - cotovelo_d[1]) / altura_tronco * 100
            medidas["diferenca_pulsos_pct"] = abs(pulso_e[1] - pulso_d[1]) / altura_tronco * 100

            # Compara o comprimento aparente do braço inteiro (ombro → cotovelo → punho)
            # e da perna inteira (quadril → joelho → tornozelo) nos dois lados. Uma
            # diferença grande e consistente pode indicar dismetria de membros ou
            # apenas uma leve rotação do corpo na hora da foto — por isso o texto
            # sempre pede confirmação em mais de uma foto antes de tirar conclusão.
            comp_braco_e = _dist(ombro_e, cotovelo_e) + _dist(cotovelo_e, pulso_e)
            comp_braco_d = _dist(ombro_d, cotovelo_d) + _dist(cotovelo_d, pulso_d)
            maior_braco = max(comp_braco_e, comp_braco_d) or 1.0
            medidas["dif_comprimento_bracos_pct"] = abs(comp_braco_e - comp_braco_d) / maior_braco * 100
            medidas["lado_braco_maior"] = "esquerdo" if comp_braco_e > comp_braco_d else "direito"

            comp_perna_e = _dist(quadril_e, joelho_e) + _dist(joelho_e, tornozelo_e)
            comp_perna_d = _dist(quadril_d, joelho_d) + _dist(joelho_d, tornozelo_d)
            maior_perna = max(comp_perna_e, comp_perna_d) or 1.0
            medidas["dif_comprimento_pernas_pct"] = abs(comp_perna_e - comp_perna_d) / maior_perna * 100
            medidas["lado_perna_maior"] = "esquerda" if comp_perna_e > comp_perna_d else "direita"

        if tipo in TIPOS_LATERAIS:
            # No lado direito a IA enxerga melhor os pontos do lado direito
            # do corpo (e vice-versa) — usa o lado que a própria vista mostra.
            lado_orelha = orelha_d if tipo == "lateral_direita" else orelha_e
            lado_ombro = ombro_d if tipo == "lateral_direita" else ombro_e
            lado_cotovelo = cotovelo_d if tipo == "lateral_direita" else cotovelo_e
            medidas["cabeca_projetada_pct"] = abs(lado_orelha[0] - lado_ombro[0]) / altura_tronco * 100
            medidas["cotovelo_projetado_pct"] = abs(lado_cotovelo[0] - lado_ombro[0]) / altura_tronco * 100

        diagnostico, gravidades, pontuacao = gerar_diagnostico(tipo, medidas)

        # --- desenho da imagem anotada ---
        draw = ImageDraw.Draw(img)
        espessura = max(2, w // 300)

        if tipo in ("frontal", "costas"):
            cor_ombro = _cor_por_gravidade(_classificar(medidas["angulo_ombro"], NIVEIS_ANGULO))
            cor_quadril = _cor_por_gravidade(_classificar(medidas["angulo_quadril"], NIVEIS_ANGULO))
            cor_cabeca = _cor_por_gravidade(_classificar(medidas["angulo_cabeca"], NIVEIS_ANGULO))
            cor_tronco = _cor_por_gravidade(_classificar(medidas["desvio_tronco_pct"], NIVEIS_DESVIO_PCT))

            draw.line([ombro_e, ombro_d], fill=cor_ombro, width=espessura)
            draw.line([quadril_e, quadril_d], fill=cor_quadril, width=espessura)
            draw.line([orelha_e, orelha_d], fill=cor_cabeca, width=max(1, espessura - 1))
            draw.line([ombro_medio, quadril_medio], fill=cor_tronco, width=max(1, espessura - 1))
            r_marco = espessura * 1.3
            for centro in (ombro_medio, quadril_medio):
                draw.ellipse([centro[0] - r_marco, centro[1] - r_marco,
                              centro[0] + r_marco, centro[1] + r_marco], fill=(250, 204, 21))
        else:
            # Vista lateral: ombro/quadril quase colados no eixo X não têm
            # leitura útil de "nível" — desenha só um marcador neutro nos
            # pontos-chave (ombro/quadril) pra referência visual.
            for p in [ombro_e, ombro_d, quadril_e, quadril_d]:
                r = espessura * 1.2
                draw.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], outline=(148, 163, 184), width=2)

        if tipo in ("frontal", "costas"):
            cor_braco_e = _cor_por_gravidade(_classificar(medidas.get("diferenca_cotovelos_pct", 0), NIVEIS_DESVIO_PCT))
            cor_braco_d = cor_braco_e
            draw.line([ombro_e, cotovelo_e, pulso_e], fill=cor_braco_e, width=max(1, espessura - 1))
            draw.line([ombro_d, cotovelo_d, pulso_d], fill=cor_braco_d, width=max(1, espessura - 1))

            cor_perna = _cor_por_gravidade(_classificar(medidas.get("dif_comprimento_pernas_pct", 0), NIVEIS_DESVIO_PCT))
            draw.line([quadril_e, joelho_e, tornozelo_e], fill=cor_perna, width=max(1, espessura - 1))
            draw.line([quadril_d, joelho_d, tornozelo_d], fill=cor_perna, width=max(1, espessura - 1))
            for p in [joelho_e, joelho_d, tornozelo_e, tornozelo_d]:
                r = espessura * 1.6
                draw.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=(59, 130, 246))
        else:
            cor_braco = _cor_por_gravidade(_classificar(medidas.get("cotovelo_projetado_pct", 0), NIVEIS_DESVIO_PCT))
            lado_ombro = ombro_d if tipo == "lateral_direita" else ombro_e
            lado_cotovelo = cotovelo_d if tipo == "lateral_direita" else cotovelo_e
            lado_pulso = pulso_d if tipo == "lateral_direita" else pulso_e
            draw.line([lado_ombro, lado_cotovelo, lado_pulso], fill=cor_braco, width=max(1, espessura - 1))

        for p in [ombro_e, ombro_d, quadril_e, quadril_d, cotovelo_e, cotovelo_d, pulso_e, pulso_d]:
            r = espessura * 1.6
            draw.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=(59, 130, 246))

        # selo com o placar no canto da imagem
        try:
            fonte = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", max(14, w // 25))
        except Exception:
            fonte = ImageFont.load_default()
        texto_placar = f"{pontuacao}/100"
        draw.rectangle([8, 8, 8 + w // 5, 8 + h // 14], fill=(15, 23, 42))
        draw.text((16, 12), texto_placar, font=fonte, fill=(96, 165, 250))

        os.makedirs(os.path.dirname(caminho_saida), exist_ok=True)
        img.save(caminho_saida, quality=92)

        pior_gravidade = "dentro do esperado"
        for g in gravidades:
            if g == "acentuada":
                pior_gravidade = "acentuada"
                break
            if g == "moderada" and pior_gravidade != "acentuada":
                pior_gravidade = "moderada"
            if g == "leve" and pior_gravidade == "dentro do esperado":
                pior_gravidade = "leve"

        alerta = None
        if pior_gravidade != "dentro do esperado":
            alerta = (f"Assimetria {pior_gravidade} detectada nesta vista (placar {pontuacao}/100). "
                       "Isso NÃO é um diagnóstico — é um apoio visual. Avalie com atenção e, se achar "
                       "necessário, encaminhe a um profissional de saúde.")

        return {
            "caminho_anotado": caminho_saida,
            "angulo_ombro": round(medidas["angulo_ombro"], 1) if "angulo_ombro" in medidas else None,
            "angulo_quadril": round(medidas["angulo_quadril"], 1) if "angulo_quadril" in medidas else None,
            "angulo_cabeca": round(medidas["angulo_cabeca"], 1) if "angulo_cabeca" in medidas else None,
            "desvio_tronco_pct": round(medidas["desvio_tronco_pct"], 1) if "desvio_tronco_pct" in medidas else None,
            "diferenca_cotovelos_pct": round(medidas["diferenca_cotovelos_pct"], 1) if "diferenca_cotovelos_pct" in medidas else None,
            "diferenca_pulsos_pct": round(medidas["diferenca_pulsos_pct"], 1) if "diferenca_pulsos_pct" in medidas else None,
            "cabeca_projetada_pct": round(medidas["cabeca_projetada_pct"], 1) if "cabeca_projetada_pct" in medidas else None,
            "cotovelo_projetado_pct": round(medidas["cotovelo_projetado_pct"], 1) if "cotovelo_projetado_pct" in medidas else None,
            "dif_comprimento_bracos_pct": round(medidas["dif_comprimento_bracos_pct"], 1) if "dif_comprimento_bracos_pct" in medidas else None,
            "dif_comprimento_pernas_pct": round(medidas["dif_comprimento_pernas_pct"], 1) if "dif_comprimento_pernas_pct" in medidas else None,
            "pontuacao": pontuacao,
            "gravidade_geral": pior_gravidade,
            "alerta": alerta,
            "diagnostico": diagnostico,
        }
