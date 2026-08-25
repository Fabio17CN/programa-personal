import os
import json
import base64
import uuid
import shutil
import logging
import tempfile
import time
import re
from functools import wraps
from datetime import datetime, timedelta

# Carrega variáveis de um arquivo .env na pasta do projeto, se existir —
# assim, rodando local (ex: VS Code, sem Docker), as mesmas variáveis
# SMTP_* usadas no docker-compose.yml também funcionam aqui, sem precisar
# configurar nada no sistema operacional. Em produção (Render, Docker etc.)
# as variáveis normalmente já vêm do ambiente, então isso não atrapalha.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from flask import (
    Flask, render_template, request, redirect, url_for, session,
    flash, jsonify, send_file, abort
)

import database as db
import pdf_gen
import postural
import security
import calculos
import email_service
from calculos import (classificar_imc, classificar_bf, comparar_avaliacoes, PERGUNTAS_ANAMNESE,
                      calcular_imc, calcular_composicao_corporal, gauge_info)

BASE_DIR = os.path.dirname(__file__)
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.join(BASE_DIR, "uploads"))
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ---------- Frase motivacional do rodapé (painel do personal + área do aluno) ----------
# Gira sozinha uma vez por dia (mesma frase o dia inteiro, pra todo mundo).
# Se o personal cadastrar um slogan próprio em Configurações, ele continua
# tendo prioridade sobre essa lista.
FRASES_MOTIVACIONAIS = [
    "Seu corpo alcança o que sua mente acredita.",
    "Disciplina hoje, resultado sempre.",
    "Constância vence intensidade.",
    "Cada treino é um depósito no seu futuro.",
    "O único treino ruim é o que não aconteceu.",
    "Progresso, não perfeição.",
    "Force o limite de ontem.",
    "Grandes resultados pedem pequenos hábitos repetidos.",
    "Foco no processo, o resultado é consequência.",
    "Você não precisa ser extremo, só ser constante.",
    "A dor de hoje é a força de amanhã.",
    "Menos desculpa, mais treino.",
    "Transformação é feita de dias comuns bem vividos.",
    "Sua única competição é quem você foi ontem.",
]


def frase_do_dia():
    """Escolhe uma frase da lista com base na data de hoje — muda
    automaticamente todos os dias, sem precisar guardar estado no banco."""
    indice = datetime.now().toordinal() % len(FRASES_MOTIVACIONAIS)
    return FRASES_MOTIVACIONAIS[indice]

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "troque-esta-chave-em-producao")
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    # Usado apenas quando a sessão é "permanente" (opção "Mantenha-me conectado"
    # marcada no login). Sem essa opção, o cookie de sessão expira ao fechar o
    # navegador, independente deste valor.
    PERMANENT_SESSION_LIFETIME=timedelta(days=30),
)
# Filtro para extrair só o nome do arquivo de um caminho salvo no banco,
# funcionando tanto com caminhos do Windows (\) quanto do Linux (/) —
# usar .split('/') direto nos templates quebrava em servidores Windows.
app.jinja_env.filters["basename"] = lambda caminho: os.path.basename((caminho or "").replace("\\", "/"))


def _telefone_whatsapp(numero):
    """Monta o número no formato que o wa.me espera (55 + DDD + número),
    removendo um '55' que a pessoa já tenha digitado na frente ao cadastrar
    — sem isso, o link ficava com o DDI duplicado e não abria a conversa
    certa (ex: 5555889...  em vez de 5588999...)."""
    if not numero:
        return ""
    digitos = re.sub(r"\D", "", numero)
    if len(digitos) >= 12 and digitos.startswith("55"):
        digitos = digitos[2:]
    return "55" + digitos


app.jinja_env.filters["telefone_whatsapp"] = _telefone_whatsapp


def _youtube_id(url):
    """Extrai o ID de um link do YouTube (normal, encurtado youtu.be ou
    /shorts/), pra montar o player embutido na ficha do aluno. Devolve None
    pra qualquer outro link (Instagram, Google Drive etc.), que continua
    aparecendo como um botão de link normal em vez de player."""
    if not url:
        return None
    m = re.search(r"(?:youtube\.com/(?:watch\?v=|shorts/|embed/)|youtu\.be/)([A-Za-z0-9_-]{11})", url)
    return m.group(1) if m else None


app.jinja_env.filters["youtube_id"] = _youtube_id
app.jinja_env.globals["enumerate"] = enumerate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nm_personal")

db.criar_tabelas()


def _enviar_pdf_temporario(nome_arquivo, download_name, funcao_geracao):
    """
    Gera um PDF em uma pasta temporária e o envia como download.

    Importante: a pasta temporária NÃO pode ser apagada com
    `with tempfile.TemporaryDirectory()` aqui, porque o Flask só lê o
    arquivo do disco depois que esta função retorna (o envio é feito de
    forma streamada pelo servidor). Se a pasta for apagada antes disso,
    o download falha de forma intermitente — essa é a causa do erro
    "NotADirectoryError" ao tentar apagar a pasta do Windows Temp.

    Por isso a limpeza é agendada para rodar somente depois que a
    resposta terminar de ser enviada (`response.call_on_close`).
    """
    tmp_dir = tempfile.mkdtemp(prefix="nm_personal_")
    try:
        caminho_pdf = os.path.join(tmp_dir, nome_arquivo)
        funcao_geracao(caminho_pdf, tmp_dir)
        resposta = send_file(caminho_pdf, as_attachment=True, download_name=download_name)
        resposta.call_on_close(lambda: shutil.rmtree(tmp_dir, ignore_errors=True))
        return resposta
    except Exception:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        logger.exception("Falha ao gerar/enviar PDF (%s)", download_name)
        raise


@app.context_processor
def inject_csrf():
    return {"csrf_token": security.gerar_csrf_token}


@app.before_request
def checar_csrf():
    if request.method == "POST":
        # Formulários tradicionais mandam o token no corpo (form-urlencoded);
        # as chamadas JSON do modal de anamnese (fetch) mandam no cabeçalho
        # X-CSRFToken, já que não têm um <form> por trás.
        token = request.form.get("csrf_token") or request.headers.get("X-CSRFToken")
        if not security.validar_csrf(token):
            abort(400, description="Sessão expirada ou requisição inválida. Recarregue a página e tente novamente.")


