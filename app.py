from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import streamlit as st

# =========================================================
# CONFIG
# =========================================================

st.set_page_config(
    page_title="MODO MUSTANG",
    page_icon="🐎",
    layout="wide",
    initial_sidebar_state="collapsed",
)

DATA_FILE = Path(__file__).with_name("mustang_data.json")

# =========================================================
# DATA LAYER
# =========================================================

DEFAULT_DATA = {
    "tasks": [],
    "plans": [],
    "habits": [],
    "sessions": [],
    "settings": {
        "theme": "dark",
        "accountability_name": "",
        "daily_target_minutes": 90,
        "daily_target_tasks": 3,
    },
}


def load_data() -> dict:
    if not DATA_FILE.exists():
        return json.loads(json.dumps(DEFAULT_DATA))
    try:
        with DATA_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        merged = json.loads(json.dumps(DEFAULT_DATA))
        for key, value in data.items():
            merged[key] = value
        return merged
    except (json.JSONDecodeError, OSError):
        return json.loads(json.dumps(DEFAULT_DATA))


def save_data(data: dict) -> None:
    tmp = DATA_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(DATA_FILE)


if "data" not in st.session_state:
    st.session_state.data = load_data()

DATA = st.session_state.data

if "active_timer" not in st.session_state:
    st.session_state.active_timer = None

if "mustang_mode" not in st.session_state:
    st.session_state.mustang_mode = False

# =========================================================
# HELPERS
# =========================================================


def uid() -> str:
    return uuid.uuid4().hex[:10]


def today_iso() -> str:
    return date.today().isoformat()


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def friendly_date(value: str) -> str:
    d = parse_date(value)
    return d.strftime("%d/%m/%Y")


def priority_rank(priority: str) -> int:
    return {"Alta": 0, "Média": 1, "Baixa": 2}.get(priority, 1)


def current_plan_name(plan_id: str | None) -> str:
    if not plan_id:
        return "Sem cronograma"
    plan = next((p for p in DATA["plans"] if p["id"] == plan_id), None)
    return plan["name"] if plan else "Sem cronograma"


def task_is_due(task: dict) -> bool:
    return task.get("due_date") == today_iso()


def today_tasks() -> list[dict]:
    return [t for t in DATA["tasks"] if task_is_due(t)]


def completed_today_tasks() -> list[dict]:
    return [t for t in today_tasks() if t.get("completed")]


def pending_today_tasks() -> list[dict]:
    return [t for t in today_tasks() if not t.get("completed")]


def total_focus_minutes_today() -> int:
    total = 0
    for session in DATA["sessions"]:
        if session.get("date") == today_iso():
            total += int(session.get("minutes", 0))
    return total


def weekly_focus_minutes() -> int:
    start = date.today() - timedelta(days=6)
    total = 0
    for session in DATA["sessions"]:
        try:
            d = parse_date(session.get("date", ""))
            if d >= start:
                total += int(session.get("minutes", 0))
        except ValueError:
            pass
    return total


def habit_done_today(habit_id: str) -> bool:
    today = today_iso()
    for habit in DATA["habits"]:
        if habit["id"] == habit_id:
            return today in habit.get("completions", [])
    return False


def toggle_habit(habit_id: str) -> None:
    today = today_iso()
    for habit in DATA["habits"]:
        if habit["id"] == habit_id:
            completions = set(habit.get("completions", []))
            if today in completions:
                completions.remove(today)
            else:
                completions.add(today)
            habit["completions"] = sorted(completions)
            break
    save_data(DATA)


def next_priority_task() -> dict | None:
    pending = pending_today_tasks()
    if not pending:
        # Bring forward overdue tasks only if the user has nothing today.
        overdue = [
            t
            for t in DATA["tasks"]
            if not t.get("completed")
            and t.get("due_date")
            and t.get("due_date") < today_iso()
        ]
        pending = overdue
    if not pending:
        return None
    return sorted(
        pending,
        key=lambda t: (priority_rank(t.get("priority", "Média")), t.get("due_date", "9999-12-31"), t.get("created_at", "")),
    )[0]


def add_task(title: str, due_date: date, priority: str, duration: int, plan_id: str | None, category: str) -> None:
    DATA["tasks"].append(
        {
            "id": uid(),
            "title": title.strip(),
            "due_date": due_date.isoformat(),
            "priority": priority,
            "duration": int(duration),
            "plan_id": plan_id,
            "category": category.strip() or "Geral",
            "completed": False,
            "completed_at": None,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        }
    )
    save_data(DATA)


