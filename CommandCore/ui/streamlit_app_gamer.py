"""
Adaptive Lighthouse Core — Command Core UI  v5
===============================================
Milestone 4 · Round Table · Real Time
Layout matching tactical command-center screenshot:
  - Header bar: title, system status, timestamp
  - 3-column dashboard:
      LEFT  : Event Summary + Urgency Matrix + Active Veto Rules + Veto Log
      CENTER: Animated Round Table (components.html) + Conflict Resolutions + Synthesized Decision
      RIGHT : Recommendations (agent report cards)
  - Chat history + input below the dashboard
  - File upload in sidebar
  - ALL original functionality 100% preserved
"""

import streamlit as st
import streamlit.components.v1 as components
import sys, os, json, concurrent.futures
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.agent_factory   import SpecialistFactory
from agents.commander_agent import CommanderAgent, CONSTITUTION, VETO_TRIGGERS
from llm.llm_client         import LLMClient

# ── geo & weather helpers ─────────────────────────────────────────────────────
import re as _re
import urllib.request, urllib.parse

def _extract_location(text: str):
    """
    Extract location from free text (Hebrew + English) and geocode via Nominatim.
    Returns (lat, lon, display_name) or None.
    """
    candidates = []

    # ── Hebrew patterns ──
    # "בשוק הכרמל", "בתל אביב", "ליד הכרמל", "באזור תל אביב"
    he_patterns = [
        r'ב([\u05d0-\u05ea][\u05d0-\u05ea\s\-]{2,25}?)(?:\s|,|\.|$)',
        r'ליד\s+([\u05d0-\u05ea][\u05d0-\u05ea\s\-]{2,25}?)(?:\s|,|\.|$)',
        r'באזור\s+([\u05d0-\u05ea][\u05d0-\u05ea\s\-]{2,25}?)(?:\s|,|\.|$)',
        r'(?:עיר|רחוב|שכונת|שוק|כביש|צומת)\s+([\u05d0-\u05ea][\u05d0-\u05ea\s\-]{2,20}?)(?:\s|,|\.|$)',
    ]
    for pat in he_patterns:
        for m in _re.finditer(pat, text):
            candidates.append(m.group(1).strip())

    # ── Known Hebrew city names — direct lookup ──
    he_cities = [
        "תל אביב", "ירושלים", "חיפה", "באר שבע", "ראשון לציון",
        "פתח תקווה", "נתניה", "אשדוד", "אשקלון", "רמת גן",
        "בני ברק", "הרצליה", "חולון", "רחובות", "מודיעין",
        "רעננה", "כפר סבא", "עכו", "נצרת", "טבריה",
    ]
    for city in he_cities:
        if city in text:
            candidates.insert(0, city)

    # ── English: Title-Case runs ──
    words = text.split()
    for length in (3, 2, 4):
        for i in range(len(words) - length + 1):
            chunk = " ".join(words[i:i+length])
            if _re.match(r'^[A-Z][a-zA-Z ,\-]+$', chunk):
                candidates.append(chunk)

    # ── Deduplicate while preserving order ──
    seen = set()
    unique = []
    for c in candidates:
        if c not in seen and len(c) > 1:
            seen.add(c)
            unique.append(c)

    for candidate in unique[:8]:  # try up to 8 candidates
        try:
            q   = urllib.parse.quote(candidate)
            url = f"https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=1&accept-language=he,en"
            req = urllib.request.Request(url, headers={"User-Agent": "AdaptiveLighthouseCore/1.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read())
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"]), data[0]["display_name"]
        except Exception:
            continue
    return None


def _get_weather(lat: float, lon: float) -> dict:
    """Fetch current weather from Open-Meteo (free, no key needed)."""
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,wind_speed_10m,weathercode,relative_humidity_2m"
            f"&timezone=auto"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "AdaptiveLighthouseCore/1.0"})
        with urllib.request.urlopen(req, timeout=4) as r:
            data = json.loads(r.read())
        c = data.get("current", {})
        code = c.get("weathercode", 0)
        # WMO code → simple label
        if code == 0:               condition = "Clear ☀️"
        elif code in range(1, 4):   condition = "Partly Cloudy 🌤️"
        elif code in range(45, 68): condition = "Fog / Drizzle 🌫️"
        elif code in range(61, 68): condition = "Rain 🌧️"
        elif code in range(71, 78): condition = "Snow ❄️"
        elif code in range(80, 83): condition = "Showers 🌦️"
        elif code in range(95, 100):condition = "Thunderstorm ⛈️"
        else:                       condition = "Overcast ☁️"
        return {
            "temp":     c.get("temperature_2m", "—"),
            "wind":     c.get("wind_speed_10m", "—"),
            "humidity": c.get("relative_humidity_2m", "—"),
            "condition":condition,
        }
    except Exception:
        return {}


def _build_map_html(lat: float, lon: float, label: str) -> str:
    """Return a self-contained Folium map as HTML string."""
    import folium
    m = folium.Map(
        location=[lat, lon], zoom_start=14,
        tiles="CartoDB dark_matter",
    )
    folium.Marker(
        [lat, lon],
        popup=label,
        icon=folium.Icon(color="red", icon="exclamation-sign"),
    ).add_to(m)
    folium.Circle(
        [lat, lon], radius=300,
        color="#ff3b3b", fill=True, fill_opacity=0.15, weight=2,
    ).add_to(m)
    return m._repr_html_()

MAX_UPLOAD_BYTES = 2 * 1024 * 1024

st.set_page_config(
    page_title="Adaptive Lighthouse Core",
    page_icon="🔱",
    layout="wide",
)

# ── session state ─────────────────────────────────────────────────────────────
for _k, _v in [
    ("llm",               None),
    ("chat_history",      []),
    ("constitution_text", CONSTITUTION),
    ("veto_triggers",     dict(VETO_TRIGGERS)),
    ("last_result",       None),
]:
    if _k not in st.session_state:
        st.session_state[_k] = _v if _k != "llm" else LLMClient()

