"""
Command Core — Streamlit UI v2 (Dark Tactical Redesign)
========================================================
Three-column dark tactical interface with:
  - Left:   Incident input · Language LED · Constitution Tree
  - Center: Specialist agent cards with veto status
  - Right:  Military dispatch · Veto audit table · Conflict panel
  - Sidebar: Rule toggles · Trigger chip manager

All backend logic identical to streamlit_app.py (Milestone 4).
"""

import streamlit as st
import sys
import os
import json
import re
import concurrent.futures
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.agent_factory import SpecialistFactory
from agents.commander_agent import CommanderAgent, CONSTITUTION, VETO_TRIGGERS
from llm.llm_client import LLMClient

MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # 2 MB

_URGENCY_BADGE = {
    "CRITICAL": ("🔴", "#dc2626"),
    "HIGH":     ("🟠", "#ea580c"),
    "MEDIUM":   ("🟡", "#ca8a04"),
    "LOW":      ("🟢", "#16a34a"),
}

_RULE_ICONS = {
    1: "❤️", 2: "🏗️", 3: "🚑", 4: "💊", 5: "🔥", 6: "⚖️", 7: "🎖️",
}

st.set_page_config(
    page_title="Command Core — Tactical Operations",
    page_icon="🎖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ──────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Roboto+Mono:wght@300;400;500;600&family=Inter:wght@300;400;500;600;700&display=swap');

/* ── Global ── */
html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background-color: #0d1117 !important;
    color: #c9d1d9 !important;
}
.stApp { background-color: #0d1117 !important; }
.main .block-container { padding: 0.75rem 1rem 1rem 1rem !important; max-width: 100% !important; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background-color: #161b22 !important;
    border-right: 1px solid #30363d !important;
}
[data-testid="stSidebar"] * { color: #c9d1d9 !important; }
[data-testid="stSidebar"] .stButton > button {
    background: #21262d !important; border: 1px solid #30363d !important;
    color: #c9d1d9 !important; border-radius: 6px !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: #30363d !important; border-color: #8b949e !important;
}

/* ── Column panels ── */
.col-panel {
    background: #161b22;
    border: 1px solid #21262d;
    border-radius: 10px;
    padding: 14px;
    height: calc(100vh - 100px);
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: #30363d #161b22;
}
.col-panel::-webkit-scrollbar { width: 4px; }
.col-panel::-webkit-scrollbar-track { background: #161b22; }
.col-panel::-webkit-scrollbar-thumb { background: #30363d; border-radius: 4px; }

/* ── Section headers ── */
.section-header {
    font-family: 'Roboto Mono', monospace;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: #8b949e;
    border-bottom: 1px solid #21262d;
    padding-bottom: 6px;
    margin-bottom: 10px;
    margin-top: 6px;
}

/* ── Language LED ── */
.led-container { display: flex; align-items: center; gap: 8px; margin: 8px 0; }
.led {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 10px; border-radius: 20px;
    font-family: 'Roboto Mono', monospace; font-size: 11px; font-weight: 600;
    letter-spacing: 1px;
}
.led-dot { width: 8px; height: 8px; border-radius: 50%; }
.led-heb { background: #1a2744; border: 1px solid #3b5bdb; color: #74c0fc; }
.led-heb .led-dot { background: #74c0fc; box-shadow: 0 0 6px #74c0fc; }
.led-eng { background: #1a2e1a; border: 1px solid #2d6a2d; color: #69db7c; }
.led-eng .led-dot { background: #69db7c; box-shadow: 0 0 6px #69db7c; }
.led-neutral { background: #1e1e1e; border: 1px solid #3d3d3d; color: #8b949e; }
.led-neutral .led-dot { background: #555; }

/* ── Constitution rule badges ── */
.rule-badge {
    display: flex; align-items: center; gap: 8px;
    padding: 6px 10px; border-radius: 6px; margin-bottom: 5px;
    font-family: 'Roboto Mono', monospace; font-size: 11px;
    background: #0d1117; border: 1px solid #21262d;
    transition: all 0.2s ease;
}
.rule-badge.active {
    background: #1a2e1a; border-color: #2d6a2d; color: #69db7c;
}
.rule-badge.vetoed {
    background: #2e1a1a; border-color #6a2d2d; color: #f87171;
}
.rule-badge.disabled { opacity: 0.3; }
.rule-num {
    font-weight: 700; font-size: 10px; color: #8b949e;
    min-width: 44px;
}
.rule-text { font-size: 10px; color: #8b949e; flex: 1; line-height: 1.3; }
.rule-badge.active .rule-text { color: #69db7c; }
.rule-badge.vetoed .rule-text { color: #f87171; }

/* ── Agent cards ── */
.agent-card {
    border-radius: 8px; padding: 12px 14px; margin-bottom: 10px;
    border-left: 3px solid; position: relative;
}
.agent-fire   { background: #1a1208; border-color: #c2410c; }
.agent-med    { background: #0a1a1f; border-color: #0e7490; }
.agent-police { background: #0d1227; border-color: #1d4ed8; }

.agent-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.agent-icon { font-size: 18px; }
.agent-name {
    font-family: 'Roboto Mono', monospace; font-weight: 700;
    font-size: 13px; flex: 1;
}
.agent-fire   .agent-name { color: #fb923c; }
.agent-med    .agent-name { color: #22d3ee; }
.agent-police .agent-name { color: #60a5fa; }

/* ── Urgency badge ── */
.urgency-badge {
    font-family: 'Roboto Mono', monospace; font-size: 10px; font-weight: 700;
    padding: 2px 7px; border-radius: 4px; letter-spacing: 0.5px;
}
.u-critical { background: #450a0a; color: #fca5a5; border: 1px solid #dc2626; }
.u-high     { background: #431407; color: #fdba74; border: 1px solid #ea580c; }
.u-medium   { background: #3d2f00; color: #fde68a; border: 1px solid #ca8a04; }
.u-low      { background: #052e16; color: #86efac; border: 1px solid #16a34a; }
.u-na       { background: #1e2430; color: #8b949e; border: 1px solid #30363d; }

/* ── Status chips ── */
.status-chip {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 10px; border-radius: 4px;
    font-family: 'Roboto Mono', monospace; font-size: 10px; font-weight: 700;
    letter-spacing: 0.5px; text-transform: uppercase;
}
.status-approved    { background: #052e16; color: #4ade80; border: 1px solid #16a34a; }
.status-prescreen   { background: #431407; color: #fdba74; border: 1px solid #c2410c; }
.status-llmveto     { background: #450a0a; color: #fca5a5; border: 1px solid #dc2626; }

.status-dot { width: 7px; height: 7px; border-radius: 50%; }
.dot-approved  { background: #4ade80; box-shadow: 0 0 5px #4ade80; }
.dot-prescreen { background: #fb923c; box-shadow: 0 0 5px #fb923c; }
.dot-llmveto   { background: #f87171; box-shadow: 0 0 5px #f87171; }

/* ── Military dispatch ── */
.dispatch-box {
    background: #0a0f14;
    border: 1px solid #30363d;
    border-top: 3px solid #f59e0b;
    border-radius: 4px;
    padding: 14px 16px;
    font-family: 'Roboto Mono', monospace;
    font-size: 12px;
    line-height: 1.7;
    color: #e5c46a;
}
.dispatch-header {
    font-size: 10px; font-weight: 700; letter-spacing: 3px;
    color: #78716c; text-transform: uppercase; margin-bottom: 8px;
    border-bottom: 1px solid #292524; padding-bottom: 5px;
}
.dispatch-body { color: #d6d3d1; white-space: pre-wrap; }

/* ── Veto table ── */
.veto-table { width: 100%; border-collapse: collapse; font-family: 'Roboto Mono', monospace; font-size: 10px; }
.veto-table th {
    background: #0d1117; color: #8b949e;
    padding: 6px 8px; text-align: left;
    border-bottom: 1px solid #21262d; font-weight: 600; letter-spacing: 1px;
    text-transform: uppercase; font-size: 9px;
}
.veto-table td { padding: 6px 8px; border-bottom: 1px solid #161b22; color: #c9d1d9; vertical-align: top; }
.veto-table tr:hover td { background: #161b22; }
.stage-pre  { color: #fb923c; font-weight: 700; }
.stage-llm  { color: #f87171; font-weight: 700; }

/* ── Conflict card ── */
.conflict-card {
    background: #0d1117; border: 1px solid #21262d;
    border-left: 3px solid #8b5cf6;
    border-radius: 6px; padding: 8px 12px; margin-bottom: 6px;
    font-family: 'Roboto Mono', monospace; font-size: 11px;
}
.conflict-topic {
    font-size: 9px; font-weight: 700; letter-spacing: 2px;
    color: #8b5cf6; text-transform: uppercase; margin-bottom: 4px;
}
.conflict-winner { color: #4ade80; font-weight: 700; }
.conflict-reason { color: #8b949e; font-size: 10px; margin-top: 3px; }

/* ── Trigger chips ── */
.trigger-chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 6px 0; }
.trigger-chip {
    display: inline-flex; align-items: center; gap: 4px;
    background: #21262d; border: 1px solid #30363d;
    border-radius: 20px; padding: 3px 10px;
    font-family: 'Roboto Mono', monospace; font-size: 10px; color: #c9d1d9;
}

/* ── Text input override ── */
.stTextArea textarea {
    background: #0d1117 !important; color: #c9d1d9 !important;
    border: 1px solid #30363d !important; border-radius: 6px !important;
    font-family: 'Roboto Mono', monospace !important; font-size: 13px !important;
    caret-color: #58a6ff !important;
}
.stTextArea textarea:focus { border-color: #58a6ff !important; box-shadow: 0 0 0 2px rgba(88,166,255,0.15) !important; }
.stTextInput input {
    background: #0d1117 !important; color: #c9d1d9 !important;
    border: 1px solid #30363d !important; border-radius: 6px !important;
    font-family: 'Roboto Mono', monospace !important;
}

/* ── Primary action button ── */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #1d4ed8, #1e40af) !important;
    border: 1px solid #3b82f6 !important; color: white !important;
    font-family: 'Roboto Mono', monospace !important; font-weight: 700 !important;
    letter-spacing: 1px !important; text-transform: uppercase !important;
    padding: 10px 0 !important; border-radius: 6px !important;
}
.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #2563eb, #1d4ed8) !important;
    box-shadow: 0 0 12px rgba(59,130,246,0.4) !important;
}
/* ── Expander ── */
.streamlit-expanderHeader {
    background: #161b22 !important; border: 1px solid #21262d !important;
    color: #8b949e !important; border-radius: 6px !important;
    font-family: 'Roboto Mono', monospace !important; font-size: 11px !important;
}
/* ── Toggle ── */
.stCheckbox label, .stToggle label { color: #8b949e !important; font-size: 12px !important; }

/* ── Info/warning boxes ── */
.info-box {
    background: #0d2137; border: 1px solid #1d4ed8; border-radius: 6px;
    padding: 8px 12px; font-family: 'Roboto Mono', monospace; font-size: 11px;
    color: #93c5fd; margin: 6px 0;
}

/* ── App title bar ── */
.app-titlebar {
    background: #161b22; border-bottom: 1px solid #21262d;
    padding: 6px 16px; margin: -0.75rem -1rem 0.75rem -1rem;
    display: flex; align-items: center; gap: 12px;
}
.app-title {
    font-family: 'Roboto Mono', monospace; font-weight: 700;
    font-size: 14px; letter-spacing: 2px; color: #f59e0b;
    text-transform: uppercase;
}
.app-subtitle { font-size: 10px; color: #8b949e; letter-spacing: 1px; }
.app-time { margin-left: auto; font-family: 'Roboto Mono', monospace; font-size: 10px; color: #30363d; }
</style>
""", unsafe_allow_html=True)


# ── Session state ────────────────────────────────────────────────────────────
if "llm" not in st.session_state:
    st.session_state.llm = LLMClient()

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "constitution_text" not in st.session_state:
    st.session_state.constitution_text = CONSTITUTION

if "veto_triggers" not in st.session_state:
    st.session_state.veto_triggers = dict(VETO_TRIGGERS)

if "last_result" not in st.session_state:
    st.session_state.last_result = None

if "processing" not in st.session_state:
    st.session_state.processing = False

if "rule_enabled" not in st.session_state:
    st.session_state.rule_enabled = {i: True for i in range(1, 8)}

if "current_input" not in st.session_state:
    st.session_state.current_input = ""


# ── Helper functions ─────────────────────────────────────────────────────────
def _detect_language(text: str) -> str:
    if not text or not text.strip():
        return "neutral"
    if re.search(r'[֐-׿]', text):
        return "heb"
    return "eng"


def _parse_constitution_rules(constitution: str) -> dict[int, str]:
    rules = {}
    for line in constitution.splitlines():
        m = re.match(r"RULE\s+(\d+)\s*:\s*(.+)", line.strip())
        if m:
            rules[int(m.group(1))] = m.group(2).strip()
    return rules


def _build_filtered_constitution() -> str:
    rules = _parse_constitution_rules(st.session_state.constitution_text)
    lines = st.session_state.constitution_text.splitlines()
    result = []
    for line in lines:
        m = re.match(r"RULE\s+(\d+)\s*:", line.strip())
        if m:
            rule_num = int(m.group(1))
            if not st.session_state.rule_enabled.get(rule_num, True):
                continue
        result.append(line)
    return "\n".join(result)


def _get_triggered_rules(veto_log: list) -> set[int]:
    triggered = set()
    for entry in veto_log:
        m = re.search(r"RULE\s+(\d+)", entry.get("reason", ""), re.IGNORECASE)
        if m:
            triggered.add(int(m.group(1)))
    return triggered


def _get_vetoed_rules(veto_log: list) -> set[int]:
    return _get_triggered_rules(veto_log)


def _get_agent_status(agent_name: str, reviews: dict, veto_log: list) -> str:
    for entry in veto_log:
        if entry.get("agent") == agent_name and entry.get("stage") == "pre_screen":
            return "prescreen"
    review = reviews.get(agent_name, {})
    if review.get("vetoed"):
        return "llmveto"
    return "approved"


def _run_agent(agent_type: str, prompt: str, history_context: str, llm_client) -> dict:
    agent = SpecialistFactory.create(agent_type, llm_client)
    response = agent.analyze(prompt, previous_findings=history_context)
    return {"name": agent.name, "response": response, "type": agent_type}


def process_event(event_text: str):
    st.session_state.chat_history.append({"role": "user", "content": event_text})

    history_context = "\n".join(
        f"{m['role']}: {m['content']}"
        for m in st.session_state.chat_history[:-1]
    )

    agent_types = ["fire", "police", "medical"]
    llm = st.session_state.llm

    agent_reports: dict[str, str] = {}
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {
            executor.submit(_run_agent, atype, event_text, history_context, llm): atype
            for atype in agent_types
        }
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            agent_reports[result["name"]] = result["response"]

    commander = CommanderAgent(llm)

    import agents.commander_agent as _ca_module
    original_constitution = _ca_module.CONSTITUTION
    original_triggers = _ca_module.VETO_TRIGGERS
    _ca_module.CONSTITUTION = _build_filtered_constitution()
    _ca_module.VETO_TRIGGERS = st.session_state.veto_triggers

    review_result = commander.review_and_synthesize(agent_reports)

    _ca_module.CONSTITUTION = original_constitution
    _ca_module.VETO_TRIGGERS = original_triggers

    reviews        = review_result["reviews"]
    final_plan     = review_result["final_plan"]
    veto_log       = review_result["veto_log"]
    urgency_scores = review_result.get("urgency_scores", {})
    conflicts      = review_result.get("conflicts", [])

    agent_icons = {"Fire_Bot": "🔥", "Police_Bot": "🚔", "Med_Bot": "🏥"}
    specialist_entries = []
    for agent_name, report_text in agent_reports.items():
        review = reviews.get(agent_name, {})
        icon = agent_icons.get(agent_name, "🤖")
        urgency = urgency_scores.get(agent_name)
        status = _get_agent_status(agent_name, reviews, veto_log)

        specialist_entries.append({
            "name":          agent_name,
            "icon":          icon,
            "status":        status,
            "reason":        review.get("reason", ""),
            "report":        report_text,
            "urgency_label": urgency.label if urgency else "N/A",
            "urgency_score": urgency.score if urgency else None,
        })

    st.session_state.last_result = {
        "input":        event_text,
        "specialists":  specialist_entries,
        "final_plan":   final_plan,
        "veto_log":     veto_log,
        "conflicts":    conflicts,
        "timestamp":    datetime.now().strftime("%H:%M:%S"),
    }
    st.session_state.processing = False
    st.rerun()


# ── Title bar ────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="app-titlebar">
  <span style="font-size:18px;">🎖️</span>
  <div>
    <div class="app-title">Command Core</div>
    <div class="app-subtitle">TACTICAL OPERATIONS CENTER · CONSENSUS ENGINE M4</div>
  </div>
  <div class="app-time">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
</div>
""", unsafe_allow_html=True)


# ── Sidebar ──────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="section-header">🛡 control panel</div>', unsafe_allow_html=True)

    if st.button("⟳  New Incident", use_container_width=True):
        st.session_state.chat_history = []
        st.session_state.last_result = None
        st.session_state.current_input = ""
        st.rerun()

    st.markdown("---")

    # ── Rule Management Grid ──
    st.markdown('<div class="section-header">⚖ constitution rules</div>', unsafe_allow_html=True)
    rules_parsed = _parse_constitution_rules(st.session_state.constitution_text)

    for rule_num in range(1, 8):
        rule_text = rules_parsed.get(rule_num, f"Rule {rule_num}")
        icon = _RULE_ICONS.get(rule_num, "•")
        short = rule_text[:38] + ("…" if len(rule_text) > 38 else "")
        col_lbl, col_tog = st.columns([3, 1])
        with col_lbl:
            st.markdown(
                f'<div style="font-family:\'Roboto Mono\',monospace;font-size:10px;'
                f'color:#8b949e;padding:4px 0;">{icon} RULE {rule_num}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div style="font-size:9px;color:#6e7681;padding-bottom:4px;line-height:1.3;">'
                f'{short}</div>',
                unsafe_allow_html=True,
            )
        with col_tog:
            enabled = st.toggle(
                "", value=st.session_state.rule_enabled.get(rule_num, True),
                key=f"rule_toggle_{rule_num}",
                label_visibility="collapsed",
            )
            st.session_state.rule_enabled[rule_num] = enabled

    st.markdown("---")

    # ── Trigger Chip Manager ──
    st.markdown('<div class="section-header">🔍 veto trigger manager</div>', unsafe_allow_html=True)

    triggers_to_delete = []
    for phrase in list(st.session_state.veto_triggers.keys()):
        rule_label = st.session_state.veto_triggers[phrase]
        short_label = rule_label[:30] + ("…" if len(rule_label) > 30 else "")
        c1, c2 = st.columns([4, 1])
        with c1:
            st.markdown(
                f'<div class="trigger-chip" style="width:100%;justify-content:space-between;">'
                f'<span style="color:#58a6ff;">{phrase}</span>'
                f'<span style="color:#6e7681;font-size:9px;">{short_label}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with c2:
            if st.button("×", key=f"del_trigger_{phrase}", help=f"Remove: {phrase}"):
                triggers_to_delete.append(phrase)

    for phrase in triggers_to_delete:
        del st.session_state.veto_triggers[phrase]
    if triggers_to_delete:
        st.rerun()

    st.markdown('<div style="margin-top:8px;"></div>', unsafe_allow_html=True)
    with st.expander("＋ Add Trigger", expanded=False):
        new_phrase = st.text_input("Phrase (keyword to detect)", key="new_trigger_phrase",
                                   placeholder="e.g. unstable roof")
        new_rule   = st.text_input("Rule label", key="new_trigger_rule",
                                   placeholder="e.g. RULE 2 — Structural hazard")
        if st.button("Add Trigger", use_container_width=True, key="add_trigger_btn"):
            if new_phrase.strip() and new_rule.strip():
                st.session_state.veto_triggers[new_phrase.strip()] = new_rule.strip()
                st.success(f"Added: \"{new_phrase.strip()}\"")
                st.rerun()
            else:
                st.error("Both fields required.")

    st.markdown("---")

    # ── File upload ──
    st.markdown('<div class="section-header">📁 field report upload</div>', unsafe_allow_html=True)
    uploaded_file = st.file_uploader("Upload report", type=["txt", "md"], label_visibility="collapsed")
    if uploaded_file is not None:
        file_bytes = uploaded_file.read()
        if len(file_bytes) > MAX_UPLOAD_BYTES:
            st.error(f"File too large ({len(file_bytes)/1024/1024:.2f} MB). Max 2 MB.")
        else:
            file_content = file_bytes.decode("utf-8", errors="replace")
            if st.button("🚀 Process Report", use_container_width=True):
                process_event(f"📄 FIELD REPORT UPLOADED:\n\n{file_content}")

    st.markdown("---")
    st.markdown(
        '<div style="font-size:9px;color:#30363d;font-family:\'Roboto Mono\',monospace;">'
        'URGENCY: 🔴 CRITICAL · 🟠 HIGH · 🟡 MEDIUM · 🟢 LOW</div>',
        unsafe_allow_html=True,
    )


# ── Three-column layout ──────────────────────────────────────────────────────
left_col, center_col, right_col = st.columns([1, 1.4, 1.2], gap="small")

result = st.session_state.last_result

# ── LEFT COLUMN ──────────────────────────────────────────────────────────────
with left_col:
    st.markdown('<div class="col-panel">', unsafe_allow_html=True)

    st.markdown('<div class="section-header">📡 incident feed</div>', unsafe_allow_html=True)

    event_text = st.text_area(
        "Incident Description",
        value=st.session_state.current_input,
        height=110,
        placeholder="Describe the incident...\nתאר את האירוע...",
        label_visibility="collapsed",
        key="incident_input",
    )
    if event_text != st.session_state.current_input:
        st.session_state.current_input = event_text

    # Language LED
    lang = _detect_language(event_text)
    if lang == "heb":
        led_html = ('<div class="led-container"><div class="led led-heb">'
                    '<span class="led-dot"></span>HEB</div>'
                    '<span style="font-size:10px;color:#6e7681;">Hebrew detected</span></div>')
    elif lang == "eng":
        led_html = ('<div class="led-container"><div class="led led-eng">'
                    '<span class="led-dot"></span>ENG</div>'
                    '<span style="font-size:10px;color:#6e7681;">English detected</span></div>')
    else:
        led_html = ('<div class="led-container"><div class="led led-neutral">'
                    '<span class="led-dot"></span>---</div>'
                    '<span style="font-size:10px;color:#6e7681;">Awaiting input</span></div>')
    st.markdown(led_html, unsafe_allow_html=True)

    dispatch_btn = st.button(
        "▶  DISPATCH TO COMMAND",
        use_container_width=True,
        type="primary",
        disabled=not event_text.strip(),
    )
    if dispatch_btn and event_text.strip():
        st.session_state.processing = True
        process_event(event_text)

    if st.session_state.processing:
        st.markdown(
            '<div class="info-box">⚡ Specialists analysing in parallel…</div>',
            unsafe_allow_html=True,
        )

    # Constitution Tree
    st.markdown(
        '<div class="section-header" style="margin-top:14px;">⚖ active constitution</div>',
        unsafe_allow_html=True,
    )

    triggered_rules = set()
    if result:
        triggered_rules = _get_triggered_rules(result.get("veto_log", []))

    rules_parsed = _parse_constitution_rules(st.session_state.constitution_text)
    for rule_num in range(1, 8):
        rule_text = rules_parsed.get(rule_num, f"Rule {rule_num}")
        enabled = st.session_state.rule_enabled.get(rule_num, True)
        icon = _RULE_ICONS.get(rule_num, "•")
        short = rule_text[:50] + ("…" if len(rule_text) > 50 else "")

        if not enabled:
            css_class = "rule-badge disabled"
        elif rule_num in triggered_rules:
            css_class = "rule-badge vetoed"
        else:
            css_class = "rule-badge" + (" active" if result else "")

        st.markdown(
            f'<div class="{css_class}">'
            f'<span style="font-size:14px;">{icon}</span>'
            f'<span class="rule-num">R-{rule_num}</span>'
            f'<span class="rule-text">{short}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # Recent incident history
    if st.session_state.chat_history:
        st.markdown(
            '<div class="section-header" style="margin-top:14px;">📋 session history</div>',
            unsafe_allow_html=True,
        )
        for msg in reversed(st.session_state.chat_history[-6:]):
            if msg["role"] == "user":
                preview = msg["content"][:60] + ("…" if len(msg["content"]) > 60 else "")
                st.markdown(
                    f'<div style="font-family:\'Roboto Mono\',monospace;font-size:9px;'
                    f'color:#6e7681;padding:3px 0;border-left:2px solid #30363d;padding-left:6px;'
                    f'margin-bottom:3px;">{preview}</div>',
                    unsafe_allow_html=True,
                )

    st.markdown('</div>', unsafe_allow_html=True)


# ── CENTER COLUMN ─────────────────────────────────────────────────────────────
with center_col:
    st.markdown('<div class="col-panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-header">🤖 operational analysis</div>', unsafe_allow_html=True)

    _AGENT_CSS = {
        "Fire_Bot":   ("agent-fire",   "🔥", "#fb923c"),
        "Med_Bot":    ("agent-med",    "🏥", "#22d3ee"),
        "Police_Bot": ("agent-police", "🚔", "#60a5fa"),
    }
    _URGENCY_CSS = {
        "CRITICAL": "u-critical", "HIGH": "u-high",
        "MEDIUM": "u-medium", "LOW": "u-low",
    }
    _STATUS_INFO = {
        "approved":  ("status-approved",  "dot-approved",  "✓ APPROVED"),
        "prescreen": ("status-prescreen", "dot-prescreen", "⚠ PRE-SCREEN VETO"),
        "llmveto":   ("status-llmveto",   "dot-llmveto",   "✕ LLM VETO"),
    }

    if result and result.get("specialists"):
        for entry in result["specialists"]:
            agent_name  = entry["name"]
            css_card, icon, _ = _AGENT_CSS.get(agent_name, ("agent-police", "🤖", "#60a5fa"))
            status      = entry.get("status", "approved")
            urgency_lbl = entry.get("urgency_label", "N/A")
            urgency_scr = entry.get("urgency_score")
            reason      = entry.get("reason", "")

            status_chip_cls, dot_cls, status_text = _STATUS_INFO[status]
            urgency_chip_cls = _URGENCY_CSS.get(urgency_lbl, "u-na")
            score_str = f" {urgency_scr:.1f}" if urgency_scr is not None else ""

            st.markdown(
                f'<div class="agent-card {css_card}">'
                f'  <div class="agent-header">'
                f'    <span class="agent-icon">{icon}</span>'
                f'    <span class="agent-name">{agent_name}</span>'
                f'    <span class="urgency-badge {urgency_chip_cls}">{urgency_lbl}{score_str}</span>'
                f'  </div>'
                f'  <div style="margin-bottom:6px;">'
                f'    <span class="status-chip {status_chip_cls}">'
                f'      <span class="status-dot {dot_cls}"></span>{status_text}'
                f'    </span>'
                f'  </div>'
                f'  {("<div style=\"font-size:10px;color:#8b949e;font-family:\'Roboto Mono\',monospace;margin-top:4px;\">⚑ " + reason + "</div>") if reason else ""}'
                f'</div>',
                unsafe_allow_html=True,
            )

            with st.expander(f"↳ {agent_name} Full Report", expanded=False):
                st.markdown(
                    f'<div style="font-family:\'Roboto Mono\',monospace;font-size:11px;'
                    f'color:#c9d1d9;line-height:1.7;white-space:pre-wrap;">'
                    f'{entry["report"]}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
    else:
        st.markdown(
            '<div class="info-box" style="margin-top:20px;text-align:center;">'
            '🛰  Awaiting incident input.<br>'
            '<span style="font-size:10px;color:#4a5568;">Specialist agents will appear here.</span>'
            '</div>',
            unsafe_allow_html=True,
        )

    st.markdown('</div>', unsafe_allow_html=True)


# ── RIGHT COLUMN ──────────────────────────────────────────────────────────────
with right_col:
    st.markdown('<div class="col-panel">', unsafe_allow_html=True)
    st.markdown('<div class="section-header">📨 unified command decision</div>', unsafe_allow_html=True)

    if result and result.get("final_plan"):
        ts = result.get("timestamp", "")
        st.markdown(
            f'<div class="dispatch-box">'
            f'  <div class="dispatch-header">'
            f'    COMMAND CORE // PRIORITY DISPATCH // {ts}'
            f'  </div>'
            f'  <div class="dispatch-body">{result["final_plan"]}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="dispatch-box" style="min-height:80px;">'
            '<div class="dispatch-header">COMMAND CORE // AWAITING INCIDENT</div>'
            '<div style="color:#44403c;font-family:\'Roboto Mono\',monospace;font-size:11px;">'
            '[ No active dispatch ]</div>'
            '</div>',
            unsafe_allow_html=True,
        )

    # Veto Audit Log
    st.markdown(
        '<div class="section-header" style="margin-top:14px;">📋 veto audit log</div>',
        unsafe_allow_html=True,
    )

    veto_log = (result or {}).get("veto_log", [])
    if veto_log:
        rows = ""
        ts_display = (result or {}).get("timestamp", "--:--:--")
        for entry in veto_log:
            stage = entry.get("stage", "")
            stage_css = "stage-pre" if stage == "pre_screen" else "stage-llm"
            stage_label = "PRE-SCREEN" if stage == "pre_screen" else "LLM-REVIEW"
            agent  = entry.get("agent", "—")
            reason = entry.get("reason", "—")
            rows += (
                f"<tr>"
                f"<td style='color:#6e7681;'>{ts_display}</td>"
                f"<td>{agent}</td>"
                f"<td class='{stage_css}'>{stage_label}</td>"
                f"<td style='color:#8b949e;'>{reason}</td>"
                f"</tr>"
            )
        st.markdown(
            f'<table class="veto-table">'
            f'<thead><tr><th>Time</th><th>Agent</th><th>Stage</th><th>Tactical Reason</th></tr></thead>'
            f'<tbody>{rows}</tbody>'
            f'</table>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div style="font-family:\'Roboto Mono\',monospace;font-size:10px;'
            'color:#30363d;padding:8px 0;">No vetoes recorded.</div>',
            unsafe_allow_html=True,
        )

    # Conflict Resolution Panel
    st.markdown(
        '<div class="section-header" style="margin-top:14px;">⚔ conflict resolution</div>',
        unsafe_allow_html=True,
    )

    conflicts = (result or {}).get("conflicts", [])
    if conflicts:
        for c in conflicts:
            topic = c.topic.replace("_", " ").upper()
            st.markdown(
                f'<div class="conflict-card">'
                f'  <div class="conflict-topic">⚑ {topic}</div>'
                f'  <div style="font-size:10px;color:#c9d1d9;">'
                f'    <span style="color:#8b949e;">{c.agent_a}</span>'
                f'    <span style="color:#6e7681;"> [{c.stance_a}] ⟷ </span>'
                f'    <span style="color:#8b949e;">{c.agent_b}</span>'
                f'    <span style="color:#6e7681;"> [{c.stance_b}]</span>'
                f'  </div>'
                f'  <div style="margin-top:3px;">'
                f'    <span style="color:#6e7681;font-size:9px;">WINNER → </span>'
                f'    <span class="conflict-winner">{c.winner}</span>'
                f'  </div>'
                f'  <div class="conflict-reason">↳ {c.resolution_reason}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            '<div style="font-family:\'Roboto Mono\',monospace;font-size:10px;'
            'color:#30363d;padding:8px 0;">No conflicts detected.</div>',
            unsafe_allow_html=True,
        )

    st.markdown('</div>', unsafe_allow_html=True)
