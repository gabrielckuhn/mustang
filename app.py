"""
Sistema pessoal de execução — habit tracker construído para reduzir a distância
entre "eu deveria estar fazendo isso" e "comecei".

Princípios do sistema (ver habit_tracker_eu.txt / persona_eu.txt):
- Menos tração -> menos informação na tela. A home é "Agora": uma prioridade.
- Ativação, não organização: botão "Começar 5 minutos" como porta de entrada.
- Modo Mustang: foco extremamente limpo, poucas decisões durante a execução.
- Métrica central é Tração (composta), não streak. Streak pune o primeiro dia ruim.
- Tempo para Engatar é rastreado como o gargalo real.
- Accountability social > gamificação artificial.
- Recuperação rápida: o sistema nunca lista atrasados, sempre pergunta "qual a
  próxima ação", mesmo quando o dia saiu do planejado.
"""

import sqlite3
from datetime import datetime, timedelta, date as date_cls

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

DB_PATH = "tracao.db"
FIVE_MIN_LABEL = "Começar 5 minutos"

# --------------------------------------------------------------------------
# Banco de dados
# --------------------------------------------------------------------------

@st.cache_resource
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    with conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY, value TEXT
            );
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT, description TEXT,
                active INTEGER DEFAULT 1, created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS priorities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT, title TEXT, project_id INTEGER,
                obrigatorio INTEGER DEFAULT 1,
                status TEXT DEFAULT 'pending',
                created_at TEXT, started_at TEXT, completed_at TEXT,
                order_idx INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS commitments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT, title TEXT, done INTEGER DEFAULT 0, created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS habits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT, active INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS habit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                habit_id INTEGER, date TEXT, done INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                priority_id INTEGER, start_time TEXT, end_time TEXT,
                duration_min REAL
            );
            CREATE TABLE IF NOT EXISTS ideas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT, created_at TEXT, reviewed INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS stuck_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                priority_id INTEGER, reason TEXT, created_at TEXT
            );
            """
        )


def q(sql, params=()):
    conn = get_conn()
    cur = conn.execute(sql, params)
    return cur.fetchall()


def run(sql, params=()):
    conn = get_conn()
    with conn:
        cur = conn.execute(sql, params)
    return cur.lastrowid


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def today_str():
    return date_cls.today().isoformat()


def get_setting(key, default=None):
    row = q("SELECT value FROM settings WHERE key=?", (key,))
    return row[0]["value"] if row else default


def set_setting(key, value):
    run(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


# --------------------------------------------------------------------------
# Tema / CSS — liquid glass, claro e escuro, persistido em settings
# --------------------------------------------------------------------------

def inject_theme():
    theme = st.session_state.get("theme", "dark")

    if theme == "dark":
        bg = "#0c0f14"
        bg_grad = "radial-gradient(circle at 15% 0%, #1a2230 0%, #0c0f14 55%), " \
                  "radial-gradient(circle at 85% 100%, #14202b 0%, #0c0f14 60%)"
        glass = "rgba(255,255,255,0.045)"
        glass_border = "rgba(255,255,255,0.09)"
        glass_strong = "rgba(255,255,255,0.07)"
        text_primary = "#eef1f5"
        text_secondary = "rgba(238,241,245,0.62)"
        text_faint = "rgba(238,241,245,0.38)"
        accent = "#8fb8ff"
        accent_soft = "rgba(143,184,255,0.16)"
        good = "#8fd8b0"
        warn = "#f0c07a"
        shadow = "0 20px 60px -25px rgba(0,0,0,0.65)"
    else:
        bg = "#f4f5f8"
        bg_grad = "radial-gradient(circle at 15% 0%, #ffffff 0%, #eef0f5 55%), " \
                   "radial-gradient(circle at 85% 100%, #fbfbfd 0%, #eef0f5 60%)"
        glass = "rgba(255,255,255,0.55)"
        glass_border = "rgba(20,25,35,0.08)"
        glass_strong = "rgba(255,255,255,0.75)"
        text_primary = "#191c22"
        text_secondary = "rgba(25,28,34,0.62)"
        text_faint = "rgba(25,28,34,0.40)"
        accent = "#3b66d6"
        accent_soft = "rgba(59,102,214,0.10)"
        good = "#1f9d63"
        warn = "#b5790f"
        shadow = "0 20px 50px -25px rgba(30,40,60,0.22)"

    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500&display=swap');

        html, body, [class*="css"] {{
            font-family: 'Manrope', -apple-system, BlinkMacSystemFont, sans-serif;
        }}

        .stApp {{
            background: {bg_grad};
            background-color: {bg};
            color: {text_primary};
        }}

        [data-testid="stSidebar"] {{
            background: {glass};
            border-right: 1px solid {glass_border};
            backdrop-filter: blur(24px);
        }}
        [data-testid="stSidebar"] * {{ color: {text_primary}; }}

        #MainMenu, footer, header {{ visibility: hidden; }}

        h1, h2, h3 {{
            font-weight: 700;
            letter-spacing: -0.02em;
            color: {text_primary};
        }}
        p, span, label, .stMarkdown {{ color: {text_secondary}; }}

        .glass-card {{
            background: {glass};
            border: 1px solid {glass_border};
            border-radius: 22px;
            padding: 28px 30px;
            backdrop-filter: blur(20px) saturate(140%);
            box-shadow: {shadow};
            margin-bottom: 18px;
            transition: transform 180ms ease, box-shadow 180ms ease;
        }}
        .glass-card.tight {{ padding: 16px 20px; }}

        .eyebrow {{
            font-size: 0.72rem;
            font-weight: 700;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            color: {text_faint};
            margin-bottom: 6px;
        }}

        .now-title {{
            font-size: 1.85rem;
            font-weight: 800;
            color: {text_primary};
            line-height: 1.25;
            margin: 2px 0 4px 0;
        }}
        .now-meta {{
            font-size: 0.85rem;
            color: {text_faint};
        }}

        .badge {{
            display: inline-block;
            font-size: 0.7rem;
            font-weight: 700;
            letter-spacing: 0.03em;
            padding: 3px 10px;
            border-radius: 100px;
            background: {accent_soft};
            color: {accent};
            margin-right: 6px;
        }}
        .badge.warn {{ background: rgba(240,192,122,0.16); color: {warn}; }}
        .badge.good {{ background: rgba(143,216,176,0.16); color: {good}; }}

        .metric-value {{
            font-size: 2.1rem;
            font-weight: 800;
            color: {text_primary};
            font-family: 'IBM Plex Mono', monospace;
        }}
        .metric-label {{
            font-size: 0.75rem;
            color: {text_faint};
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }}

        .stButton>button {{
            border-radius: 14px !important;
            border: 1px solid {glass_border} !important;
            background: {glass_strong} !important;
            color: {text_primary} !important;
            font-weight: 600 !important;
            padding: 10px 18px !important;
            backdrop-filter: blur(14px);
            transition: transform 120ms ease, background 160ms ease;
        }}
        .stButton>button:hover {{
            transform: translateY(-1px);
            border-color: {accent} !important;
        }}
        .stButton>button:active {{ transform: translateY(0px) scale(0.985); }}

        div[data-testid="stFormSubmitButton"] button,
        .primary-cta button {{
            background: linear-gradient(135deg, {accent}, {accent}) !important;
            color: #0c0f14 !important;
            border: none !important;
            font-weight: 700 !important;
        }}

        [data-testid="stVerticalBlockBorderWrapper"] {{
            border-radius: 18px !important;
            border: 1px solid {glass_border} !important;
            background: {glass} !important;
            backdrop-filter: blur(16px);
        }}

        hr {{ border-color: {glass_border}; }}

        .calm-empty {{
            text-align: center;
            padding: 46px 20px;
            color: {text_faint};
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------
# Camada de dados / regras de negócio
# --------------------------------------------------------------------------

def list_projects(active_only=True):
    sql = "SELECT * FROM projects" + (" WHERE active=1" if active_only else "")
    return q(sql + " ORDER BY name")


def create_project(name, description):
    run(
        "INSERT INTO projects (name, description, active, created_at) VALUES (?,?,1,?)",
        (name, description, now_iso()),
    )


def add_priority(title, date_val, project_id, obrigatorio=True):
    run(
        """INSERT INTO priorities (date, title, project_id, obrigatorio, status, created_at, order_idx)
           VALUES (?,?,?,?, 'pending', ?, (SELECT COALESCE(MAX(order_idx),0)+1 FROM priorities WHERE date=?))""",
        (date_val, title, project_id, int(obrigatorio), now_iso(), date_val),
    )


def add_commitment(title, date_val):
    run("INSERT INTO commitments (date, title, done, created_at) VALUES (?,?,0,?)",
        (title, date_val, now_iso()))


def get_open_session():
    rows = q(
        """SELECT s.*, p.title AS p_title, p.id AS p_id, p.obrigatorio, p.created_at AS p_created_at
           FROM sessions s JOIN priorities p ON p.id = s.priority_id
           WHERE s.end_time IS NULL ORDER BY s.id DESC LIMIT 1"""
    )
    return rows[0] if rows else None


def get_agora_priority():
    """Uma única prioridade. Prioriza obrigatórios pendentes mais antigos
    (retomada calma de atrasos), depois opcionais de hoje. Nunca lista tudo."""
    obrig = q(
        """SELECT * FROM priorities WHERE obrigatorio=1 AND status IN ('pending','started')
           ORDER BY date ASC, order_idx ASC, id ASC LIMIT 1"""
    )
    if obrig:
        return obrig[0]
    opc = q(
        """SELECT * FROM priorities WHERE date=? AND status IN ('pending','started')
           ORDER BY order_idx ASC, id ASC LIMIT 1""",
        (today_str(),),
    )
    return opc[0] if opc else None


def start_priority(priority_id):
    run("UPDATE priorities SET status='started', started_at=? WHERE id=? AND started_at IS NULL",
        (now_iso(), priority_id))
    run("INSERT INTO sessions (priority_id, start_time) VALUES (?, ?)", (priority_id, now_iso()))


def complete_open_session():
    sess = get_open_session()
    if not sess:
        return
    start = datetime.fromisoformat(sess["start_time"])
    end = datetime.now()
    duration = round((end - start).total_seconds() / 60, 1)
    run("UPDATE sessions SET end_time=?, duration_min=? WHERE id=?",
        (now_iso(), duration, sess["id"]))
    run("UPDATE priorities SET status='done', completed_at=? WHERE id=?",
        (now_iso(), sess["p_id"]))
    return duration


def abandon_open_session():
    """Encerra a sessão sem culpa — a prioridade volta para pendente."""
    sess = get_open_session()
    if not sess:
        return
    start = datetime.fromisoformat(sess["start_time"])
    duration = round((datetime.now() - start).total_seconds() / 60, 1)
    run("UPDATE sessions SET end_time=?, duration_min=? WHERE id=?",
        (now_iso(), duration, sess["id"]))
    run("UPDATE priorities SET status='pending', started_at=NULL WHERE id=?", (sess["p_id"],))


def log_stuck(priority_id, reason):
    run("INSERT INTO stuck_events (priority_id, reason, created_at) VALUES (?,?,?)",
        (priority_id, reason, now_iso()))


STUCK_INTERVENTIONS = {
    "Tédio": "Normal. Isso não pede motivação — pede 5 minutos. Volte para o cronômetro e comece só o próximo parágrafo/passo.",
    "Falta de clareza": "Você não precisa saber o caminho todo. Escreva abaixo apenas a primeira ação concreta e visível (ex: 'abrir o slide 1').",
    "Distração": "A interface foi reduzida de propósito. Feche as outras abas por 5 minutos — só isso, não precisa prometer mais que isso.",
    "Pensando em outra coisa": "Guarde essa ideia no Estacionamento agora (não precisa lembrar) e volte para esta única linha.",
    "Não sei por onde começar": "Escolha a menor ação possível que te deixaria com essa tarefa 1% mais perto de terminada. Só essa.",
}


def add_idea(text):
    run("INSERT INTO ideas (text, created_at, reviewed) VALUES (?,?,0)", (text, now_iso()))


def pending_ideas():
    return q("SELECT * FROM ideas WHERE reviewed=0 ORDER BY id DESC")


def mark_idea_reviewed(idea_id):
    run("UPDATE ideas SET reviewed=1 WHERE id=?", (idea_id,))


# --------------------------------------------------------------------------
# Métricas — Tração e Tempo para Engatar
# --------------------------------------------------------------------------

def compute_metrics(days=1):
    end = date_cls.today()
    start = end - timedelta(days=days - 1)
    start_s, end_s = start.isoformat(), end.isoformat()

    priorities = q("SELECT * FROM priorities WHERE date BETWEEN ? AND ?", (start_s, end_s))
    commitments = q("SELECT * FROM commitments WHERE date BETWEEN ? AND ?", (start_s, end_s))
    sessions = q(
        """SELECT s.* FROM sessions s JOIN priorities p ON p.id=s.priority_id
           WHERE p.date BETWEEN ? AND ? AND s.end_time IS NOT NULL""",
        (start_s, end_s),
    )

    n_priorities = len(priorities)
    n_started = sum(1 for p in priorities if p["status"] in ("started", "done"))
    n_done = sum(1 for p in priorities if p["status"] == "done")
    n_commit = len(commitments)
    n_commit_done = sum(1 for c in commitments if c["done"])
    total_focus_min = sum((s["duration_min"] or 0) for s in sessions)
    avg_focus_min = (total_focus_min / len(sessions)) if sessions else 0.0

    engage_times = []
    for p in priorities:
        if p["started_at"] and p["created_at"]:
            delta = (datetime.fromisoformat(p["started_at"]) - datetime.fromisoformat(p["created_at"])).total_seconds() / 60
            if delta >= 0:
                engage_times.append(delta)
    avg_engage_min = sum(engage_times) / len(engage_times) if engage_times else None

    pct_commit = (n_commit_done / n_commit * 100) if n_commit else None
    pct_started = (n_started / n_priorities * 100) if n_priorities else None
    pct_done = (n_done / n_priorities * 100) if n_priorities else None

    # Tração: composta, pondera início mais do que conclusão, foco, e
    # compromissos cumpridos; tempo para engatar entra invertido (quanto
    # menor, melhor) normalizado contra um teto de 60 minutos.
    score_start = (pct_started or 0)
    score_done = (pct_done or 0)
    score_commit = (pct_commit if pct_commit is not None else 70)
    score_focus = min(total_focus_min / 90 * 100, 100) if total_focus_min else 0
    if avg_engage_min is not None:
        score_engage = max(0, 100 - min(avg_engage_min, 60) / 60 * 100)
    else:
        score_engage = 60  # neutro quando não há dado suficiente

    tracao = round(
        0.30 * score_start + 0.20 * score_done + 0.20 * score_commit
        + 0.15 * score_focus + 0.15 * score_engage, 1
    )

    return {
        "n_priorities": n_priorities, "n_started": n_started, "n_done": n_done,
        "n_commit": n_commit, "n_commit_done": n_commit_done,
        "total_focus_min": round(total_focus_min, 1),
        "avg_focus_min": round(avg_focus_min, 1),
        "avg_engage_min": round(avg_engage_min, 1) if avg_engage_min is not None else None,
        "pct_commit": pct_commit, "pct_started": pct_started, "pct_done": pct_done,
        "tracao": tracao,
    }


def daily_series(days=14):
    rows = []
    for i in range(days - 1, -1, -1):
        d = date_cls.today() - timedelta(days=i)
        m = compute_metrics_for_single_day(d)
        rows.append({"data": d.isoformat(), "tracao": m["tracao"],
                     "tempo_engatar": m["avg_engage_min"], "foco_min": m["total_focus_min"]})
    return pd.DataFrame(rows)


def compute_metrics_for_single_day(d: date_cls):
    d_s = d.isoformat()
    priorities = q("SELECT * FROM priorities WHERE date=?", (d_s,))
    commitments = q("SELECT * FROM commitments WHERE date=?", (d_s,))
    sessions = q(
        """SELECT s.* FROM sessions s JOIN priorities p ON p.id=s.priority_id
           WHERE p.date=? AND s.end_time IS NOT NULL""", (d_s,)
    )
    n_priorities = len(priorities)
    n_started = sum(1 for p in priorities if p["status"] in ("started", "done"))
    n_done = sum(1 for p in priorities if p["status"] == "done")
    n_commit = len(commitments)
    n_commit_done = sum(1 for c in commitments if c["done"])
    total_focus_min = sum((s["duration_min"] or 0) for s in sessions)

    engage_times = []
    for p in priorities:
        if p["started_at"] and p["created_at"]:
            delta = (datetime.fromisoformat(p["started_at"]) - datetime.fromisoformat(p["created_at"])).total_seconds() / 60
            if delta >= 0:
                engage_times.append(delta)
    avg_engage_min = sum(engage_times) / len(engage_times) if engage_times else None

    pct_commit = (n_commit_done / n_commit * 100) if n_commit else None
    pct_started = (n_started / n_priorities * 100) if n_priorities else None
    pct_done = (n_done / n_priorities * 100) if n_priorities else None

    score_start = (pct_started or 0)
    score_done = (pct_done or 0)
    score_commit = (pct_commit if pct_commit is not None else 70)
    score_focus = min(total_focus_min / 90 * 100, 100) if total_focus_min else 0
    score_engage = max(0, 100 - min(avg_engage_min, 60) / 60 * 100) if avg_engage_min is not None else 60

    tracao = round(
        0.30 * score_start + 0.20 * score_done + 0.20 * score_commit
        + 0.15 * score_focus + 0.15 * score_engage, 1
    )
    return {"tracao": tracao, "avg_engage_min": round(avg_engage_min, 1) if avg_engage_min is not None else None,
            "total_focus_min": round(total_focus_min, 1)}


def build_daily_report(d: date_cls = None):
    d = d or date_cls.today()
    m = compute_metrics_for_single_day(d)
    priorities = q("SELECT * FROM priorities WHERE date=?", (d.isoformat(),))
    commitments = q("SELECT * FROM commitments WHERE date=?", (d.isoformat(),))
    done = [p for p in priorities if p["status"] == "done"]
    started_not_done = [p for p in priorities if p["status"] == "started"]
    pending = [p for p in priorities if p["status"] == "pending"]

    lines = [
        f"Relatório do dia — {d.strftime('%d/%m/%Y')}",
        "",
        f"Tração: {m['tracao']}/100",
        f"Tempo para engatar (médio): {m['avg_engage_min']} min" if m['avg_engage_min'] is not None else "Tempo para engatar: sem dados suficientes",
        f"Tempo total em foco: {m['total_focus_min']} min",
        "",
        f"Prioridades planejadas: {len(priorities)} | concluídas: {len(done)} | iniciadas: {len(started_not_done)} | não iniciadas: {len(pending)}",
    ]
    if done:
        lines.append("\nConcluídas:")
        lines += [f"  ✓ {p['title']}" for p in done]
    if pending:
        lines.append("\nNão iniciadas (sem drama — seguem para retomada):")
        lines += [f"  · {p['title']}" for p in pending]

    if commitments:
        n_done_c = sum(1 for c in commitments if c["done"])
        lines.append(f"\nCompromissos: {n_done_c}/{len(commitments)} cumpridos")
        for c in commitments:
            mark = "✓" if c["done"] else "·"
            lines.append(f"  {mark} {c['title']}")

    return "\n".join(lines)


# --------------------------------------------------------------------------
# Componentes de UI
# --------------------------------------------------------------------------

def live_timer(start_time_iso, accent="#8fb8ff", text_color="#eef1f5"):
    components.html(
        f"""
        <div id="timer" style="font-family:'IBM Plex Mono',monospace;font-size:3rem;
             font-weight:700;color:{text_color};letter-spacing:0.02em;">00:00</div>
        <script>
        const start = new Date("{start_time_iso}").getTime();
        function tick() {{
            const now = new Date().getTime();
            let diff = Math.max(0, Math.floor((now - start) / 1000));
            const m = String(Math.floor(diff / 60)).padStart(2, '0');
            const s = String(diff % 60).padStart(2, '0');
            document.getElementById('timer').innerText = m + ":" + s;
        }}
        setInterval(tick, 1000);
        tick();
        </script>
        """,
        height=80,
    )


def eyebrow(text):
    st.markdown(f'<div class="eyebrow">{text}</div>', unsafe_allow_html=True)


def glass_open(extra_class=""):
    st.markdown(f'<div class="glass-card {extra_class}">', unsafe_allow_html=True)


def glass_close():
    st.markdown("</div>", unsafe_allow_html=True)


def sidebar_idea_capture():
    with st.sidebar.expander("💡 Estacionar uma ideia", expanded=False):
        txt = st.text_area("O que apareceu?", key="idea_quick", label_visibility="collapsed",
                            placeholder="Guarde aqui e volte pro que importa agora.")
        agora = get_agora_priority()
        if st.button("Guardar ideia", key="save_idea_btn", use_container_width=True):
            if txt.strip():
                add_idea(txt.strip())
                st.session_state.idea_quick = ""
                if agora and agora["status"] in ("pending", "started"):
                    st.toast("Ideia guardada. Sua prioridade continua sendo: " + agora["title"])
                else:
                    st.toast("Ideia guardada.")
                st.rerun()


# --------------------------------------------------------------------------
# Páginas
# --------------------------------------------------------------------------

def page_agora():
    open_sess = get_open_session()

    if open_sess:
        render_mustang_mode(open_sess)
        return

    agora = get_agora_priority()

    if not agora:
        glass_open()
        st.markdown(
            '<div class="calm-empty">'
            '<div class="eyebrow">Agora</div>'
            '<div class="now-title" style="font-size:1.3rem;">Nada pedindo sua atenção neste instante.</div>'
            '<p>Adicione uma prioridade em "Hoje" quando quiser, ou aproveite a pausa.</p>'
            '</div>', unsafe_allow_html=True
        )
        glass_close()
        return

    is_retomada = agora["date"] != today_str()
    proj = None
    if agora["project_id"]:
        rows = q("SELECT name FROM projects WHERE id=?", (agora["project_id"],))
        proj = rows[0]["name"] if rows else None

    glass_open()
    eyebrow("Retomando" if is_retomada else "Agora")
    st.markdown(f'<div class="now-title">{agora["title"]}</div>', unsafe_allow_html=True)
    badges = ""
    if proj:
        badges += f'<span class="badge">{proj}</span>'
    badges += '<span class="badge warn">obrigatório</span>' if agora["obrigatorio"] else '<span class="badge">opcional</span>'
    st.markdown(f'<div style="margin:10px 0 18px 0;">{badges}</div>', unsafe_allow_html=True)

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button(f"▶  {FIVE_MIN_LABEL}", use_container_width=True, type="primary"):
            start_priority(agora["id"])
            st.rerun()
    with col2:
        with st.popover("Não é essa agora"):
            st.caption("Escolha outra prioridade obrigatória de hoje, se houver.")
            outras = q(
                "SELECT * FROM priorities WHERE date=? AND status='pending' AND id!=? ORDER BY order_idx",
                (today_str(), agora["id"]),
            )
            if not outras:
                st.write("Não há outra prioridade cadastrada para hoje.")
            for o in outras:
                if st.button(o["title"], key=f"swap_{o['id']}"):
                    run("UPDATE priorities SET order_idx = order_idx - 1000 WHERE id=?", (o["id"],))
                    st.rerun()
    glass_close()

    n_pending = q(
        "SELECT COUNT(*) c FROM priorities WHERE status IN ('pending','started') AND date<=?",
        (today_str(),),
    )[0]["c"]
    if n_pending > 1:
        st.caption(f"Existem outras {n_pending - 1} prioridades esperando — elas aparecerão uma de cada vez.")


def render_mustang_mode(sess):
    st.markdown('<div class="eyebrow">Modo Mustang — foco</div>', unsafe_allow_html=True)
    theme = st.session_state.get("theme", "dark")
    accent = "#8fb8ff" if theme == "dark" else "#3b66d6"
    text_color = "#eef1f5" if theme == "dark" else "#191c22"

    glass_open()
    st.markdown(f'<div class="now-title" style="font-size:1.5rem;">{sess["p_title"]}</div>', unsafe_allow_html=True)
    live_timer(sess["start_time"], accent, text_color)

    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("✓ Concluir", use_container_width=True, type="primary"):
            duration = complete_open_session()
            st.session_state["last_completed_duration"] = duration
            st.rerun()
    with col2:
        with st.popover("Estou travado"):
            st.caption("Qual é o tipo de trava agora?")
            reason = st.radio("motivo", list(STUCK_INTERVENTIONS.keys()),
                               label_visibility="collapsed", key="stuck_reason")
            if st.button("Registrar e ver o que fazer", key="stuck_confirm"):
                log_stuck(sess["p_id"], reason)
                st.session_state["stuck_message"] = STUCK_INTERVENTIONS[reason]
    with col3:
        if st.button("Encerrar sem concluir", use_container_width=True):
            abandon_open_session()
            st.rerun()

    if st.session_state.get("stuck_message"):
        st.info(st.session_state["stuck_message"])
        if st.button("Ok, entendi"):
            st.session_state["stuck_message"] = None
            st.rerun()

    glass_close()
    st.caption("A interface está reduzida de propósito. Só isto importa agora.")


def page_hoje():
    st.markdown('<div class="eyebrow">Hoje</div>', unsafe_allow_html=True)
    st.markdown('<h2 style="margin-top:-6px;">O que compõe o dia</h2>', unsafe_allow_html=True)

    with st.expander("+ Adicionar prioridade ou compromisso"):
        tab1, tab2 = st.tabs(["Prioridade", "Compromisso"])
        with tab1:
            with st.form("form_priority", clear_on_submit=True):
                title = st.text_input("Título da prioridade")
                projects = list_projects()
                proj_opts = {"— sem projeto —": None} | {p["name"]: p["id"] for p in projects}
                proj_choice = st.selectbox("Projeto (opcional)", list(proj_opts.keys()))
                obrig = st.checkbox("Obrigatório", value=True)
                if st.form_submit_button("Adicionar prioridade"):
                    if title.strip():
                        add_priority(title.strip(), today_str(), proj_opts[proj_choice], obrig)
                        st.rerun()
        with tab2:
            with st.form("form_commit", clear_on_submit=True):
                ctitle = st.text_input("Compromisso")
                if st.form_submit_button("Adicionar compromisso"):
                    if ctitle.strip():
                        add_commitment(ctitle.strip(), today_str())
                        st.rerun()

    st.markdown("")
    col_a, col_b = st.columns(2)

    with col_a:
        glass_open("tight")
        st.markdown("**Prioridades de hoje**")
        rows = q("SELECT * FROM priorities WHERE date=? ORDER BY obrigatorio DESC, order_idx",
                  (today_str(),))
        if not rows:
            st.caption("Nenhuma prioridade cadastrada ainda.")
        for r in rows:
            icon = {"pending": "○", "started": "◐", "done": "●"}[r["status"]]
            tag = "obrigatório" if r["obrigatorio"] else "opcional"
            st.markdown(f"{icon} {r['title']}  ·  *{tag}*")
        glass_close()

    with col_b:
        glass_open("tight")
        st.markdown("**Compromissos de hoje**")
        crows = q("SELECT * FROM commitments WHERE date=? ORDER BY id", (today_str(),))
        if not crows:
            st.caption("Nenhum compromisso cadastrado ainda.")
        for c in crows:
            checked = st.checkbox(c["title"], value=bool(c["done"]), key=f"commit_{c['id']}")
            if checked != bool(c["done"]):
                run("UPDATE commitments SET done=? WHERE id=?", (int(checked), c["id"]))
                st.rerun()
        glass_close()


def page_semana():
    st.markdown('<div class="eyebrow">Semana</div>', unsafe_allow_html=True)
    st.markdown('<h2 style="margin-top:-6px;">O que está sendo construído</h2>', unsafe_allow_html=True)

    today = date_cls.today()
    monday = today - timedelta(days=today.weekday())
    days = [monday + timedelta(days=i) for i in range(7)]

    cols = st.columns(7)
    for i, d in enumerate(days):
        with cols[i]:
            m = compute_metrics_for_single_day(d)
            label = d.strftime("%a")[:3].capitalize()
            is_today = d == today
            glass_open("tight" + (" " if is_today else ""))
            st.markdown(f"**{label}**  \n<span style='font-size:0.75rem;color:rgba(150,150,150,0.8)'>{d.strftime('%d/%m')}</span>",
                        unsafe_allow_html=True)
            st.markdown(f'<div class="metric-value" style="font-size:1.4rem;">{m["tracao"]}</div>', unsafe_allow_html=True)
            st.caption("tração")
            glass_close()


def page_projetos():
    st.markdown('<div class="eyebrow">Projetos</div>', unsafe_allow_html=True)
    st.markdown('<h2 style="margin-top:-6px;">Blocos de longo prazo</h2>', unsafe_allow_html=True)

    with st.expander("+ Novo projeto"):
        with st.form("form_project", clear_on_submit=True):
            name = st.text_input("Nome do projeto (ex: Preventiva — PSF)")
            desc = st.text_area("Descrição / conteúdos / período")
            if st.form_submit_button("Criar projeto"):
                if name.strip():
                    create_project(name.strip(), desc.strip())
                    st.rerun()

    projects = list_projects()
    if not projects:
        st.caption("Nenhum projeto cadastrado ainda.")
    for p in projects:
        glass_open("tight")
        c1, c2 = st.columns([3, 1])
        with c1:
            st.markdown(f"**{p['name']}**")
            if p["description"]:
                st.caption(p["description"])
            n_sessions = q(
                "SELECT COUNT(*) c FROM priorities WHERE project_id=? AND status='done'", (p["id"],)
            )[0]["c"]
            st.caption(f"{n_sessions} sessões concluídas")
        with c2:
            if st.button("Gerar sessão para hoje", key=f"gen_{p['id']}"):
                add_priority(f"Sessão — {p['name']}", today_str(), p["id"], obrigatorio=True)
                st.rerun()
        glass_close()


def page_dados():
    st.markdown('<div class="eyebrow">Dados</div>', unsafe_allow_html=True)
    st.markdown('<h2 style="margin-top:-6px;">O espelho, não o fiscal</h2>', unsafe_allow_html=True)

    period = st.radio("Período", ["7 dias", "14 dias", "30 dias"], horizontal=True, label_visibility="collapsed")
    days = {"7 dias": 7, "14 dias": 14, "30 dias": 30}[period]
    m = compute_metrics(days)

    cols = st.columns(5)
    metrics_display = [
        ("Tração", f"{m['tracao']}", ""),
        ("Tempo p/ engatar", f"{m['avg_engage_min']}" if m['avg_engage_min'] is not None else "—", "min"),
        ("Foco médio/sessão", f"{m['avg_focus_min']}", "min"),
        ("Compromissos", f"{m['pct_commit']:.0f}" if m['pct_commit'] is not None else "—", "%"),
        ("Iniciadas", f"{m['pct_started']:.0f}" if m['pct_started'] is not None else "—", "%"),
    ]
    for c, (label, val, unit) in zip(cols, metrics_display):
        with c:
            glass_open("tight")
            st.markdown(f'<div class="metric-value">{val}<span style="font-size:1rem;">{unit}</span></div>',
                        unsafe_allow_html=True)
            st.markdown(f'<div class="metric-label">{label}</div>', unsafe_allow_html=True)
            glass_close()

    st.markdown("")
    df = daily_series(days=days)
    glass_open()
    st.markdown("**Evolução da Tração**")
    if df["tracao"].notna().any():
        st.line_chart(df.set_index("data")["tracao"])
    else:
        st.caption("Ainda sem dados suficientes.")
    glass_close()

    glass_open()
    st.markdown("**Tempo para Engatar — a métrica que importa**")
    st.caption("Se essa linha estiver caindo, você está ficando melhor em começar — mesmo que o total de horas não mude muito.")
    df_engage = df.dropna(subset=["tempo_engatar"])
    if not df_engage.empty:
        st.line_chart(df_engage.set_index("data")["tempo_engatar"])
    else:
        st.caption("Ainda sem dados suficientes — comece algumas prioridades para ver essa métrica nascer.")
    glass_close()


def page_ideias():
    st.markdown('<div class="eyebrow">Estacionamento de Ideias</div>', unsafe_allow_html=True)
    st.markdown('<h2 style="margin-top:-6px;">Curiosidade protegida, prioridade preservada</h2>', unsafe_allow_html=True)

    with st.form("form_idea_page", clear_on_submit=True):
        txt = st.text_area("Nova ideia")
        if st.form_submit_button("Guardar"):
            if txt.strip():
                add_idea(txt.strip())
                st.rerun()

    ideas = pending_ideas()
    if not ideas:
        st.caption("Nada estacionado no momento.")
    for i in ideas:
        glass_open("tight")
        c1, c2 = st.columns([4, 1])
        with c1:
            st.write(i["text"])
            st.caption(datetime.fromisoformat(i["created_at"]).strftime("%d/%m %H:%M"))
        with c2:
            if st.button("Revisada", key=f"rev_{i['id']}"):
                mark_idea_reviewed(i["id"])
                st.rerun()
        glass_close()


def page_relatorio():
    st.markdown('<div class="eyebrow">Relatório do dia</div>', unsafe_allow_html=True)
    st.markdown('<h2 style="margin-top:-6px;">Accountability, não vigilância</h2>', unsafe_allow_html=True)

    report = build_daily_report()
    glass_open()
    st.text_area("Copie e envie para quem cobra você", report, height=340)
    st.download_button("Baixar relatório (.txt)", report, file_name=f"relatorio_{today_str()}.txt")
    glass_close()


def page_config():
    st.markdown('<div class="eyebrow">Configurações</div>', unsafe_allow_html=True)

    glass_open()
    st.markdown("**Aparência**")
    theme = st.radio("Tema", ["dark", "light"], horizontal=True,
                      index=0 if st.session_state.get("theme", "dark") == "dark" else 1,
                      format_func=lambda x: "Escuro" if x == "dark" else "Claro")
    if theme != st.session_state.get("theme"):
        st.session_state.theme = theme
        set_setting("theme", theme)
        st.rerun()
    glass_close()

    glass_open()
    st.markdown("**Zona de risco**")
    st.caption("Isso apaga todos os dados do sistema. Sem volta.")
    confirm = st.checkbox("Confirmo que quero apagar tudo")
    if st.button("Resetar todos os dados", disabled=not confirm):
        conn = get_conn()
        with conn:
            for t in ["priorities", "commitments", "sessions", "ideas", "stuck_events", "habit_logs"]:
                conn.execute(f"DELETE FROM {t}")
        st.success("Dados apagados.")
        st.rerun()
    glass_close()


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main():
    st.set_page_config(page_title="Tração", page_icon="◐", layout="centered")
    init_db()

    if "theme" not in st.session_state:
        st.session_state.theme = get_setting("theme", "dark")

    inject_theme()

    st.sidebar.markdown(
        '<div style="padding:10px 4px 20px 4px;">'
        '<div style="font-size:1.3rem;font-weight:800;">◐ Tração</div>'
        '<div style="font-size:0.78rem;opacity:0.6;">sistema pessoal de execução</div>'
        '</div>', unsafe_allow_html=True
    )

    pages = {
        "Agora": page_agora,
        "Hoje": page_hoje,
        "Semana": page_semana,
        "Projetos": page_projetos,
        "Dados": page_dados,
        "Estacionamento de Ideias": page_ideias,
        "Relatório do dia": page_relatorio,
        "Configurações": page_config,
    }
    choice = st.sidebar.radio("Navegação", list(pages.keys()), label_visibility="collapsed")
    sidebar_idea_capture()

    pages[choice]()


if __name__ == "__main__":
    main()