def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        personal_id = session.get("personal_id")
        if not personal_id:
            return redirect(url_for("login"))
        # A sessão pode ficar "logada" no navegador mesmo depois do banco de
        # dados ser trocado/resetado (ex: veio um banco novo dentro do zip).
        # Sem essa checagem, qualquer INSERT que dependa desse personal_id
        # (aluno, treino, avaliação...) quebra com FOREIGN KEY constraint failed.
        personal = db.buscar_personal_por_id(personal_id)
        if not personal:
            session.clear()
            flash("Sua sessão expirou ou o banco de dados foi atualizado. Faça login novamente.", "warning")
            return redirect(url_for("login"))
        # "Desconectar todas as outras sessões" ao trocar a senha: cada login
        # grava a versão atual na sessão. Se alguém troca a senha em outro
        # aparelho, a versão no banco muda e este cookie antigo para de bater.
        if session.get("sessao_versao") != (personal.get("sessao_versao") or 1):
            session.clear()
            flash("Sua senha foi alterada em outro acesso. Faça login novamente.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def aluno_login_required(f):
    """Equivalente ao login_required, só que para o acesso próprio do
    aluno (área com menus limitados: treinos, avaliações, anamnese,
    agenda, mensagens e perfil)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        aluno_id = session.get("aluno_id")
        if not aluno_id:
            return redirect(url_for("login"))
        aluno = db.buscar_aluno_por_id_simples(aluno_id)
        if not aluno:
            session.clear()
            flash("Sua sessão expirou ou o banco de dados foi atualizado. Faça login novamente.", "warning")
            return redirect(url_for("login"))
        if session.get("sessao_versao_aluno") != (aluno.get("sessao_versao") or 1):
            session.clear()
            flash("Sua senha foi alterada em outro acesso. Faça login novamente.", "warning")
            return redirect(url_for("login"))
        return f(aluno, *args, **kwargs)
    return wrapper


# ---------- AUTENTICAÇÃO ----------

@app.route("/")
def raiz():
    if session.get("personal_id"):
        return redirect(url_for("dashboard"))
    if session.get("aluno_id"):
        return redirect(url_for("aluno_area"))
    return redirect(url_for("login"))


MINUTOS_BLOQUEIO_LOGIN = db.BLOQUEIO_MINUTOS


@app.route("/login", methods=["GET", "POST"])
def login():
    # Se a sessão de "mantenha-me conectado" ainda está válida (o aplicativo
    # abre direto em /dashboard, que é a tela do personal — mesmo quando
    # quem abriu foi um aluno), não mostra o formulário de login de novo:
    # manda direto pra área certa. Sem isso, um aluno reabrindo o app caía
    # aqui vendo a tela de login só que com a barra de menu do aluno
    # aparecendo embaixo (a sessão dele continuava válida, só a tela é que
    # estava errada).
    if request.method == "GET":
        if session.get("personal_id") and db.buscar_personal_por_id(session["personal_id"]):
            return redirect(url_for("dashboard"))
        if session.get("aluno_id") and db.buscar_aluno_por_id_simples(session["aluno_id"]):
            return redirect(url_for("aluno_area"))

    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        senha = request.form.get("senha", "").strip()
        if not usuario or not senha:
            flash("Preencha usuário e senha.", "warning")
            return render_template("login.html")

        # Tenta primeiro como Personal; se não encontrar, tenta como Aluno
        # (usuário/e-mail de aluno só existe depois que ele ativa a própria
        # conta com o código enviado pelo personal).
        personal = db.buscar_personal_por_usuario(usuario)
        if personal:
            if db.esta_bloqueado(personal):
                flash(f"Muitas tentativas erradas. Tente novamente em até {MINUTOS_BLOQUEIO_LOGIN} minutos.", "error")
                return render_template("login.html")
            if security.conferir_senha(personal["senha_hash"], senha):
                db.limpar_falhas_login(personal["id"])
                # "Mantenha-me conectado": se marcado, a sessão vira permanente e dura
                # PERMANENT_SESSION_LIFETIME (30 dias). Se desmarcado, o cookie de
                # sessão expira assim que o navegador for fechado.
                session.permanent = bool(request.form.get("lembrar"))
                session["personal_id"] = personal["id"]
                session["personal_nome"] = personal.get("nome_exibicao") or personal["usuario"]
                session["sessao_versao"] = personal.get("sessao_versao") or 1
                return redirect(url_for("dashboard"))
            db.registrar_falha_login(usuario)
            flash("Usuário ou senha inválidos.", "error")
            return render_template("login.html")

        aluno = db.buscar_aluno_por_usuario_ou_email(usuario)
        if aluno and aluno.get("conta_ativada"):
            if db.esta_bloqueado_generico(aluno):
                flash(f"Muitas tentativas erradas. Tente novamente em até {MINUTOS_BLOQUEIO_LOGIN} minutos.", "error")
                return render_template("login.html")
            if aluno.get("senha_hash") and security.conferir_senha(aluno["senha_hash"], senha):
                db.limpar_falhas_login_aluno(aluno["id"])
                session.permanent = bool(request.form.get("lembrar"))
                session["aluno_id"] = aluno["id"]
                session["aluno_nome"] = aluno.get("nome")
                session["sessao_versao_aluno"] = aluno.get("sessao_versao") or 1
                return redirect(url_for("aluno_area"))
            db.registrar_falha_login_aluno(aluno["id"])
            flash("Usuário ou senha inválidos.", "error")
            return render_template("login.html")

        flash("Usuário ou senha inválidos.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


def _aluno_sessao_valida():
    """Confere se há um aluno logado com sessão válida. Devolve o dict do
    aluno ou None (já limpando a sessão expirada, se for o caso) — usado
    em todas as telas do painel do próprio aluno."""
    if not session.get("aluno_id"):
        return None
    aluno = db.buscar_aluno_por_id_simples(session["aluno_id"])
    if not aluno or session.get("sessao_versao_aluno") != (aluno.get("sessao_versao") or 1):
        session.clear()
        return None
    return aluno


@app.route("/aluno/area")
def aluno_area():
    """Área do aluno após o login: saudação, progresso, atalhos para as
    telas de acompanhamento (treinos, avaliações, anamnese, agenda,
    mensagens, perfil), um resumo rápido da semana e uma frase
    motivacional do próprio personal.
    """
    aluno = _aluno_sessao_valida()
    if not aluno:
        flash("Sua sessão expirou. Faça login novamente.", "warning")
        return redirect(url_for("login"))
    anamnese_pendente = db.buscar_anamnese_pendente_aluno(aluno["id"])

    # --- Resumo rápido da semana ---
    treinos = db.listar_treinos(aluno["id"])
    hoje = datetime.now()
    inicio_semana = (hoje - timedelta(days=hoje.weekday())).strftime("%Y-%m-%d")
    treinos_semana = sum(1 for t in treinos if (t.get("data") or "") >= inicio_semana)

    agendamentos = db.listar_agendamentos_aluno(aluno["id"])
    hoje_iso = hoje.strftime("%Y-%m-%d")
    compromissos_hoje = sum(1 for ag in agendamentos if (ag.get("data_hora") or "").startswith(hoje_iso))

    # --- Progresso: usa a meta ativa mais recente do aluno, se houver ---
    metas_ativas = db.listar_metas(aluno["personal_id"], aluno_id=aluno["id"], apenas_ativas=True)
    progresso_pct = 0
    progresso_titulo = "Continue treinando"
    if metas_ativas:
        meta = metas_ativas[0]
        if meta.get("valor_alvo") is not None and meta.get("valor_inicial") is not None and meta.get("valor_atual") is not None:
            distancia_total = abs(meta["valor_alvo"] - meta["valor_inicial"])
            percorrido = abs(meta["valor_atual"] - meta["valor_inicial"])
            if distancia_total > 0:
                progresso_pct = max(0, min(100, round((percorrido / distancia_total) * 100)))
            else:
                progresso_pct = 100
        progresso_titulo = meta.get("titulo") or "Em andamento"
    else:
        # Sem meta cadastrada: mostra a frequência de treinos da semana (meta implícita de 5x).
        progresso_pct = max(0, min(100, round((treinos_semana / 5) * 100)))
        progresso_titulo = "Em andamento"

    personal = db.buscar_personal_por_id(aluno["personal_id"])
    notificacoes_nao_lidas = db.contar_notificacoes_nao_lidas_aluno(aluno["id"])
    mensagens_nao_lidas = db.contar_mensagens_nao_lidas_aluno(aluno["personal_id"], aluno["id"])

    # --- Evolução: monta o comparativo (ganhou/perdeu) usando a avaliação
    # mais recente contra a anterior, com a data em que o acompanhamento
    # começou — o gráfico em si é desenhado no navegador a partir do JSON
    # de /aluno/evolucao-dados.json, e cresce sozinho a cada nova medida.
    avaliacoes_evolucao = db.listar_avaliacoes(aluno["id"], apenas_finalizadas=True)
    total_avaliacoes = len(avaliacoes_evolucao)
    data_inicio_avaliacao = avaliacoes_evolucao[0]["data"][:10] if avaliacoes_evolucao else None
    comparativo_evolucao = (comparar_avaliacoes(avaliacoes_evolucao[-2], avaliacoes_evolucao[-1])
                             if total_avaliacoes >= 2 else None)

    return render_template(
        "aluno_area.html", aluno=aluno, personal=personal, anamnese_pendente=anamnese_pendente,
        treinos_semana=treinos_semana, compromissos_hoje=compromissos_hoje,
        progresso_pct=progresso_pct, progresso_titulo=progresso_titulo, frase_dia=frase_do_dia(),
        notificacoes_nao_lidas=notificacoes_nao_lidas, mensagens_nao_lidas=mensagens_nao_lidas,
        total_avaliacoes=total_avaliacoes, data_inicio_avaliacao=data_inicio_avaliacao,
        comparativo_evolucao=comparativo_evolucao,
    )


@app.route("/aluno/evolucao-dados.json")
def aluno_evolucao_dados_json():
    """Dados (peso/BF/IMC por data) das avaliações já finalizadas do
    próprio aluno logado, para desenhar o gráfico de evolução em
    'MINHA ÁREA'."""
    aluno = _aluno_sessao_valida()
    if not aluno:
        return jsonify({"erro": "sessão expirada"}), 401
    avaliacoes = db.listar_avaliacoes(aluno["id"], apenas_finalizadas=True)
    return jsonify({
        "labels": [a["data"][:10] for a in avaliacoes],
        "peso": [a["peso"] for a in avaliacoes],
        "bf": [a["bf"] for a in avaliacoes],
        "imc": [a["imc"] for a in avaliacoes],
    })


@app.route("/aluno/notificacoes")
def aluno_notificacoes():
    """Lista as notificações do aluno (ex.: avisos de que o personal
    enviou uma anamnese nova para ele responder). Ao tocar num aviso de
    anamnese, abre direto o modal de resposta — igual ao atalho da
    própria área do aluno."""
    aluno = _aluno_sessao_valida()
    if not aluno:
        flash("Sua sessão expirou. Faça login novamente.", "warning")
        return redirect(url_for("login"))
    lista = db.listar_notificacoes_aluno(aluno["id"])
    db.marcar_notificacoes_lidas_aluno(aluno["id"])
    return render_template("aluno_notificacoes.html", notificacoes=lista)


@app.route("/aluno/notificacoes/<int:notificacao_id>/excluir", methods=["POST"])
def aluno_notificacao_excluir(notificacao_id):
    aluno = _aluno_sessao_valida()
    if not aluno:
        flash("Sua sessão expirou. Faça login novamente.", "warning")
        return redirect(url_for("login"))
    db.excluir_notificacao_aluno(notificacao_id, aluno["id"])
    return redirect(url_for("aluno_notificacoes"))


# ---------- PAINEL DO ALUNO: telas de visualização (somente leitura) ----------

@app.route("/aluno/meus-treinos")
def aluno_meus_treinos():
    aluno = _aluno_sessao_valida()
    if not aluno:
        flash("Sua sessão expirou. Faça login novamente.", "warning")
        return redirect(url_for("login"))
    treinos = db.listar_treinos(aluno["id"])
    # Calcula quantos dias/exercícios cada ficha tem, pra mostrar um resumo
    # na listagem sem o aluno precisar abrir cada uma pra descobrir.
    for t in treinos:
        dias_t = pdf_gen._normalizar_dias_treino(t)
        t["total_dias"] = len([d for d in dias_t if d.get("exercicios")])
        t["total_exercicios"] = sum(len(d.get("exercicios") or []) for d in dias_t)
    return render_template("aluno_meus_treinos.html", aluno=aluno, treinos=treinos)


@app.route("/aluno/meus-treinos/<int:treino_id>")
def aluno_treino_detalhe(treino_id):
    aluno = _aluno_sessao_valida()
    if not aluno:
        flash("Sua sessão expirou. Faça login novamente.", "warning")
        return redirect(url_for("login"))
    treino = db.buscar_treino(treino_id)
    if not treino or treino["aluno_id"] != aluno["id"]:
        abort(404)
    # O treino é salvo como uma lista de "dias" (cada um com letra,
    # dia da semana, grupo muscular e a lista de exercícios daquele dia)
    # — a mesma normalização já usada na geração do PDF, que também
    # aceita o formato antigo (lista simples de exercícios, sem dias).
    dias = pdf_gen._normalizar_dias_treino(treino)
    # Destaca automaticamente o dia de treino que bate com o dia da semana
    # de hoje (ex: se hoje é quinta e existe um dia "Quinta" na ficha, ele
    # já abre selecionado) — poupa o aluno de ter que procurar qual treino
    # fazer hoje entre várias abas.
    hoje_semana = db.DIAS_SEMANA[datetime.now().weekday()]
    indice_dia_hoje = next(
        (i for i, d in enumerate(dias) if d.get("exercicios") and d.get("dia_semana") == hoje_semana),
        None
    )
    return render_template("aluno_treino_detalhe.html", aluno=aluno, treino=treino, dias=dias,
                            indice_dia_hoje=indice_dia_hoje)


@app.route("/aluno/meus-treinos/<int:treino_id>/pdf")
def aluno_treino_pdf(treino_id):
    """Permite o próprio aluno baixar a ficha em PDF (mesmo layout que o
    personal usa), sem precisar pedir pra ele mandar de novo."""
    aluno = _aluno_sessao_valida()
    if not aluno:
        flash("Sua sessão expirou. Faça login novamente.", "warning")
        return redirect(url_for("login"))
    treino = db.buscar_treino(treino_id)
    if not treino or treino["aluno_id"] != aluno["id"]:
        abort(404)
    personal = db.buscar_personal_por_id(aluno["personal_id"])

    nome_arquivo = f"treino_{aluno['nome'].replace(' ', '_')}.pdf"

    def gerar(caminho_pdf, tmp_dir):
        pdf_gen.gerar_pdf_treino(caminho_pdf, personal, aluno, treino)

    return _enviar_pdf_temporario(nome_arquivo, f"Treino_{aluno['nome'].replace(' ', '_')}.pdf", gerar)


@app.route("/aluno/minhas-avaliacoes")
def aluno_minhas_avaliacoes():
    aluno = _aluno_sessao_valida()
    if not aluno:
        flash("Sua sessão expirou. Faça login novamente.", "warning")
        return redirect(url_for("login"))
    # O aluno só vê avaliações que o personal já finalizou (medidas
    # completas e conferidas) — enquanto está em rascunho, fica visível
    # só no painel do personal.
    avaliacoes = sorted(db.listar_avaliacoes(aluno["id"], apenas_finalizadas=True),
                         key=lambda a: a.get("data") or "", reverse=True)
    return render_template("aluno_minhas_avaliacoes.html", aluno=aluno, avaliacoes=avaliacoes)


@app.route("/aluno/minhas-avaliacoes/<int:avaliacao_id>")
def aluno_avaliacao_detalhe(avaliacao_id):
    aluno = _aluno_sessao_valida()
    if not aluno:
        flash("Sua sessão expirou. Faça login novamente.", "warning")
        return redirect(url_for("login"))
    avaliacao = db.buscar_avaliacao(avaliacao_id)
    if not avaliacao or avaliacao["aluno_id"] != aluno["id"] or not avaliacao.get("finalizada"):
        abort(404)
    cat_imc = classificar_imc(avaliacao.get("imc"))
    cat_bf = classificar_bf(avaliacao.get("bf"), aluno.get("sexo"))
    gauge_imc = gauge_info(avaliacao.get("imc"), 15, 40, cat_imc)
    gauge_bf = gauge_info(avaliacao.get("bf"), 3, 45, cat_bf)

    # Mesmos indicadores profissionais mostrados pro personal, só que
    # aqui na visão (somente leitura) do próprio aluno.
    rcq_val = calculos.calcular_rcq(avaliacao.get("cintura"), avaliacao.get("quadril"))
    rcest_val = calculos.calcular_rcest(avaliacao.get("cintura"), avaliacao.get("altura"))
    ic_val = calculos.calcular_indice_conicidade(avaliacao.get("peso"), avaliacao.get("altura"), avaliacao.get("cintura"))
    tmb_val = calculos.calcular_tmb(avaliacao.get("peso"), avaliacao.get("altura"), aluno.get("idade"), aluno.get("sexo"))
    peso_ideal_detalhe = calculos.calcular_peso_ideal_detalhado(avaliacao.get("altura"), aluno.get("sexo"))
    peso_ideal_val = peso_ideal_detalhe["media"] if peso_ideal_detalhe else None
    indicadores_extra = {
        "rcq": rcq_val, "cat_rcq": calculos.classificar_rcq(rcq_val, aluno.get("sexo")),
        "rcest": rcest_val, "cat_rcest": calculos.classificar_rcest(rcest_val),
        "ic": ic_val, "cat_ic": calculos.classificar_indice_conicidade(ic_val, aluno.get("sexo")),
        "tmb": tmb_val, "peso_ideal": peso_ideal_val, "peso_ideal_detalhe": peso_ideal_detalhe,
    }
    return render_template("aluno_avaliacao_detalhe.html", aluno=aluno, avaliacao=avaliacao,
                            cat_imc=cat_imc, cat_bf=cat_bf, gauge_imc=gauge_imc, gauge_bf=gauge_bf,
                            indicadores_extra=indicadores_extra)


@app.route("/aluno/minhas-avaliacoes/apagar-historico", methods=["POST"])
def aluno_avaliacoes_apagar_historico():
    """Apaga todo o histórico de avaliações físicas do próprio aluno —
    ação irreversível, disparada pelo botão em 'Minha Avaliação'."""
    aluno = _aluno_sessao_valida()
    if not aluno:
        flash("Sua sessão expirou. Faça login novamente.", "warning")
        return redirect(url_for("login"))
    db.excluir_historico_avaliacoes(aluno["id"])
    flash("Seu histórico de avaliações foi apagado.", "success")
    return redirect(url_for("aluno_minhas_avaliacoes"))


@app.route("/aluno/minhas-avaliacoes/<int:avaliacao_id>/excluir", methods=["POST"])
def aluno_avaliacao_excluir(avaliacao_id):
    """Apaga uma única avaliação do próprio aluno — botão pequeno no
    cantinho da tela de detalhe (em vez do antigo botão grande que
    apagava o histórico inteiro lá na listagem)."""
    aluno = _aluno_sessao_valida()
    if not aluno:
        flash("Sua sessão expirou. Faça login novamente.", "warning")
        return redirect(url_for("login"))
    avaliacao = db.buscar_avaliacao(avaliacao_id)
    if not avaliacao or avaliacao["aluno_id"] != aluno["id"]:
        abort(404)
    ok = db.excluir_avaliacao(avaliacao_id, aluno["id"])
    flash("Avaliação excluída." if ok else "Não foi possível excluir essa avaliação.",
          "success" if ok else "warning")
    return redirect(url_for("aluno_minhas_avaliacoes"))


@app.route("/aluno/minha-anamnese")
def aluno_minha_anamnese():
    aluno = _aluno_sessao_valida()
    if not aluno:
        flash("Sua sessão expirou. Faça login novamente.", "warning")
        return redirect(url_for("login"))
    pendente = db.buscar_anamnese_pendente_aluno(aluno["id"])
    respondida = db.buscar_ultima_anamnese_respondida(aluno["id"])
    respostas = []
    if respondida:
        try:
            respostas = json.loads(respondida.get("respostas_json") or "[]")
        except (TypeError, ValueError):
            respostas = []
    return render_template("aluno_minha_anamnese.html", aluno=aluno, pendente=pendente,
                            respondida=respondida, respostas=respostas)


@app.route("/aluno/minha-agenda")
def aluno_minha_agenda():
    aluno = _aluno_sessao_valida()
    if not aluno:
        flash("Sua sessão expirou. Faça login novamente.", "warning")
        return redirect(url_for("login"))
    hoje_iso = datetime.now().strftime("%Y-%m-%d")
    proximos = db.listar_agendamentos_aluno(aluno["id"], a_partir_de=hoje_iso)
    anteriores = [a for a in db.listar_agendamentos_aluno(aluno["id"]) if a["id"] not in {p["id"] for p in proximos}]
    return render_template("aluno_minha_agenda.html", aluno=aluno, proximos=proximos, anteriores=anteriores)


@app.route("/aluno/minhas-mensagens")
def aluno_minhas_mensagens():
    """Tela inicial de mensagens do aluno: só o card do personal dele (foto,
    nome e contador de não lidas) — igual à lista de conversas do WhatsApp,
    só que com uma única conversa possível (o aluno só fala com o próprio
    personal). Tocar no card abre o chat em tela cheia."""
    aluno = _aluno_sessao_valida()
    if not aluno:
        flash("Sua sessão expirou. Faça login novamente.", "warning")
        return redirect(url_for("login"))
    personal_id = aluno["personal_id"]
    personal = db.buscar_personal_por_id(personal_id)
    nao_lidas = db.contar_mensagens_nao_lidas_aluno(personal_id, aluno["id"])
    ultima = db.listar_mensagens_chat(personal_id, aluno["id"], limite=1000)
    ultima_msg = ultima[-1] if ultima else None
    return render_template("aluno_minhas_mensagens.html", aluno=aluno, personal=personal,
                            nao_lidas=nao_lidas, ultima_msg=ultima_msg)


@app.route("/aluno/minhas-mensagens/conversa")
def aluno_minhas_mensagens_conversa():
    """Chat real do aluno com o próprio personal — o aluno só conversa com
    o personal dele (não há outros alunos ou personals pra falar aqui)."""
    aluno = _aluno_sessao_valida()
    if not aluno:
        flash("Sua sessão expirou. Faça login novamente.", "warning")
        return redirect(url_for("login"))
    personal_id = aluno["personal_id"]
    db.marcar_chat_lido_aluno(personal_id, aluno["id"])
    mensagens_lista = db.listar_mensagens_chat(personal_id, aluno["id"])
    ultimo_id = mensagens_lista[-1]["id"] if mensagens_lista else 0
    ultimo_dia = (mensagens_lista[-1]["enviado_em"] or "")[:10] if mensagens_lista else ""
    personal = db.buscar_personal_por_id(personal_id)
    agrupadas = _enriquecer_mensagens(_agrupar_mensagens_por_dia(mensagens_lista), aluno, "aluno")
    return render_template("aluno_minhas_mensagens_conversa.html", aluno=aluno, personal=personal,
                            mensagens=agrupadas,
                            ultimo_id=ultimo_id, ultimo_dia=ultimo_dia)


@app.route("/aluno/minhas-mensagens/enviar", methods=["POST"])
def aluno_mensagens_enviar():
    aluno = _aluno_sessao_valida()
    if not aluno:
        return jsonify({"ok": False, "erro": "Sessão expirada."}), 401
    texto = (request.form.get("texto") or "").strip()
    if not texto:
        return jsonify({"ok": False, "erro": "Escreva uma mensagem."}), 400
    texto = texto[:4000]
    mid = db.enviar_mensagem_chat(aluno["personal_id"], aluno["id"], "aluno", texto)
    return jsonify({"ok": True, "id": mid})


@app.route("/aluno/minhas-mensagens/enviar-midia", methods=["POST"])
def aluno_mensagens_enviar_midia():
    aluno = _aluno_sessao_valida()
    if not aluno:
        return jsonify({"ok": False, "erro": "Sessão expirada."}), 401
    tipo = request.form.get("tipo", "")
    if tipo not in ("audio", "video", "imagem"):
        return jsonify({"ok": False, "erro": "Tipo de mídia inválido."}), 400
    arquivo = request.files.get("arquivo")
    if not arquivo or not arquivo.filename:
        return jsonify({"ok": False, "erro": "Nenhum arquivo recebido."}), 400
    arquivo.seek(0, os.SEEK_END)
    if arquivo.tell() > TAMANHO_MAX_MIDIA_CHAT:
        return jsonify({"ok": False, "erro": "Arquivo muito grande (máx. 25MB)."}), 400
    arquivo.seek(0)
    try:
        caminho_salvo = _salvar_midia_chat(aluno["id"], arquivo, tipo)
    except MidiaChatInvalida as e:
        return jsonify({"ok": False, "erro": str(e)}), 400
    except OSError:
        logger.exception("Falha ao salvar mídia do chat (aluno_id=%s)", aluno["id"])
        return jsonify({"ok": False, "erro": "Não foi possível salvar o arquivo. Tente novamente."}), 500
    duracao = request.form.get("duracao", type=float)
    mid = db.enviar_mensagem_chat(aluno["personal_id"], aluno["id"], "aluno", "", tipo=tipo,
                                   midia_arquivo=caminho_salvo, midia_duracao=duracao)
    return jsonify({"ok": True, "id": mid})


@app.route("/aluno/minhas-mensagens/novas")
def aluno_mensagens_novas():
    aluno = _aluno_sessao_valida()
    if not aluno:
        return jsonify({"ok": False, "erro": "Sessão expirada."}), 401
    personal_id = aluno["personal_id"]
    depois_de = request.args.get("depois_de", 0, type=int)
    novas = db.listar_mensagens_chat_novas(personal_id, aluno["id"], depois_de)
    if any(m["remetente"] == "personal" for m in novas):
        db.marcar_chat_lido_aluno(personal_id, aluno["id"])
    novas_json = [_mensagem_para_json(m, aluno, "aluno") for m in novas]
    lidas = db.listar_ids_lidos(personal_id, aluno["id"], "aluno")
    apagadas = db.listar_ids_apagados(personal_id, aluno["id"])
    return jsonify({"ok": True, "mensagens": novas_json, "lidas": lidas, "apagadas": apagadas})


@app.route("/aluno/minhas-mensagens/apagar", methods=["POST"])
def aluno_mensagens_apagar():
    """'Apagar para todos' (estilo WhatsApp): o aluno só pode apagar
    mensagens que ELE mesmo enviou — o personal também deixa de ver o
    conteúdo assim que a tela dele buscar mensagens novas de novo."""
    aluno = _aluno_sessao_valida()
    if not aluno:
        return jsonify({"ok": False, "erro": "Sessão expirada."}), 401
    mensagem_id = request.form.get("mensagem_id", type=int)
    if not mensagem_id:
        return jsonify({"ok": False, "erro": "Mensagem inválida."}), 400
    ok = db.apagar_mensagem_chat(mensagem_id, aluno["personal_id"], aluno["id"], "aluno")
    if not ok:
        return jsonify({"ok": False, "erro": "Só é possível apagar mensagens enviadas por você."}), 403
    return jsonify({"ok": True, "id": mensagem_id})


@app.route("/aluno/meu-perfil", methods=["GET", "POST"])
def aluno_meu_perfil():
    aluno = _aluno_sessao_valida()
    if not aluno:
        flash("Sua sessão expirou. Faça login novamente.", "warning")
        return redirect(url_for("login"))

    if request.method == "POST":
        arquivo = request.files.get("foto_perfil")
        if arquivo and arquivo.filename:
            extensao = os.path.splitext(arquivo.filename)[1].lower() or ".jpg"
            if extensao not in EXTENSOES_FOTO_PERMITIDAS:
                flash("Formato de imagem não suportado. Use PNG, JPG, WEBP ou GIF.", "warning")
                return redirect(url_for("aluno_meu_perfil"))
            pasta_aluno = os.path.join(UPLOAD_DIR, str(aluno["id"]))
            os.makedirs(pasta_aluno, exist_ok=True)
            nome_arquivo = f"perfil_{uuid.uuid4().hex[:8]}{extensao}"
            caminho = os.path.join(pasta_aluno, nome_arquivo)
            arquivo.save(caminho)
            db.atualizar_foto_perfil(aluno["id"], aluno["personal_id"], caminho)
            flash("Foto de perfil atualizada!", "success")
        else:
            flash("Selecione uma imagem para enviar.", "warning")
        return redirect(url_for("aluno_meu_perfil"))

    return render_template("aluno_meu_perfil.html", aluno=aluno)


@app.route("/aluno/meu-perfil/senha", methods=["POST"])
def aluno_meu_perfil_senha():
    """Aluno trocar a própria senha de dentro do app — mesmo padrão que já
    existe pro personal em Configurações. Continua exigindo a senha atual
    por segurança. Trocar a senha invalida outras sessões abertas com essa
    conta (mesmo comportamento do personal), mas a sessão ATUAL é
    atualizada na hora pra quem trocou não ser deslogado por engano."""
    aluno = _aluno_sessao_valida()
    if not aluno:
        flash("Sua sessão expirou. Faça login novamente.", "warning")
        return redirect(url_for("login"))

    senha_atual = (request.form.get("senha_atual") or "").strip()
    senha_nova = (request.form.get("senha_nova") or "").strip()
    senha_nova2 = (request.form.get("senha_nova2") or "").strip()

    if not senha_atual or not senha_nova or not senha_nova2:
        flash("Preencha a senha atual e a nova senha (com confirmação).", "warning")
        return redirect(url_for("aluno_meu_perfil"))
    if not aluno.get("senha_hash") or not security.conferir_senha(aluno["senha_hash"], senha_atual):
        flash("Senha atual incorreta.", "error")
        return redirect(url_for("aluno_meu_perfil"))
    if senha_nova != senha_nova2:
        flash("A nova senha e a confirmação não coincidem.", "warning")
        return redirect(url_for("aluno_meu_perfil"))
    if not security.senha_forte_o_suficiente(senha_nova):
        flash(security.motivo_senha_fraca(senha_nova), "warning")
        return redirect(url_for("aluno_meu_perfil"))

    db.atualizar_senha_hash_aluno(aluno["id"], security.hash_senha(senha_nova))
    aluno_atualizado = db.buscar_aluno_por_id_simples(aluno["id"])
    session["sessao_versao_aluno"] = aluno_atualizado.get("sessao_versao") or 1
    flash("Senha alterada com sucesso!", "success")
    return redirect(url_for("aluno_meu_perfil"))


SEGUNDOS_CODIGO_VALIDO = 10 * 60  # 10 minutos, igual à validade gravada no banco


# ---------- CRIAÇÃO DE CONTA: ESCOLHA DO TIPO DE PERFIL ----------

@app.route("/criar-conta")
def criar_conta_escolha():
    """Primeira tela ao clicar em 'Criar conta': escolher Aluno ou Personal.
    Aluno não se cadastra sozinho do zero — precisa do código que o
    Personal gera ao cadastrar a ficha dele — então aqui só orientamos."""
    return render_template("criar_conta_escolha.html")


# ---------- CADASTRO DE PERSONAL (com verificação de e-mail em 2 etapas) ----------

@app.route("/cadastro-personal", methods=["GET"])
def cadastro_personal():
    return render_template("cadastro_personal.html")


@app.route("/cadastro-personal/enviar-codigo", methods=["POST"])
def cadastro_personal_enviar_codigo():
    email = (request.form.get("email") or "").strip().lower()
    if not security.email_valido(email):
        return jsonify({"ok": False, "erro": "Informe um e-mail válido."}), 400
    if db.email_existe_personal(email):
        return jsonify({"ok": False, "erro": "Este e-mail já está cadastrado no sistema."}), 409
    codigo = db.criar_codigo_verificacao(email, "cadastro_personal")
    enviado = email_service.enviar_codigo_verificacao(email, codigo, finalidade="cadastro")
    if not enviado:
        return jsonify({"ok": False, "erro": "Não foi possível enviar o e-mail agora. Tente novamente em instantes."}), 502
    session["cadastro_personal_email"] = email
    return jsonify({"ok": True, "mensagem": "Código enviado! Confira seu e-mail (validade de 10 minutos)."})


@app.route("/cadastro-personal/verificar-codigo", methods=["POST"])
def cadastro_personal_verificar_codigo():
    email = (request.form.get("email") or "").strip().lower()
    codigo = (request.form.get("codigo") or "").strip()
    if not email or session.get("cadastro_personal_email") != email:
        return jsonify({"ok": False, "erro": "Sessão de cadastro expirada. Reenvie o código."}), 400
    ok, motivo = db.validar_codigo_verificacao(email, "cadastro_personal", codigo)
    if ok:
        session["cadastro_personal_email_verificado"] = email
        return jsonify({"ok": True})
    mensagens = {
        "nao_encontrado": "Nenhum código pendente para este e-mail. Solicite um novo.",
        "expirado": "Código expirado. Solicite um novo código.",
        "tentativas": "Limite de tentativas atingido. Solicite um novo código.",
        "invalido": "Código incorreto. Confira e tente novamente.",
    }
    return jsonify({"ok": False, "erro": mensagens.get(motivo, "Código inválido.")}), 400


@app.route("/cadastro-personal/finalizar", methods=["POST"])
def cadastro_personal_finalizar():
    email = session.get("cadastro_personal_email_verificado")
    if not email:
        flash("Confirme seu e-mail antes de continuar.", "warning")
        return redirect(url_for("cadastro_personal"))

    usuario = (request.form.get("usuario") or "").strip()
    senha = (request.form.get("senha") or "").strip()
    senha2 = (request.form.get("senha2") or "").strip()
    aceite_termos = request.form.get("aceite_termos") == "1"
    nome = usuario  # O nome completo digitado aqui é o que aparece no painel.

    def voltar_com_erro(msg):
        flash(msg, "warning")
        return render_template("cadastro_personal.html", etapa_dados=True, email=email,
                                usuario=usuario)

    if not usuario or not senha or not senha2:
        return voltar_com_erro("Preencha todos os campos.")
    if not aceite_termos:
        return voltar_com_erro("É necessário aceitar os termos de uso e a política de privacidade.")
    if db.usuario_existe_personal(usuario):
        return voltar_com_erro("Já existe um cadastro com esse nome. Inclua o sobrenome para diferenciar.")
    if senha != senha2:
        return voltar_com_erro("As senhas não coincidem.")
    if not security.senha_forte_o_suficiente(senha):
        return voltar_com_erro(security.motivo_senha_fraca(senha))
    if db.email_existe_personal(email):
        return voltar_com_erro("Este e-mail já está cadastrado no sistema.")

    if db.criar_personal_com_email(email, usuario, security.hash_senha(senha), nome):
        session.pop("cadastro_personal_email", None)
        session.pop("cadastro_personal_email_verificado", None)
        novo_personal = db.buscar_personal_por_email(email)
        if novo_personal:
            codigo_acesso = db.gerar_codigo_acesso("PT", novo_personal["id"])
            flash(f"Conta criada com sucesso! Seu ID de acesso é {codigo_acesso}. "
                  f"Faça login com esse ID (ou seu e-mail) e a senha que você criou.", "success")
        else:
            flash("Conta criada com sucesso! Faça login.", "success")
        return redirect(url_for("login"))
    return voltar_com_erro("Já existe um cadastro com esse nome. Inclua o sobrenome para diferenciar.")


# ---------- ATIVAÇÃO DE CONTA DO ALUNO (código enviado pelo Personal) ----------

@app.route("/aluno/criar-conta", methods=["GET"])
def aluno_criar_conta():
    return render_template("aluno_criar_conta.html")


@app.route("/aluno/criar-conta/reenviar-codigo", methods=["POST"])
def aluno_criar_conta_reenviar_codigo():
    """Autoatendimento: o próprio aluno pede um novo código quando o
    personal demora pra liberar o acesso ou o e-mail original se perdeu.
    Só reenvia se o e-mail bater com uma ficha que o personal já
    cadastrou e que ainda não teve a conta ativada."""
    email = (request.form.get("email") or "").strip().lower()
    if not security.email_valido(email):
        return jsonify({"ok": False, "erro": "Informe um e-mail válido."}), 400
    aluno = db.buscar_aluno_por_email(email)
    if not aluno:
        return jsonify({"ok": False, "erro": "Não encontramos nenhuma ficha com esse e-mail. Confirme com seu "
                                              "personal se ele já te cadastrou no sistema."}), 404
    if aluno.get("conta_ativada"):
        return jsonify({"ok": False, "erro": "Essa conta já está ativa. Você já pode fazer login normalmente."}), 409
    codigo = db.criar_codigo_verificacao(email, "cadastro_aluno", referencia_id=aluno["id"])
    enviado = email_service.enviar_codigo_verificacao(email, codigo, finalidade="cadastro_aluno")
    if not enviado:
        return jsonify({"ok": False, "erro": "Não foi possível enviar o e-mail agora. Tente novamente em instantes."}), 502
    return jsonify({"ok": True, "mensagem": "Novo código enviado! Confira seu e-mail (validade de 10 minutos)."})


@app.route("/aluno/criar-conta/verificar-codigo", methods=["POST"])
def aluno_criar_conta_verificar_codigo():
    email = (request.form.get("email") or "").strip()
    codigo = (request.form.get("codigo") or "").strip()
    if not email:
        return jsonify({"ok": False, "erro": "Informe o e-mail cadastrado pelo seu personal."}), 400
    ok, motivo, aluno_id = db.validar_codigo_verificacao_por_email_aluno(email, codigo)
    if ok:
        session["aluno_cadastro_id_verificado"] = aluno_id
        aluno = db.buscar_aluno_por_id_simples(aluno_id)
        return jsonify({"ok": True, "nome": aluno["nome"] if aluno else ""})
    mensagens = {
        "nao_encontrado": "Nenhum código pendente para este e-mail. Peça ao seu personal para reenviar.",
        "expirado": "Código expirado. Peça ao seu personal para gerar um novo.",
        "tentativas": "Limite de tentativas atingido. Peça um novo código.",
        "invalido": "Código incorreto. Confira e tente novamente.",
    }
    return jsonify({"ok": False, "erro": mensagens.get(motivo, "Código inválido.")}), 400


@app.route("/aluno/criar-conta/finalizar", methods=["POST"])
def aluno_criar_conta_finalizar():
    aluno_id = session.get("aluno_cadastro_id_verificado")
    if not aluno_id:
        flash("Confirme o código enviado antes de continuar.", "warning")
        return redirect(url_for("aluno_criar_conta"))

    aluno = db.buscar_aluno_por_id_simples(aluno_id)
    senha = (request.form.get("senha") or "").strip()
    senha2 = (request.form.get("senha2") or "").strip()

    def voltar_com_erro(msg):
        flash(msg, "warning")
        return render_template("aluno_criar_conta.html", etapa_dados=True,
                                nome=aluno["nome"] if aluno else "")

    if not aluno:
        flash("Ficha não encontrada. Fale com seu personal.", "error")
        return redirect(url_for("aluno_criar_conta"))
    if not aluno.get("email"):
        flash("Sua ficha não tem e-mail cadastrado. Fale com seu personal antes de continuar.", "error")
        return redirect(url_for("aluno_criar_conta"))
    if not senha or not senha2:
        return voltar_com_erro("Preencha a senha e a confirmação.")
    if senha != senha2:
        return voltar_com_erro("As senhas não coincidem.")
    if not security.senha_forte_o_suficiente(senha):
        return voltar_com_erro(security.motivo_senha_fraca(senha))

    # O login do aluno pode ser feito com o e-mail já cadastrado na ficha
    # OU com o ID de acesso gerado agora (ex.: AL0007) — o ID não muda
    # mesmo que o e-mail seja editado depois, evitando confusão na hora
    # de entrar (nome sozinho poderia se repetir entre alunos diferentes).
    if db.ativar_conta_aluno(aluno["id"], aluno["email"], security.hash_senha(senha)):
        session.pop("aluno_cadastro_id_verificado", None)
        codigo_acesso = db.gerar_codigo_acesso("AL", aluno["id"])
        flash(f"Conta criada com sucesso! Seu ID de acesso é {codigo_acesso}. "
              f"Faça login com esse ID (ou seu e-mail) e a senha que você acabou de criar.", "success")
        return redirect(url_for("login"))
    return voltar_com_erro("Não foi possível ativar sua conta. Fale com seu personal.")


# ---------- RECUPERAÇÃO DE SENHA (Personal ou Aluno, por código de e-mail) ----------

@app.route("/recuperar-senha", methods=["GET"])
def recuperar_senha():
    return render_template("recuperar_senha.html")


def _buscar_conta_para_recuperacao(usuario_ou_email):
    """Procura primeiro entre os Personals e depois entre os Alunos com
    conta ativada. Retorna (tipo, registro, email) ou (None, None, None)."""
    personal = db.buscar_personal_por_usuario(usuario_ou_email)
    if not personal and security.email_valido(usuario_ou_email):
        personal = db.buscar_personal_por_email(usuario_ou_email)
    if personal and personal.get("email"):
        return "personal", personal, personal["email"]

    aluno = db.buscar_aluno_por_usuario_ou_email(usuario_ou_email)
    if aluno and aluno.get("conta_ativada") and aluno.get("email"):
        return "aluno", aluno, aluno["email"]

    return None, None, None


@app.route("/recuperar-senha/enviar-codigo", methods=["POST"])
def recuperar_senha_enviar_codigo():
    usuario_ou_email = (request.form.get("usuario") or "").strip()
    tipo, registro, email = _buscar_conta_para_recuperacao(usuario_ou_email)
    if not tipo:
        # Por segurança, não revela se o usuário existe ou não.
        return jsonify({"ok": False, "erro": "Não encontramos uma conta com esse usuário ou e-mail."}), 404

    proposito = "reset_personal" if tipo == "personal" else "reset_aluno"
    codigo = db.criar_codigo_verificacao(email, proposito, referencia_id=registro["id"])
    enviado = email_service.enviar_codigo_verificacao(email, codigo, finalidade="reset")
    if not enviado:
        return jsonify({"ok": False, "erro": "Não foi possível enviar o e-mail agora. Tente novamente em instantes."}), 502
    session["recuperar_tipo"] = tipo
    session["recuperar_id"] = registro["id"]
    session["recuperar_email"] = email
    return jsonify({"ok": True, "email_mascarado": security.mascarar_email(email)})


@app.route("/recuperar-senha/verificar-codigo", methods=["POST"])
def recuperar_senha_verificar_codigo():
    codigo = (request.form.get("codigo") or "").strip()
    tipo = session.get("recuperar_tipo")
    email = session.get("recuperar_email")
    if not tipo or not email:
        return jsonify({"ok": False, "erro": "Sessão de recuperação expirada. Comece novamente."}), 400

    proposito = "reset_personal" if tipo == "personal" else "reset_aluno"
    ok, motivo = db.validar_codigo_verificacao(email, proposito, codigo)
    if ok:
        session["recuperar_verificado"] = True
        return jsonify({"ok": True})
    mensagens = {
        "nao_encontrado": "Nenhum código pendente. Solicite um novo.",
        "expirado": "Código expirado. Solicite um novo código.",
        "tentativas": "Limite de tentativas atingido. Solicite um novo código.",
        "invalido": "Código incorreto. Confira e tente novamente.",
    }
    return jsonify({"ok": False, "erro": mensagens.get(motivo, "Código inválido.")}), 400


@app.route("/recuperar-senha/finalizar", methods=["POST"])
def recuperar_senha_finalizar():
    tipo = session.get("recuperar_tipo")
    registro_id = session.get("recuperar_id")
    if not tipo or not registro_id or not session.get("recuperar_verificado"):
        flash("Confirme o código enviado por e-mail antes de continuar.", "warning")
        return redirect(url_for("recuperar_senha"))

    senha1 = (request.form.get("senha1") or "").strip()
    senha2 = (request.form.get("senha2") or "").strip()

    def voltar_com_erro(msg):
        flash(msg, "warning")
        return render_template("recuperar_senha.html", etapa_nova_senha=True)

    if not senha1 or not senha2:
        return voltar_com_erro("Preencha os dois campos de senha.")
    if senha1 != senha2:
        return voltar_com_erro("As senhas não coincidem.")
    if not security.senha_forte_o_suficiente(senha1):
        return voltar_com_erro(security.motivo_senha_fraca(senha1))

    novo_hash = security.hash_senha(senha1)
    if tipo == "personal":
        personal = db.buscar_personal_por_id(registro_id)
        db.atualizar_senha_hash(personal["usuario"], novo_hash)
    else:
        db.atualizar_senha_hash_aluno(registro_id, novo_hash)

    for chave in ("recuperar_tipo", "recuperar_id", "recuperar_email", "recuperar_verificado"):
        session.pop(chave, None)
    flash("Senha atualizada com sucesso! Todas as outras sessões foram desconectadas. Faça login.", "success")
    return redirect(url_for("login"))


# ---------- CONFIGURAÇÕES DO PERSONAL (slogan, contato, logo no PDF) ----------

@app.route("/configuracoes", methods=["GET", "POST"])
@login_required
def configuracoes():
    personal = db.buscar_personal_por_id(session["personal_id"])
    if request.method == "POST":
        nome_exibicao = request.form.get("nome_exibicao", "").strip() or personal.get("usuario")
        slogan = request.form.get("slogan", "").strip()
        telefone = request.form.get("telefone", "").strip()
        instagram = request.form.get("instagram", "").strip()
        cref = request.form.get("cref", "").strip()
        mostrar_resultado_auto = request.form.get("mostrar_resultado_auto") == "1"

        logo_path = personal.get("logo_path")
        arquivo_logo = request.files.get("logo")
        if arquivo_logo and arquivo_logo.filename:
            pasta_personal = os.path.join(UPLOAD_DIR, "_personal", str(personal["id"]))
            os.makedirs(pasta_personal, exist_ok=True)
            extensao = os.path.splitext(arquivo_logo.filename)[1].lower() or ".png"
            logo_path = os.path.join(pasta_personal, f"logo{extensao}")
            arquivo_logo.save(logo_path)

        db.atualizar_perfil_personal(personal["id"], nome_exibicao, slogan, telefone, instagram,
                                      logo_path, cref, mostrar_resultado_auto)
        session["personal_nome"] = nome_exibicao
        flash("Dados atualizados! Os próximos PDFs já saem com essas informações.", "success")
        return redirect(url_for("configuracoes"))
    return render_template("configuracoes.html", personal=personal)


@app.route("/configuracoes/senha", methods=["POST"])
@login_required
def configuracoes_senha():
    """Trocar a senha de dentro do sistema (sem precisar deslogar e usar
    o fluxo de 'esqueci minha senha'). Continua exigindo a senha atual
    por segurança. Como trocar a senha invalida outras sessões abertas
    (ver atualizar_senha_hash), a sessão ATUAL é atualizada na hora pra
    quem trocou não ser deslogado por engano."""
    personal = db.buscar_personal_por_id(session["personal_id"])
    senha_atual = (request.form.get("senha_atual") or "").strip()
    senha_nova = (request.form.get("senha_nova") or "").strip()
    senha_nova2 = (request.form.get("senha_nova2") or "").strip()

    if not senha_atual or not senha_nova or not senha_nova2:
        flash("Preencha a senha atual e a nova senha (com confirmação).", "warning")
        return redirect(url_for("configuracoes"))
    if not security.conferir_senha(personal["senha_hash"], senha_atual):
        flash("Senha atual incorreta.", "error")
        return redirect(url_for("configuracoes"))
    if senha_nova != senha_nova2:
        flash("A nova senha e a confirmação não coincidem.", "warning")
        return redirect(url_for("configuracoes"))
    if not security.senha_forte_o_suficiente(senha_nova):
        flash(security.motivo_senha_fraca(senha_nova), "warning")
        return redirect(url_for("configuracoes"))

    db.atualizar_senha_hash(personal["usuario"], security.hash_senha(senha_nova))
    personal_atualizado = db.buscar_personal_por_id(personal["id"])
    session["sessao_versao"] = personal_atualizado.get("sessao_versao") or 1
    flash("Senha alterada com sucesso!", "success")
    return redirect(url_for("configuracoes"))


EXTENSOES_FOTO_PERMITIDAS = (".png", ".jpg", ".jpeg", ".webp", ".gif")


@app.route("/configuracoes/foto", methods=["POST"])
@login_required
def configuracoes_foto():
    """Recebe a foto de perfil (avatar) por AJAX e salva na hora, sem
    precisar apertar SALVAR nem recarregar a página — é só escolher a
    imagem que ela já fica valendo."""
    personal_id = session["personal_id"]
    arquivo = request.files.get("foto")
    if not arquivo or not arquivo.filename:
        return jsonify({"ok": False, "erro": "Nenhuma imagem foi enviada."}), 400

    extensao = os.path.splitext(arquivo.filename)[1].lower()
    if extensao not in EXTENSOES_FOTO_PERMITIDAS:
        return jsonify({"ok": False, "erro": "Formato de imagem não suportado. Use PNG, JPG, WEBP ou GIF."}), 400

    pasta_personal = os.path.join(UPLOAD_DIR, "_personal", str(personal_id))
    os.makedirs(pasta_personal, exist_ok=True)

    # Remove qualquer avatar antigo (mesmo com outra extensão) pra não
    # acumular arquivo órfão toda vez que a pessoa trocar a foto.
    for nome_antigo in os.listdir(pasta_personal):
        if nome_antigo.startswith("avatar."):
            try:
                os.remove(os.path.join(pasta_personal, nome_antigo))
            except OSError:
                pass

    nome_arquivo = f"avatar{extensao}"
    arquivo.save(os.path.join(pasta_personal, nome_arquivo))
    db.atualizar_foto_perfil_personal(personal_id, nome_arquivo)

    url = url_for("servir_foto_personal", personal_id=personal_id, nome_arquivo=nome_arquivo)
    url += f"?v={int(time.time())}"  # evita ficar mostrando a foto antiga em cache
    return jsonify({"ok": True, "url": url})


# ---------- DASHBOARD ----------

DIAS_SEMANA_LABEL = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


def _proxima_ocorrencia_semanal(dia_semana, hora_str, agora=None):
    """Calcula a próxima data/hora em que um horário fixo semanal (ex: toda
    quarta às 08:00) volta a acontecer a partir de agora."""
    agora = agora or datetime.now()
    h, m = [int(x) for x in hora_str.split(":")]
    dias_ate = (dia_semana - agora.weekday()) % 7
    candidato = (agora + timedelta(days=dias_ate)).replace(hour=h, minute=m, second=0, microsecond=0)
    if candidato < agora:
        candidato += timedelta(days=7)
    return candidato


def _proximos_atendimentos(personal_id, janela_horas=18):
    """Junta os agendamentos avulsos com a próxima ocorrência de cada horário
    fixo semanal, devolvendo tudo já ordenado — usado pro banner do painel
    e pro alarme (som/notificação) da agenda.

    Não filtra por janela de tempo aqui: manda todos os atendimentos futuros
    e quem decide se toca o alarme agora ou mais tarde é o JavaScript (que já
    só agenda o alarme para o que está a menos de 18h — ver agenda.html).
    Filtrar dos dois lados fazia a lista chegar vazia sempre que o próximo
    atendimento estava marcado pra depois desse prazo."""
    agora = datetime.now()

    itens = []
    for ag in db.listar_agendamentos(personal_id, a_partir_de=agora.isoformat()):
        itens.append({"titulo": ag["titulo"], "aluno_nome": ag.get("aluno_nome"), "data_hora": ag["data_hora"]})

    for hf in db.listar_horarios_fixos(personal_id):
        ocorrencia = _proxima_ocorrencia_semanal(hf["dia_semana"], hf["hora"], agora)
        itens.append({
            "titulo": f"Treino — {hf['aluno_nome']}",
            "aluno_nome": hf["aluno_nome"],
            "data_hora": ocorrencia.isoformat(),
        })

    itens.sort(key=lambda i: i["data_hora"])
    proximo = itens[0] if itens else None
    return proximo, itens


@app.route("/dashboard")
@login_required
def dashboard():
    personal_id = session["personal_id"]
    termo = request.args.get("q", "").strip()
    if termo:
        # Uma busca feita direto no painel continua funcionando normalmente.
        alunos = db.listar_alunos(personal_id, termo)
        total = db.contar_alunos(personal_id)
        return render_template("dashboard.html", alunos=alunos, total=total, termo=termo,
                                proximo_agendamento=None, proximos_json="[]",
                                personal=db.buscar_personal_por_id(personal_id), frase_dia=frase_do_dia())

    total = db.contar_alunos(personal_id)
    proximo_agendamento, proximos_para_alarme = _proximos_atendimentos(personal_id)

    stats_mes = db.estatisticas_cadastro_mes(personal_id)
    resumo_dia = {
        "atendimentos_hoje": db.contar_atendimentos_hoje(personal_id),
        "treinos_concluidos": db.contar_checkins_hoje(personal_id),
        "novos_alunos": db.contar_novos_alunos_hoje(personal_id),
        "faturamento_hoje": db.somar_receitas_hoje(personal_id),
    }
    pagamentos_pendentes = db.contar_pagamentos_pendentes(personal_id)
    notificacoes_nao_lidas = db.contar_notificacoes_nao_lidas(personal_id)
    mensagens_nao_lidas = db.contar_mensagens_nao_lidas_personal(personal_id)

    return render_template("dashboard.html", alunos=[], total=total, termo="",
                            proximo_agendamento=proximo_agendamento,
                            proximos_json=json.dumps(proximos_para_alarme, ensure_ascii=False),
                            stats_mes=stats_mes, resumo_dia=resumo_dia,
                            pagamentos_pendentes=pagamentos_pendentes,
                            notificacoes_nao_lidas=notificacoes_nao_lidas,
                            mensagens_nao_lidas=mensagens_nao_lidas,
                            personal=db.buscar_personal_por_id(personal_id), frase_dia=frase_do_dia())


@app.route("/notificacoes")
@login_required
def notificacoes():
    personal_id = session["personal_id"]
    lista = db.listar_notificacoes(personal_id)
    db.marcar_notificacoes_lidas(personal_id)
    return render_template("notificacoes.html", notificacoes=lista)


@app.route("/notificacoes/<int:notificacao_id>/excluir", methods=["POST"])
@login_required
def notificacao_excluir(notificacao_id):
    db.excluir_notificacao_personal(notificacao_id, session["personal_id"])
    return redirect(url_for("notificacoes"))


@app.route("/alunos")
@login_required
def alunos_lista():
    """Tela dedicada de 'Listar / Gerenciar alunos' — busca, filtra por
    status, abre o perfil, exclui."""
    termo = request.args.get("q", "").strip()
    status_filtro = request.args.get("status", "Todos").strip() or "Todos"
    alunos = db.listar_alunos(session["personal_id"], termo or None, status_filtro)
    total = db.contar_alunos(session["personal_id"])
    return render_template("alunos_lista.html", alunos=alunos, total=total, termo=termo,
                            status_filtro=status_filtro)


@app.route("/treino/selecionar-aluno")
@login_required
def treino_selecionar_aluno():
    """Tela de 'Montar ficha de treino' — mostra a lista de alunos primeiro;
    escolhendo um, vai direto pro formulário de montar a ficha dele."""
    termo = request.args.get("q", "").strip()
    alunos = db.listar_alunos(session["personal_id"], termo or None)
    resumo_treinos = db.contagem_treinos_por_aluno(session["personal_id"])
    return render_template("treino_selecionar_aluno.html", alunos=alunos, termo=termo,
                            resumo_treinos=resumo_treinos)


# ---------- ALUNO: CADASTRO (P1) ----------

@app.route("/aluno/novo", methods=["GET", "POST"])
@login_required
def aluno_novo():
    if request.method == "POST":
        dados = {k: request.form.get(k, "").strip() for k in
                 ["nome", "telefone", "email", "cidade", "regiao", "sexo", "idade", "academia",
                  "objetivo", "como_conheceu", "indicacao", "observacoes"]}
        if not dados["nome"]:
            flash("O nome do aluno é obrigatório.", "warning")
            return render_template("aluno_form.html", aluno=dados)
        aluno_id = db.criar_aluno(session["personal_id"], dados)
        # Ao finalizar o cadastro da ficha, se um e-mail foi informado, o
        # sistema já dispara o código de verificação para o aluno criar o
        # próprio usuário/senha de acesso (conforme especificação de login).
        email_aluno = dados.get("email")
        if email_aluno and security.email_valido(email_aluno):
            codigo = db.criar_codigo_verificacao(email_aluno, "cadastro_aluno", referencia_id=aluno_id)
            enviado = email_service.enviar_codigo_verificacao(email_aluno, codigo, finalidade="cadastro_aluno")
            if enviado:
                flash("Ficha criada! Um código de acesso foi enviado para o e-mail do aluno.", "success")
            else:
                flash("Ficha criada, mas não foi possível enviar o e-mail de acesso agora. "
                      "Você pode reenviar depois pelo perfil do aluno.", "warning")
        return redirect(url_for("anamnese_nova", aluno_id=aluno_id))
    return render_template("aluno_form.html", aluno=None)


@app.route("/aluno/<int:aluno_id>/editar", methods=["GET", "POST"])
@login_required
def aluno_editar(aluno_id):
    aluno = db.buscar_aluno(aluno_id, session["personal_id"])
    if not aluno:
        abort(404)
    if request.method == "POST":
        dados = {k: request.form.get(k, "").strip() for k in
                 ["nome", "telefone", "email", "cidade", "regiao", "sexo", "idade", "academia",
                  "objetivo", "como_conheceu", "indicacao", "observacoes"]}
        if not dados["nome"]:
            flash("O nome do aluno é obrigatório.", "warning")
            return render_template("aluno_form.html", aluno=dados, editando=True, aluno_id=aluno_id)
        db.atualizar_aluno(aluno_id, session["personal_id"], dados)
        flash("Dados do aluno atualizados!", "success")
        return redirect(url_for("aluno_perfil", aluno_id=aluno_id))
    return render_template("aluno_form.html", aluno=aluno, editando=True, aluno_id=aluno_id)


@app.route("/aluno/<int:aluno_id>/reenviar-codigo", methods=["POST"])
@login_required
def aluno_reenviar_codigo(aluno_id):
    """Corrige a promessa feita ao personal na hora de cadastrar a ficha
    ('você pode reenviar depois pelo perfil do aluno') — esse botão não
    existia. Reenvia o código de ativação pro e-mail já cadastrado na
    ficha, útil quando o e-mail original falhou ou o aluno demorou pra
    usar o código dentro dos 10 minutos de validade."""
    aluno = db.buscar_aluno(aluno_id, session["personal_id"])
    if not aluno:
        abort(404)
    if not aluno.get("email") or not security.email_valido(aluno["email"]):
        flash("Esse aluno não tem um e-mail válido cadastrado na ficha. Edite os dados dele antes de reenviar.", "warning")
        return redirect(url_for("aluno_perfil", aluno_id=aluno_id))
    if aluno.get("conta_ativada"):
        flash("Esse aluno já ativou a própria conta — não é preciso reenviar.", "warning")
        return redirect(url_for("aluno_perfil", aluno_id=aluno_id))
    codigo = db.criar_codigo_verificacao(aluno["email"], "cadastro_aluno", referencia_id=aluno_id)
    enviado = email_service.enviar_codigo_verificacao(aluno["email"], codigo, finalidade="cadastro_aluno")
    if enviado:
        flash(f"Código de acesso reenviado para {aluno['email']}.", "success")
    else:
        flash("Não foi possível enviar o e-mail agora. Tente novamente em instantes.", "error")
    return redirect(url_for("aluno_perfil", aluno_id=aluno_id))


@app.route("/aluno/<int:aluno_id>/status", methods=["POST"])
@login_required
def aluno_status(aluno_id):
    aluno = db.buscar_aluno(aluno_id, session["personal_id"])
    if not aluno:
        abort(404)
    novo_status = "Inativo" if (aluno.get("status") or "Ativo") == "Ativo" else "Ativo"
    db.atualizar_status_aluno(aluno_id, session["personal_id"], novo_status)
    flash(f"{aluno['nome']} agora está {novo_status.lower()}.", "success")
    return redirect(url_for("aluno_perfil", aluno_id=aluno_id))


@app.route("/aluno/<int:aluno_id>")
@login_required
def aluno_perfil(aluno_id):
    aluno = db.buscar_aluno(aluno_id, session["personal_id"])
    if not aluno:
        abort(404)
    avaliacoes = db.listar_avaliacoes(aluno_id)
    treinos = db.listar_treinos(aluno_id)
    for t in treinos:
        try:
            dias_treino = json.loads(t.get("exercicios_json") or "[]")
            t["letra_principal"] = dias_treino[0].get("letra") if dias_treino and isinstance(dias_treino[0], dict) else None
        except (TypeError, ValueError, IndexError, AttributeError):
            t["letra_principal"] = None
    ultima_avaliacao = avaliacoes[-1] if avaliacoes else None
    fotos = db.listar_fotos(ultima_avaliacao["id"]) if ultima_avaliacao else []
    if not fotos:
        fotos = db.buscar_fotos_recentes_aluno(aluno_id)
    comparativo = comparar_avaliacoes(avaliacoes[-2], avaliacoes[-1]) if len(avaliacoes) >= 2 else None
    anamnese_pendente = db.buscar_anamnese_pendente_aluno(aluno_id)
    anamnese_respondida = db.buscar_ultima_anamnese(aluno_id) if not anamnese_pendente else None
    return render_template("aluno_perfil.html", aluno=aluno, avaliacoes=avaliacoes,
                            treinos=treinos, ultima_avaliacao=ultima_avaliacao, fotos=fotos,
                            comparativo=comparativo, anamnese_pendente=anamnese_pendente,
                            anamnese_respondida=anamnese_respondida)


@app.route("/aluno/<int:aluno_id>/foto", methods=["POST"])
@login_required
def aluno_foto(aluno_id):
    aluno = db.buscar_aluno(aluno_id, session["personal_id"])
    if not aluno:
        abort(404)
    arquivo = request.files.get("foto_perfil")
    if arquivo and arquivo.filename:
        extensao = os.path.splitext(arquivo.filename)[1].lower() or ".jpg"
        if extensao not in EXTENSOES_FOTO_PERMITIDAS:
            flash("Formato de imagem não suportado. Use PNG, JPG, WEBP ou GIF.", "warning")
            return redirect(url_for("aluno_perfil", aluno_id=aluno_id))
        pasta_aluno = os.path.join(UPLOAD_DIR, str(aluno_id))
        os.makedirs(pasta_aluno, exist_ok=True)
        nome_arquivo = f"perfil_{uuid.uuid4().hex[:8]}{extensao}"
        caminho = os.path.join(pasta_aluno, nome_arquivo)
        arquivo.save(caminho)
        db.atualizar_foto_perfil(aluno_id, session["personal_id"], caminho)
        flash("Foto de perfil atualizada!", "success")
    else:
        flash("Selecione uma imagem para enviar.", "warning")
    return redirect(url_for("aluno_perfil", aluno_id=aluno_id))


@app.route("/aluno/<int:aluno_id>/excluir", methods=["POST"])
@login_required
def aluno_excluir(aluno_id):
    aluno = db.buscar_aluno(aluno_id, session["personal_id"])
    if not aluno:
        abort(404)
    pasta_aluno = os.path.join(UPLOAD_DIR, str(aluno_id))
    db.excluir_aluno(aluno_id, session["personal_id"])
    shutil.rmtree(pasta_aluno, ignore_errors=True)
    flash(f"{aluno['nome']} foi removido(a) da base de dados.", "success")
    return redirect(url_for("dashboard"))


@app.route("/aluno/<int:aluno_id>/avaliacao/<int:avaliacao_id>/excluir", methods=["POST"])
@login_required
def avaliacao_excluir(aluno_id, avaliacao_id):
    aluno = db.buscar_aluno(aluno_id, session["personal_id"])
    if not aluno:
        abort(404)
    ok = db.excluir_avaliacao(avaliacao_id, aluno_id)
    flash("Avaliação excluída." if ok else "Não foi possível excluir essa avaliação.",
          "success" if ok else "warning")
    return redirect(url_for("compartilhar", aluno_id=aluno_id))


@app.route("/aluno/<int:aluno_id>/treino/<int:treino_id>/excluir", methods=["POST"])
@login_required
def treino_excluir(aluno_id, treino_id):
    aluno = db.buscar_aluno(aluno_id, session["personal_id"])
    if not aluno:
        abort(404)
    ok = db.excluir_treino(treino_id, aluno_id)
    flash("Ficha de treino excluída." if ok else "Não foi possível excluir essa ficha.",
          "success" if ok else "warning")
    # Permite que a tela de origem (ex: lista global "Treinos Registrados")
    # informe para onde voltar depois de excluir, em vez de sempre cair na
    # tela de compartilhamento do aluno.
    destino = request.form.get("next")
    if destino == "treinos_registrados":
        return redirect(url_for("treinos_registrados"))
    return redirect(url_for("compartilhar", aluno_id=aluno_id))


@app.route("/aluno/<int:aluno_id>/dados.json")
@login_required
def aluno_dados_json(aluno_id):
    aluno = db.buscar_aluno(aluno_id, session["personal_id"])
    if not aluno:
        abort(404)
    avaliacoes = db.listar_avaliacoes(aluno_id)
    return jsonify({
        "labels": [a["data"][:10] for a in avaliacoes],
        "peso": [a["peso"] for a in avaliacoes],
        "bf": [a["bf"] for a in avaliacoes],
        "imc": [a["imc"] for a in avaliacoes],
    })


# ---------- ANAMNESE (pergunta a pergunta, igual ao programa original) ----------

@app.route("/aluno/<int:aluno_id>/anamnese/nova", methods=["GET", "POST"])
@login_required
def anamnese_nova(aluno_id):
    aluno = db.buscar_aluno(aluno_id, session["personal_id"])
    if not aluno:
        abort(404)
    if request.method == "POST":
        modo = request.form.get("modo", "preencher")
        if modo == "enviar_aluno":
            # Preenchimento remoto: pula a etapa agora e libera o
            # questionário no acesso do próprio aluno responder depois.
            db.criar_anamnese_pendente(aluno_id)
            personal = db.buscar_personal_por_id(session["personal_id"])
            nome_personal = (personal.get("nome_exibicao") or personal.get("usuario")) if personal else None
            mensagem = (f"{nome_personal} enviou uma anamnese para você responder."
                        if nome_personal else "Seu personal enviou uma anamnese para você responder.")
            db.criar_notificacao_aluno(session["personal_id"], aluno_id, "anamnese_enviada", mensagem)
            flash("Anamnese enviada para o aluno responder pelo próprio acesso. "
                  "Você será avisado assim que ele concluir.", "success")
            return redirect(url_for("medidas_novas", aluno_id=aluno_id))

        respostas_raw = request.form.get("respostas_json", "[]")
        try:
            respostas = json.loads(respostas_raw)
        except (TypeError, ValueError):
            respostas = []
        observacoes_extra = request.form.get("observacoes_extra", "").strip()
        db.salvar_anamnese(aluno_id, respostas, observacoes_extra, status="respondida", origem="personal")
        return redirect(url_for("medidas_novas", aluno_id=aluno_id))
    return render_template("anamnese.html", aluno=aluno, perguntas=PERGUNTAS_ANAMNESE)


# ---------- ANAMNESE RESPONDIDA PELO ALUNO (acesso remoto do aluno) ----------

@app.route("/aluno/anamnese", methods=["GET", "POST"])
def aluno_anamnese_responder():
    """Tela em que o próprio aluno (logado com o perfil limitado dele)
    responde a anamnese que o personal enviou para preenchimento remoto."""
    if not session.get("aluno_id"):
        return redirect(url_for("login"))
    aluno = db.buscar_aluno_por_id_simples(session["aluno_id"])
    if not aluno or session.get("sessao_versao_aluno") != (aluno.get("sessao_versao") or 1):
        session.clear()
        flash("Sua sessão expirou. Faça login novamente.", "warning")
        return redirect(url_for("login"))

    anamnese = db.buscar_anamnese_pendente_aluno(aluno["id"])
    if not anamnese:
        flash("Não há nenhuma anamnese pendente para você responder no momento.", "warning")
        return redirect(url_for("aluno_area"))

    if request.method == "POST":
        acao = request.form.get("acao", "rascunho")
        respostas_raw = request.form.get("respostas_json", "[]")
        try:
            respostas = json.loads(respostas_raw)
        except (TypeError, ValueError):
            respostas = []

        if acao == "enviar":
            db.responder_anamnese_aluno(anamnese["id"], respostas)
            personal = db.buscar_personal_por_id(aluno["personal_id"])
            if personal:
                mensagem = f"{aluno['nome']} respondeu a anamnese enviada para ele(a)."
                db.criar_notificacao(personal["id"], aluno["id"], "anamnese_respondida", mensagem)
                if personal.get("email"):
                    email_service.enviar_notificacao_anamnese_respondida(personal["email"], aluno["nome"])
            flash("Respostas enviadas! Seu personal foi avisado.", "success")
            return redirect(url_for("aluno_area"))

        # Salvar rascunho: o aluno pode continuar depois de onde parou.
        db.salvar_rascunho_anamnese(anamnese["id"], respostas)
        flash("Rascunho salvo. Você pode continuar de onde parou quando quiser.", "success")
        return redirect(url_for("aluno_anamnese_responder"))

    respostas_salvas = []
    if anamnese.get("respostas_json"):
        try:
            respostas_salvas = json.loads(anamnese["respostas_json"])
        except (TypeError, ValueError):
            respostas_salvas = []
    return render_template("anamnese_responder.html", aluno=aluno, perguntas=PERGUNTAS_ANAMNESE,
                            respostas_salvas=respostas_salvas)


# ---------- MODAL DE ANAMNESE DO ALUNO (edição inline com salvamento automático) ----------

def _aluno_sessao_ou_json_401():
    aluno = _aluno_sessao_valida()
    if not aluno:
        return None, (jsonify({"erro": "sessao_expirada"}), 401)
    return aluno, None


@app.route("/aluno/anamnese/dados")
def aluno_anamnese_modal_dados():
    """Devolve as perguntas + respostas atuais em JSON, pra preencher o
    modal de anamnese sem precisar navegar pra outra página."""
    aluno, erro = _aluno_sessao_ou_json_401()
    if erro:
        return erro
    anamnese = db.obter_anamnese_editavel_aluno(aluno["id"])
    respostas_salvas = []
    if anamnese and anamnese.get("respostas_json"):
        try:
            respostas_salvas = json.loads(anamnese["respostas_json"])
        except (TypeError, ValueError):
            respostas_salvas = []
    respostas_por_pergunta = {r.get("pergunta"): r for r in respostas_salvas if isinstance(r, dict)}
    perguntas = [{
        "pergunta": p,
        "resposta": (respostas_por_pergunta.get(p) or {}).get("resposta") or "",
        "observacao": (respostas_por_pergunta.get(p) or {}).get("observacao") or "",
    } for p in PERGUNTAS_ANAMNESE]
    return jsonify({
        "perguntas": perguntas,
        "status": anamnese.get("status") if anamnese else None,
    })


@app.route("/aluno/anamnese/autosave", methods=["POST"])
def aluno_anamnese_modal_autosave():
    """Salva as respostas automaticamente a cada alteração no modal —
    o aluno não precisa clicar em nenhum botão de 'salvar'."""
    aluno, erro = _aluno_sessao_ou_json_401()
    if erro:
        return erro
    dados = request.get_json(silent=True) or {}
    respostas = dados.get("respostas") or []
    db.autosalvar_anamnese_aluno(aluno["id"], respostas)
    return jsonify({"ok": True})


@app.route("/aluno/anamnese/concluir", methods=["POST"])
def aluno_anamnese_modal_concluir():
    """Marca a anamnese como respondida/concluída e avisa o personal —
    acionado pelo botão 'Concluir' dentro do modal."""
    aluno, erro = _aluno_sessao_ou_json_401()
    if erro:
        return erro
    dados = request.get_json(silent=True) or {}
    respostas = dados.get("respostas") or []
    anamnese_id = db.autosalvar_anamnese_aluno(aluno["id"], respostas)
    db.responder_anamnese_aluno(anamnese_id, respostas)
    personal = db.buscar_personal_por_id(aluno["personal_id"])
    if personal:
        mensagem = f"{aluno['nome']} respondeu a anamnese enviada para ele(a)."
        db.criar_notificacao(personal["id"], aluno["id"], "anamnese_respondida", mensagem)
        if personal.get("email"):
            email_service.enviar_notificacao_anamnese_respondida(personal["email"], aluno["nome"])
    return jsonify({"ok": True})


# ---------- MEDIDAS ----------

def _finalizar_avaliacao_e_notificar(personal_id, aluno_id, avaliacao_id):
    """Libera a avaliação pro aluno automaticamente assim que o personal
    salva as medidas. Não aparece no chat — só um aviso no sino de
    notificações, e o resultado completo fica disponível no menu
    'Minha Avaliação' do aluno."""
    db.finalizar_avaliacao(avaliacao_id, aluno_id)
    db.criar_notificacao_aluno(personal_id, aluno_id, "avaliacao",
                                "Sua avaliação física foi finalizada. Veja seu novo relatório!")


@app.route("/aluno/<int:aluno_id>/medidas/nova", methods=["GET", "POST"])
@login_required
def medidas_novas(aluno_id):
    aluno = db.buscar_aluno(aluno_id, session["personal_id"])
    if not aluno:
        abort(404)
    if request.method == "POST":
        dados = {c: (request.form.get(c) or None) for c in db.CAMPOS_NUMERICOS}
        dados["observacoes"] = request.form.get("observacoes", "")

        # IMC, % de gordura, massa magra e massa gorda são sempre calculados
        # automaticamente a partir do peso, idade/sexo do aluno e das dobras —
        # o profissional não precisa (nem consegue) digitar esses valores.
        dados["imc"] = calcular_imc(dados.get("peso"), dados.get("altura"))
        bf, massa_gorda, massa_magra = calcular_composicao_corporal(
            dados.get("peso"), aluno.get("idade"), aluno.get("sexo"), dados
        )
        dados["bf"] = bf
        dados["massa_gorda"] = massa_gorda
        dados["massa_magra"] = massa_magra

        aval_id = db.criar_avaliacao(aluno_id, dados)

        # A avaliação já é liberada automaticamente pro aluno assim que as
        # medidas são salvas — sem etapa manual de "finalizar e liberar".
        _finalizar_avaliacao_e_notificar(session["personal_id"], aluno_id, aval_id)

        # Se o personal ativou "mostrar resultado automaticamente no
        # relatório" (Configurações), pula a tela intermediária e entrega
        # o relatório em PDF pronto, direto após salvar as medidas.
        personal = db.buscar_personal_por_id(session["personal_id"])
        if personal and personal.get("mostrar_resultado_auto"):
            return redirect(url_for("avaliacao_pdf", aluno_id=aluno_id, avaliacao_id=aval_id))
        return redirect(url_for("avaliacao_resultado", aluno_id=aluno_id, avaliacao_id=aval_id))
    return render_template("medidas_form.html", aluno=aluno)


@app.route("/aluno/<int:aluno_id>/avaliacao/<int:avaliacao_id>/resultado")
@login_required
def avaliacao_resultado(aluno_id, avaliacao_id):
    aluno = db.buscar_aluno(aluno_id, session["personal_id"])
    if not aluno:
        abort(404)
    avaliacao = db.buscar_avaliacao(avaliacao_id)
    if not avaliacao or avaliacao["aluno_id"] != aluno_id:
        abort(404)
    cat_imc = classificar_imc(avaliacao.get("imc"))
    cat_bf = classificar_bf(avaliacao.get("bf"), aluno.get("sexo"))
    gauge_imc = gauge_info(avaliacao.get("imc"), 15, 40, cat_imc)
    gauge_bf = gauge_info(avaliacao.get("bf"), 3, 45, cat_bf)

    # Indicadores profissionais extras — usam só peso/altura/cintura/idade/sexo
    # já coletados, sem precisar de nenhum campo novo no formulário.
    rcq_val = calculos.calcular_rcq(avaliacao.get("cintura"), avaliacao.get("quadril"))
    rcest_val = calculos.calcular_rcest(avaliacao.get("cintura"), avaliacao.get("altura"))
    ic_val = calculos.calcular_indice_conicidade(avaliacao.get("peso"), avaliacao.get("altura"), avaliacao.get("cintura"))
    tmb_val = calculos.calcular_tmb(avaliacao.get("peso"), avaliacao.get("altura"), aluno.get("idade"), aluno.get("sexo"))
    peso_ideal_detalhe = calculos.calcular_peso_ideal_detalhado(avaliacao.get("altura"), aluno.get("sexo"))
    peso_ideal_val = peso_ideal_detalhe["media"] if peso_ideal_detalhe else None
    indicadores_extra = {
        "rcq": rcq_val, "cat_rcq": calculos.classificar_rcq(rcq_val, aluno.get("sexo")),
        "rcest": rcest_val, "cat_rcest": calculos.classificar_rcest(rcest_val),
        "ic": ic_val, "cat_ic": calculos.classificar_indice_conicidade(ic_val, aluno.get("sexo")),
        "tmb": tmb_val, "peso_ideal": peso_ideal_val, "peso_ideal_detalhe": peso_ideal_detalhe,
    }
    return render_template("resultado_final.html", aluno=aluno, avaliacao=avaliacao,
                            cat_imc=cat_imc, cat_bf=cat_bf, gauge_imc=gauge_imc, gauge_bf=gauge_bf,
                            indicadores_extra=indicadores_extra)


# ---------- AVALIAÇÃO POSTURAL (opcional) ----------

@app.route("/aluno/<int:aluno_id>/avaliacao/<int:avaliacao_id>/postural")
@login_required
def postural_tela(aluno_id, avaliacao_id):
    aluno = db.buscar_aluno(aluno_id, session["personal_id"])
    if not aluno:
        abort(404)
    avaliacao = db.buscar_avaliacao(avaliacao_id)
    if not avaliacao or avaliacao["aluno_id"] != aluno_id:
        abort(404)
    return render_template("postural.html", aluno=aluno, avaliacao=avaliacao,
                            modelo_ia_disponivel=postural.modelo_disponivel())


@app.route("/aluno/<int:aluno_id>/avaliacao/<int:avaliacao_id>/postural/foto", methods=["POST"])
@login_required
def postural_salvar_foto(aluno_id, avaliacao_id):
    aluno = db.buscar_aluno(aluno_id, session["personal_id"])
    if not aluno:
        abort(404)
    avaliacao = db.buscar_avaliacao(avaliacao_id)
    if not avaliacao or avaliacao["aluno_id"] != aluno_id:
        abort(404)

    tipo = request.form.get("tipo")
    imagem_original = request.form.get("imagem_original")   # foto pura da câmera
    imagem_com_linha = request.form.get("imagem_com_linha")  # mesma foto + linha manual desenhada (opcional)

    if not tipo or not imagem_original or not imagem_original.startswith("data:image"):
        return jsonify({"erro": "dados incompletos"}), 400

    pasta_aluno = os.path.join(UPLOAD_DIR, str(aluno_id))
    os.makedirs(pasta_aluno, exist_ok=True)

    _, b64_original = imagem_original.split(",", 1)
    nome_original = f"aval{avaliacao_id}_{tipo}_{uuid.uuid4().hex[:8]}.jpg"
    caminho_original = os.path.join(pasta_aluno, nome_original)
    with open(caminho_original, "wb") as f:
        f.write(base64.b64decode(b64_original))

    caminho_anotado = None
    if imagem_com_linha and imagem_com_linha.startswith("data:image"):
        _, b64_linha = imagem_com_linha.split(",", 1)
        nome_anotado = f"aval{avaliacao_id}_{tipo}_manual_{uuid.uuid4().hex[:8]}.jpg"
        caminho_anotado = os.path.join(pasta_aluno, nome_anotado)
        with open(caminho_anotado, "wb") as f:
            f.write(base64.b64decode(b64_linha))

    db.marcar_avaliacao_postural(avaliacao_id)
    caminhos_antigos = db.salvar_foto_postura(avaliacao_id, tipo, caminho_original, caminho_anotado)
    for caminho_velho in caminhos_antigos:
        try:
            if caminho_velho and os.path.exists(caminho_velho):
                os.remove(caminho_velho)
        except OSError:
            pass  # se não conseguir apagar o arquivo velho, não trava o salvamento da foto nova

    foto_salva = db.listar_fotos(avaliacao_id)[-1]
    return jsonify({"ok": True, "foto_id": foto_salva["id"]})


@app.route("/aluno/<int:aluno_id>/avaliacao/<int:avaliacao_id>/postural/foto/<int:foto_id>/excluir", methods=["POST"])
@login_required
def postural_excluir_foto(aluno_id, avaliacao_id, foto_id):
    aluno = db.buscar_aluno(aluno_id, session["personal_id"])
    if not aluno:
        abort(404)
    avaliacao = db.buscar_avaliacao(avaliacao_id)
    if not avaliacao or avaliacao["aluno_id"] != aluno_id:
        abort(404)
    caminhos = db.excluir_foto_postura(foto_id, avaliacao_id)
    if caminhos is None:
        return jsonify({"erro": "foto não encontrada"}), 404
    for caminho in caminhos:
        try:
            if caminho and os.path.exists(caminho):
                os.remove(caminho)
        except OSError:
            pass
    return jsonify({"ok": True})


@app.route("/aluno/<int:aluno_id>/avaliacao/<int:avaliacao_id>/postural/foto/<int:foto_id>/observacao", methods=["POST"])
@login_required
def postural_salvar_observacao(aluno_id, avaliacao_id, foto_id):
    aluno = db.buscar_aluno(aluno_id, session["personal_id"])
    if not aluno:
        abort(404)
    avaliacao = db.buscar_avaliacao(avaliacao_id)
    if not avaliacao or avaliacao["aluno_id"] != aluno_id:
        abort(404)
    texto = request.form.get("observacao", "").strip()
    ok = db.salvar_observacao_foto(foto_id, avaliacao_id, texto)
    return jsonify({"ok": ok})


@app.route("/aluno/<int:aluno_id>/postural/foto/<int:foto_id>/auto", methods=["POST"])
@login_required
def postural_deteccao_automatica(aluno_id, foto_id):
    aluno = db.buscar_aluno(aluno_id, session["personal_id"])
    if not aluno:
        abort(404)
    foto = db.buscar_foto(foto_id)
    if not foto:
        abort(404)
    avaliacao = db.buscar_avaliacao(foto["avaliacao_id"])
    if not avaliacao or avaliacao["aluno_id"] != aluno_id:
        abort(404)

    pasta_aluno = os.path.join(UPLOAD_DIR, str(aluno_id))
    nome_saida = f"auto_{uuid.uuid4().hex[:8]}.jpg"
    caminho_saida = os.path.join(pasta_aluno, nome_saida)

    resultado = postural.detectar_postura_automatica(foto["caminho_original"], caminho_saida, tipo=foto.get("tipo") or "frontal")
    if resultado.get("erro"):
        return jsonify({"ok": False, "mensagem": resultado["mensagem"]})

    db.atualizar_foto_anotada(foto_id, resultado["caminho_anotado"])
    db.atualizar_diagnostico_foto(foto_id, resultado.get("diagnostico"))
    conn = db.conectar()
    conn.execute(
        "UPDATE fotos_postura SET angulo_ombro=?, angulo_quadril=?, alerta=?, angulo_cabeca=?, desvio_tronco_pct=?, "
        "pontuacao=?, gravidade_geral=? WHERE id=?",
        (resultado["angulo_ombro"], resultado["angulo_quadril"], resultado["alerta"],
         resultado.get("angulo_cabeca"), resultado.get("desvio_tronco_pct"),
         resultado.get("pontuacao"), resultado.get("gravidade_geral"), foto_id)
    )
    conn.commit()
    conn.close()

    return jsonify({
        "ok": True,
        "url_imagem": url_for("servir_foto", aluno_id=aluno_id, nome_arquivo=os.path.basename(resultado["caminho_anotado"])),
        "angulo_ombro": resultado["angulo_ombro"],
        "angulo_quadril": resultado["angulo_quadril"],
        "angulo_cabeca": resultado.get("angulo_cabeca"),
        "desvio_tronco_pct": resultado.get("desvio_tronco_pct"),
        "pontuacao": resultado.get("pontuacao"),
        "gravidade_geral": resultado.get("gravidade_geral"),
        "alerta": resultado["alerta"],
        "diagnostico": resultado.get("diagnostico") or [],
    })


@app.route("/aluno/<int:aluno_id>/avaliacao/<int:avaliacao_id>/postural/parecer-geral")
@login_required
def postural_parecer_geral(aluno_id, avaliacao_id):
    aluno = db.buscar_aluno(aluno_id, session["personal_id"])
    if not aluno:
        abort(404)
    avaliacao = db.buscar_avaliacao(avaliacao_id)
    if not avaliacao or avaliacao["aluno_id"] != aluno_id:
        abort(404)

    fotos_raw = db.listar_fotos(avaliacao_id)
    fotos = []
    for f in fotos_raw:
        diagnostico = json.loads(f["diagnostico_json"]) if f["diagnostico_json"] else None
        if diagnostico:
            fotos.append({"tipo": f["tipo"], "diagnostico": diagnostico, "pontuacao": f["pontuacao"]})

    if len(fotos) < 2:
        return jsonify({"ok": False, "mensagem": "Analise pelo menos 2 fotos (idealmente as 4) pra gerar o parecer combinado."})

    parecer = postural.gerar_parecer_postural_completo(fotos)
    return jsonify({"ok": True, "parecer": parecer})


# ---------- PDF DA AVALIAÇÃO ----------

@app.route("/aluno/<int:aluno_id>/avaliacao/<int:avaliacao_id>/pdf")
@login_required
def avaliacao_pdf(aluno_id, avaliacao_id):
    aluno = db.buscar_aluno(aluno_id, session["personal_id"])
    if not aluno:
        abort(404)
    avaliacao = db.buscar_avaliacao(avaliacao_id)
    if not avaliacao or avaliacao["aluno_id"] != aluno_id:
        abort(404)
    personal = db.buscar_personal_por_id(session["personal_id"])
    historico = db.listar_avaliacoes(aluno_id)
    fotos = db.listar_fotos(avaliacao_id)
    if not fotos:
        fotos = db.buscar_fotos_recentes_aluno(aluno_id)
    anamnese = db.buscar_ultima_anamnese(aluno_id)

    nome_arquivo = f"avaliacao_{aluno['nome'].replace(' ', '_')}.pdf"

    def gerar(caminho_pdf, tmp_dir):
        pdf_gen.gerar_pdf_avaliacao(caminho_pdf, personal, aluno, avaliacao, historico, fotos, anamnese, tmp_dir)

    return _enviar_pdf_temporario(nome_arquivo, f"Avaliacao_{aluno['nome'].replace(' ', '_')}.pdf", gerar)


# ---------- TREINOS ----------

def _extrair_dias_do_form(form):
    nome_treino = form.get("nome_treino", "Treino") or "Treino"
    observacoes = form.get("observacoes", "")

    letras = form.getlist("dia_letra")
    dias_semana_form = form.getlist("dia_semana")
    grupos = form.getlist("dia_grupo")
    exercicios_json_por_dia = form.getlist("dia_exercicios_json")

    dias = []
    for letra, dia_semana, grupo, exercicios_raw in zip(letras, dias_semana_form, grupos, exercicios_json_por_dia):
        try:
            exercicios = json.loads(exercicios_raw or "[]")
        except (TypeError, ValueError):
            exercicios = []
        exercicios = [e for e in exercicios if (e.get("nome") or "").strip()]
        if not letra.strip() or not exercicios:
            continue
        dias.append({
            "letra": letra.strip().upper(),
            "dia_semana": dia_semana.strip(),
            "grupo_muscular": grupo.strip(),
            "exercicios": exercicios,
        })
    return nome_treino, dias, observacoes


@app.route("/aluno/<int:aluno_id>/treino/novo", methods=["GET", "POST"])
@login_required
def treino_novo(aluno_id):
    aluno = db.buscar_aluno(aluno_id, session["personal_id"])
    if not aluno:
        abort(404)
    if request.method == "POST":
        nome_treino, dias, observacoes = _extrair_dias_do_form(request.form)

        if not dias:
            flash("Adicione ao menos um dia de treino com exercícios.", "warning")
            return render_template("treino_form.html", aluno=aluno, dias_semana=db.DIAS_SEMANA)

        treino_id = db.criar_treino(aluno_id, nome_treino, json.dumps(dias, ensure_ascii=False), observacoes)
        flash("Treino salvo com sucesso!", "success")
        # Assim que o personal finaliza a ficha, o aluno já é avisado por
        # e-mail automaticamente — sem precisar de nenhum clique extra.
        if aluno.get("email") and security.email_valido(aluno["email"]):
            email_service.enviar_notificacao_novo_treino(aluno["email"], aluno["nome"], nome_treino, eh_edicao=False)
        # "Salvar e Baixar PDF" continua indo direto pro PDF; "Salvar" apenas
        # grava a ficha e volta pra tela de busca de aluno.
        if request.form.get("acao") == "salvar_pdf":
            return redirect(url_for("treino_pdf", aluno_id=aluno_id, treino_id=treino_id))
        return redirect(url_for("treino_selecionar_aluno"))
    return render_template("treino_form.html", aluno=aluno, dias_semana=db.DIAS_SEMANA)


@app.route("/aluno/<int:aluno_id>/treino/<int:treino_id>/editar", methods=["GET", "POST"])
@login_required
def treino_editar(aluno_id, treino_id):
    aluno = db.buscar_aluno(aluno_id, session["personal_id"])
    if not aluno:
        abort(404)
    treino = db.buscar_treino(treino_id)
    if not treino or treino["aluno_id"] != aluno_id:
        abort(404)

    if request.method == "POST":
        nome_treino, dias, observacoes = _extrair_dias_do_form(request.form)

        if not dias:
            flash("Adicione ao menos um dia de treino com exercícios.", "warning")
            dias_existentes = pdf_gen._normalizar_dias_treino(treino)
            return render_template("treino_form.html", aluno=aluno, dias_semana=db.DIAS_SEMANA,
                                    treino_existente=treino, treino_id=treino_id, dias_existentes=dias_existentes)

        db.atualizar_treino(treino_id, aluno_id, nome_treino, json.dumps(dias, ensure_ascii=False), observacoes)
        flash("Treino atualizado com sucesso!", "success")
        # Mesmo comportamento da criação: o aluno é avisado automaticamente
        # assim que a edição é salva.
        if aluno.get("email") and security.email_valido(aluno["email"]):
            email_service.enviar_notificacao_novo_treino(aluno["email"], aluno["nome"], nome_treino, eh_edicao=True)
        if request.form.get("acao") == "salvar_pdf":
            return redirect(url_for("treino_pdf", aluno_id=aluno_id, treino_id=treino_id))
        return redirect(url_for("treino_selecionar_aluno"))

    dias_existentes = pdf_gen._normalizar_dias_treino(treino)
    return render_template("treino_form.html", aluno=aluno, dias_semana=db.DIAS_SEMANA,
                            treino_existente=treino, treino_id=treino_id, dias_existentes=dias_existentes)


@app.route("/aluno/<int:aluno_id>/treino/<int:treino_id>/pdf")
@login_required
def treino_pdf(aluno_id, treino_id):
    aluno = db.buscar_aluno(aluno_id, session["personal_id"])
    if not aluno:
        abort(404)
    treino = db.buscar_treino(treino_id)
    if not treino or treino["aluno_id"] != aluno_id:
        abort(404)
    personal = db.buscar_personal_por_id(session["personal_id"])

    nome_arquivo = f"treino_{aluno['nome'].replace(' ', '_')}.pdf"

    def gerar(caminho_pdf, tmp_dir):
        pdf_gen.gerar_pdf_treino(caminho_pdf, personal, aluno, treino)

    return _enviar_pdf_temporario(nome_arquivo, f"Treino_{aluno['nome'].replace(' ', '_')}.pdf", gerar)


# ---------- RELATÓRIO COMPLETO (avaliação com fotos/análise de IA + treino da semana, tudo junto) ----------

@app.route("/aluno/<int:aluno_id>/relatorio-completo")
@login_required
def relatorio_completo_pdf(aluno_id):
    aluno = db.buscar_aluno(aluno_id, session["personal_id"])
    if not aluno:
        abort(404)
    avaliacoes = db.listar_avaliacoes(aluno_id)
    if not avaliacoes:
        flash("Cadastre uma avaliação física antes de gerar o relatório completo.", "warning")
        return redirect(url_for("aluno_perfil", aluno_id=aluno_id))

    avaliacao = avaliacoes[-1]
    personal = db.buscar_personal_por_id(session["personal_id"])
    historico = avaliacoes
    fotos = db.listar_fotos(avaliacao["id"])
    if not fotos:
        fotos = db.buscar_fotos_recentes_aluno(aluno_id)
    anamnese = db.buscar_ultima_anamnese(aluno_id)
    treinos = db.listar_treinos(aluno_id)
    treino = treinos[0] if treinos else None  # mais recente

    nome_arquivo = f"relatorio_completo_{aluno['nome'].replace(' ', '_')}.pdf"

    def gerar(caminho_pdf, tmp_dir):
        pdf_gen.gerar_pdf_relatorio_completo(caminho_pdf, personal, aluno, avaliacao, historico,
                                              fotos, anamnese, treino, tmp_dir)

    return _enviar_pdf_temporario(nome_arquivo, f"Relatorio_Completo_{aluno['nome'].replace(' ', '_')}.pdf", gerar)


# ---------- COMPARTILHAR ----------

@app.route("/aluno/<int:aluno_id>/compartilhar")
@login_required
def compartilhar(aluno_id):
    aluno = db.buscar_aluno(aluno_id, session["personal_id"])
    if not aluno:
        abort(404)
    avaliacoes = db.listar_avaliacoes(aluno_id)
    treinos = db.listar_treinos(aluno_id)
    ultima_avaliacao = avaliacoes[-1] if avaliacoes else None
    ultimo_treino = treinos[0] if treinos else None  # listar_treinos já vem em ordem decrescente
    return render_template("compartilhar.html", aluno=aluno, avaliacoes=avaliacoes, treinos=treinos,
                            ultima_avaliacao=ultima_avaliacao, ultimo_treino=ultimo_treino)


# ---------- ARQUIVOS ----------

@app.route("/uploads/<int:aluno_id>/<path:nome_arquivo>")
@login_required
def servir_foto(aluno_id, nome_arquivo):
    aluno = db.buscar_aluno(aluno_id, session["personal_id"])
    if not aluno:
        abort(404)
    caminho = os.path.join(UPLOAD_DIR, str(aluno_id), nome_arquivo)
    if not os.path.exists(caminho):
        abort(404)
    return send_file(caminho)


@app.route("/uploads/personal/<int:personal_id>/<path:nome_arquivo>")
@login_required
def servir_foto_personal(personal_id, nome_arquivo):
    """Serve a foto de perfil (avatar) do próprio personal logado — cada um
    só enxerga a sua, igual já acontece com as fotos dos alunos."""
    if personal_id != session["personal_id"]:
        abort(404)
    caminho = os.path.join(UPLOAD_DIR, "_personal", str(personal_id), nome_arquivo)
    if not os.path.exists(caminho):
        abort(404)
    return send_file(caminho)


@app.route("/uploads/personal-visto-por-aluno/<int:personal_id>/<path:nome_arquivo>")
def servir_foto_personal_para_aluno(personal_id, nome_arquivo):
    """Permite que o aluno veja a foto de perfil do próprio personal (ex:
    no cabeçalho da conversa) — só funciona se o aluno logado for
    vinculado a esse personal, ninguém mais enxerga essa foto por aqui."""
    aluno_id = session.get("aluno_id")
    if not aluno_id:
        abort(404)
    aluno = db.buscar_aluno_por_id_simples(aluno_id)
    if not aluno or aluno.get("personal_id") != personal_id:
        abort(404)
    caminho = os.path.join(UPLOAD_DIR, "_personal", str(personal_id), nome_arquivo)
    if not os.path.exists(caminho):
        abort(404)
    return send_file(caminho)


@app.route("/uploads/aluno-proprio/<int:aluno_id>/<path:nome_arquivo>")
def servir_foto_aluno(aluno_id, nome_arquivo):
    """Serve a própria foto de perfil do aluno logado (visão do painel
    dele) — diferente de 'servir_foto', que é a visão do personal."""
    if session.get("aluno_id") != aluno_id:
        abort(404)
    caminho = os.path.join(UPLOAD_DIR, str(aluno_id), nome_arquivo)
    if not os.path.exists(caminho):
        abort(404)
    return send_file(caminho)


@app.route("/chat-midia/<int:aluno_id>/<path:nome_arquivo>")
def servir_midia_chat(aluno_id, nome_arquivo):
    """Serve os áudios/vídeos/fotos trocados no chat — só quem participa
    daquela conversa específica enxerga (o personal dono do aluno, ou o
    próprio aluno logado)."""
    if session.get("personal_id"):
        aluno = db.buscar_aluno(aluno_id, session["personal_id"])
        if not aluno:
            abort(404)
    elif session.get("aluno_id") == aluno_id:
        pass
    else:
        abort(404)
    caminho = os.path.join(UPLOAD_DIR, str(aluno_id), nome_arquivo)
    if not os.path.exists(caminho):
        abort(404)
    # O Content-Type é escolhido explicitamente pela extensão real do
    # arquivo, em vez de deixar o Flask adivinhar sozinho (mimetypes.guess_type
    # não reconhece .m4a/.webm em todo sistema operacional) — sem isso, o
    # navegador podia receber "application/octet-stream" pra um áudio válido
    # e simplesmente recusar tocar (o problema clássico de "áudio não toca"
    # em áudios gravados no iPhone/Safari).
    extensao = os.path.splitext(nome_arquivo)[1].lower()
    mimetype = EXTENSAO_PARA_MIME_MIDIA_CHAT.get(extensao)
    if extensao == ".webm":
        # .webm sozinho é ambíguo (pode ser áudio ou vídeo) — confere o
        # tipo real da mensagem no banco pra não servir um vídeo como
        # "audio/webm" (ou vice-versa) e quebrar a reprodução.
        tipo_real = db.buscar_tipo_midia_chat(aluno_id, nome_arquivo)
        if tipo_real == "video":
            mimetype = "video/webm"
    return send_file(caminho, mimetype=mimetype) if mimetype else send_file(caminho)


# ---------- AGENDA (horários de atendimento) ----------

@app.route("/agenda")
@login_required
def agenda():
    agora_iso = datetime.now().isoformat()
    futuros = db.listar_agendamentos(session["personal_id"], a_partir_de=agora_iso)
    passados = [a for a in db.listar_agendamentos(session["personal_id"]) if a["data_hora"] < agora_iso]
    passados = list(reversed(passados))[:10]  # só os 10 últimos, pra não poluir a tela
    alunos = db.listar_alunos(session["personal_id"], None)

    horarios_fixos = db.listar_horarios_fixos(session["personal_id"])
    grade_semana = {i: [] for i in range(7)}
    for hf in horarios_fixos:
        grade_semana[hf["dia_semana"]].append(hf)

    _, proximos_para_alarme = _proximos_atendimentos(session["personal_id"])
    return render_template("agenda.html", futuros=futuros, passados=passados, alunos=alunos,
                            grade_semana=grade_semana, dias_semana_label=DIAS_SEMANA_LABEL,
                            proximos_json=json.dumps(proximos_para_alarme, ensure_ascii=False))


@app.route("/agenda/novo", methods=["POST"])
@login_required
def agenda_novo():
    aluno_id = request.form.get("aluno_id") or None
    titulo = request.form.get("titulo", "").strip()
    data = request.form.get("data", "").strip()
    hora = request.form.get("hora", "").strip()
    duracao = request.form.get("duracao_min", "60").strip()
    observacao = request.form.get("observacao", "").strip()

    if not data or not hora:
        flash("Escolha a data e o horário do atendimento.", "warning")
        return redirect(url_for("agenda"))

    aluno = db.buscar_aluno(int(aluno_id), session["personal_id"]) if aluno_id else None
    if aluno_id and not aluno:
        abort(404)

    if not titulo and aluno:
        titulo = f"Atendimento — {aluno['nome']}"
    elif not titulo:
        titulo = "Atendimento"

    try:
        duracao_min = int(duracao)
    except ValueError:
        duracao_min = 60

    data_hora = f"{data}T{hora}:00"
    db.criar_agendamento(session["personal_id"], int(aluno_id) if aluno_id else None,
                          titulo, data_hora, duracao_min, observacao)
    flash("Atendimento agendado! Deixe a aba da agenda aberta pra receber o aviso na hora.", "success")
    return redirect(url_for("agenda"))


@app.route("/agenda/<int:agendamento_id>/excluir", methods=["POST"])
@login_required
def agenda_excluir(agendamento_id):
    db.excluir_agendamento(agendamento_id, session["personal_id"])
    flash("Agendamento removido.", "success")
    return redirect(url_for("agenda"))


@app.route("/agenda/fixo/novo", methods=["POST"])
@login_required
def agenda_fixo_novo():
    aluno_id = request.form.get("aluno_id")
    dia_semana = request.form.get("dia_semana")
    hora = request.form.get("hora", "").strip()
    duracao = request.form.get("duracao_min", "60").strip()

    if not aluno_id or dia_semana is None or dia_semana == "" or not hora:
        flash("Escolha o aluno, o dia da semana e o horário.", "warning")
        return redirect(url_for("agenda"))

    aluno = db.buscar_aluno(int(aluno_id), session["personal_id"])
    if not aluno:
        abort(404)

    try:
        duracao_min = int(duracao)
    except ValueError:
        duracao_min = 60

    db.criar_horario_fixo(session["personal_id"], int(aluno_id), int(dia_semana), hora, duracao_min)
    flash(f"Horário fixo criado: {aluno['nome']} — {DIAS_SEMANA_LABEL[int(dia_semana)]} às {hora}.", "success")
    return redirect(url_for("agenda"))


@app.route("/agenda/fixo/<int:horario_id>/excluir", methods=["POST"])
@login_required
def agenda_fixo_excluir(horario_id):
    db.excluir_horario_fixo(horario_id, session["personal_id"])
    flash("Horário fixo removido.", "success")
    return redirect(url_for("agenda"))


# ---------- TREINOS REGISTRADOS (lista global, todos os alunos) ----------

@app.route("/treinos-registrados")
@login_required
def treinos_registrados():
    treinos = db.listar_treinos_do_personal(session["personal_id"])
    for t in treinos:
        try:
            dias = json.loads(t.get("exercicios_json") or "[]")
            t["letra_principal"] = dias[0].get("letra") if dias and isinstance(dias[0], dict) else None
            t["n_exercicios"] = sum(len(d.get("exercicios", [])) for d in dias) if dias and isinstance(dias[0], dict) else 0
        except (TypeError, ValueError, IndexError, AttributeError):
            t["letra_principal"] = None
            t["n_exercicios"] = 0
    return render_template("treinos_registrados.html", treinos=treinos, total=len(treinos))


# ---------- AVALIAÇÕES FÍSICAS (lista global, todos os alunos) ----------

@app.route("/avaliacoes-fisicas")
@login_required
def avaliacoes_fisicas_lista():
    avaliacoes = db.listar_avaliacoes_do_personal(session["personal_id"])
    for av in avaliacoes:
        av["imc_class"] = classificar_imc(av["imc"]) if av.get("imc") else None
    return render_template("avaliacoes_lista.html", avaliacoes=avaliacoes, total=len(avaliacoes))


# ---------- FINANCEIRO ----------

@app.route("/financeiro")
@login_required
def financeiro():
    tipo = request.args.get("tipo") or None
    lancamentos = db.listar_financeiro(session["personal_id"], tipo=tipo)
    resumo = db.resumo_financeiro_mes(session["personal_id"])
    alunos = db.listar_alunos(session["personal_id"])
    return render_template("financeiro.html", lancamentos=lancamentos, resumo=resumo,
                            alunos=alunos, filtro_tipo=tipo or "", hoje=datetime.now().date().isoformat())


@app.route("/financeiro/novo", methods=["POST"])
@login_required
def financeiro_novo():
    tipo = request.form.get("tipo", "receita")
    categoria = request.form.get("categoria", "").strip()
    descricao = request.form.get("descricao", "").strip()
    valor_raw = request.form.get("valor", "0").replace(",", ".").strip()
    data = request.form.get("data", "").strip() or datetime.now().date().isoformat()
    aluno_id = request.form.get("aluno_id") or None
    try:
        valor = abs(float(valor_raw))
    except ValueError:
        flash("Informe um valor numérico válido.", "warning")
        return redirect(url_for("financeiro"))
    if valor <= 0:
        flash("O valor precisa ser maior que zero.", "warning")
        return redirect(url_for("financeiro"))
    if aluno_id and not db.buscar_aluno(int(aluno_id), session["personal_id"]):
        abort(404)
    db.criar_lancamento_financeiro(session["personal_id"], tipo, categoria or None, descricao or None,
                                    valor, data, int(aluno_id) if aluno_id else None)
    flash("Lançamento registrado!", "success")
    return redirect(url_for("financeiro"))


@app.route("/financeiro/<int:lancamento_id>/excluir", methods=["POST"])
@login_required
def financeiro_excluir(lancamento_id):
    ok = db.excluir_lancamento_financeiro(lancamento_id, session["personal_id"])
    flash("Lançamento excluído." if ok else "Não foi possível excluir.", "success" if ok else "warning")
    return redirect(url_for("financeiro"))


# ---------- PLANOS PERSONALIZADOS ----------

@app.route("/planos")
@login_required
def planos():
    lista = db.listar_planos(session["personal_id"])
    contagem = db.contar_alunos_por_plano(session["personal_id"])
    for p in lista:
        p["n_alunos"] = contagem.get(p["id"], 0)
    alunos = db.listar_alunos(session["personal_id"])
    return render_template("planos.html", planos=lista, alunos=alunos)


@app.route("/planos/novo", methods=["POST"])
@login_required
def planos_novo():
    nome = request.form.get("nome", "").strip()
    descricao = request.form.get("descricao", "").strip()
    valor_raw = request.form.get("valor", "").replace(",", ".").strip()
    duracao_raw = request.form.get("duracao_dias", "30").strip()
    if not nome:
        flash("Dê um nome ao plano.", "warning")
        return redirect(url_for("planos"))
    try:
        valor = float(valor_raw) if valor_raw else None
    except ValueError:
        valor = None
    try:
        duracao_dias = int(duracao_raw)
    except ValueError:
        duracao_dias = 30
    db.criar_plano(session["personal_id"], nome, descricao or None, valor, duracao_dias)
    flash("Plano criado!", "success")
    return redirect(url_for("planos"))


@app.route("/planos/<int:plano_id>/alternar", methods=["POST"])
@login_required
def planos_alternar(plano_id):
    db.alternar_plano_ativo(plano_id, session["personal_id"])
    return redirect(url_for("planos"))


@app.route("/planos/<int:plano_id>/excluir", methods=["POST"])
@login_required
def planos_excluir(plano_id):
    ok = db.excluir_plano(plano_id, session["personal_id"])
    flash("Plano excluído." if ok else "Não foi possível excluir.", "success" if ok else "warning")
    return redirect(url_for("planos"))


@app.route("/planos/<int:plano_id>/atribuir", methods=["POST"])
@login_required
def planos_atribuir(plano_id):
    aluno_id = request.form.get("aluno_id")
    plano = db.buscar_plano(plano_id, session["personal_id"])
    aluno = db.buscar_aluno(int(aluno_id), session["personal_id"]) if aluno_id else None
    if not plano or not aluno:
        flash("Escolha um aluno válido.", "warning")
        return redirect(url_for("planos"))
    db.vincular_plano_aluno(aluno["id"], plano_id)
    flash(f"Plano '{plano['nome']}' vinculado a {aluno['nome']}.", "success")
    return redirect(url_for("planos"))


# ---------- CONTROLE DE PAGAMENTOS (mensalidades) ----------

@app.route("/pagamentos")
@login_required
def pagamentos():
    status = request.args.get("status") or None
    lista = db.listar_pagamentos(session["personal_id"], status=status)
    alunos = db.listar_alunos(session["personal_id"])
    return render_template("pagamentos.html", pagamentos=lista, alunos=alunos, filtro_status=status or "")


@app.route("/pagamentos/novo", methods=["POST"])
@login_required
def pagamentos_novo():
    aluno_id = request.form.get("aluno_id")
    descricao = request.form.get("descricao", "").strip() or "Mensalidade"
    valor_raw = request.form.get("valor", "0").replace(",", ".").strip()
    vencimento = request.form.get("vencimento", "").strip()
    if not aluno_id or not vencimento:
        flash("Escolha o aluno e a data de vencimento.", "warning")
        return redirect(url_for("pagamentos"))
    try:
        valor = abs(float(valor_raw))
    except ValueError:
        flash("Informe um valor numérico válido.", "warning")
        return redirect(url_for("pagamentos"))
    aluno = db.buscar_aluno(int(aluno_id), session["personal_id"])
    if not aluno:
        abort(404)
    db.criar_pagamento(session["personal_id"], aluno["id"], descricao, valor, vencimento)
    flash("Cobrança criada!", "success")
    return redirect(url_for("pagamentos"))


@app.route("/pagamentos/<int:pagamento_id>/pagar", methods=["POST"])
@login_required
def pagamentos_pagar(pagamento_id):
    ok = db.marcar_pagamento_pago(pagamento_id, session["personal_id"])
    flash("Pagamento confirmado e lançado no Financeiro!" if ok else "Não foi possível confirmar.",
          "success" if ok else "warning")
    return redirect(url_for("pagamentos"))


@app.route("/pagamentos/<int:pagamento_id>/excluir", methods=["POST"])
@login_required
def pagamentos_excluir(pagamento_id):
    ok = db.excluir_pagamento(pagamento_id, session["personal_id"])
    flash("Cobrança excluída." if ok else "Não foi possível excluir.", "success" if ok else "warning")
    return redirect(url_for("pagamentos"))


# ---------- METAS DOS ALUNOS ----------

@app.route("/metas")
@login_required
def metas():
    aluno_id = request.args.get("aluno_id", type=int)
    lista = db.listar_metas(session["personal_id"], aluno_id=aluno_id)
    for m in lista:
        pct = 0
        if m.get("valor_alvo") is not None and m.get("valor_inicial") is not None and m.get("valor_atual") is not None:
            distancia_total = abs(m["valor_alvo"] - m["valor_inicial"])
            percorrido = abs(m["valor_atual"] - m["valor_inicial"])
            if distancia_total > 0:
                pct = max(0, min(100, round((percorrido / distancia_total) * 100)))
            else:
                pct = 100
        m["pct"] = pct
    alunos = db.listar_alunos(session["personal_id"])
    return render_template("metas.html", metas=lista, alunos=alunos, filtro_aluno_id=aluno_id)


@app.route("/metas/novo", methods=["POST"])
@login_required
def metas_novo():
    aluno_id = request.form.get("aluno_id")
    titulo = request.form.get("titulo", "").strip()
    tipo = request.form.get("tipo", "").strip() or "outro"
    unidade = request.form.get("unidade", "").strip()
    prazo = request.form.get("prazo", "").strip() or None

    def _num(campo):
        bruto = request.form.get(campo, "").replace(",", ".").strip()
        try:
            return float(bruto) if bruto else None
        except ValueError:
            return None

    valor_inicial, valor_alvo = _num("valor_inicial"), _num("valor_alvo")
    if not aluno_id or not titulo:
        flash("Escolha o aluno e dê um título à meta.", "warning")
        return redirect(url_for("metas"))
    aluno = db.buscar_aluno(int(aluno_id), session["personal_id"])
    if not aluno:
        abort(404)
    db.criar_meta(aluno["id"], session["personal_id"], titulo, tipo, valor_inicial, valor_alvo,
                  valor_inicial, unidade or None, prazo)
    flash("Meta criada!", "success")
    return redirect(url_for("metas"))


@app.route("/metas/<int:meta_id>/progresso", methods=["POST"])
@login_required
def metas_progresso(meta_id):
    bruto = request.form.get("valor_atual", "").replace(",", ".").strip()
    try:
        valor_atual = float(bruto)
    except ValueError:
        flash("Informe um valor numérico válido.", "warning")
        return redirect(url_for("metas"))
    ok = db.atualizar_progresso_meta(meta_id, session["personal_id"], valor_atual)
    flash("Progresso atualizado!" if ok else "Não foi possível atualizar.", "success" if ok else "warning")
    return redirect(url_for("metas"))


@app.route("/metas/<int:meta_id>/status", methods=["POST"])
@login_required
def metas_status(meta_id):
    status = request.form.get("status", "em_andamento")
    db.atualizar_status_meta(meta_id, session["personal_id"], status)
    return redirect(url_for("metas"))


@app.route("/metas/<int:meta_id>/excluir", methods=["POST"])
@login_required
def metas_excluir(meta_id):
    ok = db.excluir_meta(meta_id, session["personal_id"])
    flash("Meta excluída." if ok else "Não foi possível excluir.", "success" if ok else "warning")
    return redirect(url_for("metas"))


# ---------- ANOTAÇÕES RÁPIDAS ----------

@app.route("/anotacoes")
@login_required
def anotacoes():
    aluno_id = request.args.get("aluno_id", type=int)
    lista = db.listar_anotacoes(session["personal_id"], aluno_id=aluno_id)
    alunos = db.listar_alunos(session["personal_id"])
    return render_template("anotacoes.html", anotacoes=lista, alunos=alunos, filtro_aluno_id=aluno_id)


@app.route("/anotacoes/novo", methods=["POST"])
@login_required
def anotacoes_novo():
    texto = request.form.get("texto", "").strip()
    aluno_id = request.form.get("aluno_id") or None
    if not texto:
        flash("Escreva algo para anotar.", "warning")
        return redirect(url_for("anotacoes"))
    if aluno_id and not db.buscar_aluno(int(aluno_id), session["personal_id"]):
        abort(404)
    db.criar_anotacao(session["personal_id"], int(aluno_id) if aluno_id else None, texto)
    flash("Anotação salva!", "success")
    return redirect(url_for("anotacoes"))


@app.route("/anotacoes/<int:anotacao_id>/fixar", methods=["POST"])
@login_required
def anotacoes_fixar(anotacao_id):
    db.alternar_fixar_anotacao(anotacao_id, session["personal_id"])
    return redirect(url_for("anotacoes"))


@app.route("/anotacoes/<int:anotacao_id>/excluir", methods=["POST"])
@login_required
def anotacoes_excluir(anotacao_id):
    ok = db.excluir_anotacao(anotacao_id, session["personal_id"])
    flash("Anotação excluída." if ok else "Não foi possível excluir.", "success" if ok else "warning")
    return redirect(url_for("anotacoes"))


# ---------- CHECK-IN DE ALUNOS (presença) ----------

@app.route("/checkin")
@login_required
def checkin():
    alunos = db.listar_alunos(session["personal_id"])
    presentes_hoje = db.listar_checkins_hoje(session["personal_id"])
    ids_presentes = {c["aluno_id"] for c in presentes_hoje}
    return render_template("checkin.html", alunos=alunos, presentes_hoje=presentes_hoje,
                            ids_presentes=ids_presentes)


@app.route("/checkin/novo", methods=["POST"])
@login_required
def checkin_novo():
    aluno_id = request.form.get("aluno_id")
    if not aluno_id:
        flash("Escolha um aluno.", "warning")
        return redirect(url_for("checkin"))
    aluno = db.buscar_aluno(int(aluno_id), session["personal_id"])
    if not aluno:
        abort(404)
    if db.aluno_ja_fez_checkin_hoje(aluno["id"]):
        flash(f"{aluno['nome']} já fez check-in hoje.", "warning")
    else:
        db.registrar_checkin(aluno["id"], session["personal_id"])
        flash(f"Check-in de {aluno['nome']} registrado!", "success")
    return redirect(url_for("checkin"))


@app.route("/checkin/<int:checkin_id>/excluir", methods=["POST"])
@login_required
def checkin_excluir(checkin_id):
    db.excluir_checkin(checkin_id, session["personal_id"])
    return redirect(url_for("checkin"))


# ---------- MENSAGENS (chat real dentro do app, estilo WhatsApp) ----------

def _rotulo_data_chat(data_iso, hoje):
    """'Hoje' / 'Ontem' / dd/mm/aaaa — igual ao separador de data do
    WhatsApp entre grupos de mensagens de dias diferentes."""
    dia = (data_iso or "")[:10]
    if dia == hoje.strftime("%Y-%m-%d"):
        return "Hoje"
    if dia == (hoje - timedelta(days=1)).strftime("%Y-%m-%d"):
        return "Ontem"
    try:
        return datetime.strptime(dia, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return dia


def _agrupar_mensagens_por_dia(mensagens_lista):
    """Intercala as mensagens com marcadores de separação de data, prontos
    pra tela desenhar o separador 'Hoje'/'Ontem'/data entre os grupos.
    Usa a chave '_kind' pra distinguir separador de mensagem — 'tipo' fica
    livre para indicar o TIPO DE MÍDIA da mensagem (texto/áudio/vídeo/...)."""
    agrupado = []
    hoje = datetime.now()
    dia_atual = None
    for m in mensagens_lista:
        dia = (m.get("enviado_em") or "")[:10]
        if dia != dia_atual:
            agrupado.append({"_kind": "data", "label": _rotulo_data_chat(m.get("enviado_em"), hoje)})
            dia_atual = dia
        item = dict(m)
        item["_kind"] = "msg"
        agrupado.append(item)
    return agrupado


def _midia_chat_url(m):
    """URL pública do arquivo de mídia (áudio/vídeo/foto) de uma mensagem,
    servida por rota que confere se quem pede é o personal ou o aluno
    daquela conversa específica."""
    if not m.get("midia_arquivo"):
        return None
    return url_for("servir_midia_chat", aluno_id=m["aluno_id"], nome_arquivo=m["midia_arquivo"])


def _resumo_avaliacao_chat(avaliacao, aluno):
    """Monta os números compactos (IMC, %gordura, massa magra/gorda e as
    classificações/cores dos medidores) usados no cartão de relatório que
    aparece direto na conversa quando o personal finaliza uma avaliação."""
    if not avaliacao:
        return None
    cat_imc = classificar_imc(avaliacao.get("imc"))
    cat_bf = classificar_bf(avaliacao.get("bf"), aluno.get("sexo"))
    gauge_imc = gauge_info(avaliacao.get("imc"), 15, 40, cat_imc)
    gauge_bf = gauge_info(avaliacao.get("bf"), 3, 45, cat_bf)
    return {
        "peso": avaliacao.get("peso"), "imc": avaliacao.get("imc"), "bf": avaliacao.get("bf"),
        "massa_magra": avaliacao.get("massa_magra"), "massa_gorda": avaliacao.get("massa_gorda"),
        "cat_imc": cat_imc, "cat_bf": cat_bf, "gauge_imc": gauge_imc, "gauge_bf": gauge_bf,
    }


def _url_relatorio_chat(aluno_id, avaliacao_id, quem):
    """Link do botão 'Ver relatório completo' dentro do cartão — muda
    conforme quem está olhando a conversa (o personal cai na tela de
    resultado dele; o aluno, na tela de detalhe da própria avaliação)."""
    if quem == "personal":
        return url_for("avaliacao_resultado", aluno_id=aluno_id, avaliacao_id=avaliacao_id)
    return url_for("aluno_avaliacao_detalhe", avaliacao_id=avaliacao_id)


def _enriquecer_mensagens(mensagens_lista, aluno, quem):
    """Acrescenta a cada mensagem (já agrupada por dia) os dados prontos
    pra tela desenhar: URL da mídia e, se for um cartão de relatório, o
    resumo da avaliação + o link certo pra quem está vendo."""
    for item in mensagens_lista:
        if item.get("_kind") != "msg":
            continue
        item["midia_url"] = _midia_chat_url(item)
        if item.get("tipo") == "relatorio_avaliacao" and item.get("avaliacao_id"):
            avaliacao = db.buscar_avaliacao(item["avaliacao_id"])
            item["resumo_avaliacao"] = _resumo_avaliacao_chat(avaliacao, aluno) if avaliacao else None
            item["url_relatorio"] = _url_relatorio_chat(aluno["id"], item["avaliacao_id"], quem)
    return mensagens_lista


def _mensagem_para_json(item, aluno, quem):
    """Serializa uma mensagem (linha do banco) pros campos que o polling em
    JavaScript precisa pra desenhar a bolha certa (texto, áudio, vídeo,
    imagem ou cartão de relatório) sem recarregar a conversa inteira."""
    dados = dict(item)
    dados["midia_url"] = _midia_chat_url(item)
    if item.get("tipo") == "relatorio_avaliacao" and item.get("avaliacao_id"):
        avaliacao = db.buscar_avaliacao(item["avaliacao_id"])
        dados["resumo_avaliacao"] = _resumo_avaliacao_chat(avaliacao, aluno) if avaliacao else None
        dados["url_relatorio"] = _url_relatorio_chat(aluno["id"], item["avaliacao_id"], quem)
    return dados


# Extensões aceitas pro upload de mídia dentro do chat — cobre o que o
# MediaRecorder do navegador grava (webm/ogg no Chrome/Android, mp4/m4a no
# Safari/iOS) e formatos comuns de foto.
EXTENSOES_MIDIA_CHAT = {
    "audio": {".webm", ".ogg", ".m4a", ".mp3", ".wav", ".mp4"},
    "video": {".webm", ".mp4", ".mov", ".ogg"},
    "imagem": {".jpg", ".jpeg", ".png", ".webp", ".gif"},
}
# Prefixo do Content-Type que o navegador manda junto do arquivo — usado
# pra conferir que o conteúdo realmente bate com o tipo declarado (ex:
# barra um arquivo disfarçado de foto que na verdade não é uma imagem).
MIME_PREFIXOS_MIDIA_CHAT = {"audio": "audio/", "video": "video/", "imagem": "image/"}
# Mapa de Content-Type -> extensão real, usado quando o nome de arquivo que
# o navegador manda não bate com nenhuma extensão conhecida (ex: iOS/Safari
# grava áudio como "audio/mp4" mas o JS às vezes nomeia o arquivo genérico).
# Sem isso, um áudio gravado em mp4 podia ser salvo com extensão .webm por
# engano — o arquivo era salvo e a mensagem enviada normalmente, mas o
# áudio não tocava depois (o navegador servia como webm um conteúdo que na
# verdade era mp4), o que dava a impressão de que "o envio de áudio não
# funciona".
MIME_PARA_EXTENSAO_MIDIA_CHAT = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/mp4": ".m4a",
    "audio/m4a": ".m4a",
    "audio/x-m4a": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "video/webm": ".webm",
    "video/mp4": ".mp4",
    "video/quicktime": ".mov",
    "video/ogg": ".ogg",
}
# Sentido inverso do mapa acima — usado na hora de SERVIR o arquivo de
# volta pro navegador, pra garantir um Content-Type correto sempre
# (essencial pro <audio>/<video> tocarem; alguns sistemas operacionais não
# têm .m4a/.webm cadastrados no mimetypes do Python, o que faria o Flask
# servir como "application/octet-stream" e o navegador recusar tocar).
EXTENSAO_PARA_MIME_MIDIA_CHAT = {
    ".webm": "audio/webm",  # sobrescrita abaixo para vídeo quando necessário
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
TAMANHO_MAX_MIDIA_CHAT = 25 * 1024 * 1024  # 25 MB


class MidiaChatInvalida(Exception):
    """Levantada quando o arquivo enviado não passa na validação de
    tipo/formato — vira erro 400 pro usuário, nunca um 500 genérico."""
    pass


def _salvar_midia_chat(aluno_id, arquivo, tipo):
    """Salva o arquivo de mídia enviado no chat (áudio/vídeo/foto) na pasta
    de uploads do aluno e devolve o nome salvo em disco. Confere se o
    Content-Type bate com o tipo declarado e grava primeiro num arquivo
    temporário na mesma pasta, só promovendo pro nome final depois que a
    gravação termina inteira — assim ninguém do outro lado da conversa
    chega a ver/baixar um arquivo pela metade se o envio for interrompido,
    e o temporário é sempre apagado (sucesso ou falha) ao final."""
    extensoes_ok = EXTENSOES_MIDIA_CHAT.get(tipo, set())
    extensao = os.path.splitext(arquivo.filename or "")[1].lower()
    if extensao not in extensoes_ok:
        # Não bate com nenhuma extensão esperada pelo nome do arquivo — usa
        # o Content-Type real que o navegador mandou pra escolher a
        # extensão certa (em vez de simplesmente forçar .webm, que corrompia
        # áudios gravados em mp4/m4a no Safari/iOS).
        extensao = MIME_PARA_EXTENSAO_MIDIA_CHAT.get((arquivo.mimetype or "").lower())
        if not extensao:
            extensao = ".webm" if tipo in ("audio", "video") else ".jpg"

    mime_esperado = MIME_PREFIXOS_MIDIA_CHAT.get(tipo)
    if mime_esperado and arquivo.mimetype and not arquivo.mimetype.startswith(mime_esperado):
        raise MidiaChatInvalida(f"O arquivo enviado não é um(a) {tipo} válido(a).")

    pasta = os.path.join(UPLOAD_DIR, str(aluno_id), "chat")
    os.makedirs(pasta, exist_ok=True)
    nome_arquivo = f"{uuid.uuid4().hex}{extensao}"
    destino = os.path.join(pasta, nome_arquivo)
    tmp_path = destino + ".tmp"
    try:
        arquivo.save(tmp_path)
        os.replace(tmp_path, destino)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    return f"chat/{nome_arquivo}"


@app.route("/mensagens")
@login_required
def mensagens():
    personal_id = session["personal_id"]
    conversas = db.listar_conversas_personal(personal_id)
    return render_template("mensagens.html", conversas=conversas)


@app.route("/mensagens/enviar/<int:aluno_id>")
@login_required
def mensagens_enviar(aluno_id):
    """Registra a mensagem no histórico e leva direto pro WhatsApp do aluno já
    com o texto preenchido — o envio de fato acontece no WhatsApp do próprio
    personal (o sistema não manda mensagem sozinho por conta própria).
    Mantido como atalho avulso; o chat real do app fica em /mensagens/conversa."""
    aluno = db.buscar_aluno(aluno_id, session["personal_id"])
    if not aluno:
        abort(404)
    texto = request.args.get("texto", "").strip()
    if not texto:
        flash("Escreva o texto da mensagem.", "warning")
        return redirect(url_for("mensagens"))
    if not aluno.get("telefone"):
        flash(f"{aluno['nome']} não tem telefone cadastrado.", "warning")
        return redirect(url_for("mensagens"))
    db.registrar_mensagem_enviada(session["personal_id"], aluno_id, texto)
    numero = _telefone_whatsapp(aluno["telefone"])
    from urllib.parse import quote
    return redirect(f"https://wa.me/{numero}?text={quote(texto)}")


@app.route("/mensagens/conversa/<int:aluno_id>")
@login_required
def mensagens_conversa(aluno_id):
    """Tela de chat do personal com um aluno específico — o personal pode
    abrir a conversa de qualquer aluno dele, mesmo que nunca tenham trocado
    mensagem ainda."""
    personal_id = session["personal_id"]
    aluno = db.buscar_aluno(aluno_id, personal_id)
    if not aluno:
        abort(404)
    db.marcar_chat_lido_personal(personal_id, aluno_id)
    mensagens_lista = db.listar_mensagens_chat(personal_id, aluno_id)
    ultimo_id = mensagens_lista[-1]["id"] if mensagens_lista else 0
    ultimo_dia = (mensagens_lista[-1]["enviado_em"] or "")[:10] if mensagens_lista else ""
    agrupadas = _enriquecer_mensagens(_agrupar_mensagens_por_dia(mensagens_lista), aluno, "personal")
    return render_template("mensagens_conversa.html", aluno=aluno,
                            mensagens=agrupadas,
                            ultimo_id=ultimo_id, ultimo_dia=ultimo_dia)


@app.route("/mensagens/conversa/<int:aluno_id>/enviar", methods=["POST"])
@login_required
def mensagens_conversa_enviar(aluno_id):
    personal_id = session["personal_id"]
    aluno = db.buscar_aluno(aluno_id, personal_id)
    if not aluno:
        abort(404)
    texto = (request.form.get("texto") or "").strip()
    if not texto:
        return jsonify({"ok": False, "erro": "Escreva uma mensagem."}), 400
    texto = texto[:4000]
    mid = db.enviar_mensagem_chat(personal_id, aluno_id, "personal", texto)
    return jsonify({"ok": True, "id": mid})


@app.route("/mensagens/conversa/<int:aluno_id>/enviar-midia", methods=["POST"])
@login_required
def mensagens_conversa_enviar_midia(aluno_id):
    """Recebe o áudio/vídeo gravado na hora (ou foto) do próprio input do
    navegador e grava como mensagem de mídia na conversa."""
    personal_id = session["personal_id"]
    aluno = db.buscar_aluno(aluno_id, personal_id)
    if not aluno:
        abort(404)
    tipo = request.form.get("tipo", "")
    if tipo not in ("audio", "video", "imagem"):
        return jsonify({"ok": False, "erro": "Tipo de mídia inválido."}), 400
    arquivo = request.files.get("arquivo")
    if not arquivo or not arquivo.filename:
        return jsonify({"ok": False, "erro": "Nenhum arquivo recebido."}), 400
    arquivo.seek(0, os.SEEK_END)
    if arquivo.tell() > TAMANHO_MAX_MIDIA_CHAT:
        return jsonify({"ok": False, "erro": "Arquivo muito grande (máx. 25MB)."}), 400
    arquivo.seek(0)
    try:
        caminho_salvo = _salvar_midia_chat(aluno_id, arquivo, tipo)
    except MidiaChatInvalida as e:
        return jsonify({"ok": False, "erro": str(e)}), 400
    except OSError:
        logger.exception("Falha ao salvar mídia do chat (aluno_id=%s)", aluno_id)
        return jsonify({"ok": False, "erro": "Não foi possível salvar o arquivo. Tente novamente."}), 500
    duracao = request.form.get("duracao", type=float)
    mid = db.enviar_mensagem_chat(personal_id, aluno_id, "personal", "", tipo=tipo,
                                   midia_arquivo=caminho_salvo, midia_duracao=duracao)
    return jsonify({"ok": True, "id": mid})


@app.route("/mensagens/conversa/<int:aluno_id>/novas")
@login_required
def mensagens_conversa_novas(aluno_id):
    personal_id = session["personal_id"]
    aluno = db.buscar_aluno(aluno_id, personal_id)
    if not aluno:
        abort(404)
    depois_de = request.args.get("depois_de", 0, type=int)
    novas = db.listar_mensagens_chat_novas(personal_id, aluno_id, depois_de)
    if any(m["remetente"] == "aluno" for m in novas):
        db.marcar_chat_lido_personal(personal_id, aluno_id)
    novas_json = [_mensagem_para_json(m, aluno, "personal") for m in novas]
    lidas = db.listar_ids_lidos(personal_id, aluno_id, "personal")
    apagadas = db.listar_ids_apagados(personal_id, aluno_id)
    return jsonify({"ok": True, "mensagens": novas_json, "lidas": lidas, "apagadas": apagadas})


@app.route("/mensagens/conversa/<int:aluno_id>/apagar", methods=["POST"])
@login_required
def mensagens_conversa_apagar(aluno_id):
    """'Apagar para todos' (estilo WhatsApp): o personal só pode apagar
    mensagens que ELE mesmo enviou — o aluno também deixa de ver o
    conteúdo assim que a tela dele buscar mensagens novas de novo."""
    personal_id = session["personal_id"]
    aluno = db.buscar_aluno(aluno_id, personal_id)
    if not aluno:
        abort(404)
    mensagem_id = request.form.get("mensagem_id", type=int)
    if not mensagem_id:
        return jsonify({"ok": False, "erro": "Mensagem inválida."}), 400
    ok = db.apagar_mensagem_chat(mensagem_id, personal_id, aluno_id, "personal")
    if not ok:
        return jsonify({"ok": False, "erro": "Só é possível apagar mensagens enviadas por você."}), 403
    return jsonify({"ok": True, "id": mensagem_id})


# ---------- BIBLIOTECA DE EXERCÍCIOS ----------

@app.route("/biblioteca-exercicios")
@login_required
def biblioteca_exercicios():
    return render_template("biblioteca_exercicios.html")


# ---------- RELATÓRIOS AVANÇADOS ----------

@app.route("/relatorios")
@login_required
def relatorios():
    personal_id = session["personal_id"]
    hoje = datetime.now().date()
    dias = [(hoje - timedelta(days=i)) for i in range(29, -1, -1)]

    conn = db.conectar()
    inicio = dias[0].isoformat()
    fim_exclusivo = (hoje + timedelta(days=1)).isoformat()

    receitas_rows = conn.execute(
        "SELECT data, valor FROM financeiro WHERE personal_id=? AND tipo='receita' AND data>=? AND data<?",
        (personal_id, inicio, fim_exclusivo)
    ).fetchall()
    despesas_rows = conn.execute(
        "SELECT data, valor FROM financeiro WHERE personal_id=? AND tipo='despesa' AND data>=? AND data<?",
        (personal_id, inicio, fim_exclusivo)
    ).fetchall()
    alunos_rows = conn.execute(
        "SELECT data_cadastro FROM alunos WHERE personal_id=? AND data_cadastro>=?",
        (personal_id, inicio)
    ).fetchall()
    checkins_rows = conn.execute(
        "SELECT data_hora FROM checkins WHERE personal_id=? AND data_hora>=?",
        (personal_id, inicio)
    ).fetchall()
    conn.close()

    def _agrupar_por_dia(rows, campo_data, campo_valor=None):
        totais = {d.isoformat(): 0.0 for d in dias}
        for r in rows:
            chave = (r[campo_data] or "")[:10]
            if chave in totais:
                totais[chave] += float(r[campo_valor]) if campo_valor else 1
        return [round(totais[d.isoformat()], 2) for d in dias]

    receitas_dia = _agrupar_por_dia(receitas_rows, "data", "valor")
    despesas_dia = _agrupar_por_dia(despesas_rows, "data", "valor")
    novos_alunos_dia = _agrupar_por_dia(alunos_rows, "data_cadastro")
    checkins_dia = _agrupar_por_dia(checkins_rows, "data_hora")

    resumo_mes = db.resumo_financeiro_mes(personal_id)
    total_alunos = db.contar_alunos(personal_id)
    total_treinos = db.contar_treinos_do_personal(personal_id)
    total_checkins_30d = sum(checkins_dia)
    total_novos_30d = sum(novos_alunos_dia)

    return render_template("relatorios.html",
                            labels=[d.strftime("%d/%m") for d in dias],
                            receitas_dia=receitas_dia, despesas_dia=despesas_dia,
                            novos_alunos_dia=novos_alunos_dia, checkins_dia=checkins_dia,
                            resumo_mes=resumo_mes, total_alunos=total_alunos,
                            total_treinos=total_treinos, total_checkins_30d=total_checkins_30d,
                            total_novos_30d=total_novos_30d)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
