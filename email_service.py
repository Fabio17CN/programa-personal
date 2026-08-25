"""
Envio de e-mails do sistema (códigos de verificação de cadastro e de
recuperação de senha).

MÉTODO PRINCIPAL — API HTTP do SendGrid (recomendado; funciona em
hospedagens como o Render no plano gratuito, que bloqueia conexões de
saída SMTP nas portas 587/465, pois o SendGrid usa HTTPS/porta 443).
    SENDGRID_API_KEY -> chave de API gerada em app.sendgrid.com/settings/api_keys
    SENDGRID_FROM    -> remetente verificado (Single Sender) no SendGrid

MÉTODO ALTERNATIVO — API HTTP do Resend:
    RESEND_API_KEY -> chave de API gerada em resend.com/api-keys
    RESEND_FROM    -> remetente verificado no Resend, ex: painelnm@seudominio.com
                       (sem domínio próprio configurado no Resend, use o
                       remetente de testes "onboarding@resend.dev" — mas
                       aí só é possível enviar para o e-mail da própria
                       conta Resend, não para qualquer aluno/personal)

MÉTODO ALTERNATIVO — SMTP tradicional (funciona em hospedagens que não
bloqueiam a porta 587, ex: rodando localmente ou em VPS próprio):
    SMTP_HOST   -> ex: smtp.gmail.com
    SMTP_PORT   -> ex: 587
    SMTP_USER   -> usuário/e-mail da conta que envia
    SMTP_PASS   -> senha ou senha de app
    SMTP_FROM   -> remetente exibido (opcional, usa SMTP_USER se vazio)
    SMTP_USE_TLS -> "1" para usar STARTTLS (padrão) ou "0" para desativar

Se nenhuma dessas variáveis estiver configurada (ex: rodando localmente
para testar), o sistema NÃO quebra: o e-mail é apenas registrado no log
do servidor, para que o desenvolvimento continue funcionando sem precisar
de uma conta de e-mail real.

Prioridade de envio: SendGrid (se SENDGRID_API_KEY definida) -> Resend
(se RESEND_API_KEY definida) -> SMTP (se configurado) -> modo simulado (log).
"""
import os
import json
import smtplib
import logging
import urllib.request
import urllib.error
from email.mime.text import MIMEText

logger = logging.getLogger("nm_personal.email")

SENDGRID_API_KEY = (os.environ.get("SENDGRID_API_KEY") or "").strip()
SENDGRID_FROM = (os.environ.get("SENDGRID_FROM") or "").strip()
SENDGRID_API_URL = "https://api.sendgrid.com/v3/mail/send"

RESEND_API_KEY = (os.environ.get("RESEND_API_KEY") or "").strip()
RESEND_FROM = (os.environ.get("RESEND_FROM") or "").strip()
RESEND_API_URL = "https://api.resend.com/emails"

SMTP_HOST = os.environ.get("SMTP_HOST")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")
SMTP_FROM = os.environ.get("SMTP_FROM") or SMTP_USER
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "1") != "0"

NOME_SISTEMA = "Painel NM"


def _sendgrid_configurado():
    return bool(SENDGRID_API_KEY and SENDGRID_FROM)


def _resend_configurado():
    return bool(RESEND_API_KEY)


def _smtp_configurado():
    return bool(SMTP_HOST and SMTP_USER and SMTP_PASS)


# Diagnóstico na inicialização: aparece uma vez só, nos logs do servidor
# assim que o app sobe, pra ficar óbvio qual caminho de envio está ativo
# sem precisar disparar um e-mail de teste pra descobrir. Não expõe a
# chave — só confirma se ela foi lida do ambiente ou não.
if _sendgrid_configurado():
    logger.info(
        "E-mail: usando SendGrid (API HTTP). Chave detectada (%d caracteres), remetente=%s",
        len(SENDGRID_API_KEY), SENDGRID_FROM
    )
elif _resend_configurado():
    logger.info(
        "E-mail: usando Resend (API HTTP). Chave detectada (%d caracteres), remetente=%s",
        len(RESEND_API_KEY), RESEND_FROM or "onboarding@resend.dev (padrão de teste)"
    )
elif _smtp_configurado():
    logger.warning(
        "E-mail: nenhuma API configurada — usando SMTP (%s:%s). "
        "Se estiver no Render, isso provavelmente vai falhar com 'Network is unreachable'.",
        SMTP_HOST, SMTP_PORT
    )
