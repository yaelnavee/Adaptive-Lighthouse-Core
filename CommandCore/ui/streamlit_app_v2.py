"""
Adaptive Lighthouse Core — UI v6
=================================
Professional clean design: Inter font, subtle borders, no glow effects.
Same layout and 100% identical functionality to v5.
"""

import streamlit as st
import streamlit.components.v1 as components
import sys, os, json, concurrent.futures
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.agent_factory   import SpecialistFactory
from agents.commander_agent import CommanderAgent, CONSTITUTION, VETO_TRIGGERS
from llm.llm_client         import LLMClient

import re as _re
import urllib.request, urllib.parse

# ── geo helpers (identical to v5) ────────────────────────────────────────────
def _extract_location(text: str):
    candidates = []
    he_patterns = [
        r'ב([\u05d0-\u05ea][\u05d0-\u05ea\s\-]{2,25}?)(?:\s|,|\.|$)',
        r'ליד\s+([\u05d0-\u05ea][\u05d0-\u05ea\s\-]{2,25}?)(?:\s|,|\.|$)',
        r'באזור\s+([\u05d0-\u05ea][\u05d0-\u05ea\s\-]{2,25}?)(?:\s|,|\.|$)',
        r'(?:עיר|רחוב|שכונת|שוק|כביש|צומת)\s+([\u05d0-\u05ea][\u05d0-\u05ea\s\-]{2,20}?)(?:\s|,|\.|$)',
    ]
    for pat in he_patterns:
        for m in _re.finditer(pat, text):
            candidates.append(m.group(1).strip())
    he_cities = [
        "תל אביב","ירושלים","חיפה","באר שבע","ראשון לציון",
        "פתח תקווה","נתניה","אשדוד","אשקלון","רמת גן",
        "בני ברק","הרצליה","חולון","רחובות","מודיעין",
        "רעננה","כפר סבא","עכו","נצרת","טבריה",
    ]
    for city in he_cities:
        if city in text:
            candidates.insert(0, city)
    words = text.split()
    for length in (3, 2, 4):
        for i in range(len(words) - length + 1):
            chunk = " ".join(words[i:i+length])
            if _re.match(r'^[A-Z][a-zA-Z ,\-]+$', chunk):
                candidates.append(chunk)
    seen, unique = set(), []
    for c in candidates:
        if c not in seen and len(c) > 1:
            seen.add(c); unique.append(c)
    for candidate in unique[:8]:
        try:
            q   = urllib.parse.quote(candidate)
            url = f"https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=1&accept-language=he,en"
            req = urllib.request.Request(url, headers={"User-Agent":"AdaptiveLighthouseCore/1.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read())
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"]), data[0]["display_name"]
        except Exception:
            continue
    return None

def _get_weather(lat, lon):
    try:
        url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
               f"&current=temperature_2m,wind_speed_10m,weathercode,relative_humidity_2m&timezone=auto")
        req = urllib.request.Request(url, headers={"User-Agent":"AdaptiveLighthouseCore/1.0"})
        with urllib.request.urlopen(req, timeout=4) as r:
            data = json.loads(r.read())
        c    = data.get("current", {})
        code = c.get("weathercode", 0)
        if code == 0:                condition = "Clear"
        elif code in range(1,4):     condition = "Partly Cloudy"
        elif code in range(45,68):   condition = "Fog / Drizzle"
        elif code in range(61,68):   condition = "Rain"
        elif code in range(71,78):   condition = "Snow"
        elif code in range(80,83):   condition = "Showers"
        elif code in range(95,100):  condition = "Thunderstorm"
        else:                        condition = "Overcast"
        return {"temp": c.get("temperature_2m","—"), "wind": c.get("wind_speed_10m","—"),
                "humidity": c.get("relative_humidity_2m","—"), "condition": condition}
    except Exception:
        return {}

def _build_map_html(lat, lon, label):
    import folium
    m = folium.Map(location=[lat,lon], zoom_start=14, tiles="CartoDB dark_matter")
    folium.Marker([lat,lon], popup=label,
                  icon=folium.Icon(color="red", icon="exclamation-sign")).add_to(m)
    folium.Circle([lat,lon], radius=300, color="#e53935",
                  fill=True, fill_opacity=0.12, weight=2).add_to(m)
    return m._repr_html_()

# ── constants ─────────────────────────────────────────────────────────────────
MAX_UPLOAD_BYTES = 2 * 1024 * 1024

_URGENCY_COLOR = {
    "CRITICAL": "#e53935",
    "HIGH":     "#fb8c00",
    "MEDIUM":   "#fdd835",
    "LOW":      "#43a047",
    "N/A":      "#5c8ab4",
}
_AGENT_META = {
    "Fire_Bot":   {"icon":"🔥", "color":"#fb8c00"},
    "Police_Bot": {"icon":"🚔", "color":"#5c8ab4"},
    "Med_Bot":    {"icon":"🏥", "color":"#43a047"},
}

st.set_page_config(page_title="Adaptive Lighthouse Core", page_icon="🔱", layout="wide")

# ── session state ──────────────────────────────────────────────────────────────
for _k, _v in [("llm",None),("chat_history",[]),("constitution_text",CONSTITUTION),
               ("veto_triggers",dict(VETO_TRIGGERS)),("last_result",None)]:
    if _k not in st.session_state:
        st.session_state[_k] = _v if _k != "llm" else LLMClient()

# ── CSS — clean professional ───────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  --bg:        #0f1117;
  --bg2:       #161b27;
  --bg3:       #1c2333;
  --border:    #2a3550;
  --border2:   #3a4a6a;
  --text:      #f0f4fc;
  --text2:     #a8bcda;
  --text3:     #6a7a9a;
  --accent:    #4a7fe8;
  --accent2:   #2d5cbf;
  --green:     #43a047;
  --red:       #e53935;
  --amber:     #fb8c00;
}

html,body,[data-testid="stAppViewContainer"] {
  background: var(--bg) !important;
  font-family: 'Inter', sans-serif !important;
}
[data-testid="stAppViewContainer"] > .main { background: var(--bg) !important; }
[data-testid="stAppViewContainer"] > .main > .block-container {
  padding-top: 1rem !important;
}
[data-testid="stSidebar"] {
  background: var(--bg2) !important;
  border-right: 1px solid var(--border) !important;
}
#MainMenu,footer,header,[data-testid="stDecoration"] {
  visibility:hidden !important; display:none !important;
}
::-webkit-scrollbar { width:4px; background:var(--bg); }
::-webkit-scrollbar-thumb { background:var(--border2); border-radius:4px; }

