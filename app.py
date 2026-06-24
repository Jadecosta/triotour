import json
import os
import sqlite3
from datetime import datetime
from functools import wraps
from pathlib import Path
from urllib.parse import quote_plus
from uuid import uuid4

import click
from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "triotour.db"
PROMO_UPLOAD_DIR = BASE_DIR / "static" / "uploads" / "promocoes"
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_SIZE = 5 * 1024 * 1024

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("TRIOTOUR_SECRET_KEY", "triotour-dev-secret")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("TRIOTOUR_SESSION_SECURE", "").lower() in ("1", "true", "yes")
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024 * 1024

DEFAULT_TERMS = """Valores sujeitos à alteração sem aviso prévio.
Reserva sujeita à disponibilidade.
Documentação de responsabilidade do passageiro.
Taxas não inclusas, se aplicável.
Política de cancelamento conforme fornecedores.
Condições de pagamento conforme proposta."""

DEFAULT_ITEMS = [
    "Passagem aérea", "Passagem rodoviária", "Hospedagem", "Café da manhã",
    "Traslados", "City tour", "Guia acompanhante", "Seguro viagem",
    "Passeios", "Ingressos", "Bagagem"
]

MONTHS = [
    (1, "Janeiro"), (2, "Fevereiro"), (3, "Março"), (4, "Abril"),
    (5, "Maio"), (6, "Junho"), (7, "Julho"), (8, "Agosto"),
    (9, "Setembro"), (10, "Outubro"), (11, "Novembro"), (12, "Dezembro"),
]


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_=None):
    conn = g.pop("db", None)
    if conn:
        conn.close()


def has_column(conn, table, column):
    return any(row["name"] == column for row in conn.execute(f"PRAGMA table_info({table})"))


