import os
import re
import json
from datetime import datetime, timedelta

# ---------- SQLite (padrão/local) ou PostgreSQL (produção) ----------
# Se a variável de ambiente DATABASE_URL estiver definida (ex.: banco
# Postgres do Render), o sistema usa PostgreSQL — melhor para vários
# acessos simultâneos e muitos alunos. Sem essa variável, continua
# funcionando com SQLite (arquivo local), sem precisar mudar nada.
DATABASE_URL = os.environ.get("DATABASE_URL")
USANDO_POSTGRES = bool(DATABASE_URL)

if USANDO_POSTGRES:
    import psycopg2
    import psycopg2.extras
    # O Render (e a maioria dos provedores) entrega a URL no formato antigo
    # "postgres://" — o driver psycopg2 exige "postgresql://".
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]
    ErroIntegridade = psycopg2.IntegrityError
else:
    import sqlite3
    DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "instance", "app.db"))
    ErroIntegridade = sqlite3.IntegrityError

MAX_TENTATIVAS = 5
BLOQUEIO_MINUTOS = 15


def _traduzir_sql(sql):
    """Deixa o mesmo SQL (escrito com '?' no estilo SQLite) funcionar também
    no PostgreSQL, que usa '%s' — e troca as duas funções específicas do
    SQLite usadas neste arquivo pelos equivalentes do Postgres."""
    if not USANDO_POSTGRES:
        return sql
    sql = sql.replace("?", "%s")
    sql = sql.replace("last_insert_rowid()", "lastval()")
    sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    return sql


class _ConexaoPostgres:
    """Faz uma conexão psycopg2 se comportar o bastante como uma conexão
    sqlite3 (que permite conn.execute(...) direto, sem precisar de cursor
    manual) para que o resto deste arquivo não precise ser reescrito."""

    def __init__(self, bruta):
        self._bruta = bruta

    def execute(self, sql, params=()):
        cur = self._bruta.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(_traduzir_sql(sql), params)
        return cur

    def commit(self):
        self._bruta.commit()

    def rollback(self):
        self._bruta.rollback()

    def close(self):
        self._bruta.close()

    def cursor(self):
        return self._bruta.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


def conectar():
    if USANDO_POSTGRES:
        bruta = psycopg2.connect(DATABASE_URL)
        return _ConexaoPostgres(bruta)
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def criar_tabelas():
    conn = conectar()

    conn.execute("""CREATE TABLE IF NOT EXISTS personals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario TEXT UNIQUE NOT NULL,
        login TEXT,
        senha_hash TEXT NOT NULL,
        nome_exibicao TEXT,
        data_criacao TEXT,
        tentativas_falhas INTEGER DEFAULT 0,
        bloqueado_ate TEXT
    )""")

    conn.execute("""CREATE TABLE IF NOT EXISTS alunos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        personal_id INTEGER NOT NULL,
        nome TEXT NOT NULL,
        cpf TEXT, telefone TEXT, endereco TEXT, numero TEXT,
        cidade TEXT, sexo TEXT, idade INTEGER,
        academia TEXT, objetivo TEXT,
        data_cadastro TEXT,
        FOREIGN KEY(personal_id) REFERENCES personals(id)
    )""")

    conn.execute("""CREATE TABLE IF NOT EXISTS anamneses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        aluno_id INTEGER NOT NULL,
        respostas_json TEXT,
        data TEXT,
        FOREIGN KEY(aluno_id) REFERENCES alunos(id)
    )""")

    # Notificações do personal (ex.: aviso quando o aluno responde a
    # anamnese enviada para ele preencher em casa).
    conn.execute("""CREATE TABLE IF NOT EXISTS notificacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        personal_id INTEGER NOT NULL,
        aluno_id INTEGER,
        tipo TEXT,
        mensagem TEXT,
        lida INTEGER DEFAULT 0,
        data TEXT,
        FOREIGN KEY(personal_id) REFERENCES personals(id)
    )""")

    conn.execute("""CREATE TABLE IF NOT EXISTS avaliacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        aluno_id INTEGER NOT NULL,
        data TEXT,
        peso REAL, altura REAL, imc REAL, bf REAL,
        massa_magra REAL, massa_gorda REAL,
        dobra_peitoral REAL, dobra_abdominal REAL, dobra_coxa REAL,
        dobra_triceps REAL, dobra_suprailiaca REAL, dobra_axilar REAL,
        dobra_subescapular REAL, dobra_bicipital REAL,
        ombro REAL, peito REAL, cintura REAL, abdome REAL, quadril REAL,
        braco_d REAL, braco_e REAL, antebraco_d REAL, antebraco_e REAL,
        coxa_d REAL, coxa_e REAL, panturrilha_d REAL, panturrilha_e REAL,
        observacoes TEXT,
        fez_avaliacao_postural INTEGER DEFAULT 0,
        FOREIGN KEY(aluno_id) REFERENCES alunos(id)
    )""")

    conn.execute("""CREATE TABLE IF NOT EXISTS fotos_postura (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        avaliacao_id INTEGER NOT NULL,
        tipo TEXT,
        caminho_original TEXT,
        caminho_anotado TEXT,
        angulo_ombro REAL,
        angulo_quadril REAL,
        alerta TEXT,
        linhas_manuais_json TEXT,
        diagnostico_json TEXT,
        FOREIGN KEY(avaliacao_id) REFERENCES avaliacoes(id)
    )""")

    conn.execute("""CREATE TABLE IF NOT EXISTS treinos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        aluno_id INTEGER NOT NULL,
        data TEXT,
        nome_treino TEXT,
        exercicios_json TEXT,
        observacoes TEXT,
        FOREIGN KEY(aluno_id) REFERENCES alunos(id)
    )""")

    conn.execute("""CREATE TABLE IF NOT EXISTS agendamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        personal_id INTEGER NOT NULL,
        aluno_id INTEGER,
        titulo TEXT,
        data_hora TEXT NOT NULL,
        duracao_min INTEGER DEFAULT 60,
        observacao TEXT,
        criado_em TEXT,
        FOREIGN KEY(personal_id) REFERENCES personals(id),
        FOREIGN KEY(aluno_id) REFERENCES alunos(id)
    )""")

    conn.execute("""CREATE TABLE IF NOT EXISTS horarios_fixos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        personal_id INTEGER NOT NULL,
        aluno_id INTEGER NOT NULL,
        dia_semana INTEGER NOT NULL,
        hora TEXT NOT NULL,
        duracao_min INTEGER DEFAULT 60,
        ativo INTEGER DEFAULT 1,
        criado_em TEXT,
        FOREIGN KEY(personal_id) REFERENCES personals(id),
        FOREIGN KEY(aluno_id) REFERENCES alunos(id)
    )""")

    # ---------- Módulos novos do Painel NM ----------

    conn.execute("""CREATE TABLE IF NOT EXISTS financeiro (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        personal_id INTEGER NOT NULL,
        aluno_id INTEGER,
        tipo TEXT NOT NULL,
        categoria TEXT,
        descricao TEXT,
        valor REAL NOT NULL,
        data TEXT NOT NULL,
        criado_em TEXT,
        FOREIGN KEY(personal_id) REFERENCES personals(id),
        FOREIGN KEY(aluno_id) REFERENCES alunos(id)
    )""")

    conn.execute("""CREATE TABLE IF NOT EXISTS planos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        personal_id INTEGER NOT NULL,
        nome TEXT NOT NULL,
        descricao TEXT,
        valor REAL,
        duracao_dias INTEGER,
        ativo INTEGER DEFAULT 1,
        criado_em TEXT,
        FOREIGN KEY(personal_id) REFERENCES personals(id)
    )""")

    conn.execute("""CREATE TABLE IF NOT EXISTS aluno_planos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        aluno_id INTEGER NOT NULL,
        plano_id INTEGER NOT NULL,
        data_inicio TEXT,
        ativo INTEGER DEFAULT 1,
        FOREIGN KEY(aluno_id) REFERENCES alunos(id),
        FOREIGN KEY(plano_id) REFERENCES planos(id)
    )""")

    conn.execute("""CREATE TABLE IF NOT EXISTS pagamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        personal_id INTEGER NOT NULL,
        aluno_id INTEGER NOT NULL,
        descricao TEXT,
        valor REAL NOT NULL,
        vencimento TEXT NOT NULL,
        pago_em TEXT,
        status TEXT DEFAULT 'pendente',
        criado_em TEXT,
        FOREIGN KEY(personal_id) REFERENCES personals(id),
        FOREIGN KEY(aluno_id) REFERENCES alunos(id)
    )""")

    conn.execute("""CREATE TABLE IF NOT EXISTS metas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        aluno_id INTEGER NOT NULL,
        personal_id INTEGER NOT NULL,
        titulo TEXT NOT NULL,
        tipo TEXT,
        valor_inicial REAL,
        valor_alvo REAL,
        valor_atual REAL,
        unidade TEXT,
        prazo TEXT,
        status TEXT DEFAULT 'em_andamento',
        criado_em TEXT,
        FOREIGN KEY(aluno_id) REFERENCES alunos(id),
        FOREIGN KEY(personal_id) REFERENCES personals(id)
    )""")

    conn.execute("""CREATE TABLE IF NOT EXISTS anotacoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        personal_id INTEGER NOT NULL,
        aluno_id INTEGER,
        texto TEXT NOT NULL,
        fixada INTEGER DEFAULT 0,
        criado_em TEXT,
        FOREIGN KEY(personal_id) REFERENCES personals(id),
        FOREIGN KEY(aluno_id) REFERENCES alunos(id)
    )""")

    conn.execute("""CREATE TABLE IF NOT EXISTS checkins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        aluno_id INTEGER NOT NULL,
        personal_id INTEGER NOT NULL,
        data_hora TEXT NOT NULL,
        FOREIGN KEY(aluno_id) REFERENCES alunos(id),
        FOREIGN KEY(personal_id) REFERENCES personals(id)
    )""")

    conn.execute("""CREATE TABLE IF NOT EXISTS mensagens_modelo (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        personal_id INTEGER NOT NULL,
        titulo TEXT NOT NULL,
        texto TEXT NOT NULL,
        criado_em TEXT,
        FOREIGN KEY(personal_id) REFERENCES personals(id)
    )""")

    conn.execute("""CREATE TABLE IF NOT EXISTS mensagens_enviadas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        personal_id INTEGER NOT NULL,
        aluno_id INTEGER NOT NULL,
        texto TEXT NOT NULL,
        enviado_em TEXT,
        FOREIGN KEY(personal_id) REFERENCES personals(id),
        FOREIGN KEY(aluno_id) REFERENCES alunos(id)
    )""")

    # Chat real (dentro do app, estilo WhatsApp) entre o personal e cada
    # aluno — cada linha é uma mensagem de uma conversa (par personal+aluno).
    # 'remetente' diz quem escreveu ('personal' ou 'aluno') e 'lida' indica
    # se quem RECEBEU já viu (usado pros badges de não lida).
    conn.execute("""CREATE TABLE IF NOT EXISTS mensagens_chat (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        personal_id INTEGER NOT NULL,
        aluno_id INTEGER NOT NULL,
        remetente TEXT NOT NULL,
        texto TEXT NOT NULL,
        enviado_em TEXT,
        lida INTEGER DEFAULT 0,
        FOREIGN KEY(personal_id) REFERENCES personals(id),
        FOREIGN KEY(aluno_id) REFERENCES alunos(id)
    )""")
    conn.execute("""CREATE INDEX IF NOT EXISTS ix_mensagens_chat_conversa
                     ON mensagens_chat (personal_id, aluno_id, id)""")

    conn.execute("""CREATE TABLE IF NOT EXISTS codigos_verificacao (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        codigo TEXT NOT NULL,
        proposito TEXT NOT NULL,
        referencia_id INTEGER,
        tentativas INTEGER DEFAULT 0,
        usado INTEGER DEFAULT 0,
        criado_em TEXT,
        expira_em TEXT NOT NULL
    )""")

    conn.commit()
    conn.close()
    _migrar_colunas_novas()


