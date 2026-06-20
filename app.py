import json
import sqlite3
from datetime import datetime
from pathlib import Path
from flask import Flask, g, redirect, render_template, request, url_for, abort, flash

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "triotour.db"
app = Flask(__name__)
app.config["SECRET_KEY"] = "triotour-dev-secret"

DEFAULT_TERMS = """Valores sujeitos à alteração sem aviso prévio.\nReserva sujeita à disponibilidade.\nDocumentação de responsabilidade do passageiro.\nTaxas não inclusas, se aplicável.\nPolítica de cancelamento conforme fornecedores.\nCondições de pagamento conforme proposta."""
DEFAULT_ITEMS = ["Passagem aérea", "Passagem rodoviária", "Hospedagem", "Café da manhã", "Traslados", "City tour", "Guia acompanhante", "Seguro viagem", "Passeios", "Ingressos", "Bagagem"]


def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_=None):
    conn = g.pop("db", None)
    if conn:
        conn.close()


def init_db():
    conn = db()
    conn.executescript('''
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
        termos TEXT, nao_inclusos TEXT, criado_em TEXT NOT NULL, atualizado_em TEXT NOT NULL,
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
    CREATE TABLE IF NOT EXISTS termos (id INTEGER PRIMARY KEY AUTOINCREMENT, texto TEXT NOT NULL);
    ''')
    conn.execute("INSERT OR IGNORE INTO configuracoes_empresa (id,nome,telefone,whatsapp,email,instagram,endereco,slogan,termos_padrao) VALUES (1,?,?,?,?,?,?,?,?)",
                 ("Triotour", "", "", "", "", "", "Sua próxima viagem começa aqui", DEFAULT_TERMS))
    conn.commit()


@app.before_request
def before():
    init_db()


def rows(query, args=()):
    return db().execute(query, args).fetchall()

def one(query, args=()):
    return db().execute(query, args).fetchone()