def complete_task(task_id: str) -> None:
    for task in DATA["tasks"]:
        if task["id"] == task_id:
            task["completed"] = not task.get("completed", False)
            task["completed_at"] = datetime.now().isoformat(timespec="seconds") if task["completed"] else None
            break
    save_data(DATA)


def delete_task(task_id: str) -> None:
    DATA["tasks"] = [t for t in DATA["tasks"] if t["id"] != task_id]
    save_data(DATA)


def stop_timer(save_session: bool = True) -> None:
    timer = st.session_state.active_timer
    if not timer:
        return
    try:
        start = datetime.fromisoformat(timer["started_at"])
        elapsed = max(1, int((datetime.now() - start).total_seconds() // 60))
        elapsed = min(elapsed, 24 * 60)
        if save_session:
            DATA["sessions"].append(
                {
                    "id": uid(),
                    "date": today_iso(),
                    "task_id": timer.get("task_id"),
                    "minutes": elapsed,
                    "started_at": timer["started_at"],
                    "finished_at": datetime.now().isoformat(timespec="seconds"),
                    "kind": timer.get("kind", "focus"),
                }
            )
            save_data(DATA)
    except (TypeError, ValueError):
        pass
    st.session_state.active_timer = None


# =========================================================
# THEME / CSS
# =========================================================

THEME = DATA["settings"].get("theme", "dark")

if "theme_select" not in st.session_state:
    st.session_state.theme_select = THEME

# Theme switch lives in the page header, but the CSS is controlled by the state.
if st.session_state.theme_select != THEME:
    DATA["settings"]["theme"] = st.session_state.theme_select
    save_data(DATA)
    THEME = st.session_state.theme_select

if THEME == "dark":
    bg = "#081019"
    text = "#F5F7FA"
    muted = "#98A2B3"
    glass = "rgba(255,255,255,0.065)"
    glass2 = "rgba(255,255,255,0.09)"
    border = "rgba(255,255,255,0.13)"
    shadow = "0 18px 60px rgba(0,0,0,0.28)"
    accent = "#8B5CF6"
    accent2 = "#22D3EE"
    input_bg = "rgba(255,255,255,0.055)"
    chip_bg = "rgba(255,255,255,0.08)"
else:
    bg = "#EEF2F7"
    text = "#111827"
    muted = "#667085"
    glass = "rgba(255,255,255,0.64)"
    glass2 = "rgba(255,255,255,0.82)"
    border = "rgba(17,24,39,0.10)"
    shadow = "0 18px 60px rgba(31,41,55,0.10)"
    accent = "#6D28D9"
    accent2 = "#0891B2"
    input_bg = "rgba(255,255,255,0.72)"
    chip_bg = "rgba(17,24,39,0.06)"

st.markdown(
    f"""
    <style>
    :root {{
        --bg: {bg};
        --text: {text};
        --muted: {muted};
        --glass: {glass};
        --glass2: {glass2};
        --border: {border};
        --shadow: {shadow};
        --accent: {accent};
        --accent2: {accent2};
        --input: {input_bg};
        --chip: {chip_bg};
    }}

    .stApp {{
        background:
            radial-gradient(circle at 10% 0%, rgba(139,92,246,.14), transparent 32%),
            radial-gradient(circle at 95% 5%, rgba(34,211,238,.11), transparent 28%),
            var(--bg);
        color: var(--text);
    }}

    [data-testid="stHeader"] {{
        background: transparent;
    }}

    .main .block-container {{
        max-width: 1240px;
        padding-top: 2rem;
        padding-bottom: 4rem;
    }}

    [data-testid="stToolbar"] {{
        visibility: hidden;
        height: 0;
    }}

    h1, h2, h3, h4, p, label, .stMarkdown {{
        color: var(--text);
    }}

    .glass {{
        background: linear-gradient(135deg, var(--glass2), var(--glass));
        backdrop-filter: blur(24px) saturate(140%);
        -webkit-backdrop-filter: blur(24px) saturate(140%);
        border: 1px solid var(--border);
        box-shadow: var(--shadow);
        border-radius: 28px;
    }}

    .hero {{
        padding: 28px 30px;
        margin-bottom: 18px;
    }}

    .eyebrow {{
        text-transform: uppercase;
        letter-spacing: .13em;
        font-size: .72rem;
        font-weight: 800;
        color: var(--muted);
        margin-bottom: 7px;
    }}

    .hero-title {{
        font-size: clamp(2rem, 4vw, 3.65rem);
        line-height: .98;
        font-weight: 900;
        letter-spacing: -.045em;
        margin: 0;
    }}

    .hero-sub {{
        color: var(--muted);
        font-size: 1rem;
        max-width: 760px;
        margin-top: 10px;
        line-height: 1.5;
    }}

    .kpi {{
        padding: 20px 22px;
        min-height: 128px;
    }}

    .kpi-label {{
        color: var(--muted);
        font-size: .82rem;
        margin-bottom: 10px;
        font-weight: 700;
    }}

    .kpi-value {{
        font-size: 2rem;
        font-weight: 900;
        letter-spacing: -.04em;
    }}

    .kpi-note {{
        color: var(--muted);
        font-size: .8rem;
        margin-top: 4px;
    }}

    .section-title {{
        font-size: 1.1rem;
        font-weight: 850;
        margin: 14px 0 10px;
    }}

    .next-card {{
        padding: 30px;
        text-align: center;
    }}

    .next-title {{
        font-size: clamp(1.55rem, 3vw, 2.35rem);
        line-height: 1.08;
        font-weight: 900;
        margin: 4px auto 8px;
        max-width: 850px;
        letter-spacing: -.035em;
    }}

    .next-meta {{
        color: var(--muted);
        margin-bottom: 20px;
    }}

    .chip {{
        display: inline-flex;
        align-items: center;
        gap: 7px;
        padding: 6px 10px;
        border-radius: 999px;
        background: var(--chip);
        border: 1px solid var(--border);
        font-size: .76rem;
        font-weight: 800;
        margin: 0 3px;
    }}

    .muted {{ color: var(--muted); }}

    .task-row {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        padding: 14px 16px;
        margin: 8px 0;
        border-radius: 18px;
        background: var(--glass);
        border: 1px solid var(--border);
    }}

    .task-main {{ flex: 1; min-width: 0; }}
    .task-name {{ font-weight: 800; margin-bottom: 3px; }}
    .task-meta {{ color: var(--muted); font-size: .78rem; }}

    .empty {{
        padding: 28px;
        text-align: center;
        color: var(--muted);
    }}

    .quote {{
        padding: 22px 24px;
        font-size: 1.05rem;
        font-weight: 700;
        line-height: 1.45;
    }}

    .mustang {{
        background:
            linear-gradient(135deg, rgba(139,92,246,.24), rgba(34,211,238,.12)),
            var(--glass2);
    }}

    .timer {{
        text-align: center;
        font-variant-numeric: tabular-nums;
        font-size: clamp(3rem, 9vw, 6rem);
        font-weight: 900;
        letter-spacing: -.06em;
        margin: 12px 0;
    }}

    .small-note {{
        color: var(--muted);
        font-size: .78rem;
        line-height: 1.45;
    }}

    div[data-testid="stMetric"] {{
        background: var(--glass);
        border: 1px solid var(--border);
        padding: 15px;
        border-radius: 20px;
    }}

    .stButton > button, .stDownloadButton > button {{
        border-radius: 16px !important;
        border: 1px solid var(--border) !important;
        background: var(--glass2) !important;
        color: var(--text) !important;
        font-weight: 800 !important;
        min-height: 2.7rem;
        transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
        box-shadow: none !important;
    }}

    .stButton > button:hover {{
        transform: translateY(-1px);
        border-color: rgba(139,92,246,.5) !important;
    }}

    .primary-btn button {{
        background: linear-gradient(135deg, var(--accent), #7C3AED) !important;
        color: white !important;
        border: 0 !important;
        box-shadow: 0 10px 28px rgba(109,40,217,.28) !important;
    }}

    .danger-btn button {{
        background: rgba(239,68,68,.09) !important;
        border-color: rgba(239,68,68,.26) !important;
    }}

    .stTextInput input, .stNumberInput input, .stTextArea textarea, .stDateInput input, .stSelectbox div[data-baseweb="select"] > div {{
        background: var(--input) !important;
        color: var(--text) !important;
        border-radius: 14px !important;
        border-color: var(--border) !important;
    }}

    .stCheckbox label, .stRadio label, .stSelectSlider label, .stToggle label {{
        color: var(--text) !important;
    }}

    [data-testid="stTabs"] button {{
        font-weight: 800;
    }}

    hr {{ border-color: var(--border) !important; }}
    </style>
    """,
    unsafe_allow_html=True,
)

# =========================================================
# HEADER
# =========================================================

hcol1, hcol2 = st.columns([5, 1], vertical_alignment="center")
with hcol1:
    st.markdown(
        f"""
        <div class="glass hero">
            <div class="eyebrow">Seu cockpit pessoal de execução</div>
            <div class="hero-title">MODO MUSTANG 🐎</div>
            <div class="hero-sub">
                Menos coisas para olhar. Mais coisas realmente feitas.
                O sistema foi desenhado para reduzir a fricção de começar e transformar pressão,
                contexto e accountability em tração.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
with hcol2:
    theme = st.toggle("Modo claro", value=(THEME == "light"), key="theme_toggle")
    desired = "light" if theme else "dark"
    if desired != THEME:
        DATA["settings"]["theme"] = desired
        save_data(DATA)
        st.rerun()
    st.session_state.mustang_mode = st.toggle("🐎 Modo Mustang", value=st.session_state.mustang_mode)

# =========================================================
# NAVIGATION
# =========================================================

page = st.radio(
    "Navegação",
    ["Hoje", "Cronogramas", "Hábitos", "Dashboard", "Accountability"],
    horizontal=True,
    label_visibility="collapsed",
)

# =========================================================
# PAGE: HOJE
# =========================================================

if page == "Hoje":
    today = today_tasks()
    done = completed_today_tasks()
    pending = pending_today_tasks()
    focus_today = total_focus_minutes_today()
    target_minutes = max(1, int(DATA["settings"].get("daily_target_minutes", 90)))
    target_tasks = max(1, int(DATA["settings"].get("daily_target_tasks", 3)))
    task_ratio = min(1.0, len(done) / target_tasks)
    focus_ratio = min(1.0, focus_today / target_minutes)
    traction = round(((task_ratio * 0.55) + (focus_ratio * 0.45)) * 100)

    kc1, kc2, kc3, kc4 = st.columns(4)
    kpis = [
        ("Tração", f"{traction}%", "execução combinada hoje"),
        ("Foco", f"{focus_today} min", f"meta {target_minutes} min"),
        ("Entregas", f"{len(done)}/{target_tasks}", "compromissos concluídos"),
        ("Pendências", f"{len(pending)}", "sem sobrecarregar a tela"),
    ]
    for col, (label, value, note) in zip([kc1, kc2, kc3, kc4], kpis):
        with col:
            st.markdown(
                f"""
                <div class="glass kpi">
                    <div class="kpi-label">{label}</div>
                    <div class="kpi-value">{value}</div>
                    <div class="kpi-note">{note}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.write("")

    next_task = next_priority_task()

    if st.session_state.active_timer:
        timer = st.session_state.active_timer
        task = next((t for t in DATA["tasks"] if t["id"] == timer.get("task_id")), None)
        timer_title = task["title"] if task else "Sessão livre"
        started_at = timer["started_at"]
        st.markdown(f'<div class="glass mustang next-card">', unsafe_allow_html=True)
        st.markdown('<div class="eyebrow">EM EXECUÇÃO</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="next-title">{timer_title}</div>', unsafe_allow_html=True)
        st.markdown(
            f'''<div class="timer" id="mustang-timer">00:00</div>
            <div class="small-note">Começou em {started_at[11:16]} · não negocie com a tarefa durante a sessão.</div>
            <script>
                (() => {{
                    const start = new Date("{started_at.replace("'", "")}");
                    const el = document.getElementById("mustang-timer");
                    const tick = () => {{
                        const seconds = Math.max(0, Math.floor((new Date() - start) / 1000));
                        const h = Math.floor(seconds / 3600);
                        const m = Math.floor((seconds % 3600) / 60);
                        const s = seconds % 60;
                        el.textContent = (h > 0 ? String(h).padStart(2, '0') + ':' : '') + String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
                    }};
                    tick(); setInterval(tick, 1000);
                }})();
            </script>''',
            unsafe_allow_html=True,
        )
        b1, b2 = st.columns(2)
        with b1:
            st.markdown('<div class="primary-btn">', unsafe_allow_html=True)
            if st.button("Concluir sessão", use_container_width=True):
                stop_timer(save_session=True)
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
        with b2:
            st.markdown('<div class="danger-btn">', unsafe_allow_html=True)
            if st.button("Parar sem registrar", use_container_width=True):
                stop_timer(save_session=False)
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        if next_task:
            st.markdown(
                f"""
                <div class="glass next-card">
                    <div class="eyebrow">AGORA</div>
                    <div class="next-title">{next_task['title']}</div>
                    <div class="next-meta">
                        <span class="chip">{next_task.get('duration', 0)} min</span>
                        <span class="chip">{next_task.get('priority', 'Média')}</span>
                        <span class="chip">{next_task.get('category', 'Geral')}</span>
                        <span class="chip">{current_plan_name(next_task.get('plan_id'))}</span>
                    </div>
                    <div class="small-note">A barreira de entrada é o problema. A sessão começa com 5 minutos.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            q1, q2, q3 = st.columns([1.2, 1.2, 1])
            with q1:
                st.markdown('<div class="primary-btn">', unsafe_allow_html=True)
                if st.button("🐎 Começar 5 minutos", use_container_width=True):
                    st.session_state.active_timer = {
                        "task_id": next_task["id"],
                        "started_at": datetime.now().isoformat(timespec="seconds"),
                        "kind": "5_min_start",
                    }
                    st.rerun()
                st.markdown('</div>', unsafe_allow_html=True)
            with q2:
                if st.button("Começar sessão completa", use_container_width=True):
                    st.session_state.active_timer = {
                        "task_id": next_task["id"],
                        "started_at": datetime.now().isoformat(timespec="seconds"),
                        "kind": "focus",
                    }
                    st.rerun()
            with q3:
                if st.button("✅ Já fiz", use_container_width=True):
                    complete_task(next_task["id"])
                    st.rerun()
        else:
            st.markdown(
                """
                <div class="glass next-card">
                    <div class="eyebrow">HOJE</div>
                    <div class="next-title">Tudo que era obrigatório foi feito.</div>
                    <div class="next-meta">Não invente pendências só porque a tela ficou vazia.</div>
                    <div class="small-note">Você pode descansar, estudar por prazer ou preparar amanhã.</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    if not st.session_state.mustang_mode:
        st.write("")
        left, right = st.columns([1.35, 1])
        with left:
            st.markdown('<div class="section-title">Hoje</div>', unsafe_allow_html=True)
            if not today:
                st.markdown('<div class="glass empty">Nenhuma pendência para hoje. Isso também é um resultado.</div>', unsafe_allow_html=True)
            else:
                for task in sorted(today, key=lambda t: (t.get("completed", False), priority_rank(t.get("priority", "Média")))):
                    status = "✅" if task.get("completed") else "○"
                    plan = current_plan_name(task.get("plan_id"))
                    c1, c2, c3 = st.columns([6, 1, 1])
                    with c1:
                        st.markdown(
                            f"""
                            <div class="task-row">
                                <div class="task-main">
                                    <div class="task-name">{status} {task['title']}</div>
                                    <div class="task-meta">{task.get('duration', 0)} min · {task.get('category', 'Geral')} · {plan}</div>
                                </div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                    with c2:
                        if st.button("↺" if task.get("completed") else "✓", key=f"done_{task['id']}"):
                            complete_task(task["id"])
                            st.rerun()
                    with c3:
                        if st.button("×", key=f"del_{task['id']}"):
                            delete_task(task["id"])
                            st.rerun()

        with right:
            st.markdown('<div class="section-title">Adicionar</div>', unsafe_allow_html=True)
            with st.form("quick_add", clear_on_submit=True):
                title = st.text_input("O que precisa ser feito?", placeholder="Ex.: Preventiva — aula 03")
                c1, c2 = st.columns(2)
                with c1:
                    duration = st.number_input("Minutos", min_value=5, max_value=600, value=30, step=5)
                    category = st.text_input("Categoria", value="Estudo")
                with c2:
                    priority = st.selectbox("Prioridade", ["Alta", "Média", "Baixa"], index=1)
                    due = st.date_input("Dia", value=date.today())
                plan_options = {"Sem cronograma": None}
                plan_options.update({p["name"]: p["id"] for p in DATA["plans"]})
                plan_name = st.selectbox("Cronograma", list(plan_options.keys()))
                submitted = st.form_submit_button("Adicionar tarefa", use_container_width=True)
                if submitted:
                    if title.strip():
                        add_task(title, due, priority, duration, plan_options[plan_name], category)
                        st.rerun()
                    else:
                        st.warning("Dê um nome para a tarefa.")

            st.markdown('<div class="section-title">Começar sem pensar</div>', unsafe_allow_html=True)
            with st.form("quick_focus", clear_on_submit=False):
                free_minutes = st.number_input("Sessão livre", min_value=5, max_value=240, value=25, step=5)
                ok = st.form_submit_button("Iniciar foco livre", use_container_width=True)
                if ok:
                    st.session_state.active_timer = {
                        "task_id": None,
                        "started_at": datetime.now().isoformat(timespec="seconds"),
                        "kind": f"free_{free_minutes}",
                    }
                    st.rerun()

# =========================================================
# PAGE: CRONOGRAMAS
# =========================================================

elif page == "Cronogramas":
    st.markdown('<div class="section-title">Seus cronogramas</div>', unsafe_allow_html=True)
    left, right = st.columns([1.25, 1])
    with left:
        if not DATA["plans"]:
            st.markdown('<div class="glass empty">Crie seu primeiro cronograma. A ideia é transformar uma meta abstrata em ações datadas.</div>', unsafe_allow_html=True)
        for plan in DATA["plans"]:
            tasks = [t for t in DATA["tasks"] if t.get("plan_id") == plan["id"]]
            completed = sum(1 for t in tasks if t.get("completed"))
            percent = int((completed / len(tasks)) * 100) if tasks else 0
            st.markdown(
                f"""
                <div class="glass" style="padding:20px 22px; margin-bottom:10px;">
                    <div class="eyebrow">CRONOGRAMA</div>
                    <h3 style="margin:0;">{plan['name']}</h3>
                    <div class="small-note">{friendly_date(plan['start'])} → {friendly_date(plan['end'])}</div>
                    <div style="margin-top:12px; height:8px; border-radius:99px; background:rgba(128,128,128,.16); overflow:hidden;">
                        <div style="width:{percent}%; height:100%; border-radius:99px; background:linear-gradient(90deg, var(--accent), var(--accent2));"></div>
                    </div>
                    <div class="small-note" style="margin-top:7px;">{completed}/{len(tasks)} tarefas · {percent}%</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
        st.markdown("---")
        st.markdown('<div class="section-title">Sessões do cronograma</div>', unsafe_allow_html=True)
        if DATA["plans"]:
            selected_plan_name = st.selectbox("Escolha um cronograma", [p["name"] for p in DATA["plans"]])
            selected_plan = next(p for p in DATA["plans"] if p["name"] == selected_plan_name)
            plan_tasks = [t for t in DATA["tasks"] if t.get("plan_id") == selected_plan["id"]]
            for task in sorted(plan_tasks, key=lambda x: x.get("due_date", "9999-12-31")):
                icon = "✅" if task.get("completed") else "○"
                st.markdown(
                    f"<div class='task-row'><div class='task-main'><div class='task-name'>{icon} {task['title']}</div><div class='task-meta'>{friendly_date(task['due_date'])} · {task['duration']} min · {task['priority']}</div></div></div>",
                    unsafe_allow_html=True,
                )

    with right:
        st.markdown('<div class="section-title">Novo cronograma</div>', unsafe_allow_html=True)
        with st.form("new_plan", clear_on_submit=True):
            plan_name = st.text_input("Nome", placeholder="Preventiva — PSF")
            c1, c2 = st.columns(2)
            with c1:
                start = st.date_input("Início", value=date.today())
            with c2:
                end = st.date_input("Fim", value=date.today() + timedelta(days=30))
            objective = st.text_area("Objetivo", placeholder="Ex.: dominar o conteúdo do rodízio com microestudo diário")
            submitted = st.form_submit_button("Criar cronograma", use_container_width=True)
            if submitted:
                if not plan_name.strip():
                    st.warning("Dê um nome ao cronograma.")
                elif end < start:
                    st.warning("A data final não pode ser anterior à inicial.")
                else:
                    DATA["plans"].append({
                        "id": uid(),
                        "name": plan_name.strip(),
                        "start": start.isoformat(),
                        "end": end.isoformat(),
                        "objective": objective.strip(),
                    })
                    save_data(DATA)
                    st.rerun()

        st.markdown('<div class="section-title">Adicionar sessão ao cronograma</div>', unsafe_allow_html=True)
        if DATA["plans"]:
            with st.form("new_plan_task", clear_on_submit=True):
                selected_name = st.selectbox("Cronograma", [p["name"] for p in DATA["plans"]])
                selected_plan = next(p for p in DATA["plans"] if p["name"] == selected_name)
                title = st.text_input("Sessão", placeholder="Ex.: Aula — vigilância epidemiológica")
                c1, c2 = st.columns(2)
                with c1:
                    due = st.date_input("Data", value=date.today())
                    duration = st.number_input("Duração", min_value=5, max_value=600, value=30, step=5)
                with c2:
                    priority = st.selectbox("Prioridade", ["Alta", "Média", "Baixa"], index=1)
                    category = st.text_input("Categoria", value="Estudo")
                submitted = st.form_submit_button("Adicionar sessão", use_container_width=True)
                if submitted:
                    if title.strip():
                        add_task(title, due, priority, duration, selected_plan["id"], category)
                        st.rerun()
                    else:
                        st.warning("Nomeie a sessão.")
        else:
            st.info("Crie um cronograma primeiro.")

# =========================================================
# PAGE: HÁBITOS
# =========================================================

elif page == "Hábitos":
    st.markdown('<div class="section-title">Hábitos que realmente importam</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="glass quote">Não estamos tentando acompanhar 17 hábitos. Estamos procurando comportamentos que sustentem sua vida real.</div>',
        unsafe_allow_html=True,
    )
    left, right = st.columns([1.15, 1])
    with left:
        if not DATA["habits"]:
            st.markdown('<div class="glass empty">Nenhum hábito cadastrado. Comece com poucos.</div>', unsafe_allow_html=True)
        for habit in DATA["habits"]:
            done_habit = habit_done_today(habit["id"])
            c1, c2 = st.columns([7, 1])
            with c1:
                st.markdown(
                    f"<div class='task-row'><div class='task-main'><div class='task-name'>{'✅' if done_habit else '○'} {habit['name']}</div><div class='task-meta'>{habit.get('why', '')}</div></div></div>",
                    unsafe_allow_html=True,
                )
            with c2:
                if st.button("✓" if not done_habit else "↺", key=f"habit_{habit['id']}"):
                    toggle_habit(habit["id"])
                    st.rerun()
        st.markdown("---")
        st.markdown('<div class="section-title">Regra para você</div>', unsafe_allow_html=True)
        st.markdown(
            f"""
            <div class="glass quote">
                Meta não é ser perfeito. Meta é manter o motor ligado.<br><br>
                Hoje você marcou <b>{sum(1 for h in DATA['habits'] if habit_done_today(h['id']))}/{len(DATA['habits'])}</b> hábitos.
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        with st.form("new_habit", clear_on_submit=True):
            name = st.text_input("Novo hábito", placeholder="Ex.: 10 minutos de leitura")
            why = st.text_input("Por que isso importa?", placeholder="Ex.: constância > intensidade")
            submitted = st.form_submit_button("Adicionar hábito", use_container_width=True)
            if submitted:
                if name.strip():
                    DATA["habits"].append({
                        "id": uid(),
                        "name": name.strip(),
                        "why": why.strip(),
                        "completions": [],
                    })
                    save_data(DATA)
                    st.rerun()
                else:
                    st.warning("Dê um nome ao hábito.")

# =========================================================
# PAGE: DASHBOARD
# =========================================================

elif page == "Dashboard":
    st.markdown('<div class="section-title">Painel de tração</div>', unsafe_allow_html=True)
    week_minutes = weekly_focus_minutes()
    today_minutes = total_focus_minutes_today()
    done_today = len(completed_today_tasks())
    all_due = [t for t in DATA["tasks"] if t.get("due_date")]
    done_all = sum(1 for t in all_due if t.get("completed"))
    completion_rate = round((done_all / len(all_due)) * 100) if all_due else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Foco hoje", f"{today_minutes} min")
    c2.metric("Foco 7 dias", f"{week_minutes} min")
    c3.metric("Tarefas concluídas hoje", done_today)
    c4.metric("Conclusão geral", f"{completion_rate}%")

    st.write("")
    left, right = st.columns(2)

    with left:
        st.markdown('<div class="glass" style="padding:24px;"><div class="eyebrow">Tendência de foco</div>', unsafe_allow_html=True)
        rows = []
        for i in range(6, -1, -1):
            d = date.today() - timedelta(days=i)
            mins = sum(int(s.get("minutes", 0)) for s in DATA["sessions"] if s.get("date") == d.isoformat())
            rows.append((d.strftime("%a"), mins))
        max_m = max([m for _, m in rows] + [1])
        for day_name, mins in rows:
            pct = int((mins / max_m) * 100)
            st.markdown(
                f"<div style='display:flex;align-items:center;gap:10px;margin:9px 0;'><div style='width:38px;color:var(--muted);font-size:.78rem;'>{day_name}</div><div style='flex:1;height:10px;background:rgba(128,128,128,.15);border-radius:99px;overflow:hidden;'><div style='width:{pct}%;height:100%;background:linear-gradient(90deg,var(--accent),var(--accent2));border-radius:99px;'></div></div><div style='width:42px;text-align:right;font-weight:800;font-size:.8rem;'>{mins}m</div></div>",
                unsafe_allow_html=True,
            )
        st.markdown('</div>', unsafe_allow_html=True)

    with right:
        st.markdown('<div class="glass" style="padding:24px;"><div class="eyebrow">Diagnóstico</div>', unsafe_allow_html=True)
        avg_activation = None
        # Approximation based on recorded session starts during the current day.
        if DATA["sessions"]:
            activation_samples = []
            for s in DATA["sessions"]:
                if s.get("date") == today_iso() and s.get("started_at"):
                    activation_samples.append(1)
            if activation_samples:
                avg_activation = "registre mais sessões para estimar"
        st.markdown(
            f"""
            <div class="task-row"><div class="task-main"><div class="task-name">A principal métrica</div><div class="task-meta">Tempo entre decidir e começar. O MVP registra sessões; a próxima versão pode medir o atraso explicitamente.</div></div></div>
            <div class="task-row"><div class="task-main"><div class="task-name">Seu padrão</div><div class="task-meta">Pressão + ambiente + meta pequena → tração.</div></div></div>
            <div class="task-row"><div class="task-main"><div class="task-name">Regra do sistema</div><div class="task-meta">Uma prioridade visível. O restante fica em segundo plano.</div></div></div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown('</div>', unsafe_allow_html=True)

    st.write("")
    st.markdown(
        """
        <div class="glass quote">
            O dashboard não existe para mostrar uma vida perfeita. Ele existe para mostrar que você está em movimento.
        </div>
        """,
        unsafe_allow_html=True,
    )

# =========================================================
# PAGE: ACCOUNTABILITY
# =========================================================

else:
    st.markdown('<div class="section-title">Prestação de contas</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="glass quote">A cobrança que funciona para você é social. Este módulo prepara o resumo que você pode mandar para uma pessoa real.</div>',
        unsafe_allow_html=True,
    )

    left, right = st.columns([1, 1.2])
    with left:
        st.markdown('<div class="section-title">Configuração</div>', unsafe_allow_html=True)
        with st.form("accountability_settings"):
            name = st.text_input("Pessoa que recebe sua prestação", value=DATA["settings"].get("accountability_name", ""), placeholder="Ex.: meu amigo de estudos")
            target_minutes = st.number_input("Meta diária de foco (min)", min_value=10, max_value=720, value=int(DATA["settings"].get("daily_target_minutes", 90)), step=10)
            target_tasks = st.number_input("Meta diária de entregas", min_value=1, max_value=20, value=int(DATA["settings"].get("daily_target_tasks", 3)), step=1)
            submitted = st.form_submit_button("Salvar", use_container_width=True)
            if submitted:
                DATA["settings"]["accountability_name"] = name.strip()
                DATA["settings"]["daily_target_minutes"] = int(target_minutes)
                DATA["settings"]["daily_target_tasks"] = int(target_tasks)
                save_data(DATA)
                st.rerun()

    completed = completed_today_tasks()
    report = "\n".join(
        [
            f"PRESTAÇÃO DE CONTAS — {date.today().strftime('%d/%m/%Y')}",
            "",
            f"Foco hoje: {total_focus_minutes_today()} min / {DATA['settings'].get('daily_target_minutes', 90)} min",
            f"Entregas: {len(completed)}/{DATA['settings'].get('daily_target_tasks', 3)}",
            "",
            "Concluído:",
            *(f"- {t['title']}" for t in completed),
            "",
            "Status: EM MOVIMENTO" if completed or total_focus_minutes_today() > 0 else "Status: PRECISO COMEÇAR",
        ]
    )

    with right:
        st.markdown('<div class="section-title">Mensagem do dia</div>', unsafe_allow_html=True)
        st.code(report, language="text")
        name = DATA["settings"].get("accountability_name", "")
        if name:
            st.markdown(
                f"<div class='small-note'>Destinatário configurado: <b>{name}</b>. O envio continua deliberadamente humano — copie e mande para a pessoa.</div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<div class="small-note">Configure uma pessoa real. O algoritmo não substitui accountability social.</div>', unsafe_allow_html=True)

# =========================================================
# FOOTER
# =========================================================

st.write("")
st.markdown(
    f"<div class='small-note' style='text-align:center;'>MODO MUSTANG · {date.today().strftime('%d/%m/%Y')} · menos negociação, mais tração.</div>",
    unsafe_allow_html=True,
)
