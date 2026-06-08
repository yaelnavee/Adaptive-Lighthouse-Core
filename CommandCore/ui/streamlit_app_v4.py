"""
Command Core — Streamlit UI  ·  Milestone 4  ·  Tactical Command Center
========================================================================
REDESIGNED: Full tactical command-center aesthetic.
  - Animated SVG network diagram (Commander ↔ Agents) with live pulse lines
  - Agent nodes glow cyan while processing, green=APPROVED, red=VETO
  - Dark military palette: #050b14 background, cyan/electric-blue accents
  - All original functionality preserved 100%
"""

import streamlit as st
import streamlit.components.v1 as components
import sys
import os
import json
import concurrent.futures
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.agent_factory import SpecialistFactory
from agents.commander_agent import CommanderAgent, CONSTITUTION, VETO_TRIGGERS
from llm.llm_client import LLMClient

MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # 2 MB

_URGENCY_BADGE = {
    "CRITICAL": "🔴",
    "HIGH":     "🟠",
    "MEDIUM":   "🟡",
    "LOW":      "🟢",
}

_URGENCY_COLOR = {
    "CRITICAL": "#ff3b3b",
    "HIGH":     "#ff8c00",
    "MEDIUM":   "#f5c518",
    "LOW":      "#00e676",
    "N/A":      "#00b4ff",
}

st.set_page_config(
    page_title="Command Core — M4 Consensus Engine",
    page_icon="⚖️",
    layout="wide",
)

# ── Global CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;500;600;700&family=Share+Tech+Mono&family=Orbitron:wght@400;700;900&display=swap');

/* ── Root & body ── */
:root {
    --bg-deep:    #020810;
    --bg-panel:   #060e1c;
    --bg-card:    #0a1628;
    --border:     #0d2545;
    --cyan:       #00c8ff;
    --cyan-dim:   #005a7a;
    --blue-glow:  #0066ff;
    --green:      #00ff88;
    --red:        #ff2244;
    --amber:      #ff8c00;
    --text-main:  #c8e4ff;
    --text-dim:   #3d6080;
    --text-label: #6ba3bf;
}

html, body, [data-testid="stAppViewContainer"] {
    background: var(--bg-deep) !important;
    font-family: 'Rajdhani', sans-serif !important;
}

[data-testid="stAppViewContainer"] > .main {
    background: var(--bg-deep) !important;
}

[data-testid="stSidebar"] {
    background: var(--bg-panel) !important;
    border-right: 1px solid var(--border) !important;
}

/* ── Hide streamlit chrome ── */
#MainMenu, footer, header { visibility: hidden !important; }
[data-testid="stDecoration"] { display: none !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 4px; background: var(--bg-deep); }
::-webkit-scrollbar-thumb { background: var(--cyan-dim); border-radius: 2px; }

/* ── Chat input ── */
[data-testid="stChatInput"] textarea {
    background: var(--bg-card) !important;
    border: 1px solid var(--cyan-dim) !important;
    color: var(--cyan) !important;
    font-family: 'Share Tech Mono', monospace !important;
    font-size: 13px !important;
    border-radius: 2px !important;
}
[data-testid="stChatInput"] textarea:focus {
    border-color: var(--cyan) !important;
    box-shadow: 0 0 12px rgba(0,200,255,0.25) !important;
}

/* ── Chat messages ── */
[data-testid="stChatMessage"] {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    border-left: 3px solid var(--cyan) !important;
    border-radius: 2px !important;
    margin-bottom: 12px !important;
}
[data-testid="stChatMessage"][data-testid*="user"] {
    border-left-color: var(--blue-glow) !important;
}

/* ── Expanders ── */
[data-testid="stExpander"] {
    background: #080f1e !important;
    border: 1px solid var(--border) !important;
    border-radius: 2px !important;
}
[data-testid="stExpander"] summary {
    color: var(--cyan) !important;
    font-family: 'Rajdhani', sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: 1px !important;
}

