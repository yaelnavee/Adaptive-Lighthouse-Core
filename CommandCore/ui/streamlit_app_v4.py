"""
Command Core — Streamlit UI v4 (Corporate Light Tactical)
==========================================================
Two-zone layout — 30% left management panel + 70% main operational area.
Three vertical stages in main area: Input → Agent Analysis → Command Decision.

Stage 3 contains Veto Audit Log and Conflict Resolution inline (not separate cards).

All backend logic identical to streamlit_app.py (Milestone 4).
To run: streamlit run ui/streamlit_app_v4.py
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
    "CRITICAL": ("🔴", "u-critical"),
    "HIGH":     ("🟠", "u-high"),
    "MEDIUM":   ("🟡", "u-medium"),
    "LOW":      ("🟢", "u-low"),
}

_RULE_ICONS = {
    1: "❤️", 2: "🏗️", 3: "🚑", 4: "💊", 5: "🔥", 6: "⚖️", 7: "🎖️",
}

st.set_page_config(
    page_title="Command Core — Operations Center",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

/* ── Reset & Global ── */
html, body, [class*="css"] {
    font-family: 'Inter', system-ui, -apple-system, sans-serif !important;
    background-color: #F8FAFC !important;
    color: #1E293B !important;
}
.stApp { background-color: #F8FAFC !important; }
.main .block-container {
    padding: 0 !important;
    max-width: 100% !important;
}

/* ── Hide default Streamlit sidebar ── */
[data-testid="collapsedControl"] { display: none !important; }
[data-testid="stSidebar"] { display: none !important; }

/* ── Title bar ── */
.titlebar {
    background: #FFFFFF;
    border-bottom: 2px solid #E2E8F0;
    padding: 12px 24px;
    display: flex;
    align-items: center;
    gap: 14px;
    margin-bottom: 0;
}
.titlebar-icon { font-size: 22px; }
.titlebar-title {
    font-size: 18px;
    font-weight: 800;
    color: #0052CC;
    letter-spacing: -0.3px;
}
.titlebar-sub {
    font-size: 11px;
    color: #64748B;
    font-weight: 400;
    letter-spacing: 0.5px;
}
.titlebar-time {
    margin-left: auto;
    font-size: 11px;
    color: #94A3B8;
    font-variant-numeric: tabular-nums;
}

/* ── Panel section headers ── */
.panel-section-header {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: #64748B;
    border-bottom: 1px solid #CBD5E1;
    padding-bottom: 6px;
    margin: 14px 0 8px 0;
}

/* ── Rule toggle row ── */
.rule-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 5px 8px;
    border-radius: 6px;
    margin-bottom: 3px;
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    transition: border-color 0.15s;
}
.rule-row.active   { border-color: #BFDBFE; background: #EFF6FF; }
.rule-row.triggered { border-color: #FCA5A5; background: #FEF2F2; }
.rule-row.disabled { opacity: 0.35; }
.rule-icon { font-size: 13px; }
.rule-num  { font-size: 10px; font-weight: 700; color: #94A3B8; min-width: 34px; }
.rule-text { font-size: 10px; color: #475569; flex: 1; line-height: 1.3; }
.rule-row.active    .rule-text { color: #1D4ED8; }
.rule-row.triggered .rule-text { color: #DC2626; }

/* ── Trigger chip ── */
.trigger-chip {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    background: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 20px;
    padding: 3px 10px;
    font-size: 11px;
    color: #0052CC;
    font-weight: 500;
}

/* ── Stage cards ── */
.stage-card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 12px;
    padding: 20px 22px;
    margin-bottom: 18px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.stage-title {
    font-size: 13px;
    font-weight: 800;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: #1E293B;
    margin-bottom: 14px;
}

/* ── Language LED ── */
.led-wrap { display: flex; align-items: center; gap: 8px; margin: 8px 0 10px 0; }
.led {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 12px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
}
.led-dot { width: 8px; height: 8px; border-radius: 50%; }
.led-heb     { background: #EFF6FF; border: 1.5px solid #93C5FD; color: #1D4ED8; }
.led-heb     .led-dot { background: #3B82F6; box-shadow: 0 0 5px #93C5FD; }
.led-eng     { background: #F0FDF4; border: 1.5px solid #86EFAC; color: #15803D; }
.led-eng     .led-dot { background: #22C55E; box-shadow: 0 0 5px #86EFAC; }
.led-neutral { background: #F8FAFC; border: 1.5px solid #CBD5E1; color: #94A3B8; }
.led-neutral .led-dot { background: #CBD5E1; }

/* ── Dispatch button ── */
button[kind="primary"] {
    background: #0052CC !important;
    border: none !important;
    color: #FFFFFF !important;
    font-weight: 700 !important;
    font-size: 14px !important;
    letter-spacing: 0.5px !important;
    border-radius: 8px !important;
    padding: 12px 0 !important;
    box-shadow: 0 2px 8px rgba(0,82,204,0.3) !important;
    transition: all 0.15s !important;
}
button[kind="primary"]:hover {
    background: #0047B3 !important;
    box-shadow: 0 4px 14px rgba(0,82,204,0.4) !important;
}
button[kind="primary"]:disabled {
    background: #94A3B8 !important;
    box-shadow: none !important;
    cursor: not-allowed !important;
}

/* ── Agent analysis cards ── */
.agent-analysis-card {
    background: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 10px;
    padding: 14px 16px;
    border-left-width: 4px;
    border-left-style: solid;
    height: 100%;
    box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.agent-fire-card   { border-left-color: #F97316; }
.agent-med-card    { border-left-color: #0EA5E9; }
.agent-police-card { border-left-color: #1E40AF; }

.agent-card-name { font-size: 13px; font-weight: 700; margin-bottom: 8px; }
.agent-fire-card   .agent-card-name { color: #C2410C; }
.agent-med-card    .agent-card-name { color: #0369A1; }
.agent-police-card .agent-card-name { color: #1E40AF; }

/* ── Status badges ── */
.status-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 4px 10px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.3px;
    margin-bottom: 6px;
}
.status-dot { width: 7px; height: 7px; border-radius: 50%; }

.status-approved  { background: #F0FDF4; border: 1px solid #86EFAC; color: #15803D; }
.dot-approved     { background: #22C55E; box-shadow: 0 0 4px #86EFAC; }
.status-prescreen { background: #FFF7ED; border: 1px solid #FDBA74; color: #C2410C; }
.dot-prescreen    { background: #F97316; box-shadow: 0 0 4px #FDBA74; }
.status-llmveto   { background: #FEF2F2; border: 1px solid #FCA5A5; color: #DC2626; }
.dot-llmveto      { background: #EF4444; box-shadow: 0 0 4px #FCA5A5; }

/* ── Urgency badges ── */
.urgency-badge {
    display: inline-flex;
    align-items: center;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.5px;
    margin-left: 6px;
}
.u-critical { background: #FEF2F2; border: 1px solid #FECACA; color: #DC2626; }
.u-high     { background: #FFF7ED; border: 1px solid #FED7AA; color: #C2410C; }
.u-medium   { background: #FEFCE8; border: 1px solid #FDE68A; color: #92400E; }
.u-low      { background: #F0FDF4; border: 1px solid #BBF7D0; color: #15803D; }
.u-na       { background: #F8FAFC; border: 1px solid #E2E8F0; color: #94A3B8; }

/* ── Unified Command Decision card (Stage 3) ── */
.command-decision-card {
    background: #F0F5FF;
    border: 2px solid #3B82F6;
    border-radius: 12px;
    padding: 22px 24px;
    margin-bottom: 18px;
}
.command-decision-title {
    font-size: 14px;
    font-weight: 800;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: #1E40AF;
    margin-bottom: 14px;
    padding-bottom: 10px;
    border-bottom: 1px solid #BFDBFE;
}
.command-decision-text {
    font-size: 16px;
    font-weight: 600;
    color: #1E293B;
    line-height: 1.7;
    white-space: pre-wrap;
}

/* ── Veto Audit Log section (inside Stage 3) ── */
.veto-section-header {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    color: #475569;
    margin: 18px 0 8px 0;
    padding-top: 14px;
    border-top: 1px solid #BFDBFE;
}
.veto-tbl { width: 100%; border-collapse: collapse; font-size: 12px; }
.veto-tbl th {
    background: #E8EFFE;
    color: #475569;
    padding: 8px 10px;
    text-align: left;
    border-bottom: 2px solid #BFDBFE;
    font-weight: 700;
    font-size: 11px;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}
.veto-tbl td {
    padding: 8px 10px;
    border-bottom: 1px solid #DBEAFE;
    color: #334155;
    vertical-align: top;
}
.veto-tbl tr:hover td { background: #EFF6FF; }
.stage-pre { color: #C2410C; font-weight: 700; }
.stage-llm { color: #DC2626; font-weight: 700; }

/* ── Conflict card (inside Stage 3) ── */
.conflict-section-header {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    color: #475569;
    margin: 18px 0 8px 0;
    padding-top: 14px;
    border-top: 1px solid #BFDBFE;
}
.conflict-card {
    background: #EEF2FF;
    border: 1px solid #C7D2FE;
    border-left: 3px solid #6366F1;
    border-radius: 8px;
    padding: 10px 14px;
    margin-bottom: 8px;
}
.conflict-topic {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.5px;
    color: #4F46E5;
    text-transform: uppercase;
    margin-bottom: 5px;
}
.conflict-winner { color: #15803D; font-weight: 700; }
.conflict-reason { color: #64748B; font-size: 11px; margin-top: 4px; }

/* ── Empty state ── */
.empty-state {
    background: #F8FAFC;
    border: 1.5px dashed #CBD5E1;
    border-radius: 10px;
    padding: 28px 20px;
    text-align: center;
    color: #94A3B8;
    font-size: 13px;
}

/* ── Text area / input overrides ── */
.stTextArea textarea {
    background: #FFFFFF !important;
    color: #1E293B !important;
    border: 1.5px solid #CBD5E1 !important;
    border-radius: 8px !important;
    font-size: 16px !important;
    line-height: 1.6 !important;
}
.stTextArea textarea:focus {
    border-color: #0052CC !important;
    box-shadow: 0 0 0 3px rgba(0,82,204,0.12) !important;
}
.stTextInput input {
    background: #FFFFFF !important;
    color: #1E293B !important;
    border: 1.5px solid #CBD5E1 !important;
    border-radius: 8px !important;
    font-size: 13px !important;
}
.stTextInput input:focus {
    border-color: #0052CC !important;
    box-shadow: 0 0 0 3px rgba(0,82,204,0.12) !important;
}

/* ── Expander ── */
.streamlit-expanderHeader {
    background: #F8FAFC !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 8px !important;
    color: #475569 !important;
    font-size: 12px !important;
}

/* ── Toggle / checkbox ── */
.stToggle label, .stCheckbox label { color: #475569 !important; font-size: 12px !important; }

/* ── Scrollable report area ── */
.report-scroll {
    max-height: 280px;
    overflow-y: auto;
    font-size: 12px;
    color: #334155;
    line-height: 1.65;
    white-space: pre-wrap;
    padding: 10px 12px;
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 6px;
    scrollbar-width: thin;
    scrollbar-color: #CBD5E1 #F8FAFC;
}
</style>
""", unsafe_allow_html=True)