def add_column(conn, table, column, definition):
    if not has_column(conn, table, column):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, telefone TEXT, email TEXT,
        documento TEXT, observacoes TEXT, criado_em TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS configuracoes_empresa (
        id INTEGER PRIMARY KEY CHECK (id=1), nome TEXT NOT NULL, telefone TEXT, whatsapp TEXT,
        email TEXT, instagram TEXT, endereco TEXT, slogan TEXT, logo TEXT, termos_padrao TEXT
    );
    CREATE TABLE IF NOT EXISTS propostas (
        id INTEGER PRIMARY KEY AUTOINCREMENT, tipo TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'rascunho',
        cliente_id INTEGER NOT NULL, titulo TEXT NOT NULL, subtipo TEXT, origem TEXT NOT NULL, destino TEXT NOT NULL,
        data_inicio TEXT NOT NULL, data_fim TEXT, dias_noites TEXT, bagagem TEXT,
        valor_total REAL NOT NULL DEFAULT 0, valor_parcelado REAL DEFAULT 0, parcelas INTEGER DEFAULT 1,
        termos TEXT, nao_inclusos TEXT, criado_em TEXT NOT NULL, atualizado_em TEXT NOT NULL, data_aprovacao TEXT,
        FOREIGN KEY(cliente_id) REFERENCES clientes(id)
    );
    CREATE TABLE IF NOT EXISTS transportes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, proposta_id INTEGER NOT NULL, trecho TEXT NOT NULL,
        data TEXT, horario TEXT, companhia TEXT, identificacao TEXT,
        FOREIGN KEY(proposta_id) REFERENCES propostas(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS hospedagens (
        id INTEGER PRIMARY KEY AUTOINCREMENT, proposta_id INTEGER NOT NULL, nome TEXT,
        checkin TEXT, checkout TEXT, quarto TEXT, alimentacao TEXT,
        FOREIGN KEY(proposta_id) REFERENCES propostas(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS roteiro_dias (
        id INTEGER PRIMARY KEY AUTOINCREMENT, proposta_id INTEGER NOT NULL, ordem INTEGER NOT NULL,
        dia TEXT, data TEXT, local TEXT, titulo TEXT, descricao TEXT, horario TEXT, observacoes TEXT,
        FOREIGN KEY(proposta_id) REFERENCES propostas(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS itens_inclusos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, proposta_id INTEGER NOT NULL, nome TEXT NOT NULL,
        FOREIGN KEY(proposta_id) REFERENCES propostas(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS passageiros (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proposta_id INTEGER NOT NULL UNIQUE,
        adultos INTEGER NOT NULL DEFAULT 0,
        criancas INTEGER NOT NULL DEFAULT 0,
        bebes INTEGER NOT NULL DEFAULT 0,
        idades_criancas TEXT,
        idades_bebes TEXT,
        FOREIGN KEY(proposta_id) REFERENCES propostas(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS termos (id INTEGER PRIMARY KEY AUTOINCREMENT, texto TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        usuario TEXT UNIQUE,
        senha_hash TEXT NOT NULL,
        perfil TEXT NOT NULL DEFAULT 'atendente',
        ativo INTEGER NOT NULL DEFAULT 1,
        criado_em TEXT NOT NULL,
        atualizado_em TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS promocoes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo TEXT NOT NULL,
        destino TEXT NOT NULL,
        origem TEXT,
        descricao_curta TEXT,
        descricao_completa TEXT,
        categoria TEXT,
        data_inicio TEXT,
        data_fim TEXT,
        validade TEXT,
        dias INTEGER,
        noites INTEGER,
        vagas INTEGER,
        preco_original REAL,
        preco_promocional REAL,
        parcelas INTEGER DEFAULT 1,
        valor_parcela REAL,
        texto_preco TEXT,
        preco_por TEXT,
        status TEXT NOT NULL DEFAULT 'rascunho',
        destaque INTEGER NOT NULL DEFAULT 0,
        ordem INTEGER DEFAULT 0,
        hospedagem TEXT,
        transportadora TEXT,
        tipo_transporte TEXT,
        horarios TEXT,
        ponto_embarque TEXT,
        bagagem TEXT,
        documentacao TEXT,
        politica_criancas TEXT,
        politica_cancelamento TEXT,
        observacoes TEXT,
        termos TEXT,
        link_externo TEXT,
        link_whatsapp TEXT,
        texto_botao TEXT,
        criado_por INTEGER,
        criado_em TEXT NOT NULL,
        atualizado_em TEXT NOT NULL,
        publicado_em TEXT,
        FOREIGN KEY (criado_por) REFERENCES usuarios(id)
    );
    CREATE TABLE IF NOT EXISTS promocao_imagens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        promocao_id INTEGER NOT NULL,
        arquivo TEXT NOT NULL,
        nome_original TEXT,
        principal INTEGER NOT NULL DEFAULT 0,
        ordem INTEGER DEFAULT 0,
        criado_em TEXT NOT NULL,
        FOREIGN KEY (promocao_id) REFERENCES promocoes(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS promocao_inclusos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        promocao_id INTEGER NOT NULL,
        nome TEXT NOT NULL,
        ordem INTEGER DEFAULT 0,
        FOREIGN KEY (promocao_id) REFERENCES promocoes(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS promocao_nao_inclusos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        promocao_id INTEGER NOT NULL,
        nome TEXT NOT NULL,
        ordem INTEGER DEFAULT 0,
        FOREIGN KEY (promocao_id) REFERENCES promocoes(id) ON DELETE CASCADE
    );
    """)
    PROMO_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    for column, definition in {
        "data_aprovacao": "TEXT",
    }.items():
        add_column(conn, "propostas", column, definition)

    for column, definition in {
        "ordem": "INTEGER",
        "tipo_trecho": "TEXT",
        "tipo_passagem": "TEXT",
        "origem": "TEXT",
        "destino": "TEXT",
        "horario_saida": "TEXT",
        "horario_chegada": "TEXT",
        "companhia_personalizada": "TEXT",
        "classe": "TEXT",
        "bagagem": "TEXT",
        "observacoes": "TEXT",
    }.items():
        add_column(conn, "transportes", column, definition)

    for column, definition in {
        "cidade": "TEXT",
        "tipo_acomodacao": "TEXT",
        "acomodacao_personalizada": "TEXT",
        "quartos": "INTEGER DEFAULT 0",
        "camas": "INTEGER DEFAULT 0",
        "pessoas": "INTEGER DEFAULT 0",
        "tipos_camas": "TEXT",
        "itens_inclusos": "TEXT",
        "itens_outros": "TEXT",
        "nota": "REAL",
        "estrelas": "INTEGER",
        "localizacao": "TEXT",
        "mapa_link": "TEXT",
        "valor_total": "REAL DEFAULT 0",
        "parcelas": "INTEGER DEFAULT 1",
        "valor_parcelado": "REAL DEFAULT 0",
        "observacoes": "TEXT",
        "diarias": "INTEGER DEFAULT 0",
    }.items():
        add_column(conn, "hospedagens", column, definition)

    conn.execute(
        """INSERT OR IGNORE INTO configuracoes_empresa
        (id,nome,telefone,whatsapp,email,instagram,endereco,slogan,termos_padrao)
        VALUES (1,?,?,?,?,?,?,?,?)""",
        ("Triotour", "", "", "", "", "", "Sua próxima viagem começa aqui", DEFAULT_TERMS),
    )
    conn.commit()


@app.before_request
def before():
    init_db()


def rows(query, args=()):
    return db().execute(query, args).fetchall()


def one(query, args=()):
    return db().execute(query, args).fetchone()


def br_date(value):
    if not value:
        return ""
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return value


def money(value):
    try:
        amount = float(value or 0)
        s = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {s}"
    except (TypeError, ValueError):
        return "R$ 0,00"


def parse_money(value):
    if value in (None, ""):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = str(value).strip().replace("R$", "").replace(" ", "")
    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    return float(cleaned or 0)


def parse_int(value, default=0):
    if value in (None, ""):
        return default
    return int(value)


def parse_note(value):
    if value in (None, ""):
        return None
    return float(str(value).replace(",", "."))


def safe_json(value, default):
    if not value:
        return default
    try:
        data = json.loads(value)
        return data if isinstance(data, type(default)) else default
    except (TypeError, json.JSONDecodeError):
        raise ValueError("Dados dinâmicos inválidos. Recarregue a página e tente novamente.")


def date_diff_days(start, end):
    if not start or not end:
        return 0
    a = datetime.strptime(start, "%Y-%m-%d").date()
    b = datetime.strptime(end, "%Y-%m-%d").date()
    return (b - a).days


def json_loads_or(value, fallback):
    try:
        return json.loads(value) if value else fallback
    except (TypeError, json.JSONDecodeError):
        return fallback


app.jinja_env.filters["br_date"] = br_date
app.jinja_env.filters["money"] = money


def current_user():
    if not session.get("usuario_id"):
        return None
    return {
        "id": session.get("usuario_id"),
        "nome": session.get("usuario_nome"),
        "perfil": session.get("usuario_perfil"),
    }


@app.context_processor
def inject_user():
    return {"usuario_logado": current_user()}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("usuario_id"):
            flash("Entre para acessar a area interna.", "error")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("usuario_id"):
            flash("Entre para acessar a area administrativa.", "error")
            return redirect(url_for("login", next=request.path))
        if session.get("usuario_perfil") != "administrador":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def parse_bool(value):
    return 1 if str(value or "").lower() in ("1", "true", "on", "sim") else 0


def public_phone(value):
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def whatsapp_link(promo, cfg):
    direct = (dict(promo).get("link_whatsapp") if promo else "") or ""
    if direct:
        return direct
    phone = public_phone(cfg["whatsapp"] if cfg else "")
    message = f"Olá! Tenho interesse no pacote \"{promo['titulo']}\" para \"{promo['destino']}\". Gostaria de receber mais informações."
    if phone:
        return f"https://wa.me/{phone}?text={quote_plus(message)}"
    return f"https://wa.me/?text={quote_plus(message)}"


def promocao_image_url(image):
    if image and image["arquivo"]:
        return url_for("static", filename=f"uploads/promocoes/{image['arquivo']}")
    return url_for("static", filename="img/logo_triotour.png")


def load_promo_images(promocao_id):
    return rows("SELECT * FROM promocao_imagens WHERE promocao_id=? ORDER BY principal DESC, COALESCE(ordem,id), id", (promocao_id,))


def load_promo_lists(promocao_id):
    return {
        "inclusos": rows("SELECT * FROM promocao_inclusos WHERE promocao_id=? ORDER BY COALESCE(ordem,id), id", (promocao_id,)),
        "nao_inclusos": rows("SELECT * FROM promocao_nao_inclusos WHERE promocao_id=? ORDER BY COALESCE(ordem,id), id", (promocao_id,)),
    }


def published_promotions(extra_where="", args=()):
    today = datetime.now().strftime("%Y-%m-%d")
    sql = f"""SELECT p.*,
        (SELECT arquivo FROM promocao_imagens i WHERE i.promocao_id=p.id ORDER BY principal DESC, COALESCE(ordem,id), id LIMIT 1) imagem
        FROM promocoes p
        WHERE p.status='publicada' AND (p.validade IS NULL OR p.validade='' OR p.validade>=?) {extra_where}
        ORDER BY p.destaque DESC, COALESCE(p.ordem, 0), p.atualizado_em DESC"""
    return rows(sql, (today, *args))


def allowed_image(file_storage):
    filename = secure_filename(file_storage.filename or "")
    ext = Path(filename).suffix.lower()
    if not filename or ext not in ALLOWED_IMAGE_EXTENSIONS:
        return False, "Use imagens JPG, JPEG, PNG ou WEBP."
    pos = file_storage.stream.tell()
    file_storage.stream.seek(0, os.SEEK_END)
    size = file_storage.stream.tell()
    file_storage.stream.seek(pos)
    if size > MAX_IMAGE_SIZE:
        return False, "Cada imagem deve ter no maximo 5 MB."
    header = file_storage.stream.read(16)
    file_storage.stream.seek(pos)
    valid_header = (
        header.startswith(b"\xff\xd8\xff") or
        header.startswith(b"\x89PNG\r\n\x1a\n") or
        header.startswith(b"RIFF")
    )
    if not valid_header:
        return False, "Arquivo de imagem invalido."
    return True, ""


def save_uploaded_images(promocao_id, files, principal=False):
    saved = []
    for file_storage in files:
        if not file_storage or not file_storage.filename:
            continue
        ok, error = allowed_image(file_storage)
        if not ok:
            raise ValueError(error)
        original = secure_filename(file_storage.filename)
        ext = Path(original).suffix.lower()
        filename = f"{uuid4().hex}{ext}"
        target = PROMO_UPLOAD_DIR / filename
        file_storage.save(target)
        saved.append((filename, original, principal))
    for index, (filename, original, is_principal) in enumerate(saved, start=1):
        if is_principal:
            db().execute("UPDATE promocao_imagens SET principal=0 WHERE promocao_id=?", (promocao_id,))
        db().execute(
            "INSERT INTO promocao_imagens (promocao_id,arquivo,nome_original,principal,ordem,criado_em) VALUES (?,?,?,?,?,?)",
            (promocao_id, filename, original, 1 if is_principal else 0, index, datetime.utcnow().isoformat()),
        )


def remove_image_file(filename):
    if not filename or "/" in filename or "\\" in filename or ".." in filename:
        return
    still_used = one("SELECT id FROM promocao_imagens WHERE arquivo=? LIMIT 1", (filename,))
    if still_used:
        return
    target = (PROMO_UPLOAD_DIR / filename).resolve()
    upload_root = PROMO_UPLOAD_DIR.resolve()
    if upload_root in target.parents and target.exists():
        target.unlink()


def form_list(name):
    values = request.form.getlist(name)
    custom = request.form.get(f"{name}_custom", "")
    values.extend(item.strip() for item in custom.splitlines() if item.strip())
    return [item.strip() for item in values if item.strip()]


app.jinja_env.globals["promocao_image_url"] = promocao_image_url
app.jinja_env.globals["whatsapp_link"] = whatsapp_link


def dashboard_date_expr():
    return "COALESCE(data_aprovacao, atualizado_em, criado_em)"


def available_dashboard_years():
    date_expr = dashboard_date_expr()
    years = [
        row["ano"] for row in rows(
            f"""SELECT DISTINCT strftime('%Y', {date_expr}) ano
            FROM propostas
            WHERE {date_expr} IS NOT NULL AND strftime('%Y', {date_expr}) IS NOT NULL
            ORDER BY ano DESC"""
        ) if row["ano"]
    ]
    current_year = str(datetime.now().year)
    return years or [current_year]


def parse_dashboard_filters():
    today = datetime.now()
    years = available_dashboard_years()
    raw_year = request.args.get("ano", str(today.year)).strip()
    selected_year = raw_year if raw_year in years else str(today.year)
    if selected_year not in years:
        years = [selected_year] + years

    raw_month = request.args.get("mes", str(today.month)).strip().lower()
    if raw_month in ("todos", "all", "0", ""):
        selected_month = "todos"
    else:
        try:
            month_number = int(raw_month)
            selected_month = month_number if 1 <= month_number <= 12 else today.month
        except ValueError:
            selected_month = today.month

    return selected_month, selected_year, years


def period_clause(selected_month, selected_year):
    date_expr = dashboard_date_expr()
    clauses = [f"strftime('%Y', {date_expr}) = ?"]
    args = [selected_year]
    if selected_month != "todos":
        clauses.append(f"strftime('%m', {date_expr}) = ?")
        args.append(f"{int(selected_month):02d}")
    return " AND ".join(clauses), args


def count_period(where_sql, where_args):
    return one(f"SELECT COUNT(*) total FROM propostas WHERE {where_sql}", where_args)["total"]


def dashboard_metrics(selected_month, selected_year):
    period_sql, period_args = period_clause(selected_month, selected_year)
    sales_row = one(
        f"""SELECT COUNT(*) quantidade, COALESCE(SUM(valor_total), 0) total
        FROM propostas
        WHERE status='aprovada' AND {period_sql}""",
        period_args,
    )
    total_vendas = one("SELECT COUNT(*) total FROM propostas WHERE status='aprovada'")["total"]
    metrics = {
        "total_vendas": total_vendas,
        "vendas_periodo": sales_row["quantidade"],
        "valor_recebido": sales_row["total"],
        "total_cotacoes": count_period(f"tipo='cotacao' AND {period_sql}", period_args),
        "total_aprovadas": count_period(f"status='aprovada' AND {period_sql}", period_args),
        "total_enviadas": count_period(f"status='enviada' AND {period_sql}", period_args),
        "total_canceladas": count_period(f"status='cancelada' AND {period_sql}", period_args),
        "variacao_faturamento": None,
    }

    if selected_month != "todos":
        previous_month = int(selected_month) - 1
        previous_year = int(selected_year)
        if previous_month == 0:
            previous_month = 12
            previous_year -= 1
        previous_sql, previous_args = period_clause(previous_month, str(previous_year))
        previous_total = one(
            f"""SELECT COALESCE(SUM(valor_total), 0) total
            FROM propostas
            WHERE status='aprovada' AND {previous_sql}""",
            previous_args,
        )["total"]
        current_total = float(metrics["valor_recebido"] or 0)
        previous_total = float(previous_total or 0)
        if previous_total > 0:
            percent = ((current_total - previous_total) / previous_total) * 100
            direction = "acima" if percent >= 0 else "abaixo"
            metrics["variacao_faturamento"] = f"{abs(percent):.0f}% {direction} do mês anterior"
        else:
            metrics["variacao_faturamento"] = "Sem vendas no mês anterior"

    return metrics


@app.route("/")
def index():
    cfg = one("SELECT * FROM configuracoes_empresa WHERE id=1")
    promocoes = published_promotions()
    destaques = [p for p in promocoes if p["destaque"]]
    outras = [p for p in promocoes if not p["destaque"]]
    if not destaques:
        destaques, outras = promocoes[:3], promocoes[3:]
    inclusos = {
        p["id"]: rows("SELECT nome FROM promocao_inclusos WHERE promocao_id=? ORDER BY COALESCE(ordem,id), id LIMIT 5", (p["id"],))
        for p in promocoes
    }
    return render_template("public_home.html", cfg=cfg, destaques=destaques, outras=outras, inclusos=inclusos)


@app.route("/dashboard")
@login_required
def dashboard():
    q = request.args.get("q", "").strip()
    selected_month, selected_year, years = parse_dashboard_filters()
    metrics = dashboard_metrics(selected_month, selected_year)
    sql = """SELECT p.*, c.nome cliente FROM propostas p JOIN clientes c ON c.id=p.cliente_id
             WHERE (?='' OR c.nome LIKE ? OR p.titulo LIKE ? OR p.destino LIKE ? OR p.data_inicio LIKE ?)
             ORDER BY p.atualizado_em DESC LIMIT 8"""
    props = rows(sql, (q, f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%"))
    return render_template(
        "index.html",
        propostas=props,
        q=q,
        meses=MONTHS,
        anos_disponiveis=years,
        mes_selecionado=selected_month,
        ano_selecionado=selected_year,
        **metrics,
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("usuario_id"):
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        identificador = request.form.get("identificador", "").strip()
        senha = request.form.get("senha", "")
        usuario = one(
            "SELECT * FROM usuarios WHERE ativo=1 AND (email=? OR usuario=?)",
            (identificador, identificador),
        )
        if usuario and check_password_hash(usuario["senha_hash"], senha):
            session.clear()
            session["usuario_id"] = usuario["id"]
            session["usuario_nome"] = usuario["nome"]
            session["usuario_perfil"] = usuario["perfil"]
            return redirect(request.args.get("next") or url_for("dashboard"))
        flash("Usuario ou senha invalidos.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Voce saiu do sistema.", "ok")
    return redirect(url_for("index"))




@app.route("/clientes", methods=["GET", "POST"])
@login_required
def clientes():
    if request.method == "POST":
        f = request.form
        if not f.get("nome"):
            flash("Nome do cliente é obrigatório.", "error")
        else:
            db().execute(
                "INSERT INTO clientes (nome,telefone,email,documento,observacoes,criado_em) VALUES (?,?,?,?,?,?)",
                (f["nome"], f.get("telefone"), f.get("email"), f.get("documento"), f.get("observacoes"), datetime.utcnow().isoformat()),
            )
            db().commit()
            flash("Cliente salvo.", "ok")
            return redirect(url_for("clientes"))
    return render_template("clientes.html", clientes=rows("SELECT * FROM clientes ORDER BY nome"))


@app.route("/clientes/<int:id>/editar", methods=["POST"])
@login_required
def editar_cliente(id):
    f = request.form
    db().execute(
        "UPDATE clientes SET nome=?,telefone=?,email=?,documento=?,observacoes=? WHERE id=?",
        (f["nome"], f.get("telefone"), f.get("email"), f.get("documento"), f.get("observacoes"), id),
    )
    db().commit()
    return redirect(url_for("clientes"))


@app.route("/propostas")
@login_required
def propostas():
    args = {k: request.args.get(k, "").strip() for k in ["cliente", "destino", "tipo", "data", "status"]}
    props = rows(
        """SELECT p.*, c.nome cliente FROM propostas p JOIN clientes c ON c.id=p.cliente_id
        WHERE (?='' OR c.nome LIKE ?) AND (?='' OR p.destino LIKE ?) AND (?='' OR p.tipo=?)
        AND (?='' OR p.data_inicio=?) AND (?='' OR p.status=?)
        ORDER BY p.atualizado_em DESC""",
        (args["cliente"], f"%{args['cliente']}%", args["destino"], f"%{args['destino']}%", args["tipo"], args["tipo"], args["data"], args["data"], args["status"], args["status"]),
    )
    return render_template("propostas.html", propostas=props, args=args)


@app.route("/propostas/nova/<tipo>", methods=["GET", "POST"])
@login_required
def form_proposta(tipo):
    if tipo not in ("cotacao", "pacote"):
        abort(404)
    if request.method == "POST":
        return save_proposta(tipo)
    return render_form(tipo)


@app.route("/propostas/<int:id>/editar", methods=["GET", "POST"])
@login_required
def edit_proposta(id):
    prop = one("SELECT * FROM propostas WHERE id=?", (id,)) or abort(404)
    if request.method == "POST":
        return save_proposta(prop["tipo"], id)
    return render_form(prop["tipo"], load_prop(id))


def render_form(tipo, proposta=None):
    return render_template(
        "form_proposta.html",
        tipo=tipo,
        proposta=proposta,
        clientes=rows("SELECT * FROM clientes ORDER BY nome"),
        cfg=one("SELECT * FROM configuracoes_empresa WHERE id=1"),
        default_items=DEFAULT_ITEMS,
    )


def clean_transportes(form):
    inclui = form.get("inclui_passagens") == "1"
    data = safe_json(form.get("transportes_json"), [])
    valid = []
    for item in data:
        if not isinstance(item, dict):
            continue
        normalized = {k: str(item.get(k) or "").strip() for k in [
            "id", "tipo_trecho", "tipo_passagem", "origem", "destino", "data",
            "horario_saida", "horario_chegada", "companhia", "companhia_personalizada",
            "identificacao", "classe", "bagagem", "observacoes"
        ]}
        if not any(v for k, v in normalized.items() if k != "id"):
            continue
        valid.append(normalized)
    errors = []
    if inclui and not valid:
        errors.append("Inclua pelo menos um trecho válido de passagem.")
    for index, item in enumerate(valid, start=1):
        if not item["tipo_trecho"] or not item["tipo_passagem"] or not item["origem"] or not item["destino"] or not item["data"]:
            errors.append(f"Trecho {index}: preencha tipo, origem, destino e data.")
    return inclui, valid if inclui else [], errors


def clean_hospedagem(form):
    inclui = form.get("inclui_hospedagem") == "1"
    if not inclui:
        return False, None, []

    camas = safe_json(form.get("camas_json"), [])
    itens = safe_json(form.get("hospedagem_itens_json"), [])
    h = {
        "cidade": form.get("hosp_cidade", "").strip(),
        "checkin": form.get("checkin", "").strip(),
        "checkout": form.get("checkout", "").strip(),
        "nome": form.get("hospedagem_nome", "").strip(),
        "tipo_acomodacao": form.get("tipo_acomodacao", "").strip(),
        "acomodacao_personalizada": form.get("acomodacao_personalizada", "").strip(),
        "quartos": parse_int(form.get("quartos"), 0),
        "camas": parse_int(form.get("camas"), 0),
        "pessoas": parse_int(form.get("pessoas"), 0),
        "tipos_camas": [c for c in camas if isinstance(c, dict) and (c.get("tipo") or c.get("quantidade"))],
        "itens_inclusos": [str(i).strip() for i in itens if str(i).strip()],
        "itens_outros": form.get("hosp_itens_outros", "").strip(),
        "nota": parse_note(form.get("nota")),
        "estrelas": parse_int(form.get("estrelas"), 0) if form.get("estrelas") else None,
        "localizacao": form.get("localizacao", "").strip(),
        "mapa_link": form.get("mapa_link", "").strip(),
        "valor_total": parse_money(form.get("hosp_valor_total")),
        "parcelas": parse_int(form.get("hosp_parcelas"), 1),
        "valor_parcelado": parse_money(form.get("hosp_valor_parcelado")),
        "observacoes": form.get("hosp_observacoes", "").strip(),
    }
    errors = []
    if not h["cidade"] or not h["nome"] or not h["checkin"] or not h["checkout"]:
        errors.append("Hospedagem: cidade, hotel, check-in e check-out são obrigatórios.")
    if h["checkin"] and h["checkout"]:
        try:
            h["diarias"] = date_diff_days(h["checkin"], h["checkout"])
            if h["diarias"] < 0:
                errors.append("Hospedagem: check-out não pode ser anterior ao check-in.")
        except ValueError:
            errors.append("Hospedagem: datas inválidas.")
    else:
        h["diarias"] = 0
    for field in ["quartos", "camas", "pessoas"]:
        if h[field] < 0:
            errors.append("Hospedagem: quantidades não podem ser negativas.")
    if h["nota"] is not None and not 0 <= h["nota"] <= 10:
        errors.append("Hospedagem: a nota deve estar entre 0 e 10.")
    if h["estrelas"] is not None and h["estrelas"] not in range(1, 6):
        errors.append("Hospedagem: estrelas devem estar entre 1 e 5.")
    if h["valor_total"] < 0 or h["valor_parcelado"] < 0:
        errors.append("Hospedagem: valores não podem ser negativos.")
    if h["parcelas"] <= 0:
        errors.append("Hospedagem: parcelas devem ser maiores que zero.")
    return True, h, errors


def form_state_from_request(tipo):
    f = request.form
    transportes = json_loads_or(f.get("transportes_json"), [])
    camas = json_loads_or(f.get("camas_json"), [])
    hosp_itens = json_loads_or(f.get("hospedagem_itens_json"), [])
    chosen = [{"nome": item} for item in request.form.getlist("itens")]
    return {
        "tipo": tipo,
        "status": f.get("status", "rascunho"),
        "cliente_id": parse_int(f.get("cliente_id"), 0),
        "titulo": f.get("titulo", ""),
        "subtipo": f.get("subtipo", ""),
        "origem": f.get("origem", ""),
        "destino": f.get("destino", ""),
        "data_inicio": f.get("data_inicio", ""),
        "data_fim": f.get("data_fim", ""),
        "dias_noites": f.get("dias_noites", ""),
        "bagagem": f.get("bagagem", ""),
        "valor_total": f.get("valor_total", ""),
        "valor_parcelado": f.get("valor_parcelado", ""),
        "parcelas": f.get("parcelas", "1"),
        "termos": f.get("termos", ""),
        "nao_inclusos": f.get("nao_inclusos", ""),
        "passageiros": {
            "adultos": f.get("adultos", 0), "criancas": f.get("criancas", 0), "bebes": f.get("bebes", 0),
            "idades_criancas": f.get("idades_criancas", ""), "idades_bebes": f.get("idades_bebes", "")
        },
        "transportes_lista": transportes,
        "inclui_passagens": f.get("inclui_passagens") == "1",
        "hospedagem": {
            "cidade": f.get("hosp_cidade", ""), "nome": f.get("hospedagem_nome", ""),
            "checkin": f.get("checkin", ""), "checkout": f.get("checkout", ""),
            "tipo_acomodacao": f.get("tipo_acomodacao", ""), "acomodacao_personalizada": f.get("acomodacao_personalizada", ""),
            "quartos": f.get("quartos", ""), "camas": f.get("camas", ""), "pessoas": f.get("pessoas", ""),
            "tipos_camas": camas, "itens_inclusos": hosp_itens, "itens_outros": f.get("hosp_itens_outros", ""),
            "nota": f.get("nota", ""), "estrelas": f.get("estrelas", ""), "localizacao": f.get("localizacao", ""),
            "mapa_link": f.get("mapa_link", ""), "valor_total": f.get("hosp_valor_total", ""),
            "parcelas": f.get("hosp_parcelas", "1"), "valor_parcelado": f.get("hosp_valor_parcelado", ""),
            "observacoes": f.get("hosp_observacoes", ""), "diarias": 0
        },
        "inclui_hospedagem": f.get("inclui_hospedagem") == "1",
        "roteiro_json": json_loads_or(f.get("roteiro_json"), []),
        "itens": chosen,
    }


def save_proposta(tipo, id=None):
    f = request.form
    errors = []
    for field, label in [("cliente_id", "cliente"), ("origem", "origem"), ("destino", "destino"), ("data_inicio", "data de início"), ("valor_total", "valor total")]:
        if not f.get(field):
            errors.append(f"Preencha o campo obrigatório: {label}.")

    try:
        adultos = parse_int(f.get("adultos"), 0)
        criancas = parse_int(f.get("criancas"), 0)
        bebes = parse_int(f.get("bebes"), 0)
        valor_total = parse_money(f.get("valor_total"))
        valor_parcelado = parse_money(f.get("valor_parcelado"))
        parcelas = parse_int(f.get("parcelas"), 1)
        inclui_passagens, transportes, transport_errors = clean_transportes(f)
        inclui_hospedagem, hospedagem, hospedagem_errors = clean_hospedagem(f)
        roteiro = safe_json(f.get("roteiro_json"), [])
    except (ValueError, TypeError):
        errors.append("Revise os números, valores e dados dinâmicos informados.")
        inclui_passagens, transportes, transport_errors = False, [], []
        inclui_hospedagem, hospedagem, hospedagem_errors = False, None, []
        roteiro = []
        adultos = criancas = bebes = 0
        valor_total = valor_parcelado = 0
        parcelas = 1

    errors.extend(transport_errors)
    errors.extend(hospedagem_errors)
    if adultos < 0 or criancas < 0 or bebes < 0:
        errors.append("As quantidades de passageiros não podem ser negativas.")
    if adultos + criancas + bebes <= 0:
        errors.append("Informe pelo menos um passageiro.")
    if valor_total < 0 or valor_parcelado < 0:
        errors.append("Valores gerais não podem ser negativos.")
    if parcelas <= 0:
        errors.append("A quantidade de parcelas deve ser maior que zero.")

    if errors:
        for error in errors:
            flash(error, "error")
        return render_form(tipo, form_state_from_request(tipo))

    now = datetime.utcnow().isoformat()
    status_value = f.get("status", "rascunho")
    approval_date = now if status_value == "aprovada" else None
    titulo = f.get("titulo") or ("Cotação de viagem" if tipo == "cotacao" else f.get("nome_pacote") or "Pacote de viagem")
    data = (
        tipo, status_value, f["cliente_id"], titulo, f.get("subtipo"), f["origem"], f["destino"],
        f["data_inicio"], f.get("data_fim"), f.get("dias_noites"), f.get("bagagem"), valor_total,
        valor_parcelado, parcelas, f.get("termos"), f.get("nao_inclusos"), now,
    )

    conn = db()
    try:
        conn.execute("BEGIN")
        if id:
            conn.execute(
                """UPDATE propostas SET tipo=?,status=?,cliente_id=?,titulo=?,subtipo=?,origem=?,destino=?,
                data_inicio=?,data_fim=?,dias_noites=?,bagagem=?,valor_total=?,valor_parcelado=?,parcelas=?,
                termos=?,nao_inclusos=?,atualizado_em=?,
                data_aprovacao=CASE
                    WHEN ?='aprovada' AND data_aprovacao IS NULL THEN ?
                    ELSE data_aprovacao
                END
                WHERE id=?""",
                data + (status_value, now, id),
            )
        else:
            cur = conn.execute(
                """INSERT INTO propostas
                (tipo,status,cliente_id,titulo,subtipo,origem,destino,data_inicio,data_fim,dias_noites,bagagem,
                valor_total,valor_parcelado,parcelas,termos,nao_inclusos,atualizado_em,criado_em,data_aprovacao)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                data + (now, approval_date),
            )
            id = cur.lastrowid

        conn.execute(
            """INSERT INTO passageiros (proposta_id,adultos,criancas,bebes,idades_criancas,idades_bebes)
            VALUES (?,?,?,?,?,?)
            ON CONFLICT(proposta_id) DO UPDATE SET adultos=excluded.adultos, criancas=excluded.criancas,
            bebes=excluded.bebes, idades_criancas=excluded.idades_criancas, idades_bebes=excluded.idades_bebes""",
            (id, adultos, criancas, bebes, f.get("idades_criancas"), f.get("idades_bebes")),
        )

        conn.execute("DELETE FROM transportes WHERE proposta_id=?", (id,))
        if inclui_passagens:
            for ordem, tr in enumerate(transportes, start=1):
                conn.execute(
                    """INSERT INTO transportes
                    (proposta_id,trecho,ordem,tipo_trecho,tipo_passagem,origem,destino,data,horario,horario_saida,
                    horario_chegada,companhia,companhia_personalizada,identificacao,classe,bagagem,observacoes)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        id, tr["tipo_trecho"], ordem, tr["tipo_trecho"], tr["tipo_passagem"], tr["origem"], tr["destino"],
                        tr["data"], tr["horario_saida"], tr["horario_saida"], tr["horario_chegada"], tr["companhia"],
                        tr["companhia_personalizada"], tr["identificacao"], tr["classe"], tr["bagagem"], tr["observacoes"],
                    ),
                )

        conn.execute("DELETE FROM hospedagens WHERE proposta_id=?", (id,))
        if inclui_hospedagem and hospedagem:
            conn.execute(
                """INSERT INTO hospedagens
                (proposta_id,nome,checkin,checkout,quarto,alimentacao,cidade,tipo_acomodacao,acomodacao_personalizada,
                quartos,camas,pessoas,tipos_camas,itens_inclusos,itens_outros,nota,estrelas,localizacao,mapa_link,
                valor_total,parcelas,valor_parcelado,observacoes,diarias)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    id, hospedagem["nome"], hospedagem["checkin"], hospedagem["checkout"],
                    hospedagem["tipo_acomodacao"], ", ".join(hospedagem["itens_inclusos"]),
                    hospedagem["cidade"], hospedagem["tipo_acomodacao"], hospedagem["acomodacao_personalizada"],
                    hospedagem["quartos"], hospedagem["camas"], hospedagem["pessoas"],
                    json.dumps(hospedagem["tipos_camas"], ensure_ascii=False),
                    json.dumps(hospedagem["itens_inclusos"], ensure_ascii=False),
                    hospedagem["itens_outros"], hospedagem["nota"], hospedagem["estrelas"],
                    hospedagem["localizacao"], hospedagem["mapa_link"], hospedagem["valor_total"],
                    hospedagem["parcelas"], hospedagem["valor_parcelado"], hospedagem["observacoes"],
                    hospedagem["diarias"],
                ),
            )

        conn.execute("DELETE FROM roteiro_dias WHERE proposta_id=?", (id,))
        if tipo == "pacote":
            for ordem, dia in enumerate([d for d in roteiro if isinstance(d, dict)], start=1):
                if not any(dia.get(k) for k in ["dia", "data", "local", "titulo", "descricao", "horario", "observacoes"]):
                    continue
                conn.execute(
                    """INSERT INTO roteiro_dias
                    (proposta_id,ordem,dia,data,local,titulo,descricao,horario,observacoes)
                    VALUES (?,?,?,?,?,?,?,?,?)""",
                    (id, ordem, dia.get("dia"), dia.get("data"), dia.get("local"), dia.get("titulo"), dia.get("descricao"), dia.get("horario"), dia.get("observacoes")),
                )

        conn.execute("DELETE FROM itens_inclusos WHERE proposta_id=?", (id,))
        itens = request.form.getlist("itens") + [x.strip() for x in f.get("itens_custom", "").split(",") if x.strip()]
        for item in dict.fromkeys(itens):
            conn.execute("INSERT INTO itens_inclusos (proposta_id,nome) VALUES (?,?)", (id, item))

        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        flash(f"Não foi possível salvar a proposta: {exc}", "error")
        return render_form(tipo, form_state_from_request(tipo))

    flash("Proposta salva.", "ok")
    return redirect(url_for("view_proposta", id=id))


def normalize_transporte(row):
    data = dict(row)
    tipo_trecho = data.get("tipo_trecho") or data.get("trecho") or ""
    horario_saida = data.get("horario_saida") or data.get("horario") or ""
    return {
        "id": data.get("id"),
        "tipo_trecho": tipo_trecho.capitalize() if tipo_trecho in ("ida", "volta") else tipo_trecho,
        "tipo_passagem": data.get("tipo_passagem") or "",
        "origem": data.get("origem") or "",
        "destino": data.get("destino") or "",
        "data": data.get("data") or "",
        "horario_saida": horario_saida,
        "horario_chegada": data.get("horario_chegada") or "",
        "companhia": data.get("companhia") or "",
        "companhia_personalizada": data.get("companhia_personalizada") or "",
        "identificacao": data.get("identificacao") or "",
        "classe": data.get("classe") or "",
        "bagagem": data.get("bagagem") or "",
        "observacoes": data.get("observacoes") or "",
    }


def normalize_hospedagem(row):
    if not row:
        return None
    h = dict(row)
    h["tipos_camas"] = json_loads_or(h.get("tipos_camas"), [])
    h["itens_inclusos"] = json_loads_or(h.get("itens_inclusos"), [h.get("alimentacao")] if h.get("alimentacao") else [])
    return h


def load_prop(id):
    prop = dict(one(
        """SELECT p.*, c.nome cliente, c.telefone, c.email, c.documento, c.observacoes cliente_obs
        FROM propostas p JOIN clientes c ON c.id=p.cliente_id WHERE p.id=?""",
        (id,),
    ) or abort(404))
    transportes = [normalize_transporte(r) for r in rows("SELECT * FROM transportes WHERE proposta_id=? ORDER BY COALESCE(ordem,id), id", (id,))]
    prop["transportes_lista"] = [
        tr for tr in transportes
        if any(tr.get(k) for k in ["origem", "destino", "data", "horario_saida", "companhia", "identificacao", "tipo_passagem"])
    ]
    prop["transportes"] = {tr["tipo_trecho"].lower(): tr for tr in prop["transportes_lista"]}
    prop["inclui_passagens"] = bool(prop["transportes_lista"])
    passageiros = one("SELECT * FROM passageiros WHERE proposta_id=?", (id,))
    prop["passageiros"] = dict(passageiros) if passageiros else {"adultos": 1, "criancas": 0, "bebes": 0, "idades_criancas": "", "idades_bebes": ""}
    prop["hospedagem"] = normalize_hospedagem(one("SELECT * FROM hospedagens WHERE proposta_id=?", (id,)))
    prop["inclui_hospedagem"] = bool(prop["hospedagem"])
    prop["roteiro"] = rows("SELECT * FROM roteiro_dias WHERE proposta_id=? ORDER BY ordem", (id,))
    prop["roteiro_json"] = [dict(r) for r in prop["roteiro"]]
    prop["itens"] = rows("SELECT * FROM itens_inclusos WHERE proposta_id=?", (id,))
    return prop


@app.route("/propostas/<int:id>")
@login_required
def view_proposta(id):
    return render_template("documento.html", p=load_prop(id), cfg=one("SELECT * FROM configuracoes_empresa WHERE id=1"), emissao=datetime.now())


@app.route("/propostas/<int:id>/duplicar", methods=["POST"])
@login_required
def duplicar(id):
    now = datetime.utcnow().isoformat()
    conn = db()
    cur = conn.execute(
        """INSERT INTO propostas
        (tipo,status,cliente_id,titulo,subtipo,origem,destino,data_inicio,data_fim,dias_noites,bagagem,
        valor_total,valor_parcelado,parcelas,termos,nao_inclusos,criado_em,atualizado_em)
        SELECT tipo,'rascunho',cliente_id,titulo||' (cópia)',subtipo,origem,destino,data_inicio,data_fim,
        dias_noites,bagagem,valor_total,valor_parcelado,parcelas,termos,nao_inclusos,?,? FROM propostas WHERE id=?""",
        (now, now, id),
    )
    nid = cur.lastrowid
    for table in ["passageiros", "transportes", "hospedagens", "roteiro_dias", "itens_inclusos"]:
        cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})") if r["name"] not in ("id", "proposta_id")]
        if cols:
            conn.execute(f"INSERT INTO {table} (proposta_id,{','.join(cols)}) SELECT ?,{','.join(cols)} FROM {table} WHERE proposta_id=?", (nid, id))
    conn.commit()
    return redirect(url_for("edit_proposta", id=nid))


@app.route("/propostas/<int:id>/status", methods=["POST"])
@login_required
def status(id):
    now = datetime.utcnow().isoformat()
    new_status = request.form["status"]
    db().execute(
        """UPDATE propostas
        SET status=?,
            atualizado_em=?,
            data_aprovacao=CASE
                WHEN ?='aprovada' AND data_aprovacao IS NULL THEN ?
                ELSE data_aprovacao
            END
        WHERE id=?""",
        (new_status, now, new_status, now, id),
    )
    db().commit()
    return redirect(request.referrer or url_for("propostas"))


@app.route("/propostas/<int:id>/excluir", methods=["POST"])
@admin_required
def excluir(id):
    db().execute("DELETE FROM propostas WHERE id=?", (id,))
    db().commit()
    return redirect(url_for("propostas"))


@app.route("/configuracoes", methods=["GET", "POST"])
@admin_required
def configuracoes():
    if request.method == "POST":
        f = request.form
        db().execute(
            """UPDATE configuracoes_empresa
            SET nome=?,telefone=?,whatsapp=?,email=?,instagram=?,endereco=?,slogan=?,logo=?,termos_padrao=?
            WHERE id=1""",
            (f["nome"], f.get("telefone"), f.get("whatsapp"), f.get("email"), f.get("instagram"), f.get("endereco"), f.get("slogan"), f.get("logo"), f.get("termos_padrao")),
        )
        db().commit()
        flash("Configurações salvas.", "ok")
    return render_template("configuracoes.html", cfg=one("SELECT * FROM configuracoes_empresa WHERE id=1"))


PROMO_INCLUSOS = [
    "Passagem aérea", "Passagem rodoviária", "Hospedagem", "Café da manhã",
    "Meia pensão", "Pensão completa", "All inclusive", "Traslado",
    "Guia acompanhante", "Seguro viagem", "Passeios", "Ingressos",
    "Bagagem", "City tour", "Taxas", "Outros"
]

PROMO_NAO_INCLUSOS = [
    "Refeições não mencionadas", "Despesas pessoais", "Passeios opcionais",
    "Taxas locais", "Bagagem extra", "Outros"
]


def validate_promotion_form():
    f = request.form
    errors = []
    if not f.get("titulo", "").strip():
        errors.append("Informe o titulo da promocao.")
    if not f.get("destino", "").strip():
        errors.append("Informe o destino.")
    preco_original = parse_money(f.get("preco_original"))
    preco_promocional = parse_money(f.get("preco_promocional"))
    parcelas = parse_int(f.get("parcelas"), 1)
    valor_parcela = parse_money(f.get("valor_parcela"))
    numeric_values = [
        preco_original, preco_promocional, valor_parcela, parcelas,
        parse_int(f.get("dias"), 0), parse_int(f.get("noites"), 0), parse_int(f.get("vagas"), 0)
    ]
    if any(value < 0 for value in numeric_values):
        errors.append("Valores e quantidades nao podem ser negativos.")
    if preco_original and preco_promocional and preco_promocional > preco_original:
        errors.append("O preco promocional nao pode ser maior que o preco original.")
    if parcelas <= 0:
        errors.append("A quantidade de parcelas deve ser maior que zero.")
    if preco_promocional and parcelas and not valor_parcela:
        valor_parcela = round(preco_promocional / parcelas, 2)
    return errors, preco_original, preco_promocional, parcelas, valor_parcela


def save_promotion_lists(promocao_id):
    conn = db()
    conn.execute("DELETE FROM promocao_inclusos WHERE promocao_id=?", (promocao_id,))
    for ordem, item in enumerate(dict.fromkeys(form_list("inclusos")), start=1):
        conn.execute("INSERT INTO promocao_inclusos (promocao_id,nome,ordem) VALUES (?,?,?)", (promocao_id, item, ordem))
    conn.execute("DELETE FROM promocao_nao_inclusos WHERE promocao_id=?", (promocao_id,))
    for ordem, item in enumerate(dict.fromkeys(form_list("nao_inclusos")), start=1):
        conn.execute("INSERT INTO promocao_nao_inclusos (promocao_id,nome,ordem) VALUES (?,?,?)", (promocao_id, item, ordem))


def save_promotion(id=None):
    errors, preco_original, preco_promocional, parcelas, valor_parcela = validate_promotion_form()
    if errors:
        for error in errors:
            flash(error, "error")
        return None
    f = request.form
    now = datetime.utcnow().isoformat()
    data = (
        f.get("titulo", "").strip(), f.get("destino", "").strip(), f.get("origem", "").strip(),
        f.get("descricao_curta", "").strip(), f.get("descricao_completa", "").strip(), f.get("categoria", "").strip(),
        f.get("data_inicio"), f.get("data_fim"), f.get("validade"), parse_int(f.get("dias"), 0),
        parse_int(f.get("noites"), 0), parse_int(f.get("vagas"), 0), preco_original, preco_promocional,
        parcelas, valor_parcela, f.get("texto_preco", "").strip(), f.get("preco_por", "pessoa"),
        f.get("status", "rascunho"), parse_bool(f.get("destaque")), parse_int(f.get("ordem"), 0),
        f.get("hospedagem", "").strip(), f.get("transportadora", "").strip(), f.get("tipo_transporte", "").strip(),
        f.get("horarios", "").strip(), f.get("ponto_embarque", "").strip(), f.get("bagagem", "").strip(),
        f.get("documentacao", "").strip(), f.get("politica_criancas", "").strip(), f.get("politica_cancelamento", "").strip(),
        f.get("observacoes", "").strip(), f.get("termos", "").strip(), f.get("link_externo", "").strip(),
        f.get("link_whatsapp", "").strip(), f.get("texto_botao", "").strip() or "Quero reservar",
    )
    conn = db()
    try:
        conn.execute("BEGIN")
        publicado_em = now if f.get("status") == "publicada" else None
        if id:
            conn.execute(
                """UPDATE promocoes SET titulo=?,destino=?,origem=?,descricao_curta=?,descricao_completa=?,categoria=?,
                data_inicio=?,data_fim=?,validade=?,dias=?,noites=?,vagas=?,preco_original=?,preco_promocional=?,
                parcelas=?,valor_parcela=?,texto_preco=?,preco_por=?,status=?,destaque=?,ordem=?,hospedagem=?,
                transportadora=?,tipo_transporte=?,horarios=?,ponto_embarque=?,bagagem=?,documentacao=?,
                politica_criancas=?,politica_cancelamento=?,observacoes=?,termos=?,link_externo=?,link_whatsapp=?,
                texto_botao=?,atualizado_em=?,publicado_em=CASE WHEN ?='publicada' AND publicado_em IS NULL THEN ? ELSE publicado_em END
                WHERE id=?""",
                data + (now, f.get("status"), now, id),
            )
        else:
            cur = conn.execute(
                """INSERT INTO promocoes
                (titulo,destino,origem,descricao_curta,descricao_completa,categoria,data_inicio,data_fim,validade,dias,noites,
                vagas,preco_original,preco_promocional,parcelas,valor_parcela,texto_preco,preco_por,status,destaque,ordem,
                hospedagem,transportadora,tipo_transporte,horarios,ponto_embarque,bagagem,documentacao,politica_criancas,
                politica_cancelamento,observacoes,termos,link_externo,link_whatsapp,texto_botao,criado_por,criado_em,atualizado_em,publicado_em)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                data + (session.get("usuario_id"), now, now, publicado_em),
            )
            id = cur.lastrowid
        save_promotion_lists(id)
        for image_id in [parse_int(value, 0) for value in request.form.getlist("delete_images")]:
            image = one("SELECT * FROM promocao_imagens WHERE id=? AND promocao_id=?", (image_id, id))
            if image:
                conn.execute("DELETE FROM promocao_imagens WHERE id=?", (image_id,))
                remove_image_file(image["arquivo"])
        principal_id = parse_int(f.get("imagem_principal_id"), 0)
        if principal_id:
            conn.execute("UPDATE promocao_imagens SET principal=0 WHERE promocao_id=?", (id,))
            conn.execute("UPDATE promocao_imagens SET principal=1 WHERE id=? AND promocao_id=?", (principal_id, id))
        save_uploaded_images(id, request.files.getlist("imagem_principal"), principal=True)
        save_uploaded_images(id, request.files.getlist("imagens"), principal=False)
        conn.commit()
        return id
    except (sqlite3.Error, ValueError) as exc:
        conn.rollback()
        flash(f"Nao foi possivel salvar a promocao: {exc}", "error")
        return None


@app.route("/promocoes")
def promocoes_publicas():
    cfg = one("SELECT * FROM configuracoes_empresa WHERE id=1")
    promocoes = published_promotions()
    inclusos = {
        p["id"]: rows("SELECT nome FROM promocao_inclusos WHERE promocao_id=? ORDER BY COALESCE(ordem,id), id LIMIT 5", (p["id"],))
        for p in promocoes
    }
    return render_template("public_promocoes.html", cfg=cfg, promocoes=promocoes, inclusos=inclusos)


@app.route("/promocoes/<int:id>")
def promocao_publica(id):
    promo = one("SELECT * FROM promocoes WHERE id=? AND status='publicada' AND (validade IS NULL OR validade='' OR validade>=?)", (id, datetime.now().strftime("%Y-%m-%d"))) or abort(404)
    cfg = one("SELECT * FROM configuracoes_empresa WHERE id=1")
    lists = load_promo_lists(id)
    return render_template("public_promocao.html", promo=promo, cfg=cfg, imagens=load_promo_images(id), **lists)


@app.route("/admin/promocoes")
@admin_required
def admin_promocoes():
    args = {k: request.args.get(k, "").strip() for k in ["q", "destino", "status", "categoria", "data", "destaque"]}
    filters = []
    params = []
    if args["q"]:
        filters.append("(p.titulo LIKE ? OR p.destino LIKE ?)")
        params.extend([f"%{args['q']}%", f"%{args['q']}%"])
    if args["destino"]:
        filters.append("p.destino LIKE ?")
        params.append(f"%{args['destino']}%")
    if args["status"]:
        filters.append("p.status=?")
        params.append(args["status"])
    if args["categoria"]:
        filters.append("p.categoria LIKE ?")
        params.append(f"%{args['categoria']}%")
    if args["data"]:
        filters.append("(p.data_inicio=? OR p.data_fim=? OR p.validade=?)")
        params.extend([args["data"], args["data"], args["data"]])
    if args["destaque"]:
        filters.append("p.destaque=?")
        params.append(parse_bool(args["destaque"]))
    where = "WHERE " + " AND ".join(filters) if filters else ""
    promocoes = rows(
        f"""SELECT p.*, (SELECT arquivo FROM promocao_imagens i WHERE i.promocao_id=p.id ORDER BY principal DESC, COALESCE(ordem,id), id LIMIT 1) imagem
        FROM promocoes p {where} ORDER BY COALESCE(p.ordem,0), p.atualizado_em DESC""",
        params,
    )
    return render_template("admin_promocoes.html", promocoes=promocoes, args=args)


@app.route("/admin/promocoes/nova", methods=["GET", "POST"])
@admin_required
def nova_promocao():
    if request.method == "POST":
        promo_id = save_promotion()
        if promo_id:
            flash("Promocao salva.", "ok")
            return redirect(url_for("editar_promocao", id=promo_id))
    return render_template("admin_promocao_form.html", promo=None, imagens=[], inclusos=[], nao_inclusos=[], opcoes_inclusos=PROMO_INCLUSOS, opcoes_nao_inclusos=PROMO_NAO_INCLUSOS)


@app.route("/admin/promocoes/<int:id>/editar", methods=["GET", "POST"])
@admin_required
def editar_promocao(id):
    promo = one("SELECT * FROM promocoes WHERE id=?", (id,)) or abort(404)
    if request.method == "POST":
        promo_id = save_promotion(id)
        if promo_id:
            flash("Promocao atualizada.", "ok")
            return redirect(url_for("editar_promocao", id=id))
    lists = load_promo_lists(id)
    return render_template("admin_promocao_form.html", promo=promo, imagens=load_promo_images(id), opcoes_inclusos=PROMO_INCLUSOS, opcoes_nao_inclusos=PROMO_NAO_INCLUSOS, **lists)


@app.route("/admin/promocoes/<int:id>")
@admin_required
def visualizar_promocao_admin(id):
    promo = one("SELECT * FROM promocoes WHERE id=?", (id,)) or abort(404)
    cfg = one("SELECT * FROM configuracoes_empresa WHERE id=1")
    lists = load_promo_lists(id)
    return render_template("public_promocao.html", promo=promo, cfg=cfg, imagens=load_promo_images(id), **lists)


@app.route("/admin/promocoes/<int:id>/status", methods=["POST"])
@admin_required
def status_promocao(id):
    novo_status = request.form.get("status", "rascunho")
    now = datetime.utcnow().isoformat()
    db().execute(
        "UPDATE promocoes SET status=?, atualizado_em=?, publicado_em=CASE WHEN ?='publicada' AND publicado_em IS NULL THEN ? ELSE publicado_em END WHERE id=?",
        (novo_status, now, novo_status, now, id),
    )
    db().commit()
    return redirect(request.referrer or url_for("admin_promocoes"))


@app.route("/admin/promocoes/<int:id>/duplicar", methods=["POST"])
@admin_required
def duplicar_promocao(id):
    promo = one("SELECT * FROM promocoes WHERE id=?", (id,)) or abort(404)
    now = datetime.utcnow().isoformat()
    cols = [r["name"] for r in db().execute("PRAGMA table_info(promocoes)") if r["name"] not in ("id", "criado_em", "atualizado_em", "publicado_em", "status")]
    col_sql = ",".join(cols)
    cur = db().execute(
        f"INSERT INTO promocoes ({col_sql},status,criado_em,atualizado_em) SELECT {col_sql},'rascunho',?,? FROM promocoes WHERE id=?",
        (now, now, id),
    )
    new_id = cur.lastrowid
    db().execute("UPDATE promocoes SET titulo=? WHERE id=?", (promo["titulo"] + " (copia)", new_id))
    for table in ["promocao_inclusos", "promocao_nao_inclusos"]:
        cols = [r["name"] for r in db().execute(f"PRAGMA table_info({table})") if r["name"] not in ("id", "promocao_id")]
        db().execute(f"INSERT INTO {table} (promocao_id,{','.join(cols)}) SELECT ?,{','.join(cols)} FROM {table} WHERE promocao_id=?", (new_id, id))
    db().commit()
    flash("Promocao duplicada como rascunho.", "ok")
    return redirect(url_for("editar_promocao", id=new_id))


@app.route("/admin/promocoes/<int:id>/excluir", methods=["POST"])
@admin_required
def excluir_promocao(id):
    imagens = load_promo_images(id)
    db().execute("DELETE FROM promocoes WHERE id=?", (id,))
    db().commit()
    for image in imagens:
        remove_image_file(image["arquivo"])
    flash("Promocao excluida definitivamente.", "ok")
    return redirect(url_for("admin_promocoes"))


@app.route("/admin/usuarios", methods=["GET", "POST"])
@admin_required
def admin_usuarios():
    if request.method == "POST":
        f = request.form
        senha = f.get("senha", "")
        if not f.get("nome") or not f.get("email") or not senha:
            flash("Nome, e-mail e senha sao obrigatorios.", "error")
        else:
            now = datetime.utcnow().isoformat()
            db().execute(
                "INSERT INTO usuarios (nome,email,usuario,senha_hash,perfil,ativo,criado_em,atualizado_em) VALUES (?,?,?,?,?,?,?,?)",
                (f["nome"], f["email"], f.get("usuario") or None, generate_password_hash(senha), f.get("perfil", "atendente"), parse_bool(f.get("ativo", "1")), now, now),
            )
            db().commit()
            flash("Usuario criado.", "ok")
            return redirect(url_for("admin_usuarios"))
    return render_template("admin_usuarios.html", usuarios=rows("SELECT * FROM usuarios ORDER BY nome"))


@app.cli.command("criar-admin")
def criar_admin():
    nome = click.prompt("Nome")
    email = click.prompt("E-mail")
    usuario = click.prompt("Usuario", default=email.split("@")[0])
    senha = click.prompt("Senha", hide_input=True, confirmation_prompt=True)
    now = datetime.utcnow().isoformat()
    with app.app_context():
        init_db()
        db().execute(
            """INSERT INTO usuarios (nome,email,usuario,senha_hash,perfil,ativo,criado_em,atualizado_em)
            VALUES (?,?,?,?,?,?,?,?)""",
            (nome, email, usuario, generate_password_hash(senha), "administrador", 1, now, now),
        )
        db().commit()
    click.echo("Administrador criado com sucesso.")


if __name__ == "__main__":
    app.run(
        debug=True,
        use_reloader=True
    )