def _migrar_colunas_novas():
    """Adiciona colunas novas em bancos já existentes (idempotente)."""
    conn = conectar()
    extras = [
        ("alunos", "regiao", "TEXT"),
        ("alunos", "foto_perfil", "TEXT"),
        ("alunos", "email", "TEXT"),
        ("alunos", "como_conheceu", "TEXT"),
        ("alunos", "indicacao", "TEXT"),
        ("alunos", "observacoes", "TEXT"),
        ("alunos", "status", "TEXT"),
        ("fotos_postura", "diagnostico_json", "TEXT"),
        ("fotos_postura", "angulo_cabeca", "REAL"),
        ("fotos_postura", "desvio_tronco_pct", "REAL"),
        ("fotos_postura", "pontuacao", "INTEGER"),
        ("fotos_postura", "gravidade_geral", "TEXT"),
        ("personals", "slogan", "TEXT"),
        ("personals", "telefone", "TEXT"),
        ("personals", "instagram", "TEXT"),
        ("personals", "logo_path", "TEXT"),
        ("personals", "cref", "TEXT"),
        ("personals", "foto_perfil", "TEXT"),
        ("personals", "mostrar_resultado_auto", "INTEGER"),
        ("personals", "email", "TEXT"),
        ("personals", "email_verificado", "INTEGER"),
        ("personals", "termos_aceitos_em", "TEXT"),
        ("personals", "sessao_versao", "INTEGER"),
        ("alunos", "usuario", "TEXT"),
        ("alunos", "senha_hash", "TEXT"),
        ("alunos", "conta_ativada", "INTEGER"),
        ("alunos", "tentativas_falhas", "INTEGER"),
        ("alunos", "bloqueado_ate", "TEXT"),
        ("alunos", "sessao_versao", "INTEGER"),
        ("alunos", "termos_aceitos_em", "TEXT"),
        ("anamneses", "observacoes", "TEXT"),
        ("fotos_postura", "observacao_profissional", "TEXT"),
        # Fluxo de anamnese enviada para o aluno responder remotamente:
        # status -> 'pendente' (enviada, aluno ainda não abriu/começou),
        #           'em_andamento' (aluno salvou rascunho) ou
        #           'respondida' (aluno enviou, ou o personal preencheu na hora).
        ("anamneses", "status", "TEXT"),
        ("anamneses", "origem", "TEXT"),
        ("anamneses", "data_envio", "TEXT"),
        ("anamneses", "data_resposta", "TEXT"),
        ("anamneses", "notificado_personal", "INTEGER"),
        # Quem deve ver a notificação: 'personal' (padrão, ex.: aluno
        # respondeu a anamnese) ou 'aluno' (ex.: o personal enviou uma
        # anamnese nova para o aluno responder).
        ("notificacoes", "destino", "TEXT DEFAULT 'personal'"),
        # Avaliação física só aparece para o aluno depois que o personal
        # preenche todas as medidas e finaliza explicitamente (evita mostrar
        # um rascunho incompleto no app do aluno).
        ("avaliacoes", "finalizada", "INTEGER"),
        ("avaliacoes", "data_finalizacao", "TEXT"),
        # Chat estilo WhatsApp: mensagens deixam de ser só texto — podem
        # carregar um áudio/vídeo/foto gravado na hora, ou ser um "cartão"
        # automático de relatório de avaliação física (gerado sozinho
        # quando o personal finaliza as medidas do aluno).
        ("mensagens_chat", "tipo", "TEXT DEFAULT 'texto'"),
        ("mensagens_chat", "midia_arquivo", "TEXT"),
        ("mensagens_chat", "midia_duracao", "REAL"),
        ("mensagens_chat", "avaliacao_id", "INTEGER"),
        # "Apagar para todos" (estilo WhatsApp): quando 1, o texto/mídia já
        # foram removidos de verdade e a bolha vira só um aviso "Mensagem
        # apagada" pros dois lados da conversa.
        ("mensagens_chat", "apagada", "INTEGER DEFAULT 0"),
    ]
    for tabela, coluna, tipo in extras:
        if USANDO_POSTGRES:
            # Postgres aceita "IF NOT EXISTS" direto no ADD COLUMN — não
            # precisa de try/except pra rodar de novo sem erro.
            conn.execute(f"ALTER TABLE {tabela} ADD COLUMN IF NOT EXISTS {coluna} {tipo}")
            conn.commit()
        else:
            try:
                conn.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
                conn.commit()
            except sqlite3.OperationalError:
                if hasattr(conn, "rollback"):
                    conn.rollback()
    # Índices únicos "parciais" (ignoram NULL/vazio) para e-mail do personal
    # e usuário do aluno — permitem várias linhas antigas sem esses dados
    # preenchidos, mas impedem duplicidade assim que alguém cadastra.
    try:
        if USANDO_POSTGRES:
            conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS ux_personals_email
                             ON personals (email) WHERE email IS NOT NULL AND email <> ''""")
            conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS ux_alunos_usuario
                             ON alunos (usuario) WHERE usuario IS NOT NULL AND usuario <> ''""")
        else:
            conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS ux_personals_email
                             ON personals (email) WHERE email IS NOT NULL AND email <> ''""")
            conn.execute("""CREATE UNIQUE INDEX IF NOT EXISTS ux_alunos_usuario
                             ON alunos (usuario) WHERE usuario IS NOT NULL AND usuario <> ''""")
        conn.commit()
    except Exception:
        if hasattr(conn, "rollback"):
            conn.rollback()
    conn.close()


# ---------- SEGURANÇA / LOGIN ----------

def criar_personal(usuario, senha_hash, nome_exibicao=None):
    conn = conectar()
    try:
        conn.execute(
            "INSERT INTO personals (usuario, login, senha_hash, nome_exibicao, data_criacao) VALUES (?,?,?,?,?)",
            (usuario, usuario, senha_hash, nome_exibicao or usuario, datetime.now().isoformat())
        )
        conn.commit()
        return True
    except ErroIntegridade:
        conn.rollback()
        return False
    finally:
        conn.close()


# ---------- ID DE ACESSO ÚNICO (personal e aluno) ----------
# Gerado no momento em que a pessoa cria a senha (fim do cadastro do
# personal / ativação de conta do aluno). Usa o próprio id da linha no
# banco (que já é único), então não muda mesmo que nome ou e-mail sejam
# editados depois — evita a confusão de login com nome ou e-mail digitado
# errado. Formato: "PT0001" para personal, "AL0001" para aluno.

def gerar_codigo_acesso(prefixo, id_numerico):
    return f"{prefixo}{id_numerico:04d}"


def _extrair_id_do_codigo_acesso(valor, prefixo):
    valor = (valor or "").strip()
    if not valor:
        return None
    m = re.fullmatch(rf"{prefixo}0*([1-9][0-9]*)", valor, re.IGNORECASE)
    return int(m.group(1)) if m else None


def buscar_personal_por_usuario(valor_login):
    """Login do personal: aceita SOMENTE o código de acesso único
    (ex.: PT0007) ou o e-mail cadastrado — não aceita mais o campo
    "usuario" (que hoje guarda o nome completo digitado no cadastro,
    não um login de verdade).

    O valor digitado é checado nesta ordem:
      1) código de acesso (PT0007) — identifica a linha direto pelo id;
      2) e-mail cadastrado (busca sempre nesse campo, com ou sem "@" —
         mantém compatibilidade caso alguém copie o e-mail sem querer
         cortar algum caractere).
    """
    conn = conectar()
    valor = (valor_login or "").strip()
    row = None

    id_por_codigo = _extrair_id_do_codigo_acesso(valor, "PT")
    if id_por_codigo:
        row = conn.execute("SELECT * FROM personals WHERE id=?", (id_por_codigo,)).fetchone()

    if not row:
        row = conn.execute(
            "SELECT * FROM personals WHERE lower(email)=lower(?)", (valor,)
        ).fetchone()
    conn.close()
    return dict(row) if row else None


def atualizar_perfil_personal(personal_id, nome_exibicao=None, slogan=None, telefone=None,
                               instagram=None, logo_path=None, cref=None,
                               mostrar_resultado_auto=None):
    conn = conectar()
    conn.execute(
        """UPDATE personals SET nome_exibicao=?, slogan=?, telefone=?, instagram=?, cref=?,
           mostrar_resultado_auto=?
           WHERE id=?""",
        (nome_exibicao, slogan, telefone, instagram, cref,
         int(bool(mostrar_resultado_auto)), personal_id)
    )
    if logo_path is not None:
        conn.execute("UPDATE personals SET logo_path=? WHERE id=?", (logo_path, personal_id))
    conn.commit()
    conn.close()


def atualizar_foto_perfil_personal(personal_id, foto_perfil):
    """Salva só o nome do arquivo da foto de perfil (avatar) do personal —
    usada no círculo do topo do painel. Separado de atualizar_perfil_personal
    pra poder salvar sozinho, na hora, assim que a pessoa escolhe a imagem."""
    conn = conectar()
    conn.execute("UPDATE personals SET foto_perfil=? WHERE id=?", (foto_perfil, personal_id))
    conn.commit()
    conn.close()


def buscar_personal_por_id(pid):
    conn = conectar()
    row = conn.execute("SELECT * FROM personals WHERE id=?", (pid,)).fetchone()
    conn.close()
    return dict(row) if row else None


def esta_bloqueado(personal):
    if not personal.get("bloqueado_ate"):
        return False
    return datetime.fromisoformat(personal["bloqueado_ate"]) > datetime.now()


def registrar_falha_login(valor_login):
    """Soma uma tentativa errada ao personal correspondente, buscando pelo
    código de acesso ou pelo e-mail (mesma regra do buscar_personal_por_usuario) —
    são os únicos jeitos de logar como personal agora."""
    conn = conectar()
    valor = (valor_login or "").strip()
    row = None
    id_por_codigo = _extrair_id_do_codigo_acesso(valor, "PT")
    if id_por_codigo:
        row = conn.execute(
            "SELECT id, tentativas_falhas FROM personals WHERE id=?", (id_por_codigo,)
        ).fetchone()
    if not row:
        row = conn.execute(
            "SELECT id, tentativas_falhas FROM personals WHERE lower(email)=lower(?)", (valor,)
        ).fetchone()
    if not row:
        conn.close()
        return
    tentativas = (row["tentativas_falhas"] or 0) + 1
    bloqueado_ate = None
    if tentativas >= MAX_TENTATIVAS:
        bloqueado_ate = (datetime.now() + timedelta(minutes=BLOQUEIO_MINUTOS)).isoformat()
        tentativas = 0
    conn.execute("UPDATE personals SET tentativas_falhas=?, bloqueado_ate=? WHERE id=?",
                 (tentativas, bloqueado_ate, row["id"]))
    conn.commit()
    conn.close()


def limpar_falhas_login(personal_id):
    conn = conectar()
    conn.execute("UPDATE personals SET tentativas_falhas=0, bloqueado_ate=NULL WHERE id=?", (personal_id,))
    conn.commit()
    conn.close()


def atualizar_senha_hash(usuario, novo_hash):
    conn = conectar()
    row = conn.execute("SELECT id FROM personals WHERE usuario=? OR login=?", (usuario, usuario)).fetchone()
    if not row:
        conn.close()
        return False
    # Trocar a senha também invalida qualquer sessão aberta em outro
    # aparelho/navegador: incrementar sessao_versao faz com que o valor
    # guardado no cookie antigo pare de bater com o do banco.
    conn.execute("""UPDATE personals SET senha_hash=?, tentativas_falhas=0, bloqueado_ate=NULL,
                     sessao_versao=COALESCE(sessao_versao,1)+1 WHERE id=?""",
                 (novo_hash, row["id"]))
    conn.commit()
    conn.close()
    return True


# ---------- CADASTRO COM E-MAIL (personal) E CÓDIGOS DE VERIFICAÇÃO ----------

def buscar_personal_por_email(email):
    conn = conectar()
    row = conn.execute("SELECT * FROM personals WHERE lower(email)=lower(?)", (email,)).fetchone()
    conn.close()
    return dict(row) if row else None


def email_existe_personal(email):
    conn = conectar()
    row = conn.execute("SELECT id FROM personals WHERE lower(email)=lower(?)", (email,)).fetchone()
    conn.close()
    return bool(row)


def usuario_existe_personal(usuario):
    conn = conectar()
    row = conn.execute("SELECT id FROM personals WHERE usuario=?", (usuario,)).fetchone()
    conn.close()
    return bool(row)


def usuario_existe_aluno(usuario):
    conn = conectar()
    row = conn.execute("SELECT id FROM alunos WHERE usuario=?", (usuario,)).fetchone()
    conn.close()
    return bool(row)


def criar_codigo_verificacao(email, proposito, referencia_id=None, validade_minutos=10):
    """Gera e grava um código de 6 dígitos para o e-mail/propósito informado.
    Invalida (marca como usado) qualquer código anterior ainda pendente do
    mesmo e-mail/propósito, para que só o mais recente valha."""
    import secrets as _secrets
    codigo = f"{_secrets.randbelow(1000000):06d}"
    agora = datetime.now()
    conn = conectar()
    conn.execute("UPDATE codigos_verificacao SET usado=1 WHERE email=? AND proposito=? AND usado=0",
                 (email, proposito))
    conn.execute(
        """INSERT INTO codigos_verificacao (email, codigo, proposito, referencia_id, tentativas, usado,
           criado_em, expira_em) VALUES (?,?,?,?,0,0,?,?)""",
        (email, codigo, proposito, referencia_id, agora.isoformat(),
         (agora + timedelta(minutes=validade_minutos)).isoformat())
    )
    conn.commit()
    conn.close()
    return codigo


MAX_TENTATIVAS_CODIGO = 3


def validar_codigo_verificacao(email, proposito, codigo_digitado):
    """Confere o código informado. Retorna (ok: bool, motivo: str).
    motivo em caso de erro: 'nao_encontrado' | 'expirado' | 'tentativas' | 'invalido'."""
    conn = conectar()
    row = conn.execute(
        """SELECT * FROM codigos_verificacao WHERE email=? AND proposito=? AND usado=0
           ORDER BY id DESC LIMIT 1""",
        (email, proposito)
    ).fetchone()
    if not row:
        conn.close()
        return False, "nao_encontrado"
    row = dict(row)
    if row["tentativas"] >= MAX_TENTATIVAS_CODIGO:
        conn.close()
        return False, "tentativas"
    if datetime.fromisoformat(row["expira_em"]) < datetime.now():
        conn.close()
        return False, "expirado"
    if (codigo_digitado or "").strip() != row["codigo"]:
        conn.execute("UPDATE codigos_verificacao SET tentativas=tentativas+1 WHERE id=?", (row["id"],))
        conn.commit()
        conn.close()
        return False, "invalido"
    conn.execute("UPDATE codigos_verificacao SET usado=1 WHERE id=?", (row["id"],))
    conn.commit()
    conn.close()
    return True, "ok"


def validar_codigo_verificacao_por_nome(nome, proposito, codigo_digitado):
    """Confere o código de ativação de conta do aluno buscando pelo NOME
    cadastrado na ficha (em vez do e-mail) — usado na tela 'Ativar meu
    acesso'. Como nomes podem se repetir entre fichas, checa todos os
    códigos pendentes de alunos com esse nome e aceita se o dígito bater
    com algum deles. Retorna (ok: bool, motivo: str, aluno_id: int|None)."""
    conn = conectar()
    nome = (nome or "").strip()
    if not nome:
        conn.close()
        return False, "nao_encontrado", None
    alunos_rows = conn.execute(
        "SELECT id FROM alunos WHERE lower(nome)=lower(?)", (nome,)
    ).fetchall()
    if not alunos_rows:
        conn.close()
        return False, "nao_encontrado", None
    aluno_ids = [r["id"] for r in alunos_rows]
    placeholders = ",".join("?" * len(aluno_ids))
    rows = conn.execute(
        f"""SELECT * FROM codigos_verificacao WHERE proposito=? AND usado=0
            AND referencia_id IN ({placeholders}) ORDER BY id DESC""",
        (proposito, *aluno_ids)
    ).fetchall()
    if not rows:
        conn.close()
        return False, "nao_encontrado", None

    agora = datetime.now()
    codigo_digitado = (codigo_digitado or "").strip()
    linha_valida = None
    ativos = []
    algum_expirado = False
    algum_bloqueado = False
    for r in rows:
        r = dict(r)
        if r["tentativas"] >= MAX_TENTATIVAS_CODIGO:
            algum_bloqueado = True
            continue
        if datetime.fromisoformat(r["expira_em"]) < agora:
            algum_expirado = True
            continue
        ativos.append(r)
        if codigo_digitado and codigo_digitado == r["codigo"]:
            linha_valida = r
            break

    if linha_valida:
        conn.execute("UPDATE codigos_verificacao SET usado=1 WHERE id=?", (linha_valida["id"],))
        conn.commit()
        conn.close()
        return True, "ok", linha_valida["referencia_id"]

    # Nenhum código pendente bateu: registra a tentativa em todos os
    # códigos ainda ativos para esse nome (evita força bruta) e devolve
    # o motivo mais relevante.
    for r in ativos:
        conn.execute("UPDATE codigos_verificacao SET tentativas=tentativas+1 WHERE id=?", (r["id"],))
    conn.commit()
    conn.close()
    if ativos:
        return False, "invalido", None
    if algum_bloqueado:
        return False, "tentativas", None
    if algum_expirado:
        return False, "expirado", None
    return False, "nao_encontrado", None


def validar_codigo_verificacao_por_email_aluno(email, codigo_digitado):
    """Confere o código de ativação de conta do aluno pelo E-MAIL cadastrado
    na ficha (tela 'Ativar meu acesso') — o mesmo e-mail usado quando o
    personal enviou o código. Retorna (ok: bool, motivo: str, aluno_id: int|None)."""
    conn = conectar()
    email = (email or "").strip().lower()
    if not email:
        conn.close()
        return False, "nao_encontrado", None
    row = conn.execute(
        """SELECT * FROM codigos_verificacao WHERE lower(email)=? AND proposito='cadastro_aluno'
           AND usado=0 ORDER BY id DESC LIMIT 1""", (email,)
    ).fetchone()
    if not row:
        conn.close()
        return False, "nao_encontrado", None
    row = dict(row)
    if row["tentativas"] >= MAX_TENTATIVAS_CODIGO:
        conn.close()
        return False, "tentativas", None
    if datetime.fromisoformat(row["expira_em"]) < datetime.now():
        conn.close()
        return False, "expirado", None
    if (codigo_digitado or "").strip() != row["codigo"]:
        conn.execute("UPDATE codigos_verificacao SET tentativas=tentativas+1 WHERE id=?", (row["id"],))
        conn.commit()
        conn.close()
        return False, "invalido", None
    conn.execute("UPDATE codigos_verificacao SET usado=1 WHERE id=?", (row["id"],))
    conn.commit()
    aluno_id = row.get("referencia_id")
    conn.close()
    return True, "ok", aluno_id


def criar_personal_com_email(email, usuario, senha_hash, nome_exibicao):
    conn = conectar()
    try:
        conn.execute(
            """INSERT INTO personals (usuario, login, senha_hash, nome_exibicao, data_criacao,
               email, email_verificado, termos_aceitos_em, sessao_versao)
               VALUES (?,?,?,?,?,?,1,?,1)""",
            (usuario, usuario, senha_hash, nome_exibicao or usuario, datetime.now().isoformat(),
             email, datetime.now().isoformat())
        )
        conn.commit()
        return True
    except ErroIntegridade:
        conn.rollback()
        return False
    finally:
        conn.close()


# ---------- LOGIN/SENHA DE ALUNO ----------

def buscar_aluno_por_email(email):
    """Busca um aluno pelo e-mail da ficha, independente de já ter ativado
    a conta ou não — usado no autoatendimento de 'reenviar código de
    acesso' (tanto o aluno pedindo direto quanto o personal reenviando
    pelo perfil dele), pra diferenciar 'e-mail não encontrado' de
    'conta já ativada'."""
    conn = conectar()
    row = conn.execute("SELECT * FROM alunos WHERE lower(email)=lower(?)", ((email or "").strip(),)).fetchone()
    conn.close()
    return dict(row) if row else None


def buscar_aluno_por_usuario_ou_email(usuario_ou_email):
    """Login do aluno: aceita o código de acesso único (ex.: AL0007), o
    e-mail cadastrado (usado como usuário ao ativar a conta) ou o campo
    usuário. Mesma ordem de checagem do login do personal:
      1) código de acesso (AL0007) — identifica a linha direto pelo id;
      2) se contém "@", é tratado como e-mail e buscado só nesse campo;
      3) caso contrário, é tratado como usuário.
    """
    conn = conectar()
    valor = (usuario_ou_email or "").strip()
    row = None

    id_por_codigo = _extrair_id_do_codigo_acesso(valor, "AL")
    if id_por_codigo:
        row = conn.execute("SELECT * FROM alunos WHERE id=?", (id_por_codigo,)).fetchone()

    if not row:
        if "@" in valor:
            row = conn.execute(
                "SELECT * FROM alunos WHERE lower(email)=lower(?)", (valor,)
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM alunos WHERE usuario=?", (valor,)
            ).fetchone()
    conn.close()
    return dict(row) if row else None


def buscar_aluno_por_id_simples(aluno_id):
    conn = conectar()
    row = conn.execute("SELECT * FROM alunos WHERE id=?", (aluno_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def ativar_conta_aluno(aluno_id, usuario, senha_hash):
    conn = conectar()
    try:
        conn.execute(
            """UPDATE alunos SET usuario=?, senha_hash=?, conta_ativada=1, tentativas_falhas=0,
               bloqueado_ate=NULL, sessao_versao=1, termos_aceitos_em=? WHERE id=?""",
            (usuario, senha_hash, datetime.now().isoformat(), aluno_id)
        )
        conn.commit()
        return True
    except ErroIntegridade:
        conn.rollback()
        return False
    finally:
        conn.close()


def esta_bloqueado_generico(registro):
    """Igual a esta_bloqueado, mas serve tanto para dict de personal quanto de aluno."""
    if not registro.get("bloqueado_ate"):
        return False
    return datetime.fromisoformat(registro["bloqueado_ate"]) > datetime.now()


def registrar_falha_login_aluno(aluno_id):
    conn = conectar()
    row = conn.execute("SELECT tentativas_falhas FROM alunos WHERE id=?", (aluno_id,)).fetchone()
    if not row:
        conn.close()
        return
    tentativas = (row["tentativas_falhas"] or 0) + 1
    bloqueado_ate = None
    if tentativas >= MAX_TENTATIVAS:
        bloqueado_ate = (datetime.now() + timedelta(minutes=BLOQUEIO_MINUTOS)).isoformat()
        tentativas = 0
    conn.execute("UPDATE alunos SET tentativas_falhas=?, bloqueado_ate=? WHERE id=?",
                 (tentativas, bloqueado_ate, aluno_id))
    conn.commit()
    conn.close()


def limpar_falhas_login_aluno(aluno_id):
    conn = conectar()
    conn.execute("UPDATE alunos SET tentativas_falhas=0, bloqueado_ate=NULL WHERE id=?", (aluno_id,))
    conn.commit()
    conn.close()


def atualizar_senha_hash_aluno(aluno_id, novo_hash):
    conn = conectar()
    conn.execute("""UPDATE alunos SET senha_hash=?, tentativas_falhas=0, bloqueado_ate=NULL,
                     sessao_versao=COALESCE(sessao_versao,1)+1 WHERE id=?""", (novo_hash, aluno_id))
    conn.commit()
    conn.close()


# ---------- ALUNOS ----------

def criar_aluno(personal_id, dados):
    conn = conectar()
    conn.execute("""INSERT INTO alunos
        (personal_id, nome, telefone, email, cidade, regiao, sexo, idade, academia, objetivo,
         como_conheceu, indicacao, observacoes, status, data_cadastro)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (personal_id, dados.get("nome"), dados.get("telefone"), dados.get("email"),
         dados.get("cidade"), dados.get("regiao"), dados.get("sexo"),
         dados.get("idade") or None, dados.get("academia"), dados.get("objetivo"),
         dados.get("como_conheceu"), dados.get("indicacao"), dados.get("observacoes"),
         "Ativo", datetime.now().isoformat()))
    conn.commit()
    aluno_id = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
    conn.close()
    return aluno_id