/* chat input */
[data-testid="stChatInput"] textarea,
[data-testid="stChatInputContainer"] textarea,
.stChatInput textarea,
textarea {
  font-family: 'Segoe UI', Arial, sans-serif !important;
  font-size: 17px !important;
  line-height: 1.6 !important;
  color: #f0f4fc !important;
}
[data-testid="stChatInput"] textarea {
  background: var(--bg2) !important;
  border: 1px solid var(--border) !important;
  border-radius: 8px !important;
  padding: 18px 20px !important;
  min-height: 72px !important;
}
[data-testid="stChatInput"] {
  min-height: 80px !important;
}
[data-testid="stChatInputContainer"],
[data-testid="stChatInput"] > div {
  min-height: 80px !important;
}
[data-testid="stChatInput"] textarea:focus {
  border-color: var(--accent) !important;
  box-shadow: 0 0 0 3px rgba(74,127,232,0.15) !important;
}
[data-testid="stBottom"],
[data-testid="stBottom"] > div,
[data-testid="stBottom"] > div > div,
.stChatFloatingInputContainer,
.stChatInputContainer,
section[data-testid="stBottom"] {
  background: var(--bg) !important;
  background-color: var(--bg) !important;
  border-top: 1px solid var(--border) !important;
}

/* chat messages */
[data-testid="stChatMessage"] {
  background: var(--bg2) !important;
  border: 1px solid var(--border) !important;
  border-radius: 10px !important;
  margin-bottom: 10px !important;
}

/* expanders */
[data-testid="stExpander"] {
  background: var(--bg2) !important;
  border: 1px solid var(--border) !important;
  border-radius: 8px !important;
  overflow: hidden !important;
}
[data-testid="stExpander"] summary {
  color: #8a9bbf !important;
  font-family: 'Inter', sans-serif !important;
  font-weight: 600 !important;
  font-size: 16px !important;
  padding: 12px 14px !important;
}
[data-testid="stExpander"] summary:hover {
  background: var(--bg3) !important;
}
[data-testid="stExpander"] summary p,
[data-testid="stExpander"] summary span {
  color: #8a9bbf !important;
  font-size: 16px !important;
  font-weight: 600 !important;
}

/* buttons */
.stButton > button {
  background: var(--bg3) !important;
  border: 1px solid var(--border) !important;
  color: var(--text) !important;
  font-family: 'Inter', sans-serif !important;
  font-weight: 600 !important;
  font-size:14px !important;
  border-radius: 6px !important;
  transition: all 0.15s !important;
}
.stButton > button:hover {
  border-color: var(--accent) !important;
  background: var(--bg2) !important;
}

textarea {
  background: var(--bg2) !important;
  border: 1px solid var(--border) !important;
  color: var(--text) !important;
  font-family: 'JetBrains Mono', monospace !important;
  font-size:13px !important;
  border-radius: 6px !important;
}

.stMarkdown p, .stMarkdown li {
  color: var(--text) !important;
  font-family: 'Inter', sans-serif !important;
  font-size:16px !important;
  line-height: 1.7 !important;
}
.stMarkdown strong { color: #ffffff !important; font-size:16px !important; }
.stMarkdown code {
  background: var(--bg3) !important;
  color: var(--accent) !important;
  border: 1px solid var(--border) !important;
  border-radius: 4px !important;
  font-family: 'JetBrains Mono', monospace !important;
}
hr { border-color: var(--border) !important; }
.stCaption { color: var(--text3) !important; font-size:13px !important; }

/* sidebar close X and collapse arrow */
[data-testid="stSidebarCollapseButton"] button,
[data-testid="stSidebarContent"] button[kind="header"],
button[aria-label="Close sidebar"],
[data-testid="stBaseButton-headerNoPadding"] {
  color: var(--text) !important;
  opacity: 1 !important;
}
[data-testid="stSidebarCollapseButton"] svg,
[data-testid="stSidebarContent"] button svg,
button[aria-label="Close sidebar"] svg {
  width: 22px !important;
  height: 22px !important;
  color: var(--text2) !important;
  stroke: var(--text2) !important;
  fill: var(--text2) !important;
}
[data-testid="stSidebarCollapseButton"] button:hover svg,
button[aria-label="Close sidebar"]:hover svg {
  color: var(--text) !important;
  stroke: var(--text) !important;
}

[data-testid="stSuccess"] {
  background: rgba(67,160,71,0.1) !important;
  border: 1px solid rgba(67,160,71,0.3) !important;
  border-radius: 6px !important;
}
[data-testid="stError"] {
  background: rgba(229,57,53,0.1) !important;
  border: 1px solid rgba(229,57,53,0.3) !important;
  border-radius: 6px !important;
}

/* section headers */
.sec-header {
  font-family: 'Inter', sans-serif;
  font-size:13px;
  font-weight: 700;
  color: var(--text2);
  letter-spacing: 1.5px;
  text-transform: uppercase;
  padding-bottom: 8px;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--border);
}

/* card */
.pro-card {
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 16px;
  margin-bottom: 10px;
}

/* badge */
.badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-family: 'JetBrains Mono', monospace;
  font-size:11px;
  font-weight: 700;
  letter-spacing: 0.5px;
}