else:
    logger.warning("E-mail: nenhum provedor configurado — e-mails serão só simulados em log.")


def _enviar_via_sendgrid(destinatario, assunto, corpo_texto):
    """Envia o e-mail chamando a API HTTP do SendGrid (porta 443/HTTPS) —
    não usa socket SMTP, por isso funciona mesmo em hospedagens que
    bloqueiam as portas 587/465, como o plano gratuito do Render."""
    payload = json.dumps({
        "personalizations": [{"to": [{"email": destinatario}]}],
        "from": {"email": SENDGRID_FROM, "name": NOME_SISTEMA},
        "subject": assunto,
        "content": [{"type": "text/plain", "value": corpo_texto}],
    }).encode("utf-8")

    requisicao = urllib.request.Request(
        SENDGRID_API_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {SENDGRID_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(requisicao, timeout=15) as resposta:
            resposta.read()
        logger.info("E-mail (SendGrid) enviado com sucesso para: %s | Assunto: %s", destinatario, assunto)
        return True
    except urllib.error.HTTPError as erro:
        # SendGrid devolve o motivo do erro no corpo da resposta (ex: remetente
        # não verificado, chave de API inválida/sem permissão etc.) — isso
        # ajuda muito a diagnosticar sem precisar adivinhar.
        detalhe = erro.read().decode("utf-8", errors="replace")[:500]
        logger.error("Falha ao enviar e-mail (SendGrid) para %s — HTTP %s: %s",
                     destinatario, erro.code, detalhe)
        return False
    except Exception:
        logger.exception("Falha ao enviar e-mail (SendGrid) para %s", destinatario)
        return False


def _enviar_via_resend(destinatario, assunto, corpo_texto):
    """Envia o e-mail chamando a API HTTP do Resend (porta 443/HTTPS) —
    não usa socket SMTP, por isso funciona mesmo em hospedagens que
    bloqueiam as portas 587/465, como o plano gratuito do Render."""
    remetente_email = RESEND_FROM or SMTP_FROM or "onboarding@resend.dev"
    payload = json.dumps({
        "from": f"{NOME_SISTEMA} <{remetente_email}>",
        "to": [destinatario],
        "subject": assunto,
        "text": corpo_texto,
    }).encode("utf-8")

    requisicao = urllib.request.Request(
        RESEND_API_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
            # Sem um User-Agent "normal", o Cloudflare que protege a API
            # do Resend reconhece a assinatura padrão do urllib do Python
            # como tráfego automatizado e bloqueia com HTTP 403 (error
            # code: 1010), antes mesmo da requisição chegar no Resend.
            "User-Agent": "PainelNM/1.0 (+https://programa-personal.onrender.com)",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(requisicao, timeout=15) as resposta:
            resposta.read()
        logger.info("E-mail (Resend) enviado com sucesso para: %s | Assunto: %s", destinatario, assunto)
        return True
    except urllib.error.HTTPError as erro:
        # Resend devolve o motivo do erro no corpo da resposta (ex: domínio
        # do remetente não verificado, chave de API inválida etc.) — isso
        # ajuda muito a diagnosticar sem precisar adivinhar. Se o bloqueio
        # foi do Cloudflare (antes de chegar no Resend), o corpo vem em
        # HTML longo — corta pra não poluir o log.
        detalhe = erro.read().decode("utf-8", errors="replace")[:500]
        logger.error("Falha ao enviar e-mail (Resend) para %s — HTTP %s: %s",
                     destinatario, erro.code, detalhe)
        return False
    except Exception:
        logger.exception("Falha ao enviar e-mail (Resend) para %s", destinatario)
        return False


def _enviar_via_smtp(destinatario, assunto, corpo_texto):
    msg = MIMEText(corpo_texto, "plain", "utf-8")
    msg["Subject"] = assunto
    # Nome de exibição no remetente (ex: "Painel NM <painelnm@gmail.com>")
    # ajuda o cliente de e-mail do destinatário (e os filtros de spam) a
    # reconhecer quem está enviando, em vez de só mostrar o endereço cru.
    msg["From"] = f"{NOME_SISTEMA} <{SMTP_FROM}>"
    msg["To"] = destinatario

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as servidor:
            if SMTP_USE_TLS:
                servidor.starttls()
            servidor.login(SMTP_USER, SMTP_PASS)
            servidor.sendmail(SMTP_FROM, [destinatario], msg.as_string())
        logger.info("E-mail (SMTP) enviado com sucesso para: %s | Assunto: %s", destinatario, assunto)
        return True
    except Exception:
        logger.exception("Falha ao enviar e-mail (SMTP) para %s", destinatario)
        return False


def enviar_email(destinatario, assunto, corpo_texto):
    """Envia um e-mail simples em texto puro. Retorna True se foi enviado
    (ou simulado em log, quando nada está configurado).

    Ordem de tentativa: SendGrid (API HTTP) -> Resend (API HTTP) -> SMTP -> modo simulado.
    """
    destinatario = (destinatario or "").strip()

    if _sendgrid_configurado():
        return _enviar_via_sendgrid(destinatario, assunto, corpo_texto)

    if _resend_configurado():
        return _enviar_via_resend(destinatario, assunto, corpo_texto)

    if _smtp_configurado():
        return _enviar_via_smtp(destinatario, assunto, corpo_texto)

    # Modo desenvolvimento/local: não derruba o sistema por falta de
    # credenciais de e-mail — só deixa registrado no log do servidor,
    # o que também é útil para depurar durante os testes.
    logger.warning(
        "[E-MAIL SIMULADO — nenhum provedor configurado] Para: %s | Assunto: %s\n%s",
        destinatario, assunto, corpo_texto
    )
    return True


def enviar_codigo_verificacao(destinatario, codigo, finalidade="cadastro"):
    """finalidade: 'cadastro' | 'reset' | 'cadastro_aluno' — só muda o texto."""
    textos = {
        "cadastro": (
            f"Bem-vindo(a) ao {NOME_SISTEMA}!",
            f"Seu código de verificação é: {codigo}\n\n"
            f"Ele é válido por 10 minutos e pode ser usado em até 3 tentativas.\n"
            f"Se você não pediu esse cadastro, pode ignorar este e-mail."
        ),
        "reset": (
            f"Recuperação de senha - {NOME_SISTEMA}",
            f"Seu código para redefinir a senha é: {codigo}\n\n"
            f"Ele é válido por 10 minutos e pode ser usado em até 3 tentativas.\n"
            f"Se você não pediu essa recuperação, pode ignorar este e-mail."
        ),
        "cadastro_aluno": (
            f"Seu acesso ao {NOME_SISTEMA} está pronto!",
            f"Seu personal cadastrou sua ficha no {NOME_SISTEMA}.\n"
            f"Use o código abaixo para criar seu usuário e senha de acesso:\n\n"
            f"Código: {codigo}\n\n"
            f"Ele é válido por 10 minutos e pode ser usado em até 3 tentativas."
        ),
    }
    assunto, corpo = textos.get(finalidade, textos["cadastro"])
    return enviar_email(destinatario, assunto, corpo)


def enviar_notificacao_anamnese_respondida(destinatario, nome_aluno):
    """Avisa o personal por e-mail assim que o aluno termina de responder
    a anamnese enviada para ele preencher em casa."""
    assunto = f"{nome_aluno} respondeu a anamnese - {NOME_SISTEMA}"
    corpo = (
        f"O aluno {nome_aluno} acabou de enviar as respostas da anamnese.\n\n"
        f"Acesse o {NOME_SISTEMA} para conferir as respostas e continuar a avaliação."
    )
    return enviar_email(destinatario, assunto, corpo)


def enviar_notificacao_novo_treino(destinatario, nome_aluno, nome_treino, eh_edicao=False):
    """Avisa o aluno por e-mail assim que o personal finaliza (cria ou edita)
    a ficha de treino dele — dispara automaticamente ao salvar, sem precisar
    de nenhuma ação extra do personal."""
    if eh_edicao:
        assunto = f"Sua ficha de treino foi atualizada - {NOME_SISTEMA}"
        corpo = (
            f"Olá, {nome_aluno}!\n\n"
            f"Seu personal acabou de atualizar a ficha \"{nome_treino}\".\n"
            f"Acesse o {NOME_SISTEMA}, vá em \"Meus Treinos\" e confira as mudanças."
        )
    else:
        assunto = f"Sua nova ficha de treino chegou! - {NOME_SISTEMA}"
        corpo = (
            f"Olá, {nome_aluno}!\n\n"
            f"Seu personal acabou de montar a ficha \"{nome_treino}\" pra você, "
            f"já com os exercícios, séries, repetições e vídeos de demonstração.\n\n"
            f"Acesse o {NOME_SISTEMA}, vá em \"Meus Treinos\" e comece a treinar."
        )
    return enviar_email(destinatario, assunto, corpo)