/* ── Buttons ── */
.stButton > button {
    background: transparent !important;
    border: 1px solid var(--cyan-dim) !important;
    color: var(--cyan) !important;
    font-family: 'Rajdhani', sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: 2px !important;
    text-transform: uppercase !important;
    border-radius: 2px !important;
    transition: all 0.2s !important;
}
.stButton > button:hover {
    border-color: var(--cyan) !important;
    box-shadow: 0 0 16px rgba(0,200,255,0.3) !important;
    background: rgba(0,200,255,0.05) !important;
}

/* ── Text areas ── */
textarea {
    background: var(--bg-card) !important;
    border: 1px solid var(--border) !important;
    color: var(--text-main) !important;
    font-family: 'Share Tech Mono', monospace !important;
    font-size: 12px !important;
}

/* ── Markdown text ── */
.stMarkdown p, .stMarkdown li {
    color: var(--text-main) !important;
    font-family: 'Rajdhani', sans-serif !important;
    font-size: 15px !important;
    line-height: 1.6 !important;
}
.stMarkdown h3 {
    color: var(--cyan) !important;
    font-family: 'Orbitron', monospace !important;
    font-size: 13px !important;
    letter-spacing: 3px !important;
    text-transform: uppercase !important;
    border-bottom: 1px solid var(--border) !important;
    padding-bottom: 6px !important;
}
.stMarkdown strong { color: #ffffff !important; }
.stMarkdown code {
    background: rgba(0,200,255,0.08) !important;
    color: var(--cyan) !important;
    border: 1px solid var(--cyan-dim) !important;
    border-radius: 2px !important;
    font-family: 'Share Tech Mono', monospace !important;
}

/* ── Spinner ── */
[data-testid="stSpinner"] { color: var(--cyan) !important; }

/* ── Success / Error ── */
[data-testid="stSuccess"] {
    background: rgba(0,255,136,0.08) !important;
    border: 1px solid rgba(0,255,136,0.3) !important;
    color: var(--green) !important;
}
[data-testid="stError"] {
    background: rgba(255,34,68,0.08) !important;
    border: 1px solid rgba(255,34,68,0.3) !important;
}

/* ── Divider ── */
hr { border-color: var(--border) !important; }

/* ── Caption ── */
.stCaption { color: var(--text-dim) !important; font-family: 'Share Tech Mono', monospace !important; font-size: 11px !important; }

/* ── Header bar ── */
.cmd-header {
    display: flex;
    align-items: center;
    gap: 16px;
    padding: 16px 0 8px 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 20px;
}
.cmd-header-title {
    font-family: 'Orbitron', monospace;
    font-size: 22px;
    font-weight: 900;
    color: var(--cyan);
    letter-spacing: 4px;
    text-transform: uppercase;
    text-shadow: 0 0 20px rgba(0,200,255,0.5);
}
.cmd-header-sub {
    font-family: 'Share Tech Mono', monospace;
    font-size: 11px;
    color: var(--text-label);
    letter-spacing: 2px;
}
.cmd-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    background: var(--green);
    box-shadow: 0 0 8px var(--green);
    animation: blink 1.4s ease-in-out infinite;
    flex-shrink: 0;
}
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.3} }

/* ── Scanline overlay on network diagram ── */
.scanline-wrap { position: relative; overflow: hidden; }
.scanline-wrap::after {
    content: '';
    position: absolute;
    inset: 0;
    background: repeating-linear-gradient(
        0deg,
        transparent,
        transparent 2px,
        rgba(0,200,255,0.015) 2px,
        rgba(0,200,255,0.015) 4px
    );
    pointer-events: none;
}

