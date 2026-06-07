"""
Command Core — Mission Control UI (v6)
=======================================
JARVIS-style agent network with live data flow animation.
ALL backend logic identical to streamlit_app.py — only the visual layer changes.
"""

import streamlit as st
import sys
import os
import json
import concurrent.futures
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.agent_factory import SpecialistFactory
from agents.commander_agent import CommanderAgent, CONSTITUTION, VETO_TRIGGERS
from llm.llm_client import LLMClient

MAX_UPLOAD_BYTES = 2 * 1024 * 1024

st.set_page_config(
    page_title="THE COMMAND CORE",
    page_icon="⬡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Share+Tech+Mono&display=swap');

.stApp,.main,.block-container{background:#050B18!important;color:#C8D8E8!important;}
html,body,[class*="css"]{font-family:'Share Tech Mono',monospace!important;}
.main .block-container{padding-top:0!important;max-width:100%!important;}
section[data-testid="stSidebar"]{background:#03070F!important;border-right:1px solid #0A2040!important;}
section[data-testid="stSidebar"] *{color:#5A8AAA!important;font-family:'Share Tech Mono',monospace!important;}
textarea,input[type="text"]{background:#050B18!important;color:#00E5FF!important;border:1px solid #0A2040!important;font-family:'Share Tech Mono',monospace!important;}
textarea:focus{border-color:#00E5FF!important;box-shadow:0 0 8px rgba(0,229,255,.2)!important;}
.stButton>button{background:transparent!important;color:#00E5FF!important;border:1px solid #00E5FF!important;font-family:'Share Tech Mono',monospace!important;letter-spacing:2px!important;}
.stButton>button:hover{background:rgba(0,229,255,.1)!important;}
details{background:#03070F!important;border:1px solid #0A2040!important;border-radius:4px!important;}
summary{color:#00E5FF!important;}
[data-testid="stMetric"]{background:rgba(0,20,40,.5)!important;border:1px solid #0A2040!important;border-radius:8px!important;padding:10px!important;}
[data-testid="stMetricValue"]{color:#00E5FF!important;font-family:'Orbitron',monospace!important;}
[data-testid="stMetricLabel"]{color:#5A8AAA!important;}
.stProgress>div>div{background:#00E5FF!important;}
::-webkit-scrollbar{width:4px;}::-webkit-scrollbar-track{background:#050B18;}::-webkit-scrollbar-thumb{background:#0A2040;}
hr{border-color:#0A2040!important;}
#MainMenu,footer,header{visibility:hidden;}

/* Mission Control specific */
.mc-header{text-align:center;padding:20px 0 12px;border-bottom:1px solid #0A2040;}
.mc-title{font-family:'Orbitron',monospace;font-size:34px;font-weight:900;letter-spacing:6px;color:#00E5FF;text-shadow:0 0 20px rgba(0,229,255,.4);}
.mc-sub{font-size:11px;color:#2A4A6A;letter-spacing:4px;margin-top:4px;}

.agent-node{border-radius:50%;display:flex;align-items:center;justify-content:center;flex-direction:column;cursor:pointer;transition:all .3s;}
.agent-node:hover{transform:scale(1.05);}

.debate-card{border:1px solid rgba(0,229,255,.15);border-radius:10px;padding:14px;background:rgba(0,15,35,.6);margin-bottom:8px;}
.debate-name{font-family:'Orbitron',monospace;font-size:12px;letter-spacing:2px;margin-bottom:6px;}
.debate-text{font-size:12px;color:#C8D8E8;line-height:1.6;}

.final-box{border:2px solid #00E5FF;border-radius:8px;padding:20px;background:linear-gradient(135deg,#070F20,#050B18);box-shadow:0 0 30px rgba(0,229,255,.08);}
.final-title{font-family:'Orbitron',monospace;font-size:14px;color:#00E5FF;letter-spacing:3px;margin-bottom:12px;}
.final-text{font-size:14px;color:#E2F0FF;line-height:1.8;}

.section-hdr{font-family:'Orbitron',monospace;font-size:10px;letter-spacing:3px;color:#3A5A7A;padding:6px 0;border-bottom:1px solid #0A2040;margin-bottom:10px;}

.conflict-row{border-left:3px solid #FF8C00;padding:10px 14px;background:rgba(25,12,0,.5);border-radius:0 6px 6px 0;margin-bottom:6px;font-size:12px;}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "llm" not in st.session_state:
    st.session_state.llm = LLMClient()
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "constitution_text" not in st.session_state:
    st.session_state.constitution_text = CONSTITUTION
if "veto_triggers" not in st.session_state:
    st.session_state.veto_triggers = dict(VETO_TRIGGERS)
if "last_specialists" not in st.session_state:
    st.session_state.last_specialists = []
if "last_final_plan" not in st.session_state:
    st.session_state.last_final_plan = ""
if "last_veto_log" not in st.session_state:
    st.session_state.last_veto_log = []
if "last_conflicts" not in st.session_state:
    st.session_state.last_conflicts = []
if "last_confidence" not in st.session_state:
    st.session_state.last_confidence = 0
if "last_incident" not in st.session_state:
    st.session_state.last_incident = ""
if "processing" not in st.session_state:
    st.session_state.processing = False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _run_agent(agent_type, prompt, history_context, llm_client):
    agent = SpecialistFactory.create(agent_type, llm_client)
    response = agent.analyze(prompt, previous_findings=history_context)
    return {"name": agent.name, "response": response, "type": agent_type}

def _extract_thought(report_text):
    if not report_text:
        return "No analysis available."
    sentences = [s.strip() for s in report_text.replace('\n', ' ').split('.') if len(s.strip()) > 20]
    return (sentences[0] + ".") if sentences else report_text[:120] + "..."

def _calc_confidence(urgency_scores):
    if not urgency_scores:
        return 0
    scores = [u.score for u in urgency_scores.values() if hasattr(u, 'score')]
    return min(99, int((sum(scores) / len(scores) / 10) * 100)) if scores else 0

def _threat_info(specs):
    labels = [e["urgency_label"] for e in specs if e.get("urgency_label")]
    scores = [e["urgency_score"] for e in specs if e.get("urgency_score")]
    if not labels:
        return "STANDBY", "#3A5A7A", 0.0
    if "CRITICAL" in labels:
        return "CRITICAL", "#EF4444", min(1.0, max(scores)/10)
    if "HIGH" in labels:
        return "HIGH", "#F97316", min(1.0, max(scores)/10)
    if "MEDIUM" in labels:
        return "MEDIUM", "#EAB308", min(1.0, max(scores)/10)
    return "LOW", "#10B981", min(1.0, max(scores)/10)


# ---------------------------------------------------------------------------
# Core processing — identical to streamlit_app.py
# ---------------------------------------------------------------------------
def process_event(event_text: str):
    st.session_state.chat_history.append({"role": "user", "content": event_text})
    st.session_state.last_incident = event_text
    st.session_state.processing = True

    history_context = "\n".join(
        f"{m['role']}: {m['content']}"
        for m in st.session_state.chat_history[:-1]
    )

    llm = st.session_state.llm
    agent_reports: dict = {}
    with st.spinner("⚡ DISPATCHING TO AGENT NETWORK..."):
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(_run_agent, atype, event_text, history_context, llm): atype
                for atype in ["fire", "police", "medical"]
            }
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                agent_reports[result["name"]] = result["response"]

    commander = CommanderAgent(llm)
    import agents.commander_agent as _ca
    orig_c, orig_t = _ca.CONSTITUTION, _ca.VETO_TRIGGERS
    _ca.CONSTITUTION = st.session_state.constitution_text
    _ca.VETO_TRIGGERS = st.session_state.veto_triggers

    with st.spinner("⚖️ COMMANDER AI SYNTHESISING..."):
        review_result = commander.review_and_synthesize(agent_reports)

    _ca.CONSTITUTION, _ca.VETO_TRIGGERS = orig_c, orig_t

    reviews        = review_result["reviews"]
    final_plan     = review_result["final_plan"]
    veto_log       = review_result["veto_log"]
    urgency_scores = review_result.get("urgency_scores", {})
    conflicts      = review_result.get("conflicts", [])

    agent_icons = {"Fire_Bot": "🔥", "Police_Bot": "🚔", "Med_Bot": "🏥"}
    specialist_entries = []
    for agent_name, report_text in agent_reports.items():
        review = reviews.get(agent_name, {})
        urgency = urgency_scores.get(agent_name)
        specialist_entries.append({
            "name":          agent_name,
            "icon":          agent_icons.get(agent_name, "🤖"),
            "vetoed":        review.get("vetoed", False),
            "veto_stage":    review.get("stage", "LLM"),
            "reason":        review.get("reason", ""),
            "report":        report_text,
            "thought":       _extract_thought(report_text),
            "urgency_label": urgency.label if urgency else "N/A",
            "urgency_score": urgency.score if urgency else 0,
        })

    confidence = _calc_confidence(urgency_scores)
    st.session_state.last_specialists = specialist_entries
    st.session_state.last_final_plan  = final_plan
    st.session_state.last_veto_log    = veto_log
    st.session_state.last_conflicts   = conflicts
    st.session_state.last_confidence  = confidence
    st.session_state.processing       = False

    content = (
        "### Commander Review\n"
        + "\n".join(f"- {e['icon']} **{e['name']}**: {'VETO' if e['vetoed'] else 'APPROVED'}" for e in specialist_entries)
        + f"\n\n---\n### Unified Command Decision\n{final_plan}"
    )
    st.session_state.chat_history.append({
        "role": "assistant", "content": content,
        "avatar": "⚖️", "specialists": specialist_entries,
    })
    st.rerun()


# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("""
    <div style='text-align:center;padding:14px 0 10px;'>
        <div style='font-family:Orbitron,monospace;font-size:13px;color:#00E5FF;letter-spacing:3px;'>⬡ COMMAND CORE</div>
        <div style='font-size:9px;color:#1A3050;letter-spacing:2px;margin-top:3px;'>TACTICAL AI v6.0</div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("🗑  NEW INCIDENT", use_container_width=True):
        for k in ["chat_history","last_specialists","last_final_plan","last_veto_log",
                  "last_conflicts","last_confidence","last_incident"]:
            st.session_state[k] = [] if k in ["chat_history","last_specialists","last_veto_log","last_conflicts"] else "" if "incident" in k or "plan" in k else 0
        st.rerun()

    st.markdown("<hr style='border-color:#0A2040;'>", unsafe_allow_html=True)

    with st.expander("⚖️ CONSTITUTION", expanded=False):
        st.caption("Keep RULE N: prefix. Applied on next dispatch.")
        edited = st.text_area("", value=st.session_state.constitution_text, height=200, label_visibility="collapsed")
        if edited != st.session_state.constitution_text:
            st.session_state.constitution_text = edited
            st.success("✓ Updated")

    with st.expander("🔍 VETO TRIGGERS", expanded=False):
        st.caption("JSON — phrase: rule label")
        edited_t = st.text_area("", value=json.dumps(st.session_state.veto_triggers, indent=2), height=160, label_visibility="collapsed")
        if st.button("💾 SAVE", use_container_width=True):
            try:
                st.session_state.veto_triggers = json.loads(edited_t)
                st.success("✓ Saved")
            except json.JSONDecodeError as e:
                st.error(f"Invalid JSON: {e}")

    with st.expander("📁 UPLOAD REPORT", expanded=False):
        st.caption(f"Accepted: .txt / .md — max {MAX_UPLOAD_BYTES//(1024*1024)} MB")
        uf = st.file_uploader("Upload", type=["txt","md"], label_visibility="collapsed")
        if uf is not None:
            fb = uf.read()
            if len(fb) > MAX_UPLOAD_BYTES:
                st.error(f"❌ File too large ({len(fb)/(1024*1024):.1f} MB)")
            else:
                if st.button("🚀 PROCESS REPORT", use_container_width=True):
                    process_event(f"📄 FIELD REPORT:\n\n{fb.decode('utf-8', errors='replace')}")

    st.markdown("<hr style='border-color:#0A2040;'>", unsafe_allow_html=True)
    st.markdown("<div style='font-size:10px;color:#1A3050;text-align:center;'>🔴 CRITICAL · 🟠 HIGH · 🟡 MEDIUM · 🟢 LOW</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# MAIN AREA
# ---------------------------------------------------------------------------
specialists = st.session_state.last_specialists
final_plan  = st.session_state.last_final_plan
veto_log    = st.session_state.last_veto_log
conflicts   = st.session_state.last_conflicts
confidence  = st.session_state.last_confidence
incident    = st.session_state.last_incident
is_active   = bool(specialists)

threat_label, threat_color, threat_val = _threat_info(specialists)
spec_map = {e["name"]: e for e in specialists}

# ── HEADER ──
incident_short = (incident[:55]+"...") if len(incident)>55 else (incident or "AWAITING INCIDENT")
st.markdown(f"""
<div class="mc-header">
    <div class="mc-title">THE COMMAND CORE</div>
    <div class="mc-sub">HIERARCHICAL MULTI-AGENT TACTICAL DECISION ORCHESTRATOR · MILESTONE 4</div>
</div>
<div style='display:flex;justify-content:space-between;align-items:center;padding:10px 0 6px;
            border-bottom:1px solid #0A2040;margin-bottom:16px;'>
    <div style='font-size:11px;color:#2A4A6A;'>ACTIVE INCIDENT:
        <span style='color:#C8D8E8;margin-left:8px;'>{incident_short}</span>
    </div>
    <div style='font-family:Orbitron,monospace;font-size:14px;font-weight:700;color:{threat_color};'>
        ● {threat_label}
    </div>
</div>
""", unsafe_allow_html=True)


# ── AGENT NETWORK (SVG animated) ──
st.markdown('<div class="section-hdr">◈ AGENT NETWORK</div>', unsafe_allow_html=True)

def agent_ring_html(specs_map, is_processing):
    """Build the live SVG agent ring with animated data-flow lines."""
    AGENTS = [
        {"id": "Fire_Bot",   "label": "FIRE",    "icon": "🔥", "cx": 150, "cy": 90,  "color": "#FF6B35", "gcolor": "rgba(255,107,53,.15)"},
        {"id": "Med_Bot",    "label": "MEDICAL", "icon": "🏥", "cx": 580, "cy": 90,  "color": "#00C9A7", "gcolor": "rgba(0,201,167,.15)"},
        {"id": "Police_Bot", "label": "POLICE",  "icon": "🚔", "cx": 150, "cy": 310, "color": "#4A90D9", "gcolor": "rgba(74,144,217,.15)"},
    ]
    CMD_CX, CMD_CY = 365, 200
    R_AGENT = 55
    R_CMD = 75

    lines_html = ""
    node_html  = ""

    for ag in AGENTS:
        cx, cy, col = ag["cx"], ag["cy"], ag["color"]
        e = specs_map.get(ag["id"], {})
        is_approved = not e.get("vetoed", False) if e else True
        urg_label = e.get("urgency_label", "N/A") if e else "STANDBY"
        urg_score = e.get("urgency_score", 0) if e else 0
        thought   = e.get("thought", "Awaiting dispatch...")[:70] if e else "Awaiting dispatch..."

        # Status color
        if not e:
            status_col, status_txt = "#3A5A7A", "STANDBY"
        elif e.get("vetoed"):
            status_col, status_txt = "#EF4444", "VETO"
        else:
            status_col, status_txt = "#10B981", "APPROVED"

        # Animated flow line agent → commander
        dx = CMD_CX - cx
        dy = CMD_CY - cy
        import math
        dist = math.sqrt(dx*dx + dy*dy)
        # Start / end on circle edges
        sx = cx + R_AGENT * dx/dist
        sy = cy + R_AGENT * dy/dist
        ex = CMD_CX - R_CMD * dx/dist
        ey = CMD_CY - R_CMD * dy/dist

        if is_active:
            anim_dur = 1.8
            lines_html += f"""
<line x1="{sx:.0f}" y1="{sy:.0f}" x2="{ex:.0f}" y2="{ey:.0f}"
      stroke="{col}" stroke-width="1" opacity="0.25"/>
<line x1="{sx:.0f}" y1="{sy:.0f}" x2="{ex:.0f}" y2="{ey:.0f}"
      stroke="{col}" stroke-width="2.5" stroke-dasharray="8 {dist:.0f}"
      stroke-dashoffset="0" opacity="0.7">
    <animate attributeName="stroke-dashoffset" from="0" to="-{dist+8:.0f}"
             dur="{anim_dur}s" repeatCount="indefinite"/>
</line>"""
        else:
            lines_html += f"""
<line x1="{sx:.0f}" y1="{sy:.0f}" x2="{ex:.0f}" y2="{ey:.0f}"
      stroke="{col}" stroke-width="1" opacity="0.12" stroke-dasharray="4 4"/>"""

        # Agent node circle
        node_html += f"""
<circle cx="{cx}" cy="{cy}" r="{R_AGENT}" fill="{ag['gcolor']}"
        stroke="{col}" stroke-width="{2 if is_active else 1}"/>
<text x="{cx}" y="{cy-14}" text-anchor="middle" font-family="Share Tech Mono" font-size="18">{ag['icon']}</text>
<text x="{cx}" y="{cy+4}" text-anchor="middle" font-family="Orbitron,monospace" font-size="9"
      fill="{col}" font-weight="700" letter-spacing="1">{ag['label']}</text>
<text x="{cx}" y="{cy+18}" text-anchor="middle" font-family="Share Tech Mono" font-size="9"
      fill="{status_col}">{status_txt}</text>
<text x="{cx}" y="{cy+31}" text-anchor="middle" font-family="Share Tech Mono" font-size="8"
      fill="{col}" opacity=".7">{urg_label} {urg_score:.1f}</text>"""

    # Commander center
    conf_display = f"{confidence}%" if confidence else "—%"
    cmd_glow = "rgba(138,92,255,.2)" if is_active else "rgba(138,92,255,.05)"
    node_html += f"""
<circle cx="{CMD_CX}" cy="{CMD_CY}" r="{R_CMD}" fill="{cmd_glow}"
        stroke="#8A5CFF" stroke-width="{2.5 if is_active else 1.5}"/>"""

    if is_active:
        node_html += f"""
<circle cx="{CMD_CX}" cy="{CMD_CY}" r="82" fill="none"
        stroke="#8A5CFF" stroke-width="0.5" opacity="0.3" stroke-dasharray="4 4">
    <animateTransform attributeName="transform" type="rotate"
        from="0 {CMD_CX} {CMD_CY}" to="360 {CMD_CX} {CMD_CY}" dur="12s" repeatCount="indefinite"/>
</circle>"""

    node_html += f"""
<text x="{CMD_CX}" y="{CMD_CY-22}" text-anchor="middle"
      font-family="Orbitron,monospace" font-size="9" fill="#B388FF" font-weight="700" letter-spacing="2">COMMANDER</text>
<text x="{CMD_CX}" y="{CMD_CY-6}" text-anchor="middle"
      font-family="Orbitron,monospace" font-size="9" fill="#8A5CFF" letter-spacing="1">AI</text>
<text x="{CMD_CX}" y="{CMD_CY+14}" text-anchor="middle"
      font-family="Orbitron,monospace" font-size="22" fill="#B388FF" font-weight="900">{conf_display}</text>
<text x="{CMD_CX}" y="{CMD_CY+30}" text-anchor="middle"
      font-family="Share Tech Mono" font-size="8" fill="#5A3AAA">CONFIDENCE</text>"""

    # Also draw reverse arrows commander → agent (dashed, dimmer)
    for ag in AGENTS:
        cx, cy, col = ag["cx"], ag["cy"], ag["color"]
        dx = cx - CMD_CX
        dy = cy - CMD_CY
        import math
        dist = math.sqrt(dx*dx + dy*dy)
        sx = CMD_CX + R_CMD * dx/dist
        sy = CMD_CY + R_CMD * dy/dist
        ex = cx - R_AGENT * dx/dist
        ey = cy - R_AGENT * dy/dist
        if is_active:
            lines_html += f"""
<line x1="{sx:.0f}" y1="{sy:.0f}" x2="{ex:.0f}" y2="{ey:.0f}"
      stroke="{col}" stroke-width="1.5" stroke-dasharray="5 {dist:.0f}"
      stroke-dashoffset="0" opacity="0.3">
    <animate attributeName="stroke-dashoffset" from="-{dist+5:.0f}" to="0"
             dur="2.5s" repeatCount="indefinite"/>
</line>"""

    svg = f"""
<svg width="100%" viewBox="0 0 730 400" style="background:transparent;">
    {lines_html}
    {node_html}
</svg>"""
    return svg

ring_svg = agent_ring_html(spec_map, is_active)
st.markdown(ring_svg, unsafe_allow_html=True)


# ── DEBATE STREAM ──
if specialists:
    st.markdown("<hr style='border-color:#0A2040;margin:8px 0;'>", unsafe_allow_html=True)
    st.markdown('<div class="section-hdr">◈ LIVE DEBATE STREAM</div>', unsafe_allow_html=True)

    AGENT_COLORS = {"Fire_Bot":"#FF6B35","Police_Bot":"#4A90D9","Med_Bot":"#00C9A7"}
    cols = st.columns(3)
    for col, entry in zip(cols, specialists):
        col_color = AGENT_COLORS.get(entry["name"], "#00E5FF")
        vetoed = entry["vetoed"]
        status_color = "#EF4444" if vetoed else "#10B981"
        status_txt   = "⚠ VETO" if vetoed else "✓ APPROVED"
        preview = entry["report"][:320] + ("..." if len(entry["report"])>320 else "")
        preview_html = preview.replace('\n','<br>')

        with col:
            st.markdown(f"""
            <div class="debate-card" style="border-color:rgba({
                '255,107,53' if entry['name']=='Fire_Bot' else
                '74,144,217' if entry['name']=='Police_Bot' else
                '0,201,167'
            },.3);border-top:2px solid {col_color};">
                <div class="debate-name" style="color:{col_color};">
                    {entry['icon']} {entry['name']}
                    <span style="float:right;color:{status_color};font-size:10px;">{status_txt}</span>
                </div>
                <div style="font-size:10px;color:{col_color};opacity:.7;margin-bottom:6px;">
                    {entry['urgency_label']} {entry['urgency_score']:.1f}
                </div>
                <div class="debate-text">{preview_html}</div>
            </div>
            """, unsafe_allow_html=True)
            with st.expander(f"▼ Full {entry['name']} report"):
                st.markdown(
                    f"<div style='font-size:12px;color:#C8D8E8;line-height:1.7;'>{entry['report']}</div>",
                    unsafe_allow_html=True
                )


# ── FINAL DECISION ──
st.markdown("<hr style='border-color:#0A2040;margin:12px 0;'>", unsafe_allow_html=True)
st.markdown('<div class="section-hdr">◈ UNIFIED COMMAND DECISION</div>', unsafe_allow_html=True)

if final_plan:
    plan_html = final_plan.replace('\n','<br>')
    st.markdown(f"""
    <div class="final-box">
        <div class="final-title">🎯 UNIFIED COMMAND DECISION</div>
        <div class="final-text">{plan_html}</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2 = st.columns([3,1])
    with c1:
        st.markdown("<div style='font-size:10px;color:#3A5A7A;letter-spacing:2px;margin-bottom:4px;'>COMMANDER CONFIDENCE</div>", unsafe_allow_html=True)
        st.progress(confidence/100)
    with c2:
        st.metric("Confidence", f"{confidence}%")

    if veto_log:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="section-hdr">◈ VETO AUDIT LOG</div>', unsafe_allow_html=True)
        rows = "".join(
            f"<tr style='border-bottom:1px solid #0A2040;'>"
            f"<td style='padding:7px 10px;color:#2A4A6A;'>{v.get('timestamp',datetime.now().strftime('%H:%M:%S'))}</td>"
            f"<td style='padding:7px 10px;color:#FF8C00;'>{v.get('agent','—')}</td>"
            f"<td style='padding:7px 10px;color:#FFD700;'>{v.get('stage','—').upper()}</td>"
            f"<td style='padding:7px 10px;color:#C8D8E8;'>{v.get('reason','—')}</td></tr>"
            for v in veto_log
        )
        st.markdown(f"""
        <table style='width:100%;background:rgba(0,10,30,.5);border:1px solid #0A2040;border-radius:6px;
                      border-collapse:collapse;font-family:Share Tech Mono,monospace;font-size:11px;'>
            <thead><tr style='background:#03070F;color:#2A4A6A;font-size:9px;letter-spacing:2px;'>
                <th style='padding:8px 10px;text-align:left;'>TIME</th>
                <th style='padding:8px 10px;text-align:left;'>AGENT</th>
                <th style='padding:8px 10px;text-align:left;'>STAGE</th>
                <th style='padding:8px 10px;text-align:left;'>REASON</th>
            </tr></thead><tbody>{rows}</tbody></table>
        """, unsafe_allow_html=True)

    if conflicts:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="section-hdr">◈ CONFLICT RESOLUTIONS</div>', unsafe_allow_html=True)
        for c in conflicts:
            topic  = c.topic.upper() if hasattr(c,'topic') else "CONFLICT"
            a_a    = c.agent_a if hasattr(c,'agent_a') else "—"
            s_a    = c.stance_a if hasattr(c,'stance_a') else "—"
            a_b    = c.agent_b if hasattr(c,'agent_b') else "—"
            s_b    = c.stance_b if hasattr(c,'stance_b') else "—"
            winner = c.winner if hasattr(c,'winner') else "—"
            reason = c.resolution_reason if hasattr(c,'resolution_reason') else "—"
            st.markdown(f"""
            <div class="conflict-row">
                <span style='color:#FF8C00;letter-spacing:1px;'>[{topic}]</span>
                <span style='color:#FF6B6B;margin-left:8px;'>{a_a}</span>
                <span style='color:#FF8C00;'>({s_a})</span>
                <span style='color:#3A5A7A;'> vs </span>
                <span style='color:#FF6B6B;'>{a_b}</span>
                <span style='color:#FF8C00;'>({s_b})</span>
                <span style='color:#3A5A7A;'> → </span>
                <span style='color:#10B981;font-weight:bold;'>{winner}</span>
                <span style='color:#5A8AAA;'> — {reason}</span>
            </div>
            """, unsafe_allow_html=True)

else:
    st.markdown("""
    <div style='background:rgba(0,10,30,.5);border:1px solid #0A2040;border-radius:8px;
                padding:36px;text-align:center;color:#2A4A6A;'>
        <div style='font-family:Orbitron,monospace;font-size:13px;letter-spacing:3px;'>
            COMMAND CORE // AWAITING INCIDENT
        </div>
        <div style='font-size:11px;margin-top:8px;'>Submit an incident report to activate the agent network.</div>
    </div>
    """, unsafe_allow_html=True)


# ── SYSTEM STATUS ──
st.markdown("<hr style='border-color:#0A2040;margin:16px 0 10px;'>", unsafe_allow_html=True)
st.markdown('<div class="section-hdr">◈ SYSTEM STATUS</div>', unsafe_allow_html=True)
sa, sb, sc, sd = st.columns(4)
status = "ONLINE" if specialists else "STANDBY"
sa.metric("🔥 Fire Agent",    status)
sb.metric("🚔 Police Agent",  status)
sc.metric("🏥 Medical Agent", status)
sd.metric("⚡ Commander AI",  status)


# ── CHAT INPUT ──
if prompt := st.chat_input("► DISPATCH INCIDENT REPORT // תאר אירוע חירום..."):
    process_event(prompt)


# ── FOOTER ──
st.markdown(f"""
<div style='border-top:1px solid #0A2040;margin-top:16px;padding:8px 0;
            font-size:9px;color:#1A3050;text-align:center;letter-spacing:2px;'>
    COMMAND CORE · MILESTONE 4 · CONSENSUS ENGINE · PARALLEL EXECUTION · {datetime.now().strftime('%H:%M:%S')} UTC
</div>
""", unsafe_allow_html=True)