# ── global CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;600;700&family=Share+Tech+Mono&family=Orbitron:wght@700;900&display=swap');

html,body,[data-testid="stAppViewContainer"]{
  background:#07090f !important;
  font-family:'Rajdhani',sans-serif !important;
}
[data-testid="stAppViewContainer"]>.main{ background:#07090f !important; }
[data-testid="stSidebar"]{
  background:#060a14 !important;
  border-right:1px solid #0d1e36 !important;
}
#MainMenu,footer,header,[data-testid="stDecoration"]{
  visibility:hidden !important; display:none !important;
}
::-webkit-scrollbar{ width:4px; background:#07090f; }
::-webkit-scrollbar-thumb{ background:#1a3a60; border-radius:2px; }

[data-testid="stChatInput"] textarea{
  background:#080e1c !important; border:1px solid #1a3a60 !important;
  color:#a0c8f0 !important; font-family:'Share Tech Mono',monospace !important;
  font-size:13px !important; border-radius:4px !important;
}
[data-testid="stChatInput"] textarea:focus{
  border-color:#4aa3ee !important;
  box-shadow:0 0 10px rgba(74,163,238,0.2) !important;
}
/* sticky bottom bar — remove white background */
[data-testid="stBottom"],
[data-testid="stBottom"] > div,
[data-testid="stBottom"] > div > div,
.stChatFloatingInputContainer,
.stChatInputContainer,
section[data-testid="stBottom"] {
  background:#07090f !important;
  background-color:#07090f !important;
  border-top:1px solid #0d1e36 !important;
}
/* kill any white gap below input */
.main .block-container {
  padding-bottom: 80px !important;
}
[data-testid="stChatMessage"]{
  background:#080e1c !important; border:1px solid #0d1e36 !important;
  border-left:3px solid #1565c0 !important; border-radius:4px !important;
  margin-bottom:12px !important;
}
[data-testid="stExpander"]{
  background:#080e1c !important; border:1px solid #0d1e36 !important;
  border-radius:3px !important;
}
[data-testid="stExpander"] summary{
  color:#4aa3ee !important; font-family:'Rajdhani',sans-serif !important;
  font-weight:700 !important; font-size:15px !important;
}
.stButton>button{
  background:linear-gradient(135deg,#1a4a8a,#0d2a5a) !important;
  border:1px solid #2a6aaa !important; color:#a0c8f0 !important;
  font-family:'Rajdhani',sans-serif !important; font-weight:700 !important;
  letter-spacing:2px !important; text-transform:uppercase !important;
  border-radius:3px !important; transition:all 0.2s !important;
}
.stButton>button:hover{
  border-color:#4aa3ee !important;
  box-shadow:0 0 14px rgba(74,163,238,0.3) !important;
}
textarea{
  background:#080e1c !important; border:1px solid #0d1e36 !important;
  color:#a0c8f0 !important; font-family:'Share Tech Mono',monospace !important;
  font-size:12px !important;
}
.stMarkdown p,.stMarkdown li{
  color:#a0c8f0 !important; font-family:'Rajdhani',sans-serif !important;
  font-size:16px !important; line-height:1.6 !important;
}
.stMarkdown strong{ color:#fff !important; font-size:16px !important; }
.stMarkdown code{
  background:rgba(74,163,238,0.1) !important; color:#4aa3ee !important;
  border:1px solid #1a3a60 !important; border-radius:2px !important;
}
hr{ border-color:#0d1e36 !important; }
.stCaption{
  color:#2a5a8a !important; font-family:'Share Tech Mono',monospace !important;
  font-size:11px !important;
}
[data-testid="stSuccess"]{
  background:rgba(0,200,100,0.08) !important;
  border:1px solid rgba(0,200,100,0.3) !important;
}
[data-testid="stError"]{
  background:rgba(255,50,50,0.08) !important;
  border:1px solid rgba(255,50,50,0.3) !important;
}
</style>
""", unsafe_allow_html=True)

# ── constants ─────────────────────────────────────────────────────────────────
_URGENCY_COLOR = {
    "CRITICAL": "#ff3b3b",
    "HIGH":     "#ff8c00",
    "MEDIUM":   "#f5c518",
    "LOW":      "#00e676",
    "N/A":      "#4aa3ee",
}
_AGENT_META = {
    "Fire_Bot":   {"icon": "🔥", "color": "#ff6b35"},
    "Police_Bot": {"icon": "🚔", "color": "#4a9eff"},
    "Med_Bot":    {"icon": "🏥", "color": "#00e5ff"},
}


# ── round-table HTML ──────────────────────────────────────────────────────────
def build_round_table_html(agent_states: dict) -> str:
    fire_s   = agent_states.get("Fire_Bot",   "idle")
    police_s = agent_states.get("Police_Bot", "idle")
    med_s    = agent_states.get("Med_Bot",    "idle")
    cmd_s    = agent_states.get("Commander",  "idle")

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{background:#07090f;font-family:'Segoe UI',Arial,sans-serif;overflow:hidden;}}
#wrap{{position:relative;width:100%;height:340px;background:#07090f;}}
#rt-canvas{{position:absolute;inset:0;width:100%;height:100%;}}
#rt-svg{{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;}}

.rt-agent{{
  position:absolute;display:flex;flex-direction:column;
  align-items:center;transform:translate(-50%,-50%);z-index:10;
}}
.rt-circle{{
  width:72px;height:72px;border-radius:50%;
  border:2px solid #1a4a9a;display:flex;flex-direction:column;
  align-items:center;justify-content:center;
  transition:box-shadow 0.3s,transform 0.2s;position:relative;
}}

/* ── idle colors — uniform blue for all agents ── */
#circ-fire, #circ-police, #circ-med {{
  background:radial-gradient(circle at 35% 35%,#2a6aee,#0d2a6a 60%,#060e2a);
  border-color:#1a4a9a;
  box-shadow:0 0 0 4px rgba(26,74,154,0.15),0 0 18px rgba(13,42,106,0.3);
}}

/* ── processing: cyan pulse override ── */
.rt-circle.processing{{
  transform:scale(1.1);border-color:#4aa3ee;
  background:radial-gradient(circle at 35% 35%,#3a8aff,#1040a0 55%,#071840) !important;
  box-shadow:0 0 0 8px rgba(74,163,238,0.35),0 0 40px rgba(74,163,238,0.65) !important;
  animation:pulseGlow 1.4s ease-in-out infinite;
}}

/* ── approved: green glow ring ── */
.rt-circle.approved{{
  box-shadow:0 0 0 7px rgba(0,230,118,0.4),0 0 30px rgba(0,230,118,0.35) !important;
}}

/* ── vetoed: red override ── */
.rt-circle.vetoed{{
  background:radial-gradient(circle at 35% 35%,#ff5566,#880020 55%,#1a0008) !important;
  border-color:#ff3244 !important;
  box-shadow:0 0 0 6px rgba(255,50,68,0.35),0 0 28px rgba(255,50,68,0.4) !important;
}}

@keyframes pulseGlow{{
  0%,100%{{box-shadow:0 0 0 8px rgba(74,163,238,0.35),0 0 40px rgba(74,163,238,0.6);}}
  50%{{box-shadow:0 0 0 15px rgba(74,163,238,0.1),0 0 65px rgba(74,163,238,0.85);}}
}}
.speaking-ring{{
  position:absolute;border-radius:50%;
  border:1.5px solid rgba(74,163,238,0.6);
  animation:expandRing 1.4s ease-out infinite;pointer-events:none;
}}
@keyframes expandRing{{
  0%{{transform:scale(1);opacity:0.8;}}
  100%{{transform:scale(2.1);opacity:0;}}
}}

/* icon + sub-label inside circle */
.rt-icon{{font-size:24px;line-height:1;text-align:center;}}
.rt-label{{
  font-size:7px;font-weight:700;color:rgba(255,255,255,0.8);
  letter-spacing:1px;text-transform:uppercase;text-align:center;margin-top:1px;
}}
.rt-status{{
  font-size:7px;color:#ff8c00;letter-spacing:0.5px;
  margin-top:2px;text-align:center;height:10px;font-family:monospace;
}}
.rt-name{{
  margin-top:5px;font-size:8px;font-weight:700;
  letter-spacing:1.5px;text-transform:uppercase;
  color:#4aa3ee;text-align:center;
}}

/* ── commander ── */
.rt-commander .rt-circle{{
  width:90px;height:90px;
  background:radial-gradient(circle at 35% 35%,#5ab8ff,#0d3a9a 50%,#040f28);
  border:2.5px solid #4aa3ee;
  box-shadow:0 0 0 10px rgba(74,163,238,0.18),0 0 40px rgba(21,97,196,0.4);
}}
.rt-commander .rt-icon{{font-size:30px;}}
.rt-commander .rt-label{{font-size:8px;letter-spacing:2px;}}
.rt-commander .rt-name{{font-size:9px;color:#7dd4ff;}}
.rt-commander .rt-circle.processing{{animation:cmdPulse 1.2s ease-in-out infinite;}}
.rt-commander .rt-circle.approved{{
  box-shadow:0 0 0 10px rgba(74,163,238,0.18),0 0 40px rgba(21,97,196,0.4) !important;
  background:radial-gradient(circle at 35% 35%,#5ab8ff,#0d3a9a 50%,#040f28) !important;
  border-color:#4aa3ee !important;
}}
@keyframes cmdPulse{{
  0%,100%{{box-shadow:0 0 0 12px rgba(91,191,255,0.3),0 0 60px rgba(91,191,255,0.6);}}
  50%{{box-shadow:0 0 0 22px rgba(91,191,255,0.08),0 0 95px rgba(91,191,255,0.85);}}
}}
</style>
</head>
<body>
<div id="wrap">
  <canvas id="rt-canvas"></canvas>
  <svg id="rt-svg" xmlns="http://www.w3.org/2000/svg"></svg>

  <div class="rt-agent rt-commander" id="ag-commander" style="left:50%;top:57%">
    <div class="rt-circle" id="circ-commander">
      <div class="speaking-ring" id="ring-commander" style="width:90px;height:90px;display:none"></div>
      <div class="rt-icon">⚖️</div>
      <div class="rt-label">CMD</div>
    </div>
    <div class="rt-name">Commander</div>
    <div class="rt-status" id="st-commander"></div>
  </div>

  <div class="rt-agent" id="ag-fire" style="left:50%;top:17%">
    <div class="rt-circle" id="circ-fire">
      <div class="speaking-ring" id="ring-fire" style="width:72px;height:72px;display:none"></div>
      <div class="rt-icon">🔥</div>
      <div class="rt-label">FIRE</div>
    </div>
    <div class="rt-name">Fire_Bot</div>
    <div class="rt-status" id="st-fire"></div>
  </div>

  <div class="rt-agent" id="ag-police" style="left:16%;top:83%">
    <div class="rt-circle" id="circ-police">
      <div class="speaking-ring" id="ring-police" style="width:72px;height:72px;display:none"></div>
      <div class="rt-icon">🚔</div>
      <div class="rt-label">POLICE</div>
    </div>
    <div class="rt-name">Police_Bot</div>
    <div class="rt-status" id="st-police"></div>
  </div>

  <div class="rt-agent" id="ag-med" style="left:84%;top:83%">
    <div class="rt-circle" id="circ-med">
      <div class="speaking-ring" id="ring-med" style="width:72px;height:72px;display:none"></div>
      <div class="rt-icon">🏥</div>
      <div class="rt-label">MED</div>
    </div>
    <div class="rt-name">Med_Bot</div>
    <div class="rt-status" id="st-med"></div>
  </div>
</div>

<script>
const AGENTS = ['fire','police','med'];
const ALL    = ['commander','fire','police','med'];
const STATES = {{
  fire:      "{fire_s}",
  police:    "{police_s}",
  med:       "{med_s}",
  commander: "{cmd_s}"
}};

function getPos(id) {{
  const el   = document.getElementById('ag-'+id);
  const wrap = document.getElementById('wrap');
  if (!el||!wrap) return {{x:0,y:0}};
  const wr = wrap.getBoundingClientRect();
  const er = el.getBoundingClientRect();
  return {{ x:er.left+er.width/2-wr.left, y:er.top+er.height/2-wr.top }};
}}

function drawBg() {{
  const cv=document.getElementById('rt-canvas');
  const wrap=document.getElementById('wrap');
  cv.width=wrap.offsetWidth; cv.height=wrap.offsetHeight;
  const ctx=cv.getContext('2d');
  const W=cv.width,H=cv.height,cx=W/2,cy=H/2;
  ctx.clearRect(0,0,W,H);
  ctx.beginPath(); ctx.arc(cx,cy,Math.min(W,H)*0.39,0,Math.PI*2);
  ctx.strokeStyle='rgba(74,163,238,0.12)'; ctx.lineWidth=1;
  ctx.setLineDash([5,5]); ctx.stroke(); ctx.setLineDash([]);
  ctx.beginPath(); ctx.arc(cx,cy,Math.min(W,H)*0.21,0,Math.PI*2);
  ctx.strokeStyle='rgba(74,163,238,0.07)'; ctx.lineWidth=0.8; ctx.stroke();
}}

function clearSvg() {{
  const svg=document.getElementById('rt-svg');
  while(svg.firstChild) svg.removeChild(svg.firstChild);
}}

function drawLines() {{
  clearSvg();
  const svg=document.getElementById('rt-svg');
  const defs=document.createElementNS('http://www.w3.org/2000/svg','defs');

  function makeMarker(mid,color) {{
    const mk=document.createElementNS('http://www.w3.org/2000/svg','marker');
    mk.setAttribute('id',mid); mk.setAttribute('viewBox','0 0 10 10');
    mk.setAttribute('refX','8'); mk.setAttribute('refY','5');
    mk.setAttribute('markerWidth','5'); mk.setAttribute('markerHeight','5');
    mk.setAttribute('orient','auto-start-reverse');
    const p=document.createElementNS('http://www.w3.org/2000/svg','path');
    p.setAttribute('d','M2 1L8 5L2 9'); p.setAttribute('fill','none');
    p.setAttribute('stroke',color); p.setAttribute('stroke-width','1.5');
    mk.appendChild(p); defs.appendChild(mk);
  }}
  makeMarker('mDim',    '#1a3a60');
  makeMarker('mActive', '#4aa3ee');
  makeMarker('mGreen',  '#00e676');
  makeMarker('mRed',    '#ff3244');
  svg.appendChild(defs);

  const cmd=getPos('commander');
  AGENTS.forEach(id => {{
    const ag=getPos(id);
    const state=STATES[id];
    const dx=ag.x-cmd.x, dy=ag.y-cmd.y;
    const dist=Math.sqrt(dx*dx+dy*dy);
    const r1=44,r2=36;
    const x1=cmd.x+dx/dist*r1, y1=cmd.y+dy/dist*r1;
    const x2=ag.x-dx/dist*r2,  y2=ag.y-dy/dist*r2;

    let stroke='#0d2040',marker='mDim',sw='1',opacity='0.4',dash='4 4';
    if(state==='processing'){{stroke='#4aa3ee';marker='mActive';sw='2';opacity='0.9';dash='8 5';}}
    else if(state==='approved'){{stroke='#00e676';marker='mGreen';sw='1.5';opacity='0.7';dash='none';}}
    else if(state==='vetoed'){{stroke='#ff3244';marker='mRed';sw='1.5';opacity='0.7';dash='none';}}

    const line=document.createElementNS('http://www.w3.org/2000/svg','line');
    line.setAttribute('x1',x1); line.setAttribute('y1',y1);
    line.setAttribute('x2',x2); line.setAttribute('y2',y2);
    line.setAttribute('stroke',stroke);
    line.setAttribute('stroke-width',sw);
    line.setAttribute('stroke-dasharray',dash);
    line.setAttribute('opacity',opacity);
    line.setAttribute('marker-end','url(#'+marker+')');
    line.setAttribute('marker-start','url(#'+marker+')');
    if(state==='processing') {{
      const length=Math.sqrt((x2-x1)**2+(y2-y1)**2);
      const anim=document.createElementNS('http://www.w3.org/2000/svg','animate');
      anim.setAttribute('attributeName','stroke-dashoffset');
      anim.setAttribute('from','0');
      anim.setAttribute('to',String(-length));
      anim.setAttribute('dur','0.6s');
      anim.setAttribute('repeatCount','indefinite');
      line.appendChild(anim);
    }}
    svg.appendChild(line);
  }});
}}

function applyStates() {{
  ALL.forEach(id => {{
    const state=STATES[id];
    const circ=document.getElementById('circ-'+id);
    const ring=document.getElementById('ring-'+id);
    const st=document.getElementById('st-'+id);
    if(!circ) return;
    circ.classList.remove('processing','approved','vetoed');
    if(ring) ring.style.display='none';
    if(state==='processing') {{
      circ.classList.add('processing');
      if(ring) ring.style.display='block';
      if(st) st.textContent='ANALYZING...';
    }} else if(state==='approved') {{
      circ.classList.add('approved');
      if(st) st.textContent='APPROVED \u2713';
    }} else if(state==='vetoed') {{
      circ.classList.add('vetoed');
      if(st) st.textContent='VETOED \u2717';
    }} else {{
      if(st) st.textContent='';
    }}
  }});
}}

window.addEventListener('load',()=>{{ drawBg(); drawLines(); applyStates(); }});
window.addEventListener('resize',()=>{{ drawBg(); drawLines(); }});
</script>
</body>
</html>"""


# ── helpers ───────────────────────────────────────────────────────────────────
def _run_agent(agent_type, prompt, history_context, llm_client):
    agent = SpecialistFactory.create(agent_type, llm_client)
    response = agent.analyze(prompt, previous_findings=history_context)
    return {"name": agent.name, "response": response, "type": agent_type}


# ── process_event — 100% original logic ──────────────────────────────────────
def process_event(event_text: str):
    st.session_state.chat_history.append({"role": "user", "content": event_text})

    history_context = "\n".join(
        f"{m['role']}: {m['content']}"
        for m in st.session_state.chat_history[:-1]
    )

    agent_types = ["fire", "police", "medical"]
    llm = st.session_state.llm

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

    commander = CommanderAgent(llm)
    import agents.commander_agent as _ca
    orig_c, orig_t = _ca.CONSTITUTION, _ca.VETO_TRIGGERS
    _ca.CONSTITUTION  = st.session_state.constitution_text
    _ca.VETO_TRIGGERS = st.session_state.veto_triggers

    with st.spinner("⚖️ Commander synthesising decision..."):
        review_result = commander.review_and_synthesize(agent_reports)

    _ca.CONSTITUTION  = orig_c
    _ca.VETO_TRIGGERS = orig_t

    reviews        = review_result["reviews"]
    final_plan     = review_result["final_plan"]
    veto_log       = review_result["veto_log"]
    urgency_scores = review_result.get("urgency_scores", {})
    conflicts      = review_result.get("conflicts", [])

    specialist_entries = []
    for agent_name, report_text in agent_reports.items():
        review  = reviews.get(agent_name, {})
        vetoed  = review.get("vetoed", False)
        urgency = urgency_scores.get(agent_name)
        meta    = _AGENT_META.get(agent_name, {"icon": "🤖", "color": "#4aa3ee"})
        specialist_entries.append({
            "name":          agent_name,
            "icon":          meta["icon"],
            "color":         meta["color"],
            "vetoed":        vetoed,
            "reason":        review.get("reason", ""),
            "report":        report_text,
            "urgency_label": urgency.label if urgency else "N/A",
            "urgency_score": urgency.score if urgency else None,
        })

    agent_states = {"Commander": "approved"}
    for e in specialist_entries:
        agent_states[e["name"]] = "vetoed" if e["vetoed"] else "approved"

    conflicts_list = [
        {"topic": c.topic, "agent_a": c.agent_a, "stance_a": c.stance_a,
         "agent_b": c.agent_b, "stance_b": c.stance_b,
         "winner": c.winner, "resolution_reason": c.resolution_reason}
        for c in conflicts
    ]

    status_lines = [
        f"- {e['icon']} **{e['name']}**: {'🔴 VETO' if e['vetoed'] else '✅ APPROVED'}"
        + (f" — {e['reason']}" if e["reason"] else "")
        for e in specialist_entries
    ]
    veto_section = ""
    if veto_log:
        veto_section = "\n\n**📋 Veto Audit Log:**\n" + "\n".join(
            f"  - [{v['stage'].upper()}] **{v['agent']}**: {v['reason']}" for v in veto_log)
    conflicts_section = ""
    if conflicts:
        conflicts_section = "\n\n**⚖️ Conflict Resolutions:**\n" + "\n".join(
            f"  - **[{c.topic.upper()}]** `{c.agent_a}` ({c.stance_a}) vs "
            f"`{c.agent_b}` ({c.stance_b}) → ✅ **{c.winner}** — _{c.resolution_reason}_"
            for c in conflicts)

    content = (
        "### 🎖️ Commander Review\n" + "\n".join(status_lines)
        + veto_section + conflicts_section
        + f"\n\n---\n### 🎯 Unified Command Decision\n{final_plan}"
        + f"\n\n<!-- SPECIALISTS:{json.dumps(specialist_entries)} -->"
    )

    st.session_state.last_result = {
        "event_text":         event_text,
        "specialist_entries": specialist_entries,
        "final_plan":         final_plan,
        "veto_log":           veto_log,
        "conflicts":          conflicts_list,
        "agent_states":       agent_states,
        "urgency_scores":     {k: {"label": v.label, "score": v.score}
                               for k, v in urgency_scores.items()},
        "geo":                _extract_location(event_text),
    }
    # fetch weather if location found
    geo = st.session_state.last_result["geo"]
    st.session_state.last_result["weather"] = _get_weather(geo[0], geo[1]) if geo else {}

    st.session_state.chat_history.append({
        "role":        "assistant",
        "content":     content,
        "avatar":      "⚖️",
        "specialists": specialist_entries,
        "agent_states":agent_states,
        "conflicts":   conflicts_list,
    })
    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("""<div style="font-family:'Orbitron',monospace;font-size:12px;color:#4aa3ee;
    letter-spacing:3px;padding:10px 0 6px;border-bottom:1px solid #0d1e36;margin-bottom:14px">
    🔱 CONTROL PANEL</div>""", unsafe_allow_html=True)

    if st.button("⬛ NEW INCIDENT", use_container_width=True):
        st.session_state.chat_history = []
        st.session_state.last_result  = None
        st.rerun()

    st.markdown("<hr style='border-color:#0d1e36'>", unsafe_allow_html=True)

    with st.expander("⚖️ CONSTITUTION EDITOR", expanded=False):
        st.caption("Keep RULE N: prefix. Changes apply to next event.")
        edited = st.text_area(
            "constitution",
            value=st.session_state.constitution_text,
            height=250,
            label_visibility="collapsed",
        )
        if edited != st.session_state.constitution_text:
            st.session_state.constitution_text = edited
            st.success("✓ Updated.")

    with st.expander("🔍 VETO TRIGGERS", expanded=False):
        st.caption("JSON: phrase → rule label (case-insensitive).")
        edited_t = st.text_area(
            "triggers",
            value=json.dumps(st.session_state.veto_triggers, indent=2),
            height=200,
            label_visibility="collapsed",
        )
        if st.button("💾 SAVE TRIGGERS", use_container_width=True):
            try:
                st.session_state.veto_triggers = json.loads(edited_t)
                st.success("✓ Saved.")
            except json.JSONDecodeError as exc:
                st.error(f"Invalid JSON: {exc}")

    st.markdown("<hr style='border-color:#0d1e36'>", unsafe_allow_html=True)

    st.markdown("""<div style="font-family:'Orbitron',monospace;font-size:9px;color:#2a5a8a;
    letter-spacing:2px;margin-bottom:8px">📁 UPLOAD FIELD REPORT</div>""",
    unsafe_allow_html=True)
    st.caption("Accepted: .txt / .md — max 2 MB")

    uploaded = st.file_uploader("Upload", type=["txt", "md"], label_visibility="collapsed")
    if uploaded:
        fb = uploaded.read()
        if len(fb) > MAX_UPLOAD_BYTES:
            st.error(f"❌ File too large ({len(fb)/1024/1024:.2f} MB). Max 2 MB.")
        else:
            fc = fb.decode("utf-8", errors="replace")
            if st.button("🚀 PROCESS REPORT", use_container_width=True):
                process_event(f"📄 **FIELD REPORT:**\n\n{fc}")

    st.markdown("<hr style='border-color:#0d1e36'>", unsafe_allow_html=True)
    st.markdown("""<div style="font-family:'Share Tech Mono',monospace;font-size:10px;
    color:#1a3a60;line-height:1.9">🔴 CRITICAL &nbsp;🟠 HIGH<br>🟡 MEDIUM &nbsp;🟢 LOW</div>""",
    unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════════
res = st.session_state.last_result

st.markdown(f"""
<div style="display:flex;align-items:center;justify-content:space-between;
            padding:10px 0 12px;border-bottom:1px solid #0d1e36;margin-bottom:18px">
  <div style="display:flex;align-items:center;gap:14px">
    <div style="width:36px;height:36px;border-radius:50%;
                background:linear-gradient(135deg,#1a5aee,#0a1a4a);
                border:2px solid #4aa3ee;display:flex;align-items:center;
                justify-content:center;font-size:16px;
                box-shadow:0 0 14px rgba(74,163,238,0.4)">🔱</div>
    <div>
      <div style="font-family:'Orbitron',monospace;font-size:17px;font-weight:900;
                  color:#4aa3ee;letter-spacing:3px;
                  text-shadow:0 0 20px rgba(74,163,238,0.4)">
        ADAPTIVE LIGHTHOUSE CORE</div>
      <div style="font-family:'Share Tech Mono',monospace;font-size:10px;
                  color:#2a5a8a;letter-spacing:2px">ROUND TABLE — REAL TIME</div>
    </div>
  </div>
  <div style="display:flex;align-items:center;gap:24px">
    <div style="font-family:'Share Tech Mono',monospace;font-size:11px;color:#2a5a8a">
      System Status:
      <span style="color:#00e676;font-weight:700">ACTIVE</span>
    </div>
    <div style="font-family:'Share Tech Mono',monospace;font-size:10px;color:#1a3a60">
      {datetime.now().strftime('%H:%M:%S')}
    </div>
  </div>
</div>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD — 3 columns
# ══════════════════════════════════════════════════════════════════════════════
col_left, col_center, col_right = st.columns([1, 1.55, 1], gap="medium")


# ── LEFT ──────────────────────────────────────────────────────────────────────
with col_left:
    st.markdown("""<div style="font-family:'Orbitron',monospace;font-size:8px;color:#2a5a8a;
    letter-spacing:3px;margin-bottom:10px;border-bottom:1px solid #0d1e36;padding-bottom:6px">
    EVENT SUMMARY</div>""", unsafe_allow_html=True)

    if res:
        event_text = res.get("event_text", "—")
        severity   = "HIGH" if any(w in event_text.lower() for w in
                     ["fire","collapse","explosion","trapped","critical","flood","hazmat"]) else "MEDIUM"
        sev_color  = "#ff3b3b" if severity == "HIGH" else "#f5c518"
        geo        = res.get("geo")
        weather    = res.get("weather", {})

        # ── event info first ──
        location_str = geo[2].split(",")[0] if geo else "Unknown"
        st.markdown(f"""
        <div style="background:#060d1a;border:1px solid #0d1e36;border-left:3px solid #1565c0;
                    padding:10px 12px;border-radius:3px;margin-bottom:8px">
          <div style="font-family:'Share Tech Mono',monospace;font-size:10px;
                      color:#4aa3ee;line-height:1.9">
            <div><span style="color:#2a5a8a">Type:</span> Incident</div>
            <div><span style="color:#2a5a8a">Location:</span> {location_str}</div>
            <div><span style="color:#2a5a8a">Time:</span> {datetime.now().strftime('%H:%M')}</div>
            <div><span style="color:#2a5a8a">Severity:</span>
              <span style="color:{sev_color};font-weight:700">&nbsp;{severity}</span></div>
          </div>
          <div style="margin-top:8px;font-family:'Rajdhani',sans-serif;font-size:13px;
                      color:#a0c8f0;line-height:1.5;border-top:1px solid #0d1e36;padding-top:7px">
            {event_text[:140]}{'…' if len(event_text)>140 else ''}
          </div>
        </div>""", unsafe_allow_html=True)

        # ── map below event info ──
        if geo:
            lat, lon, place = geo
            try:
                map_html = _build_map_html(lat, lon, place)
                components.html(map_html, height=180, scrolling=False)
            except Exception:
                st.markdown("""<div style="background:#060d1a;border:1px solid #0d1e36;
                height:80px;display:flex;align-items:center;justify-content:center;
                border-radius:3px;margin-bottom:8px">
                <span style="color:#1a3a60;font-size:11px;font-family:monospace">
                Map unavailable</span></div>""", unsafe_allow_html=True)
        else:
            st.markdown("""<div style="background:#060d1a;border:1px solid #0d1e36;
            height:80px;display:flex;align-items:center;justify-content:center;
            border-radius:3px;margin-bottom:8px">
            <span style="color:#1a3a60;font-size:11px;font-family:monospace">
            📍 No location detected</span></div>""", unsafe_allow_html=True)

        # ── weather last ──
        if weather:
            st.markdown("""<div style="font-family:'Orbitron',monospace;font-size:8px;color:#2a5a8a;
            letter-spacing:3px;margin-bottom:7px">LIVE CONDITIONS</div>""", unsafe_allow_html=True)
            st.markdown(f"""
            <div style="background:#060d1a;border:1px solid #0d1e36;
                        padding:9px 12px;border-radius:3px">
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;
                          font-family:'Share Tech Mono',monospace;font-size:10px">
                <div>
                  <div style="color:#2a5a8a;margin-bottom:2px">CONDITION</div>
                  <div style="color:#a0c8f0">{weather.get('condition','—')}</div>
                </div>
                <div>
                  <div style="color:#2a5a8a;margin-bottom:2px">TEMP</div>
                  <div style="color:#a0c8f0">{weather.get('temp','—')} °C</div>
                </div>
                <div>
                  <div style="color:#2a5a8a;margin-bottom:2px">WIND</div>
                  <div style="color:#a0c8f0">{weather.get('wind','—')} km/h</div>
                </div>
                <div>
                  <div style="color:#2a5a8a;margin-bottom:2px">HUMIDITY</div>
                  <div style="color:#a0c8f0">{weather.get('humidity','—')} %</div>
                </div>
              </div>
            </div>""", unsafe_allow_html=True)

    else:
        st.markdown("""
        <div style="background:#060d1a;border:1px solid #0d1e36;
                    border-left:3px solid #1565c0;padding:12px;border-radius:3px">
          <div style="font-family:'Share Tech Mono',monospace;font-size:10px;
                      color:#1a3a60;font-style:italic">Awaiting incident input...</div>
        </div>""", unsafe_allow_html=True)

    # Veto log
    if res and res.get("veto_log"):
        st.markdown("""<div style="font-family:'Orbitron',monospace;font-size:8px;color:#ff8c00;
        letter-spacing:2px;margin:12px 0 6px;border-top:1px solid #0d1e36;padding-top:8px">
        ⚠ VETO LOG</div>""", unsafe_allow_html=True)
        for v in res["veto_log"]:
            st.markdown(f"""
            <div style="background:#0d0806;border:1px solid #2a1a08;
                        border-left:2px solid #ff8c00;padding:5px 8px;
                        margin-bottom:4px;border-radius:2px;
                        font-family:'Share Tech Mono',monospace;font-size:9px;color:#ff8c00">
              [{v['stage'].upper()}] {v['agent']}: {v['reason']}
            </div>""", unsafe_allow_html=True)


# ── CENTER ────────────────────────────────────────────────────────────────────
with col_center:
    st.markdown("""<div style="font-family:'Orbitron',monospace;font-size:8px;color:#2a5a8a;
    letter-spacing:3px;margin-bottom:8px;border-bottom:1px solid #0d1e36;padding-bottom:6px;
    text-align:center">ROUND TABLE — AGENT STATUS</div>""", unsafe_allow_html=True)

    if res:
        agent_states = res.get("agent_states",
            {"Fire_Bot":"idle","Police_Bot":"idle","Med_Bot":"idle","Commander":"idle"})
    else:
        agent_states = {"Fire_Bot":"idle","Police_Bot":"idle","Med_Bot":"idle","Commander":"idle"}

    components.html(build_round_table_html(agent_states), height=360, scrolling=False)

    # Conflict resolutions
    if res and res.get("conflicts"):
        st.markdown("""<div style="font-family:'Orbitron',monospace;font-size:8px;color:#ff8c00;
        letter-spacing:2px;margin:4px 0 6px;text-align:center">⚖ CONFLICT RESOLUTIONS</div>""",
        unsafe_allow_html=True)
        for c in res["conflicts"]:
            st.markdown(f"""
            <div style="background:#0d0a06;border:1px solid #2a2008;
                        border-left:2px solid #ff8c00;padding:5px 10px;
                        margin-bottom:4px;border-radius:2px;
                        font-family:'Share Tech Mono',monospace;font-size:9px;color:#a08040">
              <span style="color:#ff8c00">[{c['topic'].upper()}]</span>
              &nbsp;{c['agent_a']} vs {c['agent_b']}
              &nbsp;→&nbsp;<span style="color:#00e676">{c['winner']}</span>
            </div>""", unsafe_allow_html=True)

    # Synthesized decision
    if res:
        plan = res.get("final_plan", "—")
        st.markdown(f"""
        <div style="background:#060d18;border:1px solid #1a3a60;border-top:2px solid #4aa3ee;
                    padding:12px 42px 12px 14px;border-radius:3px;margin-top:8px;position:relative">
          <div style="font-family:'Orbitron',monospace;font-size:8px;color:#4aa3ee;
                      letter-spacing:3px;margin-bottom:7px">SYNTHESIZED DECISION</div>
          <div style="font-family:'Rajdhani',sans-serif;font-size:14px;
                      color:#c8e4ff;line-height:1.7">{plan}</div>
          <div style="position:absolute;top:12px;right:10px;width:26px;height:26px;
                      border-radius:50%;background:#00a040;border:2px solid #00e676;
                      display:flex;align-items:center;justify-content:center;
                      font-size:13px;box-shadow:0 0 10px rgba(0,230,118,0.4)">✓</div>
        </div>""", unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="background:#060d18;border:1px solid #0d1e36;border-top:2px solid #1a3a60;
                    padding:12px 14px;border-radius:3px;margin-top:8px">
          <div style="font-family:'Orbitron',monospace;font-size:8px;color:#1a3a60;
                      letter-spacing:3px;margin-bottom:6px">SYNTHESIZED DECISION</div>
          <div style="font-family:'Share Tech Mono',monospace;font-size:11px;
                      color:#1a3a60;font-style:italic">Awaiting agent consensus...</div>
        </div>""", unsafe_allow_html=True)


# ── RIGHT ─────────────────────────────────────────────────────────────────────
with col_right:
    st.markdown("""<div style="font-family:'Orbitron',monospace;font-size:8px;color:#2a5a8a;
    letter-spacing:3px;margin-bottom:10px;border-bottom:1px solid #0d1e36;padding-bottom:6px">
    RECOMMENDATIONS</div>""", unsafe_allow_html=True)

    if res and res.get("specialist_entries"):
        for e in res["specialist_entries"]:
            vetoed  = e.get("vetoed", False)
            color   = "#ff3244" if vetoed else e.get("color", "#4aa3ee")
            v_color = "#ff3244" if vetoed else "#00e676"
            verdict = "VETO" if vetoed else "OK"
            report  = e.get("report", "")

            with st.expander(f"{e['icon']} {e['name']}", expanded=False):
                st.markdown(
                    f'<div style="font-family:\'Rajdhani\',sans-serif;font-size:14px;'
                    f'color:#a0c8f0;line-height:1.7;border-left:3px solid {color};'
                    f'padding-left:10px">{report}</div>',
                    unsafe_allow_html=True,
                )
    else:
        for name, meta in _AGENT_META.items():
            st.markdown(f"""
            <div style="background:#060d1a;border:1px solid #0d1e36;
                        border-left:3px solid #1a3a60;padding:10px 12px;
                        margin-bottom:10px;border-radius:3px">
              <div style="font-family:'Orbitron',monospace;font-size:10px;
                          color:#1a3a60;letter-spacing:1px;margin-bottom:4px">
                {meta['icon']} {name}</div>
              <div style="font-family:'Share Tech Mono',monospace;font-size:10px;
                          color:#0d1e36;font-style:italic">Standby...</div>
            </div>""", unsafe_allow_html=True)

    # Urgency matrix — below agent cards
    if res and res.get("specialist_entries"):
        st.markdown("""<div style="font-family:'Orbitron',monospace;font-size:8px;color:#2a5a8a;
        letter-spacing:3px;margin:14px 0 8px;border-top:1px solid #0d1e36;padding-top:10px">
        URGENCY MATRIX</div>""", unsafe_allow_html=True)

        for e in res.get("specialist_entries", []):
            label     = e.get("urgency_label", "N/A")
            score     = e.get("urgency_score")
            color     = _URGENCY_COLOR.get(label, "#4aa3ee")
            bar_w     = int((score or 0) * 10)
            score_str = f"{score:.1f}" if score is not None else "—"
            st.markdown(f"""
            <div style="margin-bottom:9px">
              <div style="display:flex;justify-content:space-between;
                          font-family:'Share Tech Mono',monospace;font-size:10px;
                          color:#2a5a8a;margin-bottom:3px">
                <span>{e['icon']} {e['name']}</span>
                <span style="color:{color}">{label} {score_str}</span>
              </div>
              <div style="height:3px;background:#0d1e36;border-radius:2px">
                <div style="height:3px;width:{bar_w}%;background:{color};
                            box-shadow:0 0 5px {color};border-radius:2px"></div>
              </div>
            </div>""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# INCIDENT FEED — clean chat: user input + commander decision only
# chat_input MUST stay at top level (not inside columns/expanders)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<div style="border-top:1px solid #0d1e36;margin:24px 0 16px;
            font-family:'Orbitron',monospace;font-size:9px;color:#2a5a8a;
            letter-spacing:3px;padding-top:14px">
  ◈ INCIDENT FEED
</div>""", unsafe_allow_html=True)

# Render chat history — user messages + commander final_plan only
for msg in st.session_state.chat_history:
    if msg["role"] == "user":
        with st.chat_message("user"):
            st.markdown(
                f'<div style="font-family:\'Rajdhani\',sans-serif;font-size:16px;'
                f'color:#a0c8f0;line-height:1.6">{msg["content"]}</div>',
                unsafe_allow_html=True,
            )
    elif msg["role"] == "assistant":
        # Extract only the final_plan from stored last_result or parse from content
        final_plan = ""
        # Try to get clean final plan from the stored result matching this message
        content = msg.get("content", "")
        # Parse out just the FINAL_PLAN section
        if "### 🎯 Unified Command Decision" in content:
            final_plan = content.split("### 🎯 Unified Command Decision")[-1]
            # Strip any trailing specialist JSON comment
            if "<!-- SPECIALISTS:" in final_plan:
                final_plan = final_plan[:final_plan.rfind("\n\n<!-- SPECIALISTS:")]
            final_plan = final_plan.strip()
        else:
            final_plan = content
            if "<!-- SPECIALISTS:" in final_plan:
                final_plan = final_plan[:final_plan.rfind("\n\n<!-- SPECIALISTS:")]

        with st.chat_message("assistant", avatar="⚖️"):
            st.markdown(
                f'<div style="font-family:\'Orbitron\',monospace;font-size:9px;'
                f'color:#4aa3ee;letter-spacing:3px;margin-bottom:8px">'
                f'⚖️ COMMANDER DECISION</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div style="font-family:\'Rajdhani\',sans-serif;font-size:16px;'
                f'color:#c8e4ff;line-height:1.7">{final_plan}</div>',
                unsafe_allow_html=True,
            )

# chat_input at top level — always visible
if prompt := st.chat_input("Add details or describe a new development..."):
    process_event(prompt)

st.markdown(f"""
<div style="border-top:1px solid #0d1e36;margin-top:16px;padding-top:8px;
font-family:'Share Tech Mono',monospace;font-size:10px;color:#0d1e36;
display:flex;justify-content:space-between">
  <span>PARALLEL EXECUTION · CONSTITUTIONAL AI · CONSENSUS ENGINE · M4</span>
  <span>UPLOAD: 2MB MAX · {datetime.now().strftime('%H:%M:%S')}</span>
</div>""", unsafe_allow_html=True)