/* ── file uploader — aggressive dark override ── */
[data-testid="stFileUploader"],
[data-testid="stFileUploader"] > div,
[data-testid="stFileUploader"] section,
[data-testid="stFileUploaderDropzone"],
[data-testid="stFileUploaderDropzone"] > div,
[data-testid="stFileUploaderDropzone"] > div > div {
  background: var(--bg2) !important;
  background-color: var(--bg2) !important;
  border-color: var(--border2) !important;
  border-radius: 8px !important;
  color: var(--text2) !important;
}
[data-testid="stFileUploader"] section {
  border: 1px dashed var(--border2) !important;
}
[data-testid="stFileUploader"] section:hover {
  border-color: var(--accent) !important;
}
/* all text inside uploader */
[data-testid="stFileUploader"] span,
[data-testid="stFileUploader"] p,
[data-testid="stFileUploader"] small,
[data-testid="stFileUploader"] div {
  color: var(--text2) !important;
  background: transparent !important;
  font-family: 'Inter', sans-serif !important;
}
/* Browse files button */
[data-testid="stFileUploader"] button[kind="secondary"],
[data-testid="stFileUploader"] button {
  background: var(--bg3) !important;
  background-color: var(--bg3) !important;
  border: 1px solid var(--border2) !important;
  color: var(--text) !important;
  font-family: 'Inter', sans-serif !important;
  font-size:14px !important;
  font-weight: 500 !important;
  border-radius: 6px !important;
}
[data-testid="stFileUploader"] button:hover {
  border-color: var(--accent) !important;
  background: var(--bg2) !important;
}
/* uploaded file chip */
[data-testid="stFileUploaderFile"],
[data-testid="stFileUploaderFile"] > div {
  background: var(--bg3) !important;
  border: 1px solid var(--border) !important;
  border-radius: 6px !important;
}
[data-testid="stFileUploaderDeleteBtn"] button {
  background: transparent !important;
  border: none !important;
  color: var(--text3) !important;
}
[data-testid="stFileUploaderDeleteBtn"] button:hover {
  color: var(--red) !important;
}
</style>
""", unsafe_allow_html=True)


# ── round-table HTML (identical logic, clean visual style) ────────────────────
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
body{{background:#0f1117;font-family:'Inter',sans-serif;overflow:hidden;}}
#wrap{{position:relative;width:100%;height:320px;}}
#rt-canvas{{position:absolute;inset:0;width:100%;height:100%;}}
#rt-svg{{position:absolute;inset:0;width:100%;height:100%;pointer-events:none;}}

.rt-agent{{
  position:absolute;display:flex;flex-direction:column;
  align-items:center;transform:translate(-50%,-50%);z-index:10;
}}
.rt-circle{{
  width:72px;height:72px;border-radius:50%;
  background:#1c2333;
  border:2px solid #2a3550;
  display:flex;flex-direction:column;
  align-items:center;justify-content:center;
  transition:all 0.3s;position:relative;
}}
.rt-circle.processing{{
  border-color:#4a7fe8;
  background:#1a2540;
  box-shadow:0 0 0 4px rgba(74,127,232,0.2),0 0 20px rgba(74,127,232,0.3);
  animation:processPulse 1.6s ease-in-out infinite;
}}
.rt-circle.approved{{
  border-color:#43a047;
  background:#1a2a1c;
  box-shadow:0 0 0 3px rgba(67,160,71,0.2);
}}
.rt-circle.vetoed{{
  border-color:#e53935;
  background:#2a1a1a;
  box-shadow:0 0 0 3px rgba(229,57,53,0.2);
}}
@keyframes processPulse{{
  0%,100%{{box-shadow:0 0 0 4px rgba(74,127,232,0.2),0 0 20px rgba(74,127,232,0.25);}}
  50%{{box-shadow:0 0 0 8px rgba(74,127,232,0.08),0 0 30px rgba(74,127,232,0.4);}}
}}
.speak-ring{{
  position:absolute;border-radius:50%;
  border:1.5px solid rgba(74,127,232,0.5);
  animation:expandRing 1.6s ease-out infinite;pointer-events:none;
}}
@keyframes expandRing{{
  0%{{transform:scale(1);opacity:0.7;}}
  100%{{transform:scale(1.9);opacity:0;}}
}}
.rt-icon{{font-size:24px;line-height:1;}}
.rt-sub{{font-size:9px;font-weight:700;color:rgba(255,255,255,0.6);
         letter-spacing:1px;text-transform:uppercase;margin-top:2px;}}
.rt-name{{margin-top:7px;font-size:13px;font-weight:600;
          color:#8aaccc;text-align:center;letter-spacing:0.5px;}}
.rt-status{{font-size:11px;margin-top:3px;text-align:center;
            height:14px;font-family:'JetBrains Mono',monospace;color:#fb8c00;}}

.rt-commander .rt-circle{{
  width:86px;height:86px;
  background:#1a2540;border:2px solid #4a7fe8;
  box-shadow:0 0 0 5px rgba(74,127,232,0.12);
}}
.rt-commander .rt-icon{{font-size:30px;}}
.rt-commander .rt-name{{color:#6a9fe8;font-size:14px;font-weight:700;}}
.rt-commander .rt-circle.processing{{animation:cmdPulse 1.4s ease-in-out infinite;}}
.rt-commander .rt-circle.approved{{
  border-color:#4a7fe8 !important;
  background:#1a2540 !important;
  box-shadow:0 0 0 5px rgba(74,127,232,0.12) !important;
}}
@keyframes cmdPulse{{
  0%,100%{{box-shadow:0 0 0 5px rgba(74,127,232,0.15),0 0 25px rgba(74,127,232,0.3);}}
  50%{{box-shadow:0 0 0 10px rgba(74,127,232,0.05),0 0 40px rgba(74,127,232,0.45);}}
}}
</style>
</head>
<body>
<div id="wrap">
  <canvas id="rt-canvas"></canvas>
  <svg id="rt-svg" xmlns="http://www.w3.org/2000/svg"></svg>

  <div class="rt-agent rt-commander" id="ag-commander" style="left:50%;top:60%">
    <div class="rt-circle" id="circ-commander">
      <div class="speak-ring" id="ring-commander" style="width:86px;height:86px;display:none"></div>
      <div class="rt-icon">⚖️</div>
      <div class="rt-sub">CMD</div>
    </div>
    <div class="rt-name">Commander</div>
    <div class="rt-status" id="st-commander"></div>
  </div>

  <div class="rt-agent" id="ag-fire" style="left:50%;top:22%">
    <div class="rt-circle" id="circ-fire">
      <div class="speak-ring" id="ring-fire" style="width:72px;height:72px;display:none"></div>
      <div class="rt-icon">🔥</div>
      <div class="rt-sub">FIRE</div>
    </div>
    <div class="rt-name">Fire_Bot</div>
    <div class="rt-status" id="st-fire"></div>
  </div>

  <div class="rt-agent" id="ag-police" style="left:16%;top:87%">
    <div class="rt-circle" id="circ-police">
      <div class="speak-ring" id="ring-police" style="width:72px;height:72px;display:none"></div>
      <div class="rt-icon">🚔</div>
      <div class="rt-sub">POLICE</div>
    </div>
    <div class="rt-name">Police_Bot</div>
    <div class="rt-status" id="st-police"></div>
  </div>

  <div class="rt-agent" id="ag-med" style="left:84%;top:87%">
    <div class="rt-circle" id="circ-med">
      <div class="speak-ring" id="ring-med" style="width:72px;height:72px;display:none"></div>
      <div class="rt-icon">🏥</div>
      <div class="rt-sub">MED</div>
    </div>
    <div class="rt-name">Med_Bot</div>
    <div class="rt-status" id="st-med"></div>
  </div>
</div>
<script>
const AGENTS=['fire','police','med'];
const ALL=['commander','fire','police','med'];
const STATES={{
  fire:"{fire_s}", police:"{police_s}",
  med:"{med_s}", commander:"{cmd_s}"
}};

function getPos(id){{
  const el=document.getElementById('ag-'+id);
  const wrap=document.getElementById('wrap');
  if(!el||!wrap) return {{x:0,y:0}};
  const wr=wrap.getBoundingClientRect();
  const er=el.getBoundingClientRect();
  return{{x:er.left+er.width/2-wr.left,y:er.top+er.height/2-wr.top}};
}}

function drawBg(){{
  const cv=document.getElementById('rt-canvas');
  const wrap=document.getElementById('wrap');
  cv.width=wrap.offsetWidth; cv.height=wrap.offsetHeight;
  const ctx=cv.getContext('2d');
  const W=cv.width,H=cv.height,cx=W/2,cy=H/2;
  ctx.clearRect(0,0,W,H);
  ctx.beginPath(); ctx.arc(cx,cy,Math.min(W,H)*0.38,0,Math.PI*2);
  ctx.strokeStyle='rgba(74,127,232,0.18)';
  ctx.lineWidth=1.5; ctx.setLineDash([4,6]); ctx.stroke(); ctx.setLineDash([]);
}}

function clearSvg(){{
  const svg=document.getElementById('rt-svg');
  while(svg.firstChild) svg.removeChild(svg.firstChild);
}}

function drawLines(){{
  clearSvg();
  const svg=document.getElementById('rt-svg');
  const defs=document.createElementNS('http://www.w3.org/2000/svg','defs');
  function mkMarker(mid,col){{
    const mk=document.createElementNS('http://www.w3.org/2000/svg','marker');
    mk.setAttribute('id',mid); mk.setAttribute('viewBox','0 0 10 10');
    mk.setAttribute('refX','8'); mk.setAttribute('refY','5');
    mk.setAttribute('markerWidth','5'); mk.setAttribute('markerHeight','5');
    mk.setAttribute('orient','auto-start-reverse');
    const p=document.createElementNS('http://www.w3.org/2000/svg','path');
    p.setAttribute('d','M2 1L8 5L2 9'); p.setAttribute('fill','none');
    p.setAttribute('stroke',col); p.setAttribute('stroke-width','1.5');
    mk.appendChild(p); defs.appendChild(mk);
  }}
  mkMarker('mIdle','#2a3550'); mkMarker('mActive','#4a7fe8');
  mkMarker('mOk','#43a047'); mkMarker('mVeto','#e53935');
  svg.appendChild(defs);
  const cmd=getPos('commander');
  AGENTS.forEach(id=>{{
    const ag=getPos(id); const s=STATES[id];
    const dx=ag.x-cmd.x,dy=ag.y-cmd.y;
    const dist=Math.sqrt(dx*dx+dy*dy);
    const r1=43,r2=37;
    const x1=cmd.x+dx/dist*r1,y1=cmd.y+dy/dist*r1;
    const x2=ag.x-dx/dist*r2,y2=ag.y-dy/dist*r2;
    let stroke='#3a4a6a',marker='mIdle',sw='1.5',opacity='0.6',dash='4 5';
    if(s==='processing'){{stroke='#4a7fe8';marker='mActive';sw='2.5';opacity='0.95';dash='6 4';}}
    else if(s==='approved'){{stroke='#43a047';marker='mOk';sw='2';opacity='0.8';dash='none';}}
    else if(s==='vetoed'){{stroke='#e53935';marker='mVeto';sw='2';opacity='0.8';dash='none';}}
    const line=document.createElementNS('http://www.w3.org/2000/svg','line');
    line.setAttribute('x1',x1); line.setAttribute('y1',y1);
    line.setAttribute('x2',x2); line.setAttribute('y2',y2);
    line.setAttribute('stroke',stroke); line.setAttribute('stroke-width',sw);
    line.setAttribute('stroke-dasharray',dash); line.setAttribute('opacity',opacity);
    line.setAttribute('marker-end','url(#'+marker+')');
    line.setAttribute('marker-start','url(#'+marker+')');
    if(s==='processing'){{
      const len=Math.sqrt((x2-x1)**2+(y2-y1)**2);
      const a=document.createElementNS('http://www.w3.org/2000/svg','animate');
      a.setAttribute('attributeName','stroke-dashoffset');
      a.setAttribute('from','0'); a.setAttribute('to',String(-len));
      a.setAttribute('dur','0.8s'); a.setAttribute('repeatCount','indefinite');
      line.appendChild(a);
    }}
    svg.appendChild(line);
  }});
}}

function applyStates(){{
  ALL.forEach(id=>{{
    const s=STATES[id];
    const circ=document.getElementById('circ-'+id);
    const ring=document.getElementById('ring-'+id);
    const st=document.getElementById('st-'+id);
    if(!circ) return;
    circ.classList.remove('processing','approved','vetoed');
    if(ring) ring.style.display='none';
    if(s==='processing'){{
      circ.classList.add('processing');
      if(ring) ring.style.display='block';
      if(st) st.textContent='Analyzing...';
    }} else if(s==='approved'){{
      circ.classList.add('approved');
      if(st) st.textContent='\u2713 Approved';
    }} else if(s==='vetoed'){{
      circ.classList.add('vetoed');
      if(st) st.textContent='\u2717 Vetoed';
    }} else {{
      if(st) st.textContent='';
    }}
  }});
}}

window.addEventListener('load',()=>{{drawBg();drawLines();applyStates();}});
window.addEventListener('resize',()=>{{drawBg();drawLines();}});
</script>
</body>
</html>"""