/* ── Tactical card ── */
.tac-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-top: 2px solid var(--cyan);
    padding: 16px;
    margin-bottom: 12px;
    position: relative;
}
.tac-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 40px; height: 2px;
    background: var(--cyan);
    box-shadow: 0 0 8px var(--cyan);
}
.tac-label {
    font-family: 'Orbitron', monospace;
    font-size: 10px;
    color: var(--text-label);
    letter-spacing: 3px;
    text-transform: uppercase;
    margin-bottom: 8px;
}
.tac-value {
    font-family: 'Share Tech Mono', monospace;
    font-size: 13px;
    color: var(--text-main);
}

/* ── Urgency badge inline ── */
.urgency-badge {
    display: inline-block;
    padding: 1px 8px;
    border-radius: 2px;
    font-family: 'Share Tech Mono', monospace;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
    margin-left: 8px;
    vertical-align: middle;
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
if "network_state" not in st.session_state:
    # idle | processing | done
    st.session_state.network_state = "idle"
if "agent_states" not in st.session_state:
    # per agent: idle | processing | approved | vetoed
    st.session_state.agent_states = {
        "Fire_Bot": "idle", "Police_Bot": "idle", "Med_Bot": "idle", "Commander": "idle"
    }


# ── SVG Network Diagram ───────────────────────────────────────────────────────
def render_network_diagram(agent_states: dict):
    """
    Renders an animated SVG tactical network diagram.
    Commander in centre, three agents on a circle.
    Lines pulse when processing, go green/red on completion.
    """

    def node_color(state):
        return {
            "idle":       ("#0a1628", "#0d3060", "#3d6080"),  # bg, ring, text
            "processing": ("#001830", "#00c8ff", "#00c8ff"),
            "approved":   ("#001a0d", "#00ff88", "#00ff88"),
            "vetoed":     ("#1a0008", "#ff2244", "#ff2244"),
        }.get(state, ("#0a1628", "#0d3060", "#3d6080"))

    def line_color(agent_state, cmd_state):
        if agent_state == "processing" or cmd_state == "processing":
            return "#00c8ff"
        if agent_state == "approved":
            return "#00ff88"
        if agent_state == "vetoed":
            return "#ff2244"
        return "#0d3060"

    def pulse_active(agent_state, cmd_state):
        return agent_state in ("processing",) or cmd_state == "processing"

    fire_s   = agent_states.get("Fire_Bot",   "idle")
    police_s = agent_states.get("Police_Bot", "idle")
    med_s    = agent_states.get("Med_Bot",    "idle")
    cmd_s    = agent_states.get("Commander",  "idle")

    cx, cy, cr = 300, 200, 56   # commander centre
    ar = 42                      # agent node radius
    orbit = 130                  # distance from centre

    # Agent positions (top, bottom-left, bottom-right)
    agents_pos = {
        "Fire_Bot":   (300, 200 - orbit),
        "Police_Bot": (300 - orbit * 0.866, 200 + orbit * 0.5),
        "Med_Bot":    (300 + orbit * 0.866, 200 + orbit * 0.5),
    }

    def node_svg(nx, ny, label, icon, state, r):
        bg, ring, tc = node_color(state)
        glow_opacity = "0.7" if state == "processing" else ("0.4" if state in ("approved","vetoed") else "0.15")
        glow_r = r + 14
        pulse_anim = ""
        if state == "processing":
            pulse_anim = f"""
            <circle cx="{nx}" cy="{ny}" r="{r+6}" fill="none" stroke="{ring}" stroke-width="1.5" opacity="0.5">
              <animate attributeName="r" values="{r+4};{r+18};{r+4}" dur="1.8s" repeatCount="indefinite"/>
              <animate attributeName="opacity" values="0.6;0;0.6" dur="1.8s" repeatCount="indefinite"/>
            </circle>"""

        lines_label = label.split("_")
        tspan_y = ny - 5 if len(lines_label) == 2 else ny
        tspans = ""
        for i, part in enumerate(lines_label):
            tspans += f'<tspan x="{nx}" dy="{0 if i==0 else 14}">{part}</tspan>'

        return f"""
        <g>
          <circle cx="{nx}" cy="{ny}" r="{glow_r}" fill="{ring}" opacity="{glow_opacity}" filter="url(#glow)"/>
          {pulse_anim}
          <circle cx="{nx}" cy="{ny}" r="{r}" fill="{bg}" stroke="{ring}" stroke-width="2"/>
          <circle cx="{nx}" cy="{ny}" r="{r-6}" fill="none" stroke="{ring}" stroke-width="0.5" opacity="0.4"/>
          <text x="{nx}" y="{tspan_y}" text-anchor="middle" dominant-baseline="middle"
                font-family="Orbitron,monospace" font-size="9" font-weight="700"
                fill="{tc}" letter-spacing="1">
            {tspans}
          </text>
        </g>"""

    def line_svg(x1, y1, x2, y2, agent_state, dashed=True):
        lc = line_color(agent_state, cmd_s)
        active = pulse_active(agent_state, cmd_s)
        dash = "8,5" if dashed else "none"
        opacity = "0.9" if active else "0.35"
        anim = ""
        if active:
            anim = f'<animate attributeName="stroke-dashoffset" values="0;-26" dur="0.6s" repeatCount="indefinite"/>'
        return f"""
        <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"
              stroke="{lc}" stroke-width="1.5" stroke-dasharray="{dash}"
              stroke-dashoffset="0" opacity="{opacity}">
          {anim}
        </line>
        <polygon points="{x2},{y2} {x2-5},{y2-9} {x2+5},{y2-9}"
                 fill="{lc}" opacity="{opacity}"
                 transform="rotate({_angle(x1,y1,x2,y2)} {x2} {y2})"/>"""

    # ── Build SVG ──
    lines_svg = ""
    nodes_svg = ""

    # Outer ring connecting agents
    agent_list = [("Fire_Bot", fire_s), ("Police_Bot", police_s), ("Med_Bot", med_s)]
    for i in range(len(agent_list)):
        ax1, ay1 = agents_pos[agent_list[i][0]]
        ax2, ay2 = agents_pos[agent_list[(i+1) % len(agent_list)][0]]
        combined = agent_list[i][1] if agent_list[i][1] != "idle" else agent_list[(i+1) % len(agent_list)][1]
        lines_svg += line_svg(ax1, ay1, ax2, ay2, combined, dashed=True)

    # Commander ↔ agent spokes
    for aname, astate in agent_list:
        ax, ay = agents_pos[aname]
        # vector from agent to commander, shorten by radii
        dx, dy = cx - ax, cy - ay
        dist = (dx**2 + dy**2) ** 0.5
        ux, uy = dx / dist, dy / dist
        x1s = ax + ux * ar
        y1s = ay + uy * ar
        x2s = cx - ux * cr
        y2s = cy - uy * cr
        lines_svg += line_svg(x1s, y1s, x2s, y2s, astate, dashed=False)
        lines_svg += line_svg(x2s, y2s, x1s, y1s, astate, dashed=True)

    for aname, astate in agent_list:
        ax, ay = agents_pos[aname]
        icon = {"Fire_Bot": "🔥", "Police_Bot": "🚔", "Med_Bot": "🏥"}.get(aname, "🤖")
        nodes_svg += node_svg(ax, ay, aname, icon, astate, ar)

    # Commander node
    nodes_svg += node_svg(cx, cy, "COMMANDER", "⚖️", cmd_s, cr)

    svg = f"""
<svg viewBox="0 0 600 400" xmlns="http://www.w3.org/2000/svg"
     style="width:100%;max-width:600px;display:block;margin:0 auto;background:transparent">
  <defs>
    <filter id="glow" x="-60%" y="-60%" width="220%" height="220%">
      <feGaussianBlur stdDeviation="8" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <!-- Subtle grid -->
    <pattern id="grid" width="30" height="30" patternUnits="userSpaceOnUse">
      <path d="M30 0L0 0 0 30" fill="none" stroke="#0d2545" stroke-width="0.5"/>
    </pattern>
  </defs>
  <rect width="600" height="400" fill="url(#grid)" opacity="0.5"/>
  <!-- Outer orbit ring -->
  <circle cx="{cx}" cy="{cy}" r="{orbit}" fill="none" stroke="#0d2545" stroke-width="1"
          stroke-dasharray="4,6" opacity="0.5"/>
  {lines_svg}
  {nodes_svg}
</svg>"""
    return svg


def _angle(x1, y1, x2, y2):
    import math
    dx, dy = x2 - x1, y2 - y1
    return math.degrees(math.atan2(dy, dx)) + 90


# ── Helper: run a single specialist agent ─────────────────────────────────────
def _run_agent(agent_type: str, prompt: str, history_context: str, llm_client) -> dict:
    agent = SpecialistFactory.create(agent_type, llm_client)
    response = agent.analyze(prompt, previous_findings=history_context)
    return {"name": agent.name, "response": response, "type": agent_type}


# ── Core processing logic ─────────────────────────────────────────────────────
def process_event(event_text: str):
    st.session_state.chat_history.append({"role": "user", "content": event_text})

    history_context = "\n".join(
        f"{m['role']}: {m['content']}"
        for m in st.session_state.chat_history[:-1]
    )

    agent_types = ["fire", "police", "medical"]
    llm = st.session_state.llm

    # Stage 1: Parallel specialist analysis
    agent_reports: dict[str, str] = {}
    with st.spinner("⚡ Specialists analysing in parallel..."):
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {
                executor.submit(_run_agent, atype, event_text, history_context, llm): atype
                for atype in agent_types
            }
            for future in concurrent.futures.as_completed(futures):
                result = future.result()
                agent_reports[result["name"]] = result["response"]

    # Stage 2: Consensus Engine + Constitutional review
    commander = CommanderAgent(llm)

    import agents.commander_agent as _ca_module
    original_constitution = _ca_module.CONSTITUTION
    original_triggers     = _ca_module.VETO_TRIGGERS
    _ca_module.CONSTITUTION  = st.session_state.constitution_text
    _ca_module.VETO_TRIGGERS = st.session_state.veto_triggers

    with st.spinner("⚖️ Commander synthesising consensus decision..."):
        review_result = commander.review_and_synthesize(agent_reports)

    _ca_module.CONSTITUTION  = original_constitution
    _ca_module.VETO_TRIGGERS = original_triggers

    reviews        = review_result["reviews"]
    final_plan     = review_result["final_plan"]
    veto_log       = review_result["veto_log"]
    urgency_scores = review_result.get("urgency_scores", {})
    conflicts      = review_result.get("conflicts", [])

    agent_icons = {"Fire_Bot": "🔥", "Police_Bot": "🚔", "Med_Bot": "🏥"}

    specialist_entries = []
    for agent_name, report_text in agent_reports.items():
        review  = reviews.get(agent_name, {})
        vetoed  = review.get("vetoed", False)
        reason  = review.get("reason", "")
        icon    = agent_icons.get(agent_name, "🤖")
        urgency = urgency_scores.get(agent_name)

        specialist_entries.append({
            "name":          agent_name,
            "icon":          icon,
            "vetoed":        vetoed,
            "verdict":       "🔴 VETO" if vetoed else "✅ APPROVED",
            "reason":        reason,
            "report":        report_text,
            "urgency_label": urgency.label if urgency else "N/A",
            "urgency_score": urgency.score if urgency else None,
        })

    status_lines = [
        f"- {e['icon']} **{e['name']}** "
        f"{'🔴 VETO' if e['vetoed'] else '✅ APPROVED'}"
        + (f" — {e['reason']}" if e['reason'] else "")
        for e in specialist_entries
    ]

    veto_section = ""
    if veto_log:
        veto_entries = "\n".join(
            f"  - [{v['stage'].upper()}] **{v['agent']}**: {v['reason']}"
            for v in veto_log
        )
        veto_section = f"\n\n**📋 Veto Audit Log:**\n{veto_entries}"

    conflicts_section = ""
    if conflicts:
        conflict_lines = [
            f"  - **[{c.topic.upper()}]** `{c.agent_a}` ({c.stance_a}) vs "
            f"`{c.agent_b}` ({c.stance_b}) → ✅ **{c.winner}** — _{c.resolution_reason}_"
            for c in conflicts
        ]
        conflicts_section = "\n\n**⚖️ Conflict Resolutions:**\n" + "\n".join(conflict_lines)

    # Build agent_states for diagram
    agent_states_result = {"Commander": "approved"}
    for e in specialist_entries:
        agent_states_result[e["name"]] = "vetoed" if e["vetoed"] else "approved"

    specialists_json = json.dumps(specialist_entries)

    content = (
        "### 🎖️ Commander Review\n"
        + "\n".join(status_lines)
        + veto_section
        + conflicts_section
        + f"\n\n---\n### 🎯 Unified Command Decision\n{final_plan}"
        + f"\n\n<!-- SPECIALISTS:{specialists_json} -->"
    )

    st.session_state.chat_history.append({
        "role":         "assistant",
        "content":      content,
        "avatar":       "⚖️",
        "specialists":  specialist_entries,
        "agent_states": agent_states_result,
        "conflicts":    [{"topic": c.topic, "agent_a": c.agent_a, "stance_a": c.stance_a,
                          "agent_b": c.agent_b, "stance_b": c.stance_b,
                          "winner": c.winner, "resolution_reason": c.resolution_reason}
                         for c in conflicts],
    })
    st.rerun()


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="font-family:'Orbitron',monospace;font-size:13px;color:#00c8ff;
                letter-spacing:3px;text-transform:uppercase;padding:12px 0 8px 0;
                border-bottom:1px solid #0d2545;margin-bottom:16px;">
        🛡️ CONTROL PANEL
    </div>""", unsafe_allow_html=True)

    if st.button("⬛ NEW INCIDENT", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()

    st.markdown("<div style='margin:16px 0;border-top:1px solid #0d2545'></div>", unsafe_allow_html=True)

    with st.expander("⚖️ CONSTITUTION EDITOR", expanded=False):
        st.caption("Keep RULE N: prefix format. Changes apply to next event.")
        edited_constitution = st.text_area(
            "Constitution Rules",
            value=st.session_state.constitution_text,
            height=250,
            label_visibility="collapsed",
        )
        if edited_constitution != st.session_state.constitution_text:
            st.session_state.constitution_text = edited_constitution
            st.success("✓ Constitution updated.")

    with st.expander("🔍 VETO TRIGGERS", expanded=False):
        st.caption("JSON: phrase → rule label (case-insensitive).")
        triggers_json  = json.dumps(st.session_state.veto_triggers, indent=2)
        edited_triggers = st.text_area(
            "Veto Triggers JSON",
            value=triggers_json,
            height=200,
            label_visibility="collapsed",
        )
        if st.button("💾 SAVE TRIGGERS", use_container_width=True):
            try:
                parsed = json.loads(edited_triggers)
                st.session_state.veto_triggers = parsed
                st.success("✓ Triggers saved.")
            except json.JSONDecodeError as exc:
                st.error(f"Invalid JSON: {exc}")

    st.markdown("<div style='margin:16px 0;border-top:1px solid #0d2545'></div>", unsafe_allow_html=True)

    st.markdown("""<div style="font-family:'Orbitron',monospace;font-size:10px;color:#6ba3bf;
                   letter-spacing:2px;margin-bottom:8px;">📁 FIELD REPORT UPLOAD</div>""",
                unsafe_allow_html=True)
    st.caption(f"Accepted: .txt / .md — max {MAX_UPLOAD_BYTES // (1024*1024)} MB")

    uploaded_file = st.file_uploader(
        "Upload report", type=["txt", "md"], label_visibility="collapsed",
    )
    if uploaded_file is not None:
        file_bytes = uploaded_file.read()
        if len(file_bytes) > MAX_UPLOAD_BYTES:
            st.error(f"❌ File too large ({len(file_bytes)/(1024*1024):.2f} MB). Max 2 MB.")
        else:
            file_content = file_bytes.decode("utf-8", errors="replace")
            if st.button("🚀 PROCESS REPORT", use_container_width=True):
                process_event(f"📄 **FIELD REPORT UPLOADED:**\n\n{file_content}")

    st.markdown("<div style='margin:24px 0 8px 0;border-top:1px solid #0d2545'></div>", unsafe_allow_html=True)
    st.markdown("""
    <div style="font-family:'Share Tech Mono',monospace;font-size:10px;color:#3d6080;line-height:1.8">
    🔴 CRITICAL &nbsp; 🟠 HIGH<br>🟡 MEDIUM &nbsp; 🟢 LOW
    </div>""", unsafe_allow_html=True)


