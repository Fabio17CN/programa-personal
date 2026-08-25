import re
import secrets
from werkzeug.security import generate_password_hash, check_password_hash
from flask import session


def hash_senha(senha_plana):
    return generate_password_hash(senha_plana)


def conferir_senha(senha_hash, senha_plana):
    return check_password_hash(senha_hash, senha_plana)


def senha_forte_o_suficiente(senha):
    """Regra da especificação de login: mínimo 8 caracteres, com pelo menos
    uma letra maiúscula, uma minúscula e um número."""
    senha = senha or ""
    if len(senha) < 8:
        return False
    if not re.search(r"[A-Z]", senha):
        return False
    if not re.search(r"[a-z]", senha):
        return False
    if not re.search(r"[0-9]", senha):
        return False
    return True


def motivo_senha_fraca(senha):
    """Mensagem específica de qual regra faltou, para mostrar ao usuário."""
    senha = senha or ""
    if len(senha) < 8:
        return "A senha precisa ter no mínimo 8 caracteres."
    if not re.search(r"[A-Z]", senha):
        return "A senha precisa ter pelo menos uma letra maiúscula."
    if not re.search(r"[a-z]", senha):
        return "A senha precisa ter pelo menos uma letra minúscula."
    if not re.search(r"[0-9]", senha):
        return "A senha precisa ter pelo menos um número."
    return "Senha inválida."


EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def email_valido(email):
    return bool(email) and bool(EMAIL_REGEX.match(email.strip()))


def mascarar_email(email):
    """j***@gmail.com — mostra só a primeira letra do usuário do e-mail,
    pra não expor o e-mail completo na tela de recuperação de senha."""
    if not email or "@" not in email:
        return "***"
    usuario, dominio = email.split("@", 1)
    if len(usuario) <= 1:
        return f"{usuario}***@{dominio}"
    return f"{usuario[0]}***@{dominio}"


# ---------- CSRF (token simples por sessão, sem depender de libs externas) ----------

def gerar_csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(24)
    return session["_csrf_token"]


def validar_csrf(token_recebido):
    token_sessao = session.get("_csrf_token")
    return bool(token_sessao) and secrets.compare_digest(token_sessao, token_recebido or "")