# ── helpers ───────────────────────────────────────────────────────────────────
def _run_agent(agent_type, prompt, history_context, llm_client):
    agent    = SpecialistFactory.create(agent_type, llm_client)
    response = agent.analyze(prompt, previous_findings=history_context)
    return {"name": agent.name, "response": response, "type": agent_type}


# ── process_event — 100% original logic ──────────────────────────────────────
def process_event(event_text: str):
    st.session_state.chat_history.append({"role": "user", "content": event_text})
    history_context = "\n".join(
        f"{m['role']}: {m['content']}" for m in st.session_state.chat_history[:-1])
    agent_types = ["fire", "police", "medical"]
    llm = st.session_state.llm

    agent_reports: dict = {}
    with st.spinner("Specialists analysing in parallel…"):
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = {executor.submit(_run_agent, at, event_text, history_context, llm): at
                       for at in agent_types}
            for future in concurrent.futures.as_completed(futures):
                r = future.result()
                agent_reports[r["name"]] = r["response"]

    commander = CommanderAgent(llm)
    import agents.commander_agent as _ca
    orig_c, orig_t = _ca.CONSTITUTION, _ca.VETO_TRIGGERS
    _ca.CONSTITUTION  = st.session_state.constitution_text
    _ca.VETO_TRIGGERS = st.session_state.veto_triggers
    with st.spinner("Commander synthesising decision…"):
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
        rev     = reviews.get(agent_name, {})
        vetoed  = rev.get("vetoed", False)
        urgency = urgency_scores.get(agent_name)
        meta    = _AGENT_META.get(agent_name, {"icon":"🤖","color":"#5c8ab4"})
        specialist_entries.append({
            "name": agent_name, "icon": meta["icon"], "color": meta["color"],
            "vetoed": vetoed, "reason": rev.get("reason",""),
            "report": report_text,
            "urgency_label": urgency.label if urgency else "N/A",
            "urgency_score": urgency.score if urgency else None,
        })

    agent_states = {"Commander": "approved"}
    for e in specialist_entries:
        agent_states[e["name"]] = "vetoed" if e["vetoed"] else "approved"

    conflicts_list = [
        {"topic":c.topic,"agent_a":c.agent_a,"stance_a":c.stance_a,
         "agent_b":c.agent_b,"stance_b":c.stance_b,
         "winner":c.winner,"resolution_reason":c.resolution_reason}
        for c in conflicts]

    status_lines = [
        f"- {e['icon']} **{e['name']}**: {'🔴 VETO' if e['vetoed'] else '✅ APPROVED'}"
        + (f" — {e['reason']}" if e["reason"] else "")
        for e in specialist_entries]
    veto_section = ("\n\n**📋 Veto Audit Log:**\n" + "\n".join(
        f"  - [{v['stage'].upper()}] **{v['agent']}**: {v['reason']}" for v in veto_log)
        if veto_log else "")
    conflicts_section = ("\n\n**⚖️ Conflict Resolutions:**\n" + "\n".join(
        f"  - **[{c.topic.upper()}]** `{c.agent_a}` ({c.stance_a}) vs "
        f"`{c.agent_b}` ({c.stance_b}) → ✅ **{c.winner}** — _{c.resolution_reason}_"
        for c in conflicts) if conflicts else "")

    content = (
        "### 🎖️ Commander Review\n" + "\n".join(status_lines)
        + veto_section + conflicts_section
        + f"\n\n---\n### 🎯 Unified Command Decision\n{final_plan}"
        + f"\n\n<!-- SPECIALISTS:{json.dumps(specialist_entries)} -->")

    geo = _extract_location(event_text)
    st.session_state.last_result = {
        "event_text": event_text, "specialist_entries": specialist_entries,
        "final_plan": final_plan, "veto_log": veto_log,
        "conflicts": conflicts_list, "agent_states": agent_states,
        "urgency_scores": {k:{"label":v.label,"score":v.score} for k,v in urgency_scores.items()},
        "geo": geo,
        "weather": _get_weather(geo[0], geo[1]) if geo else {},
    }
    st.session_state.chat_history.append({
        "role":"assistant","content":content,"avatar":"⚖️",
        "specialists":specialist_entries,"agent_states":agent_states,"conflicts":conflicts_list,
    })
    st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("""<div style="font-family:'Inter',sans-serif;font-size:16px;font-weight:700;
    color:#f0f4fc;padding:12px 0 8px;border-bottom:1px solid #2a3550;margin-bottom:16px;
    letter-spacing:0.5px">🔱 Control Panel</div>""", unsafe_allow_html=True)

    if st.button("＋ New Incident", use_container_width=True):
        st.session_state.chat_history = []
        st.session_state.last_result  = None
        st.rerun()

    st.markdown("<hr style='border-color:#2a3550;margin:12px 0'>", unsafe_allow_html=True)

    with st.expander("⚖️ Constitution Editor"):
        st.caption("Keep RULE N: prefix. Changes apply to next event.")
        edited = st.text_area("const", value=st.session_state.constitution_text,
                              height=240, label_visibility="collapsed")
        if edited != st.session_state.constitution_text:
            st.session_state.constitution_text = edited
            st.success("Updated.")

    with st.expander("🔍 Veto Triggers"):
        st.caption("JSON: phrase → rule label.")
        edited_t = st.text_area("trig", value=json.dumps(st.session_state.veto_triggers, indent=2),
                                height=200, label_visibility="collapsed")
        if st.button("Save Triggers", use_container_width=True):
            try:
                st.session_state.veto_triggers = json.loads(edited_t)
                st.success("Saved.")
            except json.JSONDecodeError as exc:
                st.error(f"Invalid JSON: {exc}")

    st.markdown("<hr style='border-color:#2a3550;margin:12px 0'>", unsafe_allow_html=True)
    st.markdown("""<div style="font-family:'Inter',sans-serif;font-size:14px;font-weight:600;
    color:#a8bcda;margin-bottom:8px">📁 Upload Field Report</div>""", unsafe_allow_html=True)
    st.caption("Accepted: .txt / .md — max 2 MB")
    uploaded = st.file_uploader("Upload", type=["txt","md"], label_visibility="collapsed")
    if uploaded:
        fb = uploaded.read()
        if len(fb) > MAX_UPLOAD_BYTES:
            st.error(f"File too large ({len(fb)/1024/1024:.1f} MB). Max 2 MB.")
        else:
            fc = fb.decode("utf-8", errors="replace")
            if st.button("Process Report", use_container_width=True):
                process_event(f"📄 **FIELD REPORT:**\n\n{fc}")

    st.markdown("<hr style='border-color:#2a3550;margin:12px 0'>", unsafe_allow_html=True)
    st.markdown("""<div style="font-family:'Inter',sans-serif;font-size:14px;
    color:#6a7a9a;line-height:2">🔴 Critical &nbsp; 🟠 High<br>🟡 Medium &nbsp; 🟢 Low</div>""",
    unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════════
res = st.session_state.last_result

st.markdown(f"""
<div style="display:flex;align-items:center;justify-content:space-between;
            padding:14px 0 14px;border-bottom:1px solid #2a3550;margin-bottom:20px">
  <div style="display:flex;align-items:center;gap:14px">
    <div style="width:42px;height:42px;border-radius:10px;
                background:#1c2333;border:1px solid #3a4a6a;
                display:flex;align-items:center;justify-content:center;font-size:20px">🔱</div>
    <div>
      <div style="font-family:'Inter',sans-serif;font-size:22px;font-weight:700;
                  color:#f0f4fc;letter-spacing:-0.3px">Adaptive Lighthouse</div>
      <div style="font-family:'Inter',sans-serif;font-size:14px;color:#7a9abf;font-weight:500">
        Round Table — Real Time</div>
    </div>
  </div>
  <div style="display:flex;align-items:center;gap:20px">
    <div style="font-family:'Inter',sans-serif;font-size:14px;color:#a8bcda">
      System Status: <span style="color:#43a047;font-weight:700">ACTIVE</span></div>
    <div style="font-family:'JetBrains Mono',monospace;font-size:13px;color:#6a7a9a">
      {datetime.now().strftime('%H:%M:%S')}</div>
  </div>
</div>""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD — 3 columns
# ══════════════════════════════════════════════════════════════════════════════
col_left, col_center, col_right = st.columns([1, 1.55, 1], gap="large")

# ── LEFT ──────────────────────────────────────────────────────────────────────
with col_left:
    st.markdown('<div class="sec-header">Event Summary</div>', unsafe_allow_html=True)

    if res:
        event_text   = res.get("event_text","—")
        severity     = "HIGH" if any(w in event_text.lower() for w in
                       ["fire","collapse","explosion","trapped","critical","flood","hazmat"]) else "MEDIUM"
        sev_color    = "#e53935" if severity == "HIGH" else "#fdd835"
        geo          = res.get("geo")
        weather      = res.get("weather", {})
        location_str = geo[2].split(",")[0] if geo else "Unknown"

        # event info card
        st.markdown(f"""
        <div class="pro-card" style="border-left:3px solid #4a7fe8">
          <div style="font-family:'JetBrains Mono',monospace;font-size:13px;
                      color:#a8bcda;line-height:2">
            <div><span style="color:#6a7a9a">Type</span>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;Incident</div>
            <div><span style="color:#6a7a9a">Location</span>&nbsp;{location_str}</div>
            <div><span style="color:#6a7a9a">Time</span>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{datetime.now().strftime('%H:%M')}</div>
            <div><span style="color:#6a7a9a">Severity</span>&nbsp;
              <span style="color:{sev_color};font-weight:700">{severity}</span></div>
          </div>
          <div style="margin-top:10px;font-family:'Inter',sans-serif;font-size:15px;
                      color:#d0e0f8;line-height:1.7;border-top:1px solid #2a3550;padding-top:8px">
            {event_text[:160]}{'…' if len(event_text)>160 else ''}
          </div>
        </div>""", unsafe_allow_html=True)

        # map
        if geo:
            lat, lon, place = geo
            try:
                components.html(_build_map_html(lat, lon, place), height=175, scrolling=False)
            except Exception:
                st.markdown("""<div class="pro-card" style="height:60px;display:flex;
                align-items:center;justify-content:center;color:#4a5a7a;font-size:13px">
                Map unavailable</div>""", unsafe_allow_html=True)
        else:
            st.markdown("""<div class="pro-card" style="height:60px;display:flex;
            align-items:center;justify-content:center">
            <span style="color:#4a5a7a;font-size:13px;font-family:'Inter',sans-serif">
            📍 No location detected</span></div>""", unsafe_allow_html=True)

        # weather
        if weather:
            st.markdown('<div class="sec-header" style="margin-top:14px">Live Conditions</div>',
                        unsafe_allow_html=True)
            st.markdown(f"""
            <div class="pro-card">
              <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
                <div>
                  <div style="font-family:'Inter',sans-serif;font-size:12px;
                              color:#6a7a9a;text-transform:uppercase;
                              letter-spacing:1px;margin-bottom:3px">Condition</div>
                  <div style="font-family:'Inter',sans-serif;font-size:15px;
                              font-weight:600;color:#f0f4fc">{weather.get('condition','—')}</div>
                </div>
                <div>
                  <div style="font-family:'Inter',sans-serif;font-size:12px;
                              color:#6a7a9a;text-transform:uppercase;
                              letter-spacing:1px;margin-bottom:3px">Temperature</div>
                  <div style="font-family:'Inter',sans-serif;font-size:15px;
                              font-weight:600;color:#f0f4fc">{weather.get('temp','—')} °C</div>
                </div>
                <div>
                  <div style="font-family:'Inter',sans-serif;font-size:12px;
                              color:#6a7a9a;text-transform:uppercase;
                              letter-spacing:1px;margin-bottom:3px">Wind</div>
                  <div style="font-family:'Inter',sans-serif;font-size:15px;
                              font-weight:600;color:#f0f4fc">{weather.get('wind','—')} km/h</div>
                </div>
                <div>
                  <div style="font-family:'Inter',sans-serif;font-size:12px;
                              color:#6a7a9a;text-transform:uppercase;
                              letter-spacing:1px;margin-bottom:3px">Humidity</div>
                  <div style="font-family:'Inter',sans-serif;font-size:15px;
                              font-weight:600;color:#f0f4fc">{weather.get('humidity','—')} %</div>
                </div>
              </div>
            </div>""", unsafe_allow_html=True)

        # veto log
        if res.get("veto_log"):
            st.markdown('<div class="sec-header" style="margin-top:14px;color:#fb8c00">Veto Log</div>',
                        unsafe_allow_html=True)
            for v in res["veto_log"]:
                st.markdown(f"""
                <div style="background:#1c1810;border:1px solid #3a2a10;border-left:3px solid #fb8c00;
                            padding:8px 12px;margin-bottom:6px;border-radius:6px;
                            font-family:'JetBrains Mono',monospace;font-size:11px;color:#fb8c00">
                  [{v['stage'].upper()}] {v['agent']}: {v['reason']}
                </div>""", unsafe_allow_html=True)
    else:
        st.markdown("""<div class="pro-card">
        <div style="font-family:'Inter',sans-serif;font-size:15px;color:#6a7a9a;
                    font-style:italic">Awaiting incident input…</div>
        </div>""", unsafe_allow_html=True)


# ── CENTER ────────────────────────────────────────────────────────────────────
with col_center:
    st.markdown('<div class="sec-header">Round Table — Agent Status</div>',
                unsafe_allow_html=True)

    agent_states = (res.get("agent_states",
        {"Fire_Bot":"idle","Police_Bot":"idle","Med_Bot":"idle","Commander":"idle"})
        if res else {"Fire_Bot":"idle","Police_Bot":"idle","Med_Bot":"idle","Commander":"idle"})

    components.html(build_round_table_html(agent_states), height=340, scrolling=False)

    # conflicts
    if res and res.get("conflicts"):
        st.markdown('<div class="sec-header" style="color:#fb8c00">Conflict Resolutions</div>',
                    unsafe_allow_html=True)
        for c in res["conflicts"]:
            st.markdown(f"""
            <div style="background:#1c1810;border:1px solid #3a2a10;border-left:3px solid #fb8c00;
                        padding:8px 12px;margin-bottom:6px;border-radius:6px;
                        font-family:'Inter',sans-serif;font-size:13px;color:#c8a060">
              <span style="color:#fb8c00;font-weight:600">[{c['topic'].upper()}]</span>
              &nbsp;{c['agent_a']} vs {c['agent_b']}
              &nbsp;→&nbsp;<span style="color:#43a047;font-weight:600">{c['winner']}</span>
            </div>""", unsafe_allow_html=True)

    # synthesized decision
    if res:
        plan = res.get("final_plan","—")
        components.html(f"""
        <style>
          * {{ box-sizing:border-box; }}
          body {{ margin:0; padding:0; background:transparent;
                 font-family:'Inter','Segoe UI',Arial,sans-serif; }}
          .card {{
            background:#141c2e; border:1px solid #2a3a5a;
            border-top:2px solid #4a7fe8; border-radius:10px;
            padding:14px 48px 14px 16px; position:relative;
          }}
          .title {{
            font-size:12px; font-weight:700; color:#5c7aaa;
            text-transform:uppercase; letter-spacing:1.5px; margin-bottom:10px;
          }}
          .check {{
            position:absolute; top:12px; right:12px;
            width:28px; height:28px; border-radius:50%;
            background:#2e7d32; border:2px solid #43a047;
            display:flex; align-items:center; justify-content:center;
            font-size:14px; color:#fff;
          }}
          #text {{
            font-size:16px; color:#f0f4fc; line-height:1.75;
            max-height:calc(1.75em * 10); overflow-y:auto; padding-right:6px;
          }}
          #text::-webkit-scrollbar {{ width:4px; background:transparent; }}
          #text::-webkit-scrollbar-thumb {{ background:#3a4a6a; border-radius:2px; }}
        </style>
        <div class="card">
          <div class="title">Synthesized Decision</div>
          <div class="check">✓</div>
          <div id="text">{plan}</div>
        </div>
        """, height=310, scrolling=False)
    else:
        st.markdown("""
        <div style="background:#141c2e;border:1px solid #2a3550;border-top:2px solid #2a3a5a;
                    padding:16px;border-radius:10px;margin-top:10px">
          <div style="font-family:'Inter',sans-serif;font-size:13px;font-weight:700;
                      color:#4a5a7a;text-transform:uppercase;letter-spacing:1.5px;
                      margin-bottom:8px">Synthesized Decision</div>
          <div style="font-family:'Inter',sans-serif;font-size:15px;
                      color:#6a7a9a;font-style:italic">Awaiting agent consensus…</div>
        </div>""", unsafe_allow_html=True)


# ── RIGHT ─────────────────────────────────────────────────────────────────────
with col_right:
    st.markdown('<div class="sec-header">Recommendations</div>', unsafe_allow_html=True)

    # Agent cards — pro-card style always, expander only when report exists
    agents_to_show = res["specialist_entries"] if (res and res.get("specialist_entries")) else [
        {"name": name, "icon": meta["icon"], "color": meta["color"],
         "vetoed": False, "report": "", "urgency_label": "N/A", "urgency_score": None}
        for name, meta in _AGENT_META.items()
    ]
    for e in agents_to_show:
        vetoed  = e.get("vetoed", False)
        color   = "#e53935" if vetoed else e.get("color","#5c8ab4")
        report  = e.get("report","")
        if report:
            with st.expander(f"{e['icon']}  {e['name']}", expanded=False):
                v_color = "#e53935" if vetoed else "#43a047"
                verdict = "VETO" if vetoed else "OK"
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">' +
                    f'<span style="font-family:\'Inter\',sans-serif;font-size:11px;' +
                    f'font-weight:700;color:{v_color};background:rgba(0,0,0,0.2);' +
                    f'border:1px solid {v_color};padding:2px 8px;border-radius:4px">{verdict}</span>' +
                    f'</div>' +
                    f'<div style="font-family:\'Inter\',sans-serif;font-size:15px;' +
                    f'color:#d0e0f8;line-height:1.7;border-left:2px solid {color};' +
                    f'padding-left:10px">{report}</div>',
                    unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div class="pro-card">
              <div style="font-family:'Inter',sans-serif;font-size:15px;
                          font-weight:600;color:#6a7a9a;margin-bottom:4px">
                {e['icon']} {e['name']}</div>
              <div style="font-family:'Inter',sans-serif;font-size:14px;
                          color:#4a5a7a">Standby</div>
            </div>""", unsafe_allow_html=True)

    # urgency matrix — only when results exist
    if res and res.get("specialist_entries"):
        st.markdown('<div class="sec-header" style="margin-top:16px">Urgency Matrix</div>',
                    unsafe_allow_html=True)
        for e in res["specialist_entries"]:
            label     = e.get("urgency_label","N/A")
            score     = e.get("urgency_score")
            color     = _URGENCY_COLOR.get(label,"#5c8ab4")
            bar_w     = int((score or 0)*10)
            score_str = f"{score:.1f}" if score is not None else "—"
            st.markdown(f"""
            <div style="margin-bottom:10px">
              <div style="display:flex;justify-content:space-between;margin-bottom:4px;
                          font-family:'Inter',sans-serif;font-size:14px">
                <span style="color:#a8bcda">{e['icon']} {e['name']}</span>
                <span style="color:{color};font-weight:600">{label} {score_str}</span>
              </div>
              <div style="height:4px;background:#1c2333;border-radius:2px">
                <div style="height:4px;width:{bar_w}%;background:{color};
                            border-radius:2px"></div>
              </div>
            </div>""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# INCIDENT FEED
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("""
<div style="border-top:1px solid #2a3550;margin:24px 0 16px;padding-top:14px;
            font-family:'Inter',sans-serif;font-size:12px;font-weight:700;
            color:#8a9bbf;text-transform:uppercase;letter-spacing:1.5px">
  Incident Feed
</div>""", unsafe_allow_html=True)

for msg in st.session_state.chat_history:
    if msg["role"] == "user":
        with st.chat_message("user"):
            st.markdown(f'<div style="font-family:\'Inter\',sans-serif;font-size:16px;'
                        f'color:#f0f4fc;line-height:1.6">{msg["content"]}</div>',
                        unsafe_allow_html=True)
    elif msg["role"] == "assistant":
        final_plan = ""
        content = msg.get("content","")
        if "### 🎯 Unified Command Decision" in content:
            final_plan = content.split("### 🎯 Unified Command Decision")[-1]
            if "<!-- SPECIALISTS:" in final_plan:
                final_plan = final_plan[:final_plan.rfind("\n\n<!-- SPECIALISTS:")]
            final_plan = final_plan.strip()
        else:
            final_plan = content
            if "<!-- SPECIALISTS:" in final_plan:
                final_plan = final_plan[:final_plan.rfind("\n\n<!-- SPECIALISTS:")]

        with st.chat_message("assistant", avatar="⚖️"):
            st.markdown(
                f'<div style="font-family:\'Inter\',sans-serif;font-size:11px;font-weight:700;'
                f'color:#5c7aaa;text-transform:uppercase;letter-spacing:1.5px;margin-bottom:8px">'
                f'Commander Decision</div>'
                f'<div style="font-family:\'Inter\',sans-serif;font-size:16px;'
                f'color:#f0f4fc;line-height:1.7">{final_plan}</div>',
                unsafe_allow_html=True)

# chat_input must be at top level
if prompt := st.chat_input("Describe the incident or add details…"):
    process_event(prompt)

# Late CSS injection — runs after Streamlit finishes rendering
st.markdown("""
<style>
textarea {
  font-family: 'Segoe UI', Arial, sans-serif !important;
  font-size: 17px !important;
  line-height: 1.6 !important;
}
</style>
""", unsafe_allow_html=True)

# Force dark theme on file uploader via JS (CSS alone can't reach it)
st.markdown("""
<script>
// Force dark theme on file uploader via JS (CSS alone can't reach it)
function darkUploader() {
  document.querySelectorAll(
    '[data-testid="stFileUploaderDropzone"], [data-testid="stFileUploader"] section'
  ).forEach(el => {
    el.style.backgroundColor = '#161b27';
    el.style.background      = '#161b27';
    el.style.borderColor     = '#3a4a6a';
    el.style.color           = '#8a9bbf';
  });
  document.querySelectorAll('[data-testid="stFileUploader"] span, [data-testid="stFileUploader"] p')
    .forEach(el => { el.style.color = '#8a9bbf'; el.style.background = 'transparent'; });
  document.querySelectorAll('[data-testid="stFileUploader"] button')
    .forEach(el => {
      el.style.background    = '#1c2333';
      el.style.border        = '1px solid #3a4a6a';
      el.style.color         = '#e8edf5';
      el.style.borderRadius  = '6px';
    });
}

function styleSidebarButtons() {
  document.querySelectorAll('[data-testid="stSidebarCollapsedControl"] button')
    .forEach(el => {
      el.style.opacity         = '1';
      el.style.transform       = 'scale(1.8)';
      el.style.transformOrigin = 'center';
    });
}

function styleChatInput() {
  document.querySelectorAll('textarea').forEach(el => {
    el.style.setProperty('font-size',   '17px',  'important');
    el.style.setProperty('font-family', "'Segoe UI', Arial, sans-serif", 'important');
    el.style.setProperty('line-height', '1.6',   'important');
    el.style.setProperty('color',       '#f0f4fc','important');
  });
}

darkUploader(); styleSidebarButtons(); styleChatInput();
setInterval(() => { darkUploader(); styleSidebarButtons(); styleChatInput(); }, 300);
</script>
""", unsafe_allow_html=True)

st.markdown(f"""
<div style="border-top:1px solid #2a3550;margin-top:16px;padding-top:10px;
            font-family:'Inter',sans-serif;font-size:14px;font-weight:500;color:#6a7a9a;
            display:flex;justify-content:space-between">
  <span>Parallel Execution · Constitutional AI · Consensus Engine · M4</span>
  <span>Upload: 2MB max · {datetime.now().strftime('%H:%M:%S')}</span>
</div>""", unsafe_allow_html=True)