# ── Main layout ───────────────────────────────────────────────────────────────
# Header
st.markdown(f"""
<div class="cmd-header">
  <div class="cmd-dot"></div>
  <div>
    <div class="cmd-header-title">COMMAND CORE</div>
    <div class="cmd-header-sub">CONSENSUS ENGINE · MILESTONE 4 · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC</div>
  </div>
</div>""", unsafe_allow_html=True)

# Two-column layout: network diagram left, chat right
col_net, col_chat = st.columns([1, 2], gap="large")

with col_net:
    st.markdown("""<div style="font-family:'Orbitron',monospace;font-size:10px;color:#6ba3bf;
                   letter-spacing:3px;margin-bottom:12px;">◈ AGENT NETWORK</div>""",
                unsafe_allow_html=True)

    # Determine current agent states from last assistant message
    last_assistant = next(
        (m for m in reversed(st.session_state.chat_history) if m["role"] == "assistant"),
        None
    )
    if last_assistant and "agent_states" in last_assistant:
        current_states = last_assistant["agent_states"]
    else:
        current_states = {"Fire_Bot": "idle", "Police_Bot": "idle",
                          "Med_Bot": "idle", "Commander": "idle"}

    diagram_svg = render_network_diagram(current_states)
    components.html(f"""
    <style>
      body {{ margin:0; padding:0; background:transparent; }}
    </style>
    <div style="background:transparent">{diagram_svg}</div>
    """, height=310, scrolling=False)

    # Legend
    st.markdown("""
    <div style="display:flex;gap:16px;flex-wrap:wrap;margin-top:12px;
                font-family:'Share Tech Mono',monospace;font-size:10px;color:#3d6080">
      <span><span style="color:#3d6080">●</span> IDLE</span>
      <span><span style="color:#00c8ff">●</span> PROCESSING</span>
      <span><span style="color:#00ff88">●</span> APPROVED</span>
      <span><span style="color:#ff2244">●</span> VETOED</span>
    </div>""", unsafe_allow_html=True)

    # Stats from last result
    if last_assistant and last_assistant.get("specialists"):
        st.markdown("<div style='margin-top:20px'></div>", unsafe_allow_html=True)
        st.markdown("""<div style="font-family:'Orbitron',monospace;font-size:10px;color:#6ba3bf;
                       letter-spacing:3px;margin-bottom:10px;">◈ URGENCY MATRIX</div>""",
                    unsafe_allow_html=True)
        for e in last_assistant["specialists"]:
            score = e.get("urgency_score")
            label = e.get("urgency_label", "N/A")
            color = _URGENCY_COLOR.get(label, "#00b4ff")
            bar_w = int((score or 0) * 10) if score else 0
            icon  = e["icon"]
            name  = e["name"]
            st.markdown(f"""
            <div style="margin-bottom:10px">
              <div style="display:flex;justify-content:space-between;align-items:center;
                          font-family:'Share Tech Mono',monospace;font-size:10px;
                          color:#6ba3bf;margin-bottom:3px">
                <span>{icon} {name}</span>
                <span style="color:{color}">{label} {f'{score:.1f}' if score else '—'}</span>
              </div>
              <div style="height:3px;background:#0d2545;border-radius:2px">
                <div style="height:3px;width:{bar_w}%;background:{color};
                            border-radius:2px;box-shadow:0 0 6px {color};
                            transition:width 0.5s ease"></div>
              </div>
            </div>""", unsafe_allow_html=True)

        # Conflicts
        if last_assistant.get("conflicts"):
            st.markdown("""<div style="font-family:'Orbitron',monospace;font-size:10px;
                           color:#ff8c00;letter-spacing:3px;margin:16px 0 8px 0;">
                           ⚠ CONFLICTS RESOLVED</div>""", unsafe_allow_html=True)
            for c in last_assistant["conflicts"]:
                st.markdown(f"""
                <div style="background:#0d1a2a;border:1px solid #1a3a20;border-left:2px solid #ff8c00;
                            padding:8px 10px;margin-bottom:6px;font-family:'Share Tech Mono',monospace;
                            font-size:10px;color:#6ba3bf">
                  <span style="color:#ff8c00">[{c['topic'].upper()}]</span><br>
                  {c['agent_a']} vs {c['agent_b']}<br>
                  <span style="color:#00ff88">→ {c['winner']}</span>
                </div>""", unsafe_allow_html=True)


