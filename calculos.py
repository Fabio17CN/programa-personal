import math


def calcular_imc(peso, altura):
    try:
        peso, altura = float(peso), float(altura)
        if peso <= 0 or altura <= 0:
            return None
        return round(peso / (altura ** 2), 2)
    except (TypeError, ValueError):
        return None


def calcular_composicao_corporal(peso, idade, sexo, dobras):
    """
    Calcula % de gordura (BF), massa gorda e massa magra automaticamente a
    partir das dobras cutâneas, usando o protocolo de Jackson & Pollock:
    - 7 dobras (peitoral, axilar, tríceps, subescapular, abdominal,
      suprailíaca, coxa) quando todas estiverem preenchidas — mais preciso;
    - senão, cai para o protocolo de 3 dobras (mais simples de coletar):
      homens = peitoral + abdominal + coxa; mulheres = tríceps + suprailíaca + coxa.
    Devolve (bf, massa_gorda, massa_magra) ou (None, None, None) se não houver
    dobras suficientes ou faltar peso/idade/sexo.
    """
    try:
        peso = float(peso)
        idade = float(idade)
    except (TypeError, ValueError):
        return None, None, None
    if not peso or not idade:
        return None, None, None

    sexo = (sexo or "").strip().lower()
    if not sexo:
        return None, None, None  # sem sexo definido não dá pra escolher a fórmula certa
    homem = sexo.startswith("m") or not sexo.startswith("f")

    def val(nome):
        v = dobras.get(nome)
        try:
            v = float(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None
        # Faixa fisiológica plausível de uma dobra cutânea (mm). Fora disso
        # é quase sempre erro de digitação (ex: confundir cm com mm) — melhor
        # descartar o valor do que deixar ele distorcer o cálculo.
        if v is not None and not (1.0 <= v <= 100.0):
            return None
        return v

    peitoral, axilar, triceps = val("dobra_peitoral"), val("dobra_axilar"), val("dobra_triceps")
    subescapular, abdominal = val("dobra_subescapular"), val("dobra_abdominal")
    suprailiaca, coxa = val("dobra_suprailiaca"), val("dobra_coxa")

    sete_dobras = [peitoral, axilar, triceps, subescapular, abdominal, suprailiaca, coxa]

    densidade = None
    if all(d is not None for d in sete_dobras):
        soma = sum(sete_dobras)
        if homem:
            densidade = 1.112 - 0.00043499 * soma + 0.00000055 * (soma ** 2) - 0.00028826 * idade
        else:
            densidade = 1.097 - 0.00046971 * soma + 0.00000056 * (soma ** 2) - 0.00012828 * idade
    else:
        if homem and peitoral is not None and abdominal is not None and coxa is not None:
            soma = peitoral + abdominal + coxa
            densidade = 1.10938 - 0.0008267 * soma + 0.0000016 * (soma ** 2) - 0.0002574 * idade
        elif not homem and triceps is not None and suprailiaca is not None and coxa is not None:
            soma = triceps + suprailiaca + coxa
            densidade = 1.0994921 - 0.0009929 * soma + 0.0000023 * (soma ** 2) - 0.0001392 * idade

    if densidade is None or densidade <= 0:
        return None, None, None

    bf = (495 / densidade) - 450
    bf = max(3.0, min(60.0, bf))  # limites fisiológicos plausíveis

    massa_gorda = round(peso * bf / 100, 2)
    massa_magra = round(peso - massa_gorda, 2)
    return round(bf, 2), massa_gorda, massa_magra


def classificar_bf(bf, sexo):
    if bf is None:
        return None
    sexo = (sexo or "").lower()
    if sexo.startswith("f"):
        faixas = [(13, "Muito baixo"), (20, "Atlético"), (24, "Bom"), (31, "Aceitável"), (999, "Elevado")]
    else:
        faixas = [(6, "Muito baixo"), (13, "Atlético"), (17, "Bom"), (25, "Aceitável"), (999, "Elevado")]
    for limite, rotulo in faixas:
        if bf < limite:
            return rotulo
    return "Elevado"


def calcular_rcq(cintura, quadril):
    """Relação Cintura-Quadril (RCQ) — indicador clínico clássico de
    distribuição de gordura e risco cardiovascular, usado como complemento
    ao IMC e ao % de gordura em qualquer avaliação física profissional."""
    try:
        cintura, quadril = float(cintura), float(quadril)
        if cintura <= 0 or quadril <= 0:
            return None
    except (TypeError, ValueError):
        return None
    return round(cintura / quadril, 2)


def classificar_rcq(rcq, sexo):
    """Classificação de risco cardiovascular pela RCQ (parâmetros da OMS),
    diferente para homens e mulheres."""
    if rcq is None:
        return None
    sexo = (sexo or "").lower()
    if sexo.startswith("f"):
        if rcq < 0.80:
            return "Baixo risco"
        if rcq < 0.85:
            return "Risco moderado"
        return "Risco alto"
    if rcq < 0.90:
        return "Baixo risco"
    if rcq < 1.00:
        return "Risco moderado"
    return "Risco alto"


def calcular_tmb(peso, altura_m, idade, sexo):
    """Taxa Metabólica Basal (TMB) pela fórmula de Mifflin-St Jeor — hoje o
    padrão mais preciso e mais usado profissionalmente (mais confiável que
    Harris-Benedict). Precisa de peso, altura, idade e sexo."""
    try:
        peso = float(peso)
        altura_cm = float(altura_m) * 100
        idade = float(idade)
    except (TypeError, ValueError):
        return None
    if peso <= 0 or altura_cm <= 0 or idade <= 0:
        return None
    sexo = (sexo or "").strip().lower()
    base = (10 * peso) + (6.25 * altura_cm) - (5 * idade)
    tmb = base + 5 if not sexo.startswith("f") else base - 161
    return round(tmb)


def calcular_rcest(cintura, altura_m):
    """Relação Cintura-Estatura (RCEst / WHtR) — hoje considerado por muitos
    estudos um preditor de risco cardiometabólico até mais consistente que o
    IMC isolado, por já embutir a altura da pessoa na leitura da cintura."""
    try:
        cintura_cm = float(cintura)
        altura_cm = float(altura_m) * 100
        if cintura_cm <= 0 or altura_cm <= 0:
            return None
    except (TypeError, ValueError):
        return None
    return round(cintura_cm / altura_cm, 3)


def classificar_rcest(rcest):
    if rcest is None:
        return None
    if rcest < 0.40:
        return "Abaixo do esperado"
    if rcest < 0.50:
        return "Saudável"
    if rcest < 0.60:
        return "Risco aumentado"
    return "Risco alto"


def calcular_indice_conicidade(peso, altura_m, cintura):
    """Índice de Conicidade (IC) — compara o formato do tronco com um
    cilindro "ideal" de mesmo peso/altura; quanto mais próximo de um cone
    (gordura concentrada na cintura), maior o índice. Complementa o RCQ e o
    RCEst numa avaliação profissional de distribuição de gordura."""
    try:
        peso = float(peso)
        altura_m = float(altura_m)
        cintura_m = float(cintura) / 100
        if peso <= 0 or altura_m <= 0 or cintura_m <= 0:
            return None
    except (TypeError, ValueError):
        return None
    denominador = 0.109 * math.sqrt(peso / altura_m)
    if denominador == 0:
        return None
    return round(cintura_m / denominador, 3)


def classificar_indice_conicidade(ic, sexo):
    if ic is None:
        return None
    sexo = (sexo or "").lower()
    limite = 1.18 if sexo.startswith("f") else 1.25
    if ic < limite - 0.10:
        return "Baixo risco"
    if ic < limite:
        return "Risco moderado"
    return "Risco alto"


def calcular_peso_ideal_detalhado(altura_m, sexo):
    """Peso ideal de referência — em vez de uma única fórmula, cruza 5
    fórmulas clássicas (Lorentz, Devine, Robinson, Miller e Hamwi), cada
    uma com coeficientes próprios para homens e mulheres, e devolve também
    a faixa de peso saudável pelo IMC (18,5 a 24,9). O resultado é mais
    preciso e mais defensável num laudo do que um número isolado — mas
    continua sendo só um parâmetro de referência, não uma meta rígida."""
    try:
        altura_cm = float(altura_m) * 100
        if altura_cm <= 0:
            return None
    except (TypeError, ValueError):
        return None
    sexo = (sexo or "").strip().lower()
    mulher = sexo.startswith("f")
    altura_in = altura_cm / 2.54

    lorentz = (altura_cm - 100 - ((altura_cm - 150) / 2)) if mulher \
        else (altura_cm - 100 - ((altura_cm - 150) / 4))

    if altura_in > 60:
        excedente = altura_in - 60
        devine = (45.5 + 2.3 * excedente) if mulher else (50.0 + 2.3 * excedente)
        robinson = (49.0 + 1.7 * excedente) if mulher else (52.0 + 1.9 * excedente)
        miller = (53.1 + 1.36 * excedente) if mulher else (56.2 + 1.41 * excedente)
        hamwi = (45.5 + 2.2 * excedente) if mulher else (48.0 + 2.7 * excedente)
    else:
        # Fórmulas americanas (Devine/Robinson/Miller/Hamwi) partem de uma
        # base fixa em "5 pés" (152,4cm); abaixo disso usamos só a base, pra
        # não gerar valor negativo/irreal em alunos mais baixos.
        devine, robinson, miller, hamwi = (
            (45.5, 49.0, 53.1, 45.5) if mulher else (50.0, 52.0, 56.2, 48.0)
        )

    media = (lorentz + devine + robinson + miller + hamwi) / 5

    altura_m2 = (altura_cm / 100) ** 2
    faixa_min = 18.5 * altura_m2
    faixa_max = 24.9 * altura_m2

    return {
        "lorentz": round(lorentz, 1),
        "devine": round(devine, 1),
        "robinson": round(robinson, 1),
        "miller": round(miller, 1),
        "hamwi": round(hamwi, 1),
        "media": round(media, 1),
        "faixa_min": round(faixa_min, 1),
        "faixa_max": round(faixa_max, 1),
    }


def calcular_peso_ideal(altura_m, sexo):
    """Peso ideal de referência — média das 5 fórmulas de
    calcular_peso_ideal_detalhado(). Mantido como número único para quem só
    precisa do valor de referência (ex: PDF)."""
    detalhado = calcular_peso_ideal_detalhado(altura_m, sexo)
    return detalhado["media"] if detalhado else None


def classificar_imc(imc):
    if imc is None:
        return None
    if imc < 18.5:
        return "Abaixo do peso"
    if imc < 25:
        return "Peso normal"
    if imc < 30:
        return "Sobrepeso"
    if imc < 35:
        return "Obesidade grau I"
    if imc < 40:
        return "Obesidade grau II"
    return "Obesidade grau III"


COR_GAUGE = {
    "Abaixo do peso": "#60A5FA", "Peso normal": "#10B981", "Sobrepeso": "#F59E0B",
    "Obesidade grau I": "#F97316", "Obesidade grau II": "#EF4444", "Obesidade grau III": "#B91C1C",
    "Muito baixo": "#60A5FA", "Atlético": "#10B981", "Bom": "#22C55E",
    "Aceitável": "#F59E0B", "Elevado": "#EF4444",
}


def gauge_info(valor, minimo, maximo, categoria):
    """Retorna o percentual (0-100) para desenhar o anel do gauge e a cor
    associada à classificação, para os círculos de IMC / % de gordura."""
    if valor is None:
        return {"pct": 0, "cor": "#334155"}
    pct = max(0, min(100, (valor - minimo) / (maximo - minimo) * 100))
    cor = COR_GAUGE.get(categoria, "#3B82F6")
    return {"pct": round(pct, 1), "cor": cor}


_METRICAS_EVOLUCAO = [
    ("peso", "Peso", "kg", -1),
    ("bf", "% de Gordura (BF)", "%", -1),
    ("massa_magra", "Massa Magra", "kg", 1),
    ("massa_gorda", "Massa Gorda", "kg", -1),
    ("cintura", "Cintura", "cm", -1),
    ("abdome", "Abdome", "cm", -1),
    ("quadril", "Quadril", "cm", -1),
    ("braco_d", "Braço Direito", "cm", 1),
    ("braco_e", "Braço Esquerdo", "cm", 1),
    ("coxa_d", "Coxa Direita", "cm", 1),
    ("coxa_e", "Coxa Esquerda", "cm", 1),
]


def comparar_avaliacoes(anterior, atual):
    """
    Compara duas avaliações (dicts) e devolve uma lista de ganhos/perdas
    prontos para exibir: rótulo, diferença, unidade e se a mudança é um
    ganho (positivo) ou uma perda para o aluno, considerando que para
    algumas medidas subir é bom (massa magra) e para outras descer é bom
    (percentual de gordura, cintura etc.).
    """
    resultado = []
    for campo, rotulo, unidade, melhora_quando in _METRICAS_EVOLUCAO:
        antes, depois = anterior.get(campo), atual.get(campo)
        if antes is None or depois is None:
            continue
        diferenca = round(depois - antes, 2)
        if diferenca == 0:
            continue
        positivo = (diferenca > 0 and melhora_quando > 0) or (diferenca < 0 and melhora_quando < 0)
        resultado.append({"rotulo": rotulo, "diferenca": diferenca, "unidade": unidade, "positivo": positivo})
    return resultado


def gerar_parecer_tecnico(aluno, avaliacao, pontuacao_postural_media=None):
    """
    Monta o parecer técnico em texto corrido, no padrão de um laudo de
    avaliação física — junta a leitura de IMC, % de gordura, RCQ e (se
    houver) a pontuação postural média num parágrafo só, pra fechar o
    relatório com uma conclusão profissional em vez de só números soltos.
    """
    sexo = aluno.get("sexo")
    imc = avaliacao.get("imc")
    bf = avaliacao.get("bf")
    rcq = calcular_rcq(avaliacao.get("cintura"), avaliacao.get("quadril"))

    partes = []
    nome = aluno.get("nome") or "O(a) aluno(a)"
    primeiro_nome = nome.split(" ")[0]

    if imc is not None:
        classe_imc = classificar_imc(imc)
        partes.append(f"apresenta IMC de {imc} ({classe_imc.lower()})")
    if bf is not None:
        classe_bf = classificar_bf(bf, sexo)
        partes.append(f"percentual de gordura de {bf}% (classificação: {classe_bf.lower()} para o sexo)")
    if rcq is not None:
        classe_rcq = classificar_rcq(rcq, sexo)
        partes.append(f"relação cintura-quadril de {rcq} ({classe_rcq.lower()})")

    texto = ""
    if partes:
        texto = f"{primeiro_nome} " + ", ".join(partes) + "."

    if pontuacao_postural_media is not None:
        if pontuacao_postural_media >= 85:
            leitura_postura = "sem assimetrias posturais relevantes identificadas na análise por IA"
        elif pontuacao_postural_media >= 60:
            leitura_postura = "com assimetrias posturais leves a moderadas identificadas na análise por IA, que merecem acompanhamento"
        else:
            leitura_postura = "com assimetrias posturais que merecem atenção prioritária no planejamento do treino"
        texto += f" A avaliação postural indica um quadro {leitura_postura}."

    if aluno.get("objetivo"):
        objetivo = aluno.get("objetivo")
        texto += f" Considerando o objetivo declarado de {objetivo.lower()}, recomenda-se seguir o planejamento de treino e reavaliar periodicamente para acompanhar a evolução."

    return texto.strip()


PERGUNTAS_ANAMNESE = [
    "O aluno fuma?", "O aluno bebe?", "O aluno fez cirurgia recente?",
    "O aluno tem vida estressante?", "O aluno é cardiopata?",
    "Dores de cabeça com frequência?", "O aluno dorme bem?",
    "O aluno tem desvios posturais?", "O aluno já fez atividade física?",
    "O aluno possui pinos ou próteses?",
    "O aluno se alimenta bem? Bebe bastante água durante o dia?",
    "O aluno é hipertenso?", "O aluno é diabético?",
    "O aluno tem labirintite?", "O aluno tem colesterol alto?",
    "O aluno sente dores nas articulações?", "O aluno tem outros problemas de saúde?",
]