# ── Session state ─────────────────────────────────────────────────────────────
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


# ── Helper functions ──────────────────────────────────────────────────────────
def _detect_language(text: str) -> str:
    if not text or not text.strip():
        return "neutral"
    if re.search(r'[֐-׿]', text):
        return "heb"
    return "eng"


def _parse_constitution_rules(constitution: str) -> dict[int, str]:
    rules: dict[int, str] = {}
    for line in constitution.splitlines():
        m = re.match(r"RULE\s+(\d+)\s*:\s*(.+)", line.strip())
        if m:
            rules[int(m.group(1))] = m.group(2).strip()
    return rules


def _build_filtered_constitution() -> str:
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
    triggered: set[int] = set()
    for entry in veto_log:
        m = re.search(r"RULE\s+(\d+)", entry.get("reason", ""), re.IGNORECASE)
        if m:
            triggered.add(int(m.group(1)))
    return triggered


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
        "input":       event_text,
        "specialists": specialist_entries,
        "final_plan":  final_plan,
        "veto_log":    veto_log,
        "conflicts":   conflicts,
        "timestamp":   datetime.now().strftime("%H:%M:%S"),
    }
    st.session_state.processing = False
    st.rerun()


# ── Title bar ─────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="titlebar">
  <span class="titlebar-icon">⚖️</span>
  <div>
    <div class="titlebar-title">Command Core</div>
    <div class="titlebar-sub">CONSENSUS ENGINE · MILESTONE 4</div>
  </div>
  <div class="titlebar-time">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