def atualizar_aluno(aluno_id, personal_id, dados):
    conn = conectar()
    conn.execute("""UPDATE alunos SET nome=?, telefone=?, email=?, cidade=?, regiao=?, sexo=?,
        idade=?, academia=?, objetivo=?, como_conheceu=?, indicacao=?, observacoes=?
        WHERE id=? AND personal_id=?""",
        (dados.get("nome"), dados.get("telefone"), dados.get("email"),
         dados.get("cidade"), dados.get("regiao"), dados.get("sexo"),
         dados.get("idade") or None, dados.get("academia"), dados.get("objetivo"),
         dados.get("como_conheceu"), dados.get("indicacao"), dados.get("observacoes"),
         aluno_id, personal_id))
    conn.commit()
    conn.close()


def atualizar_status_aluno(aluno_id, personal_id, status):
    conn = conectar()
    conn.execute("UPDATE alunos SET status=? WHERE id=? AND personal_id=?",
                 (status, aluno_id, personal_id))
    conn.commit()
    conn.close()


def listar_alunos(personal_id, termo=None, status=None):
    conn = conectar()
    query = "SELECT * FROM alunos WHERE personal_id=?"
    params = [personal_id]
    if termo:
        query += " AND nome LIKE ?"
        params.append(f"%{termo}%")
    if status and status != "Todos":
        query += " AND COALESCE(status, 'Ativo')=?"
        params.append(status)
    query += " ORDER BY nome"
    rows = conn.execute(query, tuple(params)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def atualizar_foto_perfil(aluno_id, personal_id, caminho):
    conn = conectar()
    conn.execute("UPDATE alunos SET foto_perfil=? WHERE id=? AND personal_id=?",
                 (caminho, aluno_id, personal_id))
    conn.commit()
    conn.close()


def excluir_aluno(aluno_id, personal_id):
    """Remove o aluno e todos os registros ligados a ele (avaliações, fotos, anamneses, treinos, agenda)."""
    conn = conectar()
    dono = conn.execute("SELECT id FROM alunos WHERE id=? AND personal_id=?", (aluno_id, personal_id)).fetchone()
    if not dono:
        conn.close()
        return False
    avaliacao_ids = [r["id"] for r in conn.execute("SELECT id FROM avaliacoes WHERE aluno_id=?", (aluno_id,)).fetchall()]
    for aval_id in avaliacao_ids:
        conn.execute("DELETE FROM fotos_postura WHERE avaliacao_id=?", (aval_id,))
    conn.execute("DELETE FROM avaliacoes WHERE aluno_id=?", (aluno_id,))
    conn.execute("DELETE FROM anamneses WHERE aluno_id=?", (aluno_id,))
    conn.execute("DELETE FROM treinos WHERE aluno_id=?", (aluno_id,))
    conn.execute("DELETE FROM agendamentos WHERE aluno_id=?", (aluno_id,))
    conn.execute("DELETE FROM horarios_fixos WHERE aluno_id=?", (aluno_id,))
    conn.execute("DELETE FROM aluno_planos WHERE aluno_id=?", (aluno_id,))
    conn.execute("DELETE FROM pagamentos WHERE aluno_id=?", (aluno_id,))
    conn.execute("DELETE FROM metas WHERE aluno_id=?", (aluno_id,))
    conn.execute("DELETE FROM anotacoes WHERE aluno_id=?", (aluno_id,))
    conn.execute("DELETE FROM checkins WHERE aluno_id=?", (aluno_id,))
    conn.execute("DELETE FROM mensagens_enviadas WHERE aluno_id=?", (aluno_id,))
    conn.execute("DELETE FROM mensagens_chat WHERE aluno_id=?", (aluno_id,))
    conn.execute("UPDATE financeiro SET aluno_id=NULL WHERE aluno_id=?", (aluno_id,))
    conn.execute("DELETE FROM alunos WHERE id=? AND personal_id=?", (aluno_id, personal_id))
    conn.commit()
    conn.close()
    return True


def excluir_avaliacao(avaliacao_id, aluno_id):
    """Remove uma avaliação específica (e as fotos posturais ligadas a ela), sem mexer no resto do aluno."""
    conn = conectar()
    dono = conn.execute("SELECT id FROM avaliacoes WHERE id=? AND aluno_id=?", (avaliacao_id, aluno_id)).fetchone()
    if not dono:
        conn.close()
        return False
    conn.execute("DELETE FROM fotos_postura WHERE avaliacao_id=?", (avaliacao_id,))
    conn.execute("DELETE FROM avaliacoes WHERE id=? AND aluno_id=?", (avaliacao_id, aluno_id))
    conn.commit()
    conn.close()
    return True


def excluir_treino(treino_id, aluno_id):
    """Remove uma ficha de treino específica, sem mexer no resto do aluno."""
    conn = conectar()
    dono = conn.execute("SELECT id FROM treinos WHERE id=? AND aluno_id=?", (treino_id, aluno_id)).fetchone()
    if not dono:
        conn.close()
        return False
    conn.execute("DELETE FROM treinos WHERE id=? AND aluno_id=?", (treino_id, aluno_id))
    conn.commit()
    conn.close()
    return True


def contar_alunos(personal_id):
    conn = conectar()
    n = conn.execute("SELECT COUNT(*) as n FROM alunos WHERE personal_id=?", (personal_id,)).fetchone()["n"]
    conn.close()
    return n


# ---------- AGENDA (agendamentos de atendimento com o aluno) ----------

def criar_agendamento(personal_id, aluno_id, titulo, data_hora, duracao_min, observacao):
    conn = conectar()
    cur = conn.execute(
        """INSERT INTO agendamentos (personal_id, aluno_id, titulo, data_hora, duracao_min, observacao, criado_em)
           VALUES (?,?,?,?,?,?,?)""",
        (personal_id, aluno_id or None, titulo, data_hora, duracao_min or 60, observacao, datetime.now().isoformat())
    )
    conn.commit()
    novo_id = cur.lastrowid
    conn.close()
    return novo_id


def listar_agendamentos(personal_id, a_partir_de=None):
    """Lista os agendamentos do personal, do mais próximo pro mais distante.
    Se `a_partir_de` (ISO) for passado, só traz os que ainda vão acontecer."""
    conn = conectar()
    if a_partir_de:
        linhas = conn.execute(
            """SELECT ag.*, al.nome AS aluno_nome, al.telefone AS aluno_telefone
               FROM agendamentos ag LEFT JOIN alunos al ON al.id = ag.aluno_id
               WHERE ag.personal_id=? AND ag.data_hora >= ?
               ORDER BY ag.data_hora ASC""",
            (personal_id, a_partir_de)
        ).fetchall()
    else:
        linhas = conn.execute(
            """SELECT ag.*, al.nome AS aluno_nome, al.telefone AS aluno_telefone
               FROM agendamentos ag LEFT JOIN alunos al ON al.id = ag.aluno_id
               WHERE ag.personal_id=?
               ORDER BY ag.data_hora ASC""",
            (personal_id,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in linhas]


def listar_agendamentos_aluno(aluno_id, a_partir_de=None):
    """Agenda vista pelo próprio aluno: só os compromissos dele, do mais
    próximo pro mais distante. Se `a_partir_de` (ISO) for passado, só
    traz os que ainda vão acontecer."""
    conn = conectar()
    if a_partir_de:
        linhas = conn.execute(
            """SELECT * FROM agendamentos WHERE aluno_id=? AND data_hora >= ?
               ORDER BY data_hora ASC""",
            (aluno_id, a_partir_de)
        ).fetchall()
    else:
        linhas = conn.execute(
            "SELECT * FROM agendamentos WHERE aluno_id=? ORDER BY data_hora ASC",
            (aluno_id,)
        ).fetchall()
    conn.close()
    return [dict(r) for r in linhas]


def buscar_agendamento(agendamento_id, personal_id):
    conn = conectar()
    linha = conn.execute("SELECT * FROM agendamentos WHERE id=? AND personal_id=?",
                          (agendamento_id, personal_id)).fetchone()
    conn.close()
    return dict(linha) if linha else None


def excluir_agendamento(agendamento_id, personal_id):
    conn = conectar()
    dono = conn.execute("SELECT id FROM agendamentos WHERE id=? AND personal_id=?",
                         (agendamento_id, personal_id)).fetchone()
    if not dono:
        conn.close()
        return False
    conn.execute("DELETE FROM agendamentos WHERE id=? AND personal_id=?", (agendamento_id, personal_id))
    conn.commit()
    conn.close()
    return True


# ---------- HORÁRIO FIXO SEMANAL (o mesmo aluno, todo dia X, no mesmo horário) ----------

def criar_horario_fixo(personal_id, aluno_id, dia_semana, hora, duracao_min):
    conn = conectar()
    cur = conn.execute(
        """INSERT INTO horarios_fixos (personal_id, aluno_id, dia_semana, hora, duracao_min, ativo, criado_em)
           VALUES (?,?,?,?,?,1,?)""",
        (personal_id, aluno_id, dia_semana, hora, duracao_min or 60, datetime.now().isoformat())
    )
    conn.commit()
    novo_id = cur.lastrowid
    conn.close()
    return novo_id


def listar_horarios_fixos(personal_id):
    """Devolve os horários fixos ativos, já ordenados por dia da semana e hora."""
    conn = conectar()
    linhas = conn.execute(
        """SELECT hf.*, al.nome AS aluno_nome, al.telefone AS aluno_telefone
           FROM horarios_fixos hf JOIN alunos al ON al.id = hf.aluno_id
           WHERE hf.personal_id=? AND hf.ativo=1
           ORDER BY hf.dia_semana ASC, hf.hora ASC""",
        (personal_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in linhas]


def listar_horarios_fixos_aluno(aluno_id):
    """Horários fixos ativos deste aluno, vistos por ele mesmo."""
    conn = conectar()
    linhas = conn.execute(
        """SELECT * FROM horarios_fixos WHERE aluno_id=? AND ativo=1
           ORDER BY dia_semana ASC, hora ASC""",
        (aluno_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in linhas]


def excluir_horario_fixo(horario_id, personal_id):
    conn = conectar()
    dono = conn.execute("SELECT id FROM horarios_fixos WHERE id=? AND personal_id=?",
                         (horario_id, personal_id)).fetchone()
    if not dono:
        conn.close()
        return False
    conn.execute("DELETE FROM horarios_fixos WHERE id=? AND personal_id=?", (horario_id, personal_id))
    conn.commit()
    conn.close()
    return True


def buscar_aluno(aluno_id, personal_id):
    conn = conectar()
    row = conn.execute("SELECT * FROM alunos WHERE id=? AND personal_id=?", (aluno_id, personal_id)).fetchone()
    conn.close()
    return dict(row) if row else None


# ---------- ANAMNESE ----------

def salvar_anamnese(aluno_id, respostas, observacoes="", status="respondida", origem="personal"):
    """Cria uma anamnese já respondida — usado quando o personal preenche
    junto com o aluno, na hora da consulta."""
    conn = conectar()
    agora = datetime.now().isoformat()
    conn.execute(
        """INSERT INTO anamneses
           (aluno_id, respostas_json, data, observacoes, status, origem, data_resposta, notificado_personal)
           VALUES (?,?,?,?,?,?,?,?)""",
        (aluno_id, json.dumps(respostas, ensure_ascii=False), agora, observacoes or "",
         status, origem, agora, 1)
    )
    conn.commit()
    conn.close()


def criar_anamnese_pendente(aluno_id):
    """Cria a anamnese em branco com status 'pendente' e libera o
    questionário no acesso do aluno, para ele preencher remotamente."""
    conn = conectar()
    agora = datetime.now().isoformat()
    conn.execute(
        """INSERT INTO anamneses (aluno_id, respostas_json, data, observacoes, status, origem, data_envio)
           VALUES (?,?,?,?,?,?,?)""",
        (aluno_id, None, agora, "", "pendente", "aluno", agora)
    )
    conn.commit()
    conn.close()


def buscar_ultima_anamnese(aluno_id):
    """Última anamnese já respondida (ignora anamneses pendentes/rascunho
    enviadas para o aluno responder, que ainda não têm respostas)."""
    conn = conectar()
    row = conn.execute(
        """SELECT * FROM anamneses WHERE aluno_id=? AND (status='respondida' OR status IS NULL)
           ORDER BY data DESC LIMIT 1""", (aluno_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def buscar_anamnese_por_id(anamnese_id):
    conn = conectar()
    row = conn.execute("SELECT * FROM anamneses WHERE id=?", (anamnese_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def buscar_anamnese_pendente_aluno(aluno_id):
    """Anamnese ainda não concluída (pendente ou com rascunho salvo)
    esperando o aluno responder."""
    conn = conectar()
    row = conn.execute(
        """SELECT * FROM anamneses WHERE aluno_id=? AND status IN ('pendente','em_andamento')
           ORDER BY data DESC LIMIT 1""", (aluno_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def buscar_ultima_anamnese_respondida(aluno_id):
    """Anamnese mais recente já concluída — usada na tela 'Minha anamnese'
    do próprio aluno, em modo somente leitura."""
    conn = conectar()
    row = conn.execute(
        """SELECT * FROM anamneses WHERE aluno_id=? AND status='respondida'
           ORDER BY COALESCE(data_resposta, data) DESC LIMIT 1""", (aluno_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def salvar_rascunho_anamnese(anamnese_id, respostas):
    conn = conectar()
    conn.execute(
        "UPDATE anamneses SET respostas_json=?, status='em_andamento' WHERE id=?",
        (json.dumps(respostas, ensure_ascii=False), anamnese_id)
    )
    conn.commit()
    conn.close()


def responder_anamnese_aluno(anamnese_id, respostas):
    """O aluno enviou as respostas finais — muda o status para
    'respondida' e marca como não-notificado, para o personal ver o aviso."""
    conn = conectar()
    conn.execute(
        """UPDATE anamneses SET respostas_json=?, status='respondida',
           data_resposta=?, notificado_personal=0 WHERE id=?""",
        (json.dumps(respostas, ensure_ascii=False), datetime.now().isoformat(), anamnese_id)
    )
    conn.commit()
    conn.close()


def obter_anamnese_editavel_aluno(aluno_id):
    """Anamnese que o modal do aluno deve abrir para edição: primeiro uma
    pendente/em andamento (se existir); senão a última respondida (o aluno
    pode corrigir); senão None (formulário em branco)."""
    pendente = buscar_anamnese_pendente_aluno(aluno_id)
    if pendente:
        return pendente
    return buscar_ultima_anamnese_respondida(aluno_id)


def autosalvar_anamnese_aluno(aluno_id, respostas):
    """Salva as respostas automaticamente enquanto o aluno edita no modal,
    sem exigir um clique em 'salvar'. Reaproveita a anamnese pendente/em
    andamento se houver; corrige a última respondida se já existir uma;
    ou cria uma nova (já como rascunho em andamento) se for a primeira vez."""
    conn = conectar()
    agora = datetime.now().isoformat()
    respostas_json = json.dumps(respostas, ensure_ascii=False)

    anamnese = obter_anamnese_editavel_aluno(aluno_id)
    if anamnese:
        conn.execute("UPDATE anamneses SET respostas_json=? WHERE id=?", (respostas_json, anamnese["id"]))
        conn.commit()
        conn.close()
        return anamnese["id"]

    conn.execute(
        """INSERT INTO anamneses (aluno_id, respostas_json, data, observacoes, status, origem, data_envio)
           VALUES (?,?,?,?,?,?,?)""",
        (aluno_id, respostas_json, agora, "", "em_andamento", "aluno", agora)
    )
    conn.commit()
    novo_id = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
    conn.close()
    return novo_id


# ---------- NOTIFICAÇÕES (personal) ----------

def criar_notificacao(personal_id, aluno_id, tipo, mensagem):
    conn = conectar()
    conn.execute(
        "INSERT INTO notificacoes (personal_id, aluno_id, tipo, mensagem, data, destino) VALUES (?,?,?,?,?,?)",
        (personal_id, aluno_id, tipo, mensagem, datetime.now().isoformat(), "personal")
    )
    conn.commit()
    conn.close()


def listar_notificacoes(personal_id, limite=30):
    conn = conectar()
    rows = conn.execute(
        """SELECT * FROM notificacoes WHERE personal_id=?
           AND (destino='personal' OR destino IS NULL) ORDER BY data DESC LIMIT ?""",
        (personal_id, limite)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def contar_notificacoes_nao_lidas(personal_id):
    conn = conectar()
    row = conn.execute(
        """SELECT COUNT(*) AS c FROM notificacoes WHERE personal_id=? AND lida=0
           AND (destino='personal' OR destino IS NULL)""", (personal_id,)
    ).fetchone()
    conn.close()
    return dict(row)["c"] if row else 0


def marcar_notificacoes_lidas(personal_id):
    conn = conectar()
    conn.execute(
        """UPDATE notificacoes SET lida=1 WHERE personal_id=? AND lida=0
           AND (destino='personal' OR destino IS NULL)""", (personal_id,)
    )
    conn.commit()
    conn.close()


def excluir_notificacao_personal(notificacao_id, personal_id):
    """Remove uma notificação do personal — só apaga se ela realmente
    pertencer a ele (evita excluir notificação de outra conta pelo id)."""
    conn = conectar()
    conn.execute(
        """DELETE FROM notificacoes WHERE id=? AND personal_id=?
           AND (destino='personal' OR destino IS NULL)""", (notificacao_id, personal_id)
    )
    conn.commit()
    conn.close()


# ---------- NOTIFICAÇÕES (aluno) ----------
# Mesma tabela, mas com destino='aluno' — usadas para avisar o aluno
# (ex.: o personal enviou uma anamnese nova para ele responder).

def criar_notificacao_aluno(personal_id, aluno_id, tipo, mensagem):
    conn = conectar()
    conn.execute(
        "INSERT INTO notificacoes (personal_id, aluno_id, tipo, mensagem, data, destino) VALUES (?,?,?,?,?,?)",
        (personal_id, aluno_id, tipo, mensagem, datetime.now().isoformat(), "aluno")
    )
    conn.commit()
    conn.close()


def listar_notificacoes_aluno(aluno_id, limite=30):
    conn = conectar()
    rows = conn.execute(
        "SELECT * FROM notificacoes WHERE aluno_id=? AND destino='aluno' ORDER BY data DESC LIMIT ?",
        (aluno_id, limite)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def contar_notificacoes_nao_lidas_aluno(aluno_id):
    conn = conectar()
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM notificacoes WHERE aluno_id=? AND destino='aluno' AND lida=0", (aluno_id,)
    ).fetchone()
    conn.close()
    return dict(row)["c"] if row else 0


def marcar_notificacoes_lidas_aluno(aluno_id):
    conn = conectar()
    conn.execute("UPDATE notificacoes SET lida=1 WHERE aluno_id=? AND destino='aluno' AND lida=0", (aluno_id,))
    conn.commit()
    conn.close()


def excluir_notificacao_aluno(notificacao_id, aluno_id):
    """Remove uma notificação do aluno — só apaga se ela realmente
    pertencer a ele (evita excluir notificação de outra conta pelo id)."""
    conn = conectar()
    conn.execute(
        "DELETE FROM notificacoes WHERE id=? AND aluno_id=? AND destino='aluno'", (notificacao_id, aluno_id)
    )
    conn.commit()
    conn.close()


# ---------- AVALIAÇÕES ----------

CAMPOS_NUMERICOS = [
    "peso", "altura", "imc", "bf", "massa_magra", "massa_gorda",
    "dobra_peitoral", "dobra_abdominal", "dobra_coxa", "dobra_triceps",
    "dobra_suprailiaca", "dobra_axilar", "dobra_subescapular", "dobra_bicipital",
    "ombro", "peito", "cintura", "abdome", "quadril",
    "braco_d", "braco_e", "antebraco_d", "antebraco_e",
    "coxa_d", "coxa_e", "panturrilha_d", "panturrilha_e",
]


def criar_avaliacao(aluno_id, dados, fez_postural=False):
    conn = conectar()
    valores = [dados.get(c) or None for c in CAMPOS_NUMERICOS]
    campos_sql = ", ".join(CAMPOS_NUMERICOS)
    placeholders = ", ".join(["?"] * len(CAMPOS_NUMERICOS))
    # Toda avaliação nasce como rascunho (finalizada=0): o aluno só a vê
    # depois que o personal revisar as medidas e clicar em "Finalizar".
    conn.execute(
        f"INSERT INTO avaliacoes (aluno_id, data, {campos_sql}, observacoes, fez_avaliacao_postural, finalizada) "
        f"VALUES (?, ?, {placeholders}, ?, ?, 0)",
        [aluno_id, datetime.now().isoformat(), *valores, dados.get("observacoes"), int(fez_postural)]
    )
    conn.commit()
    aval_id = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
    conn.close()
    return aval_id


def marcar_avaliacao_postural(avaliacao_id):
    conn = conectar()
    conn.execute("UPDATE avaliacoes SET fez_avaliacao_postural=1 WHERE id=?", (avaliacao_id,))
    conn.commit()
    conn.close()


def excluir_historico_avaliacoes(aluno_id):
    """Remove TODAS as avaliações (e fotos posturais ligadas a elas) de um
    aluno de uma vez só — usado pelo botão 'Apagar histórico' em Minha
    Avaliação."""
    conn = conectar()
    ids = [r["id"] for r in conn.execute("SELECT id FROM avaliacoes WHERE aluno_id=?", (aluno_id,)).fetchall()]
    for aval_id in ids:
        conn.execute("DELETE FROM fotos_postura WHERE avaliacao_id=?", (aval_id,))
    conn.execute("DELETE FROM avaliacoes WHERE aluno_id=?", (aluno_id,))
    conn.commit()
    conn.close()
    return len(ids)


def finalizar_avaliacao(avaliacao_id, aluno_id):
    """Libera a avaliação para o aluno ver no app dele. Só o personal aciona,
    depois de conferir que todas as medidas foram preenchidas corretamente."""
    conn = conectar()
    conn.execute(
        "UPDATE avaliacoes SET finalizada=1, data_finalizacao=? WHERE id=? AND aluno_id=?",
        (datetime.now().isoformat(), avaliacao_id, aluno_id)
    )
    conn.commit()
    conn.close()


def listar_avaliacoes(aluno_id, apenas_finalizadas=False):
    conn = conectar()
    if apenas_finalizadas:
        rows = conn.execute(
            "SELECT * FROM avaliacoes WHERE aluno_id=? AND finalizada=1 ORDER BY data", (aluno_id,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM avaliacoes WHERE aluno_id=? ORDER BY data", (aluno_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def buscar_avaliacao(avaliacao_id):
    conn = conectar()
    row = conn.execute("SELECT * FROM avaliacoes WHERE id=?", (avaliacao_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def salvar_foto_postura(avaliacao_id, tipo, caminho_original, caminho_anotado=None,
                         angulo_ombro=None, angulo_quadril=None, alerta=None, linhas_manuais=None):
    """
    Salva a foto postural de um tipo (frontal/lateral/costas) para a avaliação.
    Se já existir uma foto desse mesmo tipo nessa avaliação, ela é substituída
    (removida do banco) — sem isso, tirar uma foto nova do mesmo ângulo ficava
    se somando à antiga, e as duas apareciam juntas no PDF.
    Devolve a lista de caminhos de arquivo das fotos antigas removidas, pra
    quem chamou também poder apagar os arquivos do disco.
    """
    conn = conectar()
    antigas = conn.execute(
        "SELECT caminho_original, caminho_anotado FROM fotos_postura WHERE avaliacao_id=? AND tipo=?",
        (avaliacao_id, tipo)
    ).fetchall()
    caminhos_antigos = []
    for row in antigas:
        if row["caminho_original"]:
            caminhos_antigos.append(row["caminho_original"])
        if row["caminho_anotado"]:
            caminhos_antigos.append(row["caminho_anotado"])
    conn.execute("DELETE FROM fotos_postura WHERE avaliacao_id=? AND tipo=?", (avaliacao_id, tipo))

    conn.execute("""INSERT INTO fotos_postura
        (avaliacao_id, tipo, caminho_original, caminho_anotado, angulo_ombro, angulo_quadril, alerta, linhas_manuais_json)
        VALUES (?,?,?,?,?,?,?,?)""",
        (avaliacao_id, tipo, caminho_original, caminho_anotado, angulo_ombro, angulo_quadril,
         alerta, json.dumps(linhas_manuais, ensure_ascii=False) if linhas_manuais else None))
    conn.commit()
    conn.close()
    return caminhos_antigos


def excluir_foto_postura(foto_id, avaliacao_id):
    """Remove uma foto postural específica (usado pelo botão 'remover' na tela de postura).
    Devolve os caminhos de arquivo pra quem chamou apagar do disco, ou None se não achou."""
    conn = conectar()
    foto = conn.execute("SELECT * FROM fotos_postura WHERE id=? AND avaliacao_id=?",
                         (foto_id, avaliacao_id)).fetchone()
    if not foto:
        conn.close()
        return None
    caminhos = [c for c in [foto["caminho_original"], foto["caminho_anotado"]] if c]
    conn.execute("DELETE FROM fotos_postura WHERE id=?", (foto_id,))
    conn.commit()
    conn.close()
    return caminhos


def listar_fotos(avaliacao_id):
    conn = conectar()
    rows = conn.execute("SELECT * FROM fotos_postura WHERE avaliacao_id=? ORDER BY id", (avaliacao_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def buscar_fotos_recentes_aluno(aluno_id):
    """
    Devolve as fotos posturais da avaliação MAIS RECENTE do aluno que tenha
    fotos — não necessariamente a última avaliação de medidas. Isso evita que
    a foto "suma" do relatório quando uma reavaliação de medidas é feita
    depois da avaliação postural, sem fotos novas.
    """
    conn = conectar()
    rows = conn.execute("""
        SELECT f.* FROM fotos_postura f
        JOIN avaliacoes a ON a.id = f.avaliacao_id
        WHERE a.aluno_id = ?
        ORDER BY a.data DESC, f.id ASC
    """, (aluno_id,)).fetchall()
    conn.close()
    if not rows:
        return []
    avaliacao_id_alvo = rows[0]["avaliacao_id"]
    return [dict(r) for r in rows if r["avaliacao_id"] == avaliacao_id_alvo]


def buscar_foto(foto_id):
    conn = conectar()
    row = conn.execute("SELECT * FROM fotos_postura WHERE id=?", (foto_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def atualizar_foto_anotada(foto_id, caminho_anotado, linhas_manuais=None):
    conn = conectar()
    conn.execute("UPDATE fotos_postura SET caminho_anotado=?, linhas_manuais_json=? WHERE id=?",
                 (caminho_anotado, json.dumps(linhas_manuais, ensure_ascii=False) if linhas_manuais else None, foto_id))
    conn.commit()
    conn.close()


def atualizar_diagnostico_foto(foto_id, diagnostico):
    conn = conectar()
    conn.execute("UPDATE fotos_postura SET diagnostico_json=? WHERE id=?",
                 (json.dumps(diagnostico, ensure_ascii=False) if diagnostico else None, foto_id))
    conn.commit()
    conn.close()


def salvar_observacao_foto(foto_id, avaliacao_id, observacao):
    """Observação escrita manualmente pelo profissional sobre a postura do
    aluno naquela vista (ex.: suspeita de escoliose, ombro mais alto,
    perna aparentemente maior etc.) — vai para o PDF da avaliação."""
    conn = conectar()
    cur = conn.execute(
        "UPDATE fotos_postura SET observacao_profissional=? WHERE id=? AND avaliacao_id=?",
        (observacao or "", foto_id, avaliacao_id)
    )
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


# ---------- TREINOS ----------

DIAS_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]


def criar_treino(aluno_id, nome_treino, exercicios_json, observacoes=""):
    """
    `exercicios_json` guarda a ficha inteira da semana, no formato:
    [{"letra": "A", "dia_semana": "Segunda", "exercicios": [{"nome","series","reps","obs"}, ...]}, ...]
    (mantém compatibilidade: se vier uma lista simples de exercícios, o gerador de PDF
    trata isso como um único dia "A" — fichas antigas continuam funcionando.)
    """
    conn = conectar()
    conn.execute("INSERT INTO treinos (aluno_id, data, nome_treino, exercicios_json, observacoes) VALUES (?,?,?,?,?)",
                 (aluno_id, datetime.now().isoformat(), nome_treino, exercicios_json, observacoes))
    conn.commit()
    tid = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
    conn.close()
    return tid


def listar_treinos(aluno_id):
    conn = conectar()
    rows = conn.execute("SELECT * FROM treinos WHERE aluno_id=? ORDER BY data DESC", (aluno_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def buscar_treino(treino_id):
    conn = conectar()
    row = conn.execute("SELECT * FROM treinos WHERE id=?", (treino_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def atualizar_treino(treino_id, aluno_id, nome_treino, exercicios_json, observacoes=""):
    """Edita uma ficha de treino já existente (em vez de criar uma nova) — usado
    quando o personal quer só trocar/ajustar algum exercício da ficha atual."""
    conn = conectar()
    dono = conn.execute("SELECT id FROM treinos WHERE id=? AND aluno_id=?", (treino_id, aluno_id)).fetchone()
    if not dono:
        conn.close()
        return False
    conn.execute(
        "UPDATE treinos SET nome_treino=?, exercicios_json=?, observacoes=? WHERE id=? AND aluno_id=?",
        (nome_treino, exercicios_json, observacoes, treino_id, aluno_id)
    )
    conn.commit()
    conn.close()
    return True





# ---------- LISTAGENS GLOBAIS (todos os alunos do personal, pro Painel) ----------

def contagem_treinos_por_aluno(personal_id):
    """Resumo (por aluno) das fichas de treino já montadas: quantas tem e qual
    é a mais recente — usado na tela 'Montar Treino' pra deixar claro quem já
    tem ficha (com atalho direto pra editar a atual) e quem ainda não tem
    nenhuma, em vez de sempre mandar criar uma ficha do zero."""
    conn = conectar()
    rows = conn.execute("""
        SELECT t.aluno_id, t.id, t.nome_treino, t.data
        FROM treinos t
        JOIN alunos a ON a.id = t.aluno_id
        WHERE a.personal_id = ?
        ORDER BY t.data DESC
    """, (personal_id,)).fetchall()
    conn.close()
    resumo = {}
    for r in rows:
        aid = r["aluno_id"]
        if aid not in resumo:
            resumo[aid] = {"total": 0, "ultimo_id": r["id"], "ultimo_nome": r["nome_treino"], "ultima_data": r["data"]}
        resumo[aid]["total"] += 1
    return resumo


def listar_treinos_do_personal(personal_id, limite=60):
    """Todas as fichas de treino de todos os alunos do personal, mais recentes primeiro
    — usado na tela 'Treinos Registrados' do painel."""
    conn = conectar()
    rows = conn.execute("""
        SELECT t.*, a.nome as aluno_nome FROM treinos t
        JOIN alunos a ON a.id = t.aluno_id
        WHERE a.personal_id = ?
        ORDER BY t.data DESC
        LIMIT ?
    """, (personal_id, limite)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def contar_treinos_do_personal(personal_id):
    conn = conectar()
    n = conn.execute("""
        SELECT COUNT(*) as n FROM treinos t JOIN alunos a ON a.id = t.aluno_id
        WHERE a.personal_id = ?
    """, (personal_id,)).fetchone()["n"]
    conn.close()
    return n


def listar_avaliacoes_do_personal(personal_id, limite=60):
    """Todas as avaliações físicas de todos os alunos, mais recentes primeiro
    — usado na tela 'Avaliações Físicas' do painel."""
    conn = conectar()
    rows = conn.execute("""
        SELECT av.*, a.nome as aluno_nome FROM avaliacoes av
        JOIN alunos a ON a.id = av.aluno_id
        WHERE a.personal_id = ?
        ORDER BY av.data DESC
        LIMIT ?
    """, (personal_id, limite)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------- ESTATÍSTICAS DO PAINEL ----------

def estatisticas_cadastro_mes(personal_id):
    """Quantos alunos novos entraram este mês e o crescimento percentual em
    relação à base de alunos que já existia antes do mês começar."""
    conn = conectar()
    inicio_mes = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    total = conn.execute("SELECT COUNT(*) as n FROM alunos WHERE personal_id=?", (personal_id,)).fetchone()["n"]
    novos_mes = conn.execute(
        "SELECT COUNT(*) as n FROM alunos WHERE personal_id=? AND data_cadastro >= ?",
        (personal_id, inicio_mes)
    ).fetchone()["n"]
    conn.close()
    base_anterior = total - novos_mes
    if base_anterior > 0:
        pct = round((novos_mes / base_anterior) * 100)
    else:
        pct = 100 if novos_mes > 0 else 0
    return {"novos_mes": novos_mes, "pct": pct}


def contar_novos_alunos_hoje(personal_id):
    conn = conectar()
    hoje = datetime.now().date().isoformat()
    n = conn.execute(
        "SELECT COUNT(*) as n FROM alunos WHERE personal_id=? AND data_cadastro LIKE ?",
        (personal_id, f"{hoje}%")
    ).fetchone()["n"]
    conn.close()
    return n


def contar_atendimentos_hoje(personal_id):
    """Atendimentos avulsos marcados pra hoje + horários fixos semanais que caem
    no dia da semana de hoje."""
    conn = conectar()
    hoje = datetime.now().date().isoformat()
    avulsos = conn.execute(
        "SELECT COUNT(*) as n FROM agendamentos WHERE personal_id=? AND data_hora LIKE ?",
        (personal_id, f"{hoje}%")
    ).fetchone()["n"]
    dia_semana_hoje = datetime.now().weekday()
    fixos = conn.execute(
        "SELECT COUNT(*) as n FROM horarios_fixos WHERE personal_id=? AND dia_semana=? AND ativo=1",
        (personal_id, dia_semana_hoje)
    ).fetchone()["n"]
    conn.close()
    return avulsos + fixos


# ---------- FINANCEIRO ----------

def criar_lancamento_financeiro(personal_id, tipo, categoria, descricao, valor, data, aluno_id=None):
    conn = conectar()
    conn.execute("""INSERT INTO financeiro (personal_id, aluno_id, tipo, categoria, descricao, valor, data, criado_em)
        VALUES (?,?,?,?,?,?,?,?)""",
        (personal_id, aluno_id, tipo, categoria, descricao, valor, data, datetime.now().isoformat()))
    conn.commit()
    lid = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
    conn.close()
    return lid


def listar_financeiro(personal_id, tipo=None, limite=200):
    conn = conectar()
    if tipo:
        rows = conn.execute(
            "SELECT * FROM financeiro WHERE personal_id=? AND tipo=? ORDER BY data DESC, id DESC LIMIT ?",
            (personal_id, tipo, limite)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM financeiro WHERE personal_id=? ORDER BY data DESC, id DESC LIMIT ?",
            (personal_id, limite)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def excluir_lancamento_financeiro(lancamento_id, personal_id):
    conn = conectar()
    cur = conn.execute("DELETE FROM financeiro WHERE id=? AND personal_id=?", (lancamento_id, personal_id))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


def resumo_financeiro_mes(personal_id):
    conn = conectar()
    inicio_mes = datetime.now().replace(day=1).date().isoformat()
    rows = conn.execute(
        "SELECT tipo, valor FROM financeiro WHERE personal_id=? AND data >= ?",
        (personal_id, inicio_mes)
    ).fetchall()
    conn.close()
    receitas = sum(r["valor"] for r in rows if r["tipo"] == "receita")
    despesas = sum(r["valor"] for r in rows if r["tipo"] == "despesa")
    return {"receitas": receitas, "despesas": despesas, "saldo": receitas - despesas}


def somar_receitas_hoje(personal_id):
    conn = conectar()
    hoje = datetime.now().date().isoformat()
    row = conn.execute(
        "SELECT COALESCE(SUM(valor),0) as total FROM financeiro WHERE personal_id=? AND tipo='receita' AND data=?",
        (personal_id, hoje)
    ).fetchone()
    conn.close()
    return row["total"] or 0


# ---------- PLANOS PERSONALIZADOS ----------

def criar_plano(personal_id, nome, descricao, valor, duracao_dias):
    conn = conectar()
    conn.execute("""INSERT INTO planos (personal_id, nome, descricao, valor, duracao_dias, ativo, criado_em)
        VALUES (?,?,?,?,?,1,?)""",
        (personal_id, nome, descricao, valor, duracao_dias, datetime.now().isoformat()))
    conn.commit()
    pid = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
    conn.close()
    return pid


def listar_planos(personal_id):
    conn = conectar()
    rows = conn.execute(
        "SELECT * FROM planos WHERE personal_id=? ORDER BY ativo DESC, valor", (personal_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def buscar_plano(plano_id, personal_id):
    conn = conectar()
    row = conn.execute("SELECT * FROM planos WHERE id=? AND personal_id=?", (plano_id, personal_id)).fetchone()
    conn.close()
    return dict(row) if row else None


def alternar_plano_ativo(plano_id, personal_id):
    conn = conectar()
    atual = conn.execute("SELECT ativo FROM planos WHERE id=? AND personal_id=?", (plano_id, personal_id)).fetchone()
    if not atual:
        conn.close()
        return False
    novo = 0 if atual["ativo"] else 1
    conn.execute("UPDATE planos SET ativo=? WHERE id=? AND personal_id=?", (novo, plano_id, personal_id))
    conn.commit()
    conn.close()
    return True


def excluir_plano(plano_id, personal_id):
    conn = conectar()
    conn.execute("DELETE FROM aluno_planos WHERE plano_id=?", (plano_id,))
    cur = conn.execute("DELETE FROM planos WHERE id=? AND personal_id=?", (plano_id, personal_id))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


def vincular_plano_aluno(aluno_id, plano_id):
    """Contrata um plano pro aluno — desativa qualquer plano anterior dele antes
    (um aluno tem só um plano ativo por vez)."""
    conn = conectar()
    conn.execute("UPDATE aluno_planos SET ativo=0 WHERE aluno_id=?", (aluno_id,))
    conn.execute(
        "INSERT INTO aluno_planos (aluno_id, plano_id, data_inicio, ativo) VALUES (?,?,?,1)",
        (aluno_id, plano_id, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()


def buscar_plano_ativo_aluno(aluno_id):
    conn = conectar()
    row = conn.execute("""
        SELECT p.* FROM aluno_planos ap JOIN planos p ON p.id = ap.plano_id
        WHERE ap.aluno_id=? AND ap.ativo=1 ORDER BY ap.id DESC LIMIT 1
    """, (aluno_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def contar_alunos_por_plano(personal_id):
    conn = conectar()
    rows = conn.execute("""
        SELECT p.id, COUNT(ap.id) as n FROM planos p
        LEFT JOIN aluno_planos ap ON ap.plano_id = p.id AND ap.ativo = 1
        WHERE p.personal_id = ? GROUP BY p.id
    """, (personal_id,)).fetchall()
    conn.close()
    return {r["id"]: r["n"] for r in rows}


# ---------- CONTROLE DE PAGAMENTOS (mensalidades) ----------

def criar_pagamento(personal_id, aluno_id, descricao, valor, vencimento):
    conn = conectar()
    conn.execute("""INSERT INTO pagamentos (personal_id, aluno_id, descricao, valor, vencimento, status, criado_em)
        VALUES (?,?,?,?,?,'pendente',?)""",
        (personal_id, aluno_id, descricao, valor, vencimento, datetime.now().isoformat()))
    conn.commit()
    pid = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
    conn.close()
    return pid


def listar_pagamentos(personal_id, status=None):
    """Lista os pagamentos já com o status atualizado (pendente vira 'atrasado'
    sozinho quando o vencimento já passou), do mais próximo de vencer pro mais distante."""
    conn = conectar()
    hoje = datetime.now().date().isoformat()
    conn.execute(
        "UPDATE pagamentos SET status='atrasado' WHERE personal_id=? AND status='pendente' AND vencimento < ?",
        (personal_id, hoje)
    )
    conn.commit()
    if status:
        rows = conn.execute("""
            SELECT pg.*, a.nome as aluno_nome FROM pagamentos pg JOIN alunos a ON a.id = pg.aluno_id
            WHERE pg.personal_id=? AND pg.status=? ORDER BY pg.vencimento
        """, (personal_id, status)).fetchall()
    else:
        rows = conn.execute("""
            SELECT pg.*, a.nome as aluno_nome FROM pagamentos pg JOIN alunos a ON a.id = pg.aluno_id
            WHERE pg.personal_id=? ORDER BY pg.vencimento
        """, (personal_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def marcar_pagamento_pago(pagamento_id, personal_id):
    """Marca como pago e já lança automaticamente a receita correspondente no
    Financeiro, pra não precisar registrar a mesma mensalidade duas vezes."""
    conn = conectar()
    pagamento = conn.execute(
        "SELECT * FROM pagamentos WHERE id=? AND personal_id=?", (pagamento_id, personal_id)
    ).fetchone()
    if not pagamento:
        conn.close()
        return False
    agora = datetime.now()
    conn.execute("UPDATE pagamentos SET status='pago', pago_em=? WHERE id=?", (agora.isoformat(), pagamento_id))
    conn.execute("""INSERT INTO financeiro (personal_id, aluno_id, tipo, categoria, descricao, valor, data, criado_em)
        VALUES (?,?,?,?,?,?,?,?)""",
        (personal_id, pagamento["aluno_id"], "receita", "Mensalidade",
         pagamento["descricao"] or "Mensalidade", pagamento["valor"], agora.date().isoformat(), agora.isoformat()))
    conn.commit()
    conn.close()
    return True


def excluir_pagamento(pagamento_id, personal_id):
    conn = conectar()
    cur = conn.execute("DELETE FROM pagamentos WHERE id=? AND personal_id=?", (pagamento_id, personal_id))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


def contar_pagamentos_pendentes(personal_id):
    conn = conectar()
    hoje = datetime.now().date().isoformat()
    conn.execute(
        "UPDATE pagamentos SET status='atrasado' WHERE personal_id=? AND status='pendente' AND vencimento < ?",
        (personal_id, hoje)
    )
    conn.commit()
    n = conn.execute(
        "SELECT COUNT(*) as n FROM pagamentos WHERE personal_id=? AND status IN ('pendente','atrasado')",
        (personal_id,)
    ).fetchone()["n"]
    conn.close()
    return n


# ---------- METAS DOS ALUNOS ----------

def criar_meta(aluno_id, personal_id, titulo, tipo, valor_inicial, valor_alvo, valor_atual, unidade, prazo):
    conn = conectar()
    conn.execute("""INSERT INTO metas
        (aluno_id, personal_id, titulo, tipo, valor_inicial, valor_alvo, valor_atual, unidade, prazo, status, criado_em)
        VALUES (?,?,?,?,?,?,?,?,?,'em_andamento',?)""",
        (aluno_id, personal_id, titulo, tipo, valor_inicial, valor_alvo, valor_atual, unidade, prazo,
         datetime.now().isoformat()))
    conn.commit()
    mid = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
    conn.close()
    return mid


def listar_metas(personal_id, aluno_id=None, apenas_ativas=False):
    conn = conectar()
    sql = """SELECT m.*, a.nome as aluno_nome FROM metas m JOIN alunos a ON a.id = m.aluno_id WHERE m.personal_id=?"""
    params = [personal_id]
    if aluno_id:
        sql += " AND m.aluno_id=?"
        params.append(aluno_id)
    if apenas_ativas:
        sql += " AND m.status='em_andamento'"
    sql += " ORDER BY (m.status='em_andamento') DESC, m.criado_em DESC"
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def atualizar_progresso_meta(meta_id, personal_id, valor_atual):
    conn = conectar()
    meta = conn.execute("SELECT * FROM metas WHERE id=? AND personal_id=?", (meta_id, personal_id)).fetchone()
    if not meta:
        conn.close()
        return False
    status = meta["status"]
    if meta["valor_alvo"] is not None and meta["valor_inicial"] is not None:
        # Meta de redução (ex: perder peso/gordura) conclui quando o valor cai até o alvo;
        # meta de ganho (ex: aumentar carga/massa) conclui quando o valor sobe até o alvo.
        if meta["valor_alvo"] <= meta["valor_inicial"]:
            status = "concluida" if valor_atual <= meta["valor_alvo"] else "em_andamento"
        else:
            status = "concluida" if valor_atual >= meta["valor_alvo"] else "em_andamento"
    conn.execute("UPDATE metas SET valor_atual=?, status=? WHERE id=?", (valor_atual, status, meta_id))
    conn.commit()
    conn.close()
    return True


def atualizar_status_meta(meta_id, personal_id, status):
    conn = conectar()
    cur = conn.execute("UPDATE metas SET status=? WHERE id=? AND personal_id=?", (status, meta_id, personal_id))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


def excluir_meta(meta_id, personal_id):
    conn = conectar()
    cur = conn.execute("DELETE FROM metas WHERE id=? AND personal_id=?", (meta_id, personal_id))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


# ---------- ANOTAÇÕES RÁPIDAS ----------

def criar_anotacao(personal_id, aluno_id, texto):
    conn = conectar()
    conn.execute("INSERT INTO anotacoes (personal_id, aluno_id, texto, fixada, criado_em) VALUES (?,?,?,0,?)",
                 (personal_id, aluno_id, texto, datetime.now().isoformat()))
    conn.commit()
    nid = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
    conn.close()
    return nid


def listar_anotacoes(personal_id, aluno_id=None):
    conn = conectar()
    if aluno_id:
        rows = conn.execute("""
            SELECT n.*, a.nome as aluno_nome FROM anotacoes n LEFT JOIN alunos a ON a.id = n.aluno_id
            WHERE n.personal_id=? AND n.aluno_id=? ORDER BY n.fixada DESC, n.criado_em DESC
        """, (personal_id, aluno_id)).fetchall()
    else:
        rows = conn.execute("""
            SELECT n.*, a.nome as aluno_nome FROM anotacoes n LEFT JOIN alunos a ON a.id = n.aluno_id
            WHERE n.personal_id=? ORDER BY n.fixada DESC, n.criado_em DESC
        """, (personal_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def alternar_fixar_anotacao(anotacao_id, personal_id):
    conn = conectar()
    atual = conn.execute("SELECT fixada FROM anotacoes WHERE id=? AND personal_id=?", (anotacao_id, personal_id)).fetchone()
    if not atual:
        conn.close()
        return False
    novo = 0 if atual["fixada"] else 1
    conn.execute("UPDATE anotacoes SET fixada=? WHERE id=?", (novo, anotacao_id))
    conn.commit()
    conn.close()
    return True


def excluir_anotacao(anotacao_id, personal_id):
    conn = conectar()
    cur = conn.execute("DELETE FROM anotacoes WHERE id=? AND personal_id=?", (anotacao_id, personal_id))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


# ---------- CHECK-IN DE ALUNOS (presença) ----------

def registrar_checkin(aluno_id, personal_id):
    conn = conectar()
    conn.execute("INSERT INTO checkins (aluno_id, personal_id, data_hora) VALUES (?,?,?)",
                 (aluno_id, personal_id, datetime.now().isoformat()))
    conn.commit()
    cid = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
    conn.close()
    return cid


def aluno_ja_fez_checkin_hoje(aluno_id):
    conn = conectar()
    hoje = datetime.now().date().isoformat()
    row = conn.execute(
        "SELECT id FROM checkins WHERE aluno_id=? AND data_hora LIKE ? ORDER BY id DESC LIMIT 1",
        (aluno_id, f"{hoje}%")
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def listar_checkins_hoje(personal_id):
    conn = conectar()
    hoje = datetime.now().date().isoformat()
    rows = conn.execute("""
        SELECT c.*, a.nome as aluno_nome FROM checkins c JOIN alunos a ON a.id = c.aluno_id
        WHERE c.personal_id=? AND c.data_hora LIKE ? ORDER BY c.data_hora DESC
    """, (personal_id, f"{hoje}%")).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def contar_checkins_hoje(personal_id):
    conn = conectar()
    hoje = datetime.now().date().isoformat()
    n = conn.execute(
        "SELECT COUNT(*) as n FROM checkins WHERE personal_id=? AND data_hora LIKE ?",
        (personal_id, f"{hoje}%")
    ).fetchone()["n"]
    conn.close()
    return n


def excluir_checkin(checkin_id, personal_id):
    conn = conectar()
    cur = conn.execute("DELETE FROM checkins WHERE id=? AND personal_id=?", (checkin_id, personal_id))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


# ---------- MENSAGENS ----------

def registrar_mensagem_enviada(personal_id, aluno_id, texto):
    conn = conectar()
    conn.execute("INSERT INTO mensagens_enviadas (personal_id, aluno_id, texto, enviado_em) VALUES (?,?,?,?)",
                 (personal_id, aluno_id, texto, datetime.now().isoformat()))
    conn.commit()
    mid = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
    conn.close()
    return mid


def listar_mensagens_enviadas(personal_id, limite=40):
    conn = conectar()
    rows = conn.execute("""
        SELECT me.*, a.nome as aluno_nome FROM mensagens_enviadas me JOIN alunos a ON a.id = me.aluno_id
        WHERE me.personal_id=? ORDER BY me.enviado_em DESC LIMIT ?
    """, (personal_id, limite)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def listar_mensagens_aluno(aluno_id, limite=40):
    """Mensagens que o personal enviou para este aluno (visão do próprio
    aluno, mais recente primeiro)."""
    conn = conectar()
    rows = conn.execute(
        "SELECT * FROM mensagens_enviadas WHERE aluno_id=? ORDER BY enviado_em DESC LIMIT ?",
        (aluno_id, limite)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------- CHAT (conversa real dentro do app, estilo WhatsApp) ----------

def enviar_mensagem_chat(personal_id, aluno_id, remetente, texto, tipo="texto",
                          midia_arquivo=None, midia_duracao=None, avaliacao_id=None):
    """Grava uma mensagem do chat. 'remetente' é 'personal' ou 'aluno'.
    'tipo' é 'texto', 'audio', 'video', 'imagem' ou 'relatorio_avaliacao'
    (cartão automático enviado quando o personal finaliza uma avaliação)."""
    conn = conectar()
    conn.execute(
        """INSERT INTO mensagens_chat
           (personal_id, aluno_id, remetente, texto, enviado_em, lida, tipo, midia_arquivo, midia_duracao, avaliacao_id)
           VALUES (?,?,?,?,?,0,?,?,?,?)""",
        (personal_id, aluno_id, remetente, texto, datetime.now().isoformat(),
         tipo, midia_arquivo, midia_duracao, avaliacao_id)
    )
    conn.commit()
    mid = conn.execute("SELECT last_insert_rowid() as id").fetchone()["id"]
    conn.close()
    return mid


def buscar_tipo_midia_chat(aluno_id, midia_arquivo):
    """Devolve o 'tipo' ('audio' ou 'video') da mensagem de chat dona desse
    arquivo de mídia — usado só para decidir o Content-Type certo na hora
    de servir o arquivo (extensão .webm sozinha não diz se é áudio ou
    vídeo)."""
    conn = conectar()
    row = conn.execute(
        "SELECT tipo FROM mensagens_chat WHERE aluno_id=? AND midia_arquivo=? LIMIT 1",
        (aluno_id, midia_arquivo)
    ).fetchone()
    conn.close()
    return row["tipo"] if row else None


def apagar_mensagem_chat(mensagem_id, personal_id, aluno_id, remetente):
    """'Apagar para todos', estilo WhatsApp: só quem enviou a mensagem pode
    apagá-la (por isso o filtro por 'remetente'), e o conteúdo (texto ou
    mídia) é removido de verdade do banco — fica só o marcador 'apagada'
    pra bolha virar 'Mensagem apagada' nos dois lados da conversa, tanto
    na tela de quem apagou quanto na do outro lado (via polling)."""
    conn = conectar()
    cur = conn.execute(
        """UPDATE mensagens_chat SET apagada=1, texto='', midia_arquivo=NULL, midia_duracao=NULL
           WHERE id=? AND personal_id=? AND aluno_id=? AND remetente=?""",
        (mensagem_id, personal_id, aluno_id, remetente)
    )
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


def listar_ids_apagados(personal_id, aluno_id):
    """Ids de todas as mensagens já apagadas 'pra todos' nessa conversa —
    usado pelo polling em JavaScript pra transformar a bolha em 'Mensagem
    apagada' do lado de quem NÃO apagou, sem precisar recarregar a tela."""
    conn = conectar()
    rows = conn.execute(
        "SELECT id FROM mensagens_chat WHERE personal_id=? AND aluno_id=? AND apagada=1",
        (personal_id, aluno_id)
    ).fetchall()
    conn.close()
    return [dict(r)["id"] for r in rows]


def listar_ids_lidos(personal_id, aluno_id, remetente):
    """Ids das mensagens ENVIADAS por 'remetente' (nessa conversa) que o
    outro lado já leu — usado pra atualizar os checks azuis (✓✓) sem
    precisar recarregar a conversa inteira."""
    conn = conectar()
    rows = conn.execute(
        "SELECT id FROM mensagens_chat WHERE personal_id=? AND aluno_id=? AND remetente=? AND lida=1",
        (personal_id, aluno_id, remetente)
    ).fetchall()
    conn.close()
    return [dict(r)["id"] for r in rows]


def listar_conversas_personal(personal_id):
    """Lista todos os alunos do personal como 'conversas' (igual à tela
    inicial do WhatsApp): cada um com a última mensagem trocada (se houver)
    e a contagem de mensagens do aluno ainda não lidas pelo personal. Quem
    já tem conversa aparece primeiro (mais recente no topo); quem nunca
    trocou mensagem aparece depois, em ordem alfabética — assim o personal
    pode iniciar uma conversa nova com qualquer aluno dele a qualquer hora."""
    conn = conectar()
    rows = conn.execute("""
        SELECT a.id as aluno_id, a.nome, a.foto_perfil,
               (SELECT texto FROM mensagens_chat mc WHERE mc.personal_id=? AND mc.aluno_id=a.id ORDER BY mc.id DESC LIMIT 1) as ultima_texto,
               (SELECT tipo FROM mensagens_chat mc WHERE mc.personal_id=? AND mc.aluno_id=a.id ORDER BY mc.id DESC LIMIT 1) as ultima_tipo,
               (SELECT remetente FROM mensagens_chat mc WHERE mc.personal_id=? AND mc.aluno_id=a.id ORDER BY mc.id DESC LIMIT 1) as ultima_remetente,
               (SELECT enviado_em FROM mensagens_chat mc WHERE mc.personal_id=? AND mc.aluno_id=a.id ORDER BY mc.id DESC LIMIT 1) as ultima_data,
               (SELECT apagada FROM mensagens_chat mc WHERE mc.personal_id=? AND mc.aluno_id=a.id ORDER BY mc.id DESC LIMIT 1) as ultima_apagada,
               (SELECT COUNT(*) FROM mensagens_chat mc WHERE mc.personal_id=? AND mc.aluno_id=a.id AND mc.remetente='aluno' AND mc.lida=0) as nao_lidas
        FROM alunos a WHERE a.personal_id=? ORDER BY a.nome
    """, (personal_id, personal_id, personal_id, personal_id, personal_id, personal_id, personal_id)).fetchall()
    conn.close()
    lista = [dict(r) for r in rows]
    com_conversa = sorted((c for c in lista if c["ultima_data"]), key=lambda c: c["ultima_data"], reverse=True)
    sem_conversa = [c for c in lista if not c["ultima_data"]]
    return com_conversa + sem_conversa


def listar_mensagens_chat(personal_id, aluno_id, limite=300):
    conn = conectar()
    rows = conn.execute(
        "SELECT * FROM mensagens_chat WHERE personal_id=? AND aluno_id=? ORDER BY id ASC LIMIT ?",
        (personal_id, aluno_id, limite)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def listar_mensagens_chat_novas(personal_id, aluno_id, depois_de_id):
    """Usado pelo polling em JavaScript: só as mensagens com id maior que o
    último que a tela já tem, pra não recarregar a conversa inteira."""
    conn = conectar()
    rows = conn.execute(
        "SELECT * FROM mensagens_chat WHERE personal_id=? AND aluno_id=? AND id>? ORDER BY id ASC",
        (personal_id, aluno_id, depois_de_id)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def marcar_chat_lido_personal(personal_id, aluno_id):
    """Marca como lidas as mensagens que o ALUNO mandou nessa conversa
    (chamado quando o personal abre/atualiza a tela de chat com ele)."""
    conn = conectar()
    conn.execute(
        "UPDATE mensagens_chat SET lida=1 WHERE personal_id=? AND aluno_id=? AND remetente='aluno' AND lida=0",
        (personal_id, aluno_id)
    )
    conn.commit()
    conn.close()


def marcar_chat_lido_aluno(personal_id, aluno_id):
    """Marca como lidas as mensagens que o PERSONAL mandou nessa conversa
    (chamado quando o aluno abre/atualiza a tela de mensagens)."""
    conn = conectar()
    conn.execute(
        "UPDATE mensagens_chat SET lida=1 WHERE personal_id=? AND aluno_id=? AND remetente='personal' AND lida=0",
        (personal_id, aluno_id)
    )
    conn.commit()
    conn.close()


def contar_mensagens_nao_lidas_personal(personal_id):
    """Total de mensagens (de todos os alunos) que o personal ainda não
    viu — usado no badge do bloco 'Mensagens' do painel."""
    conn = conectar()
    row = conn.execute(
        "SELECT COUNT(*) as c FROM mensagens_chat WHERE personal_id=? AND remetente='aluno' AND lida=0",
        (personal_id,)
    ).fetchone()
    conn.close()
    return dict(row)["c"] if row else 0


def contar_mensagens_nao_lidas_aluno(personal_id, aluno_id):
    """Mensagens do personal que este aluno ainda não viu — usado no badge
    do bloco 'Mensagens' da área do aluno."""
    conn = conectar()
    row = conn.execute(
        "SELECT COUNT(*) as c FROM mensagens_chat WHERE personal_id=? AND aluno_id=? AND remetente='personal' AND lida=0",
        (personal_id, aluno_id)
    ).fetchone()
    conn.close()
    return dict(row)["c"] if row else 0