def br_date(value):
    if not value: return ""
    try: return datetime.strptime(value, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError: return value

def money(value):
    try:
        s = f"{float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"R$ {s}"
    except (TypeError, ValueError): return "R$ 0,00"

app.jinja_env.filters["br_date"] = br_date
app.jinja_env.filters["money"] = money

@app.route("/")
def index():
    q = request.args.get("q", "").strip()
    sql = """SELECT p.*, c.nome cliente FROM propostas p JOIN clientes c ON c.id=p.cliente_id
             WHERE (?='' OR c.nome LIKE ? OR p.destino LIKE ? OR p.data_inicio LIKE ?) ORDER BY p.atualizado_em DESC"""
    props = rows(sql, (q, f"%{q}%", f"%{q}%", f"%{q}%"))
    return render_template("index.html", propostas=props, q=q)

@app.route("/clientes", methods=["GET", "POST"])
def clientes():
    if request.method == "POST":
        f = request.form
        if not f.get("nome"):
            flash("Nome do cliente é obrigatório.", "error")
        else:
            db().execute("INSERT INTO clientes (nome,telefone,email,documento,observacoes,criado_em) VALUES (?,?,?,?,?,?)",
                         (f["nome"], f.get("telefone"), f.get("email"), f.get("documento"), f.get("observacoes"), datetime.utcnow().isoformat()))
            db().commit(); flash("Cliente salvo.", "ok"); return redirect(url_for("clientes"))
    return render_template("clientes.html", clientes=rows("SELECT * FROM clientes ORDER BY nome"))

@app.route("/clientes/<int:id>/editar", methods=["POST"])
def editar_cliente(id):
    f=request.form
    db().execute("UPDATE clientes SET nome=?,telefone=?,email=?,documento=?,observacoes=? WHERE id=?", (f["nome"],f.get("telefone"),f.get("email"),f.get("documento"),f.get("observacoes"),id))
    db().commit(); return redirect(url_for("clientes"))

@app.route("/propostas")
def propostas():
    args = {k: request.args.get(k, "").strip() for k in ["cliente","destino","tipo","data","status"]}
    props = rows("""SELECT p.*, c.nome cliente FROM propostas p JOIN clientes c ON c.id=p.cliente_id
    WHERE (?='' OR c.nome LIKE ?) AND (?='' OR p.destino LIKE ?) AND (?='' OR p.tipo=?) AND (?='' OR p.data_inicio=?) AND (?='' OR p.status=?)
    ORDER BY p.atualizado_em DESC""", (args['cliente'],f"%{args['cliente']}%",args['destino'],f"%{args['destino']}%",args['tipo'],args['tipo'],args['data'],args['data'],args['status'],args['status']))
    return render_template("propostas.html", propostas=props, args=args)

@app.route("/propostas/nova/<tipo>", methods=["GET","POST"])
def form_proposta(tipo):
    if tipo not in ("cotacao","pacote"): abort(404)
    if request.method == "POST":
        return save_proposta(tipo)
    return render_template("form_proposta.html", tipo=tipo, proposta=None, clientes=rows("SELECT * FROM clientes ORDER BY nome"), cfg=one("SELECT * FROM configuracoes_empresa WHERE id=1"), default_items=DEFAULT_ITEMS)

@app.route("/propostas/<int:id>/editar", methods=["GET","POST"])
def edit_proposta(id):
    prop = one("SELECT * FROM propostas WHERE id=?", (id,)) or abort(404)
    if request.method == "POST": return save_proposta(prop["tipo"], id)
    return render_template("form_proposta.html", tipo=prop["tipo"], proposta=load_prop(id), clientes=rows("SELECT * FROM clientes ORDER BY nome"), cfg=one("SELECT * FROM configuracoes_empresa WHERE id=1"), default_items=DEFAULT_ITEMS)

def save_proposta(tipo, id=None):
    f=request.form; required=["cliente_id","origem","destino","data_inicio","valor_total"]
    if any(not f.get(k) for k in required):
        flash("Preencha os campos obrigatórios.", "error"); return redirect(request.url)
    now=datetime.utcnow().isoformat(); titulo=f.get("titulo") or ("Cotação de passagem" if tipo=="cotacao" else f.get("nome_pacote") or "Pacote de viagem")
    data=(tipo, f.get("status","rascunho"), f["cliente_id"], titulo, f.get("subtipo"), f["origem"], f["destino"], f["data_inicio"], f.get("data_fim"), f.get("dias_noites"), f.get("bagagem"), f.get("valor_total") or 0, f.get("valor_parcelado") or 0, f.get("parcelas") or 1, f.get("termos"), f.get("nao_inclusos"), now)
    if id:
        db().execute("UPDATE propostas SET tipo=?,status=?,cliente_id=?,titulo=?,subtipo=?,origem=?,destino=?,data_inicio=?,data_fim=?,dias_noites=?,bagagem=?,valor_total=?,valor_parcelado=?,parcelas=?,termos=?,nao_inclusos=?,atualizado_em=? WHERE id=?", data+(id,))
    else:
        cur=db().execute("INSERT INTO propostas (tipo,status,cliente_id,titulo,subtipo,origem,destino,data_inicio,data_fim,dias_noites,bagagem,valor_total,valor_parcelado,parcelas,termos,nao_inclusos,criado_em,atualizado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", data+(now,)); id=cur.lastrowid
    db().execute("DELETE FROM transportes WHERE proposta_id=?",(id,)); db().execute("DELETE FROM hospedagens WHERE proposta_id=?",(id,)); db().execute("DELETE FROM roteiro_dias WHERE proposta_id=?",(id,)); db().execute("DELETE FROM itens_inclusos WHERE proposta_id=?",(id,))
    for trecho in ("ida","volta"):
        db().execute("INSERT INTO transportes (proposta_id,trecho,data,horario,companhia,identificacao) VALUES (?,?,?,?,?,?)", (id,trecho,f.get(f"{trecho}_data"),f.get(f"{trecho}_horario"),f.get(f"{trecho}_companhia"),f.get(f"{trecho}_identificacao")))
    if tipo=="pacote":
        db().execute("INSERT INTO hospedagens (proposta_id,nome,checkin,checkout,quarto,alimentacao) VALUES (?,?,?,?,?,?)", (id,f.get("hospedagem_nome"),f.get("checkin"),f.get("checkout"),f.get("quarto"),f.get("alimentacao")))
        for i, dia in enumerate(json.loads(f.get("roteiro_json") or "[]"), start=1):
            db().execute("INSERT INTO roteiro_dias (proposta_id,ordem,dia,data,local,titulo,descricao,horario,observacoes) VALUES (?,?,?,?,?,?,?,?,?)", (id,i,dia.get('dia'),dia.get('data'),dia.get('local'),dia.get('titulo'),dia.get('descricao'),dia.get('horario'),dia.get('observacoes')))
    for item in request.form.getlist("itens") + [x.strip() for x in f.get("itens_custom","").split(",") if x.strip()]:
        db().execute("INSERT INTO itens_inclusos (proposta_id,nome) VALUES (?,?)",(id,item))
    db().commit(); flash("Proposta salva.", "ok"); return redirect(url_for("view_proposta", id=id))

def load_prop(id):
    prop=dict(one("SELECT p.*, c.nome cliente, c.telefone, c.email, c.documento, c.observacoes cliente_obs FROM propostas p JOIN clientes c ON c.id=p.cliente_id WHERE p.id=?",(id,)) or abort(404))
    prop["transportes"]={r["trecho"]:dict(r) for r in rows("SELECT * FROM transportes WHERE proposta_id=?",(id,))}
    prop["hospedagem"]=one("SELECT * FROM hospedagens WHERE proposta_id=?",(id,))
    prop["roteiro"]=rows("SELECT * FROM roteiro_dias WHERE proposta_id=? ORDER BY ordem",(id,))
    prop["roteiro_json"]=[dict(r) for r in prop["roteiro"]]
    prop["itens"]=rows("SELECT * FROM itens_inclusos WHERE proposta_id=?",(id,))
    return prop

@app.route("/propostas/<int:id>")
def view_proposta(id):
    return render_template("documento.html", p=load_prop(id), cfg=one("SELECT * FROM configuracoes_empresa WHERE id=1"), emissao=datetime.now())

@app.route("/propostas/<int:id>/duplicar", methods=["POST"])
def duplicar(id):
    p=load_prop(id); now=datetime.utcnow().isoformat()
    cur=db().execute("INSERT INTO propostas (tipo,status,cliente_id,titulo,subtipo,origem,destino,data_inicio,data_fim,dias_noites,bagagem,valor_total,valor_parcelado,parcelas,termos,nao_inclusos,criado_em,atualizado_em) SELECT tipo,'rascunho',cliente_id,titulo||' (cópia)',subtipo,origem,destino,data_inicio,data_fim,dias_noites,bagagem,valor_total,valor_parcelado,parcelas,termos,nao_inclusos,?,? FROM propostas WHERE id=?",(now,now,id)); nid=cur.lastrowid
    for table in ["transportes","hospedagens","roteiro_dias","itens_inclusos"]:
        cols=[r[1] for r in db().execute(f"PRAGMA table_info({table})") if r[1] not in ('id','proposta_id')]
        db().execute(f"INSERT INTO {table} (proposta_id,{','.join(cols)}) SELECT ?,{','.join(cols)} FROM {table} WHERE proposta_id=?",(nid,id))
    db().commit(); return redirect(url_for("edit_proposta", id=nid))

@app.route("/propostas/<int:id>/status", methods=["POST"])
def status(id):
    db().execute("UPDATE propostas SET status=?, atualizado_em=? WHERE id=?",(request.form['status'],datetime.utcnow().isoformat(),id)); db().commit(); return redirect(request.referrer or url_for('propostas'))

@app.route("/propostas/<int:id>/excluir", methods=["POST"])
def excluir(id):
    db().execute("DELETE FROM propostas WHERE id=?",(id,)); db().commit(); return redirect(url_for("propostas"))

@app.route("/configuracoes", methods=["GET","POST"])
def configuracoes():
    if request.method=="POST":
        f=request.form
        db().execute("UPDATE configuracoes_empresa SET nome=?,telefone=?,whatsapp=?,email=?,instagram=?,endereco=?,slogan=?,logo=?,termos_padrao=? WHERE id=1", (f['nome'],f.get('telefone'),f.get('whatsapp'),f.get('email'),f.get('instagram'),f.get('endereco'),f.get('slogan'),f.get('logo'),f.get('termos_padrao')))
        db().commit(); flash("Configurações salvas.", "ok")
    return render_template("configuracoes.html", cfg=one("SELECT * FROM configuracoes_empresa WHERE id=1"))

if __name__ == "__main__":
    app.run(debug=True)