with col_chat:
    st.markdown("""<div style="font-family:'Orbitron',monospace;font-size:10px;color:#6ba3bf;
                   letter-spacing:3px;margin-bottom:12px;">◈ INCIDENT FEED</div>""",
                unsafe_allow_html=True)

    # Chat history
    for message in st.session_state.chat_history:
        display_content = message["content"]
        if "<!-- SPECIALISTS:" in display_content:
            display_content = display_content[:display_content.rfind("\n\n<!-- SPECIALISTS:")]

        with st.chat_message(message["role"], avatar=message.get("avatar")):
            st.markdown(display_content)

            if message["role"] == "assistant" and message.get("specialists"):
                st.markdown("""<div style="font-family:'Orbitron',monospace;font-size:9px;
                               color:#3d6080;letter-spacing:2px;margin:12px 0 8px 0">
                               ▸ SPECIALIST REPORTS</div>""", unsafe_allow_html=True)
                cols = st.columns(len(message["specialists"]))
                for col, entry in zip(cols, message["specialists"]):
                    label    = entry.get("urgency_label", "N/A")
                    color    = _URGENCY_COLOR.get(label, "#00b4ff")
                    verdict  = "VETO" if entry["vetoed"] else "OK"
                    v_color  = "#ff2244" if entry["vetoed"] else "#00ff88"
                    with col:
                        with st.expander(
                            f"{entry['icon']} {entry['name']}"
                        ):
                            st.markdown(
                                f'<span class="urgency-badge" style="background:rgba(0,200,255,0.08);'
                                f'border:1px solid {color};color:{color}">{label}</span>'
                                f'<span class="urgency-badge" style="background:rgba(0,200,255,0.05);'
                                f'border:1px solid {v_color};color:{v_color}">{verdict}</span>',
                                unsafe_allow_html=True
                            )
                            st.markdown(entry["report"])

    # Footer
    st.markdown(f"""
    <div style="margin-top:24px;border-top:1px solid #0d2545;padding-top:8px;
                font-family:'Share Tech Mono',monospace;font-size:10px;color:#1e3a52;
                display:flex;justify-content:space-between">
      <span>PARALLEL EXECUTION · CONSTITUTIONAL AI · CONSENSUS ENGINE</span>
      <span>UPLOAD LIMIT: 2MB · {datetime.now().strftime('%H:%M:%S')}</span>
    </div>""", unsafe_allow_html=True)

# Chat input MUST be at top level (not inside columns/expanders)
if prompt := st.chat_input("DESCRIBE INCIDENT..."):
    process_event(prompt)