</div>
""", unsafe_allow_html=True)

# ── Two-zone columns ──────────────────────────────────────────────────────────
left_panel, main_area = st.columns([3, 7], gap="small")

result = st.session_state.last_result

# =============================================================================
# LEFT PANEL — Management Panel (30%)
# =============================================================================
with left_panel:
    st.markdown(
        '<div style="background:#F4F6F9;border-right:1px solid #CBD5E1;'
        'padding:6px 2px 20px 2px;min-height:calc(100vh - 62px);">',
        unsafe_allow_html=True,
    )

    if st.button("↺  New Incident", use_container_width=True):
        st.session_state.chat_history = []
        st.session_state.last_result = None
        st.session_state.current_input = ""
        st.rerun()

    # ── Constitution Rules (collapsible accordion) ──
    with st.expander("⚖️ Constitution Rules", expanded=False):
        st.caption(
            "Toggle rules on/off — changes apply to the next dispatch. "
            "Keep the `RULE N:` prefix format."
        )
        rules_parsed = _parse_constitution_rules(st.session_state.constitution_text)
        triggered_rules = _get_triggered_rules((result or {}).get("veto_log", []))

        for rule_num in range(1, 8):
            rule_text = rules_parsed.get(rule_num, f"Rule {rule_num}")
            icon = _RULE_ICONS.get(rule_num, "•")
            short = rule_text[:44] + ("…" if len(rule_text) > 44 else "")
            enabled = st.session_state.rule_enabled.get(rule_num, True)

            if not enabled:
                row_cls = "rule-row disabled"
            elif rule_num in triggered_rules:
                row_cls = "rule-row triggered"
            elif result:
                row_cls = "rule-row active"
            else:
                row_cls = "rule-row"

            c_lbl, c_tog = st.columns([4, 1])
            with c_lbl:
                st.markdown(
                    f'<div class="{row_cls}">'
                    f'<span class="rule-icon">{icon}</span>'
                    f'<span class="rule-num">R-{rule_num}</span>'
                    f'<span class="rule-text">{short}</span>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            with c_tog:
                new_val = st.toggle(
                    "",
                    value=st.session_state.rule_enabled.get(rule_num, True),
                    key=f"rule_toggle_{rule_num}",
                    label_visibility="collapsed",
                )
                st.session_state.rule_enabled[rule_num] = new_val

        st.markdown('<div style="margin-top:10px;"></div>', unsafe_allow_html=True)
        st.caption("Edit raw constitution text:")
        edited_constitution = st.text_area(
            "Constitution",
            value=st.session_state.constitution_text,
            height=200,
            label_visibility="collapsed",
            key="constitution_editor_v4",
        )
        if edited_constitution != st.session_state.constitution_text:
            st.session_state.constitution_text = edited_constitution
            st.success("✓ Constitution updated.")

    # ── Veto Trigger Manager (collapsible accordion) ──
    with st.expander("🔍 Veto Trigger Manager", expanded=False):
        st.caption(
            "Phrases detected at pre-screen stage (case-insensitive). "
            "Click × to remove."
        )

        triggers_to_delete = []
        for phrase in list(st.session_state.veto_triggers.keys()):
            rule_label = st.session_state.veto_triggers[phrase]
            short_label = rule_label[:28] + ("…" if len(rule_label) > 28 else "")
            c1, c2 = st.columns([5, 1])
            with c1:
                st.markdown(
                    f'<div class="trigger-chip" style="width:100%;justify-content:space-between;">'
                    f'<span>{phrase}</span>'
                    f'<span style="color:#94A3B8;font-size:9px;">{short_label}</span>'
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
        new_phrase = st.text_input(
            "Phrase", key="new_trigger_phrase_v4", placeholder="e.g. unstable roof"
        )
        new_rule = st.text_input(
            "Rule label", key="new_trigger_rule_v4", placeholder="e.g. RULE 2 — Structural hazard"
        )
        if st.button("＋ Add Trigger", use_container_width=True, key="add_trigger_btn_v4"):
            if new_phrase.strip() and new_rule.strip():
                st.session_state.veto_triggers[new_phrase.strip()] = new_rule.strip()
                st.success(f"Added: \"{new_phrase.strip()}\"")
                st.rerun()
            else:
                st.warning("Both fields are required.")

        st.markdown('<div style="margin-top:8px;"></div>', unsafe_allow_html=True)
        st.caption("Or edit raw JSON:")
        triggers_json_str = json.dumps(st.session_state.veto_triggers, indent=2)
        edited_triggers = st.text_area(
            "Triggers JSON",
            value=triggers_json_str,
            height=160,
            label_visibility="collapsed",
            key="triggers_json_editor_v4",
        )
        if st.button("💾 Save JSON", use_container_width=True, key="save_triggers_json_v4"):
            try:
                parsed = json.loads(edited_triggers)
                st.session_state.veto_triggers = parsed
                st.success("✓ Triggers saved.")
            except json.JSONDecodeError as exc:
                st.error(f"Invalid JSON: {exc}")

    # ── Field Report Upload ──
    st.markdown(
        '<div class="panel-section-header" style="margin-top:14px;">📁 Field Report Upload</div>',
        unsafe_allow_html=True,
    )
    st.caption(f"Accepted: .txt / .md — max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")

    uploaded_file = st.file_uploader(
        "Upload report",
        type=["txt", "md"],
        label_visibility="collapsed",
        key="file_uploader_v4",
    )
    if uploaded_file is not None:
        file_bytes = uploaded_file.read()
        if len(file_bytes) > MAX_UPLOAD_BYTES:
            size_mb = len(file_bytes) / (1024 * 1024)
            st.error(
                f"❌ File too large ({size_mb:.2f} MB). "
                f"Max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
            )
        else:
            file_content = file_bytes.decode("utf-8", errors="replace")
            if st.button("🚀 Process Report", use_container_width=True, key="process_upload_btn_v4"):
                process_event(f"📄 FIELD REPORT UPLOADED:\n\n{file_content}")

    st.markdown(
        '<div style="margin-top:18px;padding:8px;background:#EFF6FF;border-radius:6px;'
        'border:1px solid #BFDBFE;font-size:10px;color:#1D4ED8;text-align:center;">'
        '🔴 CRITICAL · 🟠 HIGH · 🟡 MEDIUM · 🟢 LOW'
        '</div>',
        unsafe_allow_html=True,
    )

    st.markdown('</div>', unsafe_allow_html=True)


# =============================================================================
# MAIN AREA — Three-stage operational flow (70%)
# =============================================================================
with main_area:

    # =========================================================================
    # STAGE 1 — Incident Input
    # =========================================================================
    st.markdown('<div class="stage-card">', unsafe_allow_html=True)
    st.markdown(
        '<div class="stage-title">📡 Field Report Dispatch</div>',
        unsafe_allow_html=True,
    )

    event_text = st.text_area(
        "Incident",
        value=st.session_state.current_input,
        height=110,
        placeholder="Describe the incident in detail…\nתאר את האירוע בפירוט…",
        label_visibility="collapsed",
        key="incident_input_v4",
    )
    if event_text != st.session_state.current_input:
        st.session_state.current_input = event_text

    # Language LED
    lang = _detect_language(event_text)
    if lang == "heb":
        led_html = (
            '<div class="led-wrap">'
            '<div class="led led-heb"><span class="led-dot"></span>HEB</div>'
            '<span style="font-size:11px;color:#64748B;">Hebrew detected</span></div>'
        )
    elif lang == "eng":
        led_html = (
            '<div class="led-wrap">'
            '<div class="led led-eng"><span class="led-dot"></span>ENG</div>'
            '<span style="font-size:11px;color:#64748B;">English detected</span></div>'
        )
    else:
        led_html = (
            '<div class="led-wrap">'
            '<div class="led led-neutral"><span class="led-dot"></span>---</div>'
            '<span style="font-size:11px;color:#94A3B8;">Awaiting input</span></div>'
        )
    st.markdown(led_html, unsafe_allow_html=True)

    dispatch_btn = st.button(
        "▶  DISPATCH TO COMMAND",
        use_container_width=True,
        type="primary",
        disabled=not event_text.strip(),
        key="dispatch_btn_v4",
    )
    if dispatch_btn and event_text.strip():
        st.session_state.processing = True
        process_event(event_text)

    if st.session_state.processing:
        st.info("⚡ Specialists analysing in parallel… Commander synthesising consensus decision…")

    st.markdown('</div>', unsafe_allow_html=True)

    # =========================================================================
    # STAGE 2 — Parallel Agent Analysis
    # =========================================================================
    st.markdown('<div class="stage-card">', unsafe_allow_html=True)
    st.markdown(
        '<div class="stage-title">🤖 Parallel Agent Analysis</div>',
        unsafe_allow_html=True,
    )

    _AGENT_CARD_CSS = {
        "Fire_Bot":   ("agent-fire-card",   "🔥"),
        "Med_Bot":    ("agent-med-card",    "🏥"),
        "Police_Bot": ("agent-police-card", "🚔"),
    }
    _STATUS_INFO = {
        "approved":  ("status-approved",  "dot-approved",  "✓ APPROVED"),
        "prescreen": ("status-prescreen", "dot-prescreen", "⚠ PRE-SCREEN VETO"),
        "llmveto":   ("status-llmveto",   "dot-llmveto",   "✕ LLM VETO"),
    }
    _URGENCY_CSS_MAP = {
        "CRITICAL": "u-critical", "HIGH": "u-high",
        "MEDIUM":   "u-medium",   "LOW":  "u-low",
    }

    if result and result.get("specialists"):
        agent_order = ["Fire_Bot", "Med_Bot", "Police_Bot"]
        specialists_by_name = {e["name"]: e for e in result["specialists"]}

        agent_cols = st.columns(3, gap="small")
        for col, agent_name in zip(agent_cols, agent_order):
            entry = specialists_by_name.get(agent_name)
            if not entry:
                continue

            card_cls, icon    = _AGENT_CARD_CSS.get(agent_name, ("agent-police-card", "🤖"))
            status            = entry.get("status", "approved")
            urgency_lbl       = entry.get("urgency_label", "N/A")
            urgency_scr       = entry.get("urgency_score")
            reason            = entry.get("reason", "")

            status_chip_cls, dot_cls, status_text = _STATUS_INFO[status]
            urgency_chip_cls  = _URGENCY_CSS_MAP.get(urgency_lbl, "u-na")
            score_str         = f" {urgency_scr:.1f}" if urgency_scr is not None else ""

            reason_html = (
                f'<div style="font-size:11px;color:#64748B;margin-top:5px;">'
                f'⚑ {reason}</div>'
            ) if reason else ""

            with col:
                st.markdown(
                    f'<div class="agent-analysis-card {card_cls}">'
                    f'  <div class="agent-card-name">{icon} {agent_name}'
                    f'    <span class="urgency-badge {urgency_chip_cls}">{urgency_lbl}{score_str}</span>'
                    f'  </div>'
                    f'  <div>'
                    f'    <span class="status-badge {status_chip_cls}">'
                    f'      <span class="status-dot {dot_cls}"></span>{status_text}'
                    f'    </span>'
                    f'  </div>'
                    f'  {reason_html}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                with st.expander(f"Full report — {agent_name}", expanded=False):
                    st.markdown(
                        f'<div class="report-scroll">{entry["report"]}</div>',
                        unsafe_allow_html=True,
                    )
    else:
        st.markdown(
            '<div class="empty-state">'
            '<div style="font-size:28px;margin-bottom:8px;">🛰️</div>'
            '<div style="font-size:14px;font-weight:600;color:#64748B;">Awaiting incident input</div>'
            '<div style="font-size:12px;margin-top:4px;">Specialist agents will appear here after dispatch.</div>'
            '</div>',
            unsafe_allow_html=True,
        )

    st.markdown('</div>', unsafe_allow_html=True)

    # =========================================================================
    # STAGE 3 — Unified Command Decision (most prominent)
    # Contains: final plan + Veto Audit Log + Conflict Resolution
    # =========================================================================
    st.markdown('<div class="command-decision-card">', unsafe_allow_html=True)
    st.markdown(
        '<div class="command-decision-title">🎖️ Unified Command Decision</div>',
        unsafe_allow_html=True,
    )

    if result and result.get("final_plan"):
        ts = result.get("timestamp", "")
        st.markdown(
            f'<div style="font-size:10px;color:#7C95C8;font-weight:600;'
            f'letter-spacing:1px;margin-bottom:10px;">'
            f'COMMAND CORE · PRIORITY DISPATCH · {ts}</div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div class="command-decision-text">{result["final_plan"]}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div class="empty-state" style="background:#FFFFFF;border-color:#BFDBFE;">'
            '<div style="font-size:13px;font-weight:600;color:#94A3B8;">'
            'No active dispatch — submit an incident to generate a unified command decision.'
            '</div></div>',
            unsafe_allow_html=True,
        )

    # ── Veto Audit Log (inline, inside Stage 3) ──────────────────────────────
    veto_log = (result or {}).get("veto_log", [])
    st.markdown(
        '<div class="veto-section-header">📋 Veto Audit Log</div>',
        unsafe_allow_html=True,
    )
    if veto_log:
        ts_display = (result or {}).get("timestamp", "--:--:--")
        rows_html = ""
        for entry in veto_log:
            stage       = entry.get("stage", "")
            stage_cls   = "stage-pre" if stage == "pre_screen" else "stage-llm"
            stage_label = "PRE-SCREEN" if stage == "pre_screen" else "LLM-REVIEW"
            agent       = entry.get("agent", "—")
            reason      = entry.get("reason", "—")
            rows_html += (
                f"<tr>"
                f"<td style='color:#94A3B8;font-variant-numeric:tabular-nums;'>{ts_display}</td>"
                f"<td style='font-weight:600;'>{agent}</td>"
                f"<td class='{stage_cls}'>{stage_label}</td>"
                f"<td>{reason}</td>"
                f"</tr>"
            )
        st.markdown(
            f'<table class="veto-tbl">'
            f'<thead><tr><th>Time</th><th>Agent</th><th>Stage</th><th>Tactical Reason</th></tr></thead>'
            f'<tbody>{rows_html}</tbody>'
            f'</table>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div style="font-size:12px;color:#94A3B8;padding:6px 0;">'
            'No vetoes recorded in this session.</div>',
            unsafe_allow_html=True,
        )

    # ── Conflict Resolution (inline, inside Stage 3) ──────────────────────────
    conflicts = (result or {}).get("conflicts", [])
    if conflicts:
        st.markdown(
            '<div class="conflict-section-header">⚔️ Conflict Resolution</div>',
            unsafe_allow_html=True,
        )
        for c in conflicts:
            topic = c.topic.replace("_", " ").upper()
            st.markdown(
                f'<div class="conflict-card">'
                f'  <div class="conflict-topic">⚑ {topic}</div>'
                f'  <div style="font-size:12px;color:#334155;">'
                f'    <span style="font-weight:600;">{c.agent_a}</span>'
                f'    <span style="color:#94A3B8;"> [{c.stance_a}]</span>'
                f'    <span style="color:#CBD5E1;"> ⟷ </span>'
                f'    <span style="font-weight:600;">{c.agent_b}</span>'
                f'    <span style="color:#94A3B8;"> [{c.stance_b}]</span>'
                f'  </div>'
                f'  <div style="margin-top:4px;font-size:12px;">'
                f'    <span style="color:#64748B;">WINNER → </span>'
                f'    <span class="conflict-winner">{c.winner}</span>'
                f'  </div>'
                f'  <div class="conflict-reason">↳ {c.resolution_reason}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown('</div>', unsafe_allow_html=True)  # close command-decision-card

    # Footer
    st.markdown(
        f'<div style="font-size:11px;color:#94A3B8;padding:10px 0;'
        f'border-top:1px solid #E2E8F0;margin-top:8px;">'
        f'Last update: {datetime.now().strftime("%H:%M:%S")} · '
        f'Parallel execution · Constitutional AI · Consensus Engine · '
        f'Upload limit: {MAX_UPLOAD_BYTES // (1024 * 1024)} MB'
        f'</div>',
        unsafe_allow_html=True,
    )
