"""
Command Core — Streamlit UI v5 (Tactical Round-Table Network)
=============================================================
Animated network diagram: Commander at centre, Fire/Police/Medical on outer ring.
Nodes glow while processing; turn green (APPROVED) or red (VETOED) on completion.
All backend logic preserved from streamlit_app.py (Milestone 4).
Run: streamlit run ui/streamlit_app_v5.py
"""

import json
import os
import sys
import concurrent.futures
from datetime import datetime

import streamlit as st
import streamlit.components.v1 as components

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.agent_factory import SpecialistFactory
from agents.commander_agent import CommanderAgent, CONSTITUTION, VETO_TRIGGERS
from llm.llm_client import LLMClient

MAX_UPLOAD_BYTES = 2 * 1024 * 1024

# ─────────────────────────────────────────────────────────────────────────────
# Network diagram HTML template  (%%DATA%% replaced at runtime)
# ─────────────────────────────────────────────────────────────────────────────
_NETWORK_HTML_TMPL = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
%%DATA%%
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#fff;font-family:'Segoe UI',Arial,sans-serif;overflow:hidden}
#rt-wrap{background:#fff;width:100%}
#rt-canvas-wrap{position:relative;width:100%;height:480px;background:#fff}
#rt-canvas{position:absolute;inset:0;width:100%;height:100%}
#rt-svg{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}

.rt-agent{
  position:absolute;display:flex;flex-direction:column;align-items:center;
  transform:translate(-50%,-50%);z-index:10;
}
.rt-circle{
  width:78px;height:78px;border-radius:50%;
  background:radial-gradient(circle at 35% 35%,#5bbfff,#1565c0 60%,#0d3a8a);
  border:2.5px solid #4aa3ee;
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  box-shadow:0 0 0 6px rgba(74,163,238,.18),0 0 24px rgba(21,101,192,.22);
  transition:box-shadow .4s,background .4s,border-color .4s;
  position:relative;overflow:visible;
}
.rt-circle.processing{
  box-shadow:0 0 0 8px rgba(74,163,238,.3),0 0 36px rgba(74,163,238,.55);
  animation:processPulse 1.3s ease-in-out infinite;
}
@keyframes processPulse{0%,100%{transform:scale(1)}50%{transform:scale(1.07)}}

.rt-emoji{font-size:22px;line-height:1}
.rt-label{
  font-size:8px;font-weight:700;color:rgba(255,255,255,.92);
  letter-spacing:1.2px;text-transform:uppercase;text-align:center;
  line-height:1.2;margin-top:1px;
}
.rt-name{
  margin-top:7px;font-size:9px;font-weight:700;letter-spacing:1.2px;
  text-transform:uppercase;color:#1a5fa8;text-align:center;
}
.rt-badge{
  display:none;flex-direction:row;gap:4px;align-items:center;
  margin-top:3px;font-size:9px;font-weight:700;letter-spacing:.8px;
  text-align:center;font-family:monospace;
}

.rt-commander .rt-circle{
  width:94px;height:94px;
  background:radial-gradient(circle at 35% 35%,#7dd4ff,#1361c4 55%,#08266b);
  border:3px solid #5bbfff;
  box-shadow:0 0 0 10px rgba(91,191,255,.18),0 0 40px rgba(21,97,196,.3);
}
.rt-commander .rt-emoji{font-size:26px}
.rt-commander .rt-label{font-size:9px;letter-spacing:1.5px}
.rt-commander .rt-name{font-size:10px;color:#0d3a8a}

.rt-ring{
  display:none;position:absolute;border-radius:50%;
  border:1.5px solid rgba(74,163,238,.5);
  animation:expandRing 1.4s ease-out infinite;pointer-events:none;
}
@keyframes expandRing{0%{transform:scale(1);opacity:.7}100%{transform:scale(1.9);opacity:0}}
</style>
</head>
<body>
<div id="rt-wrap">
  <div id="rt-canvas-wrap">
    <canvas id="rt-canvas"></canvas>
    <svg id="rt-svg" xmlns="http://www.w3.org/2000/svg"></svg>

    <div class="rt-agent rt-commander" id="ag-commander" style="left:50%;top:49%">
      <div class="rt-circle" id="circ-commander">
        <div class="rt-ring" id="ring-commander" style="width:94px;height:94px"></div>
        <div class="rt-emoji">⚖️</div>
        <div class="rt-label">COMMANDER</div>
      </div>
      <div class="rt-name">Commander</div>
      <div class="rt-badge" id="badge-commander"></div>
    </div>

    <div class="rt-agent" id="ag-fire" style="left:50%;top:13%">
      <div class="rt-circle" id="circ-fire">
        <div class="rt-ring" id="ring-fire" style="width:78px;height:78px"></div>
        <div class="rt-emoji">🔥</div>
        <div class="rt-label">FIRE</div>
      </div>
      <div class="rt-name">Fire_Bot</div>
      <div class="rt-badge" id="badge-fire"></div>
    </div>

    <div class="rt-agent" id="ag-police" style="left:12%;top:82%">
      <div class="rt-circle" id="circ-police">
        <div class="rt-ring" id="ring-police" style="width:78px;height:78px"></div>
        <div class="rt-emoji">🚔</div>
        <div class="rt-label">POLICE</div>
      </div>
      <div class="rt-name">Police_Bot</div>
      <div class="rt-badge" id="badge-police"></div>
    </div>

    <div class="rt-agent" id="ag-medical" style="left:88%;top:82%">
      <div class="rt-circle" id="circ-medical">
        <div class="rt-ring" id="ring-medical" style="width:78px;height:78px"></div>
        <div class="rt-emoji">🏥</div>
        <div class="rt-label">MEDICAL</div>
      </div>
      <div class="rt-name">Med_Bot</div>
      <div class="rt-badge" id="badge-medical"></div>
    </div>
  </div>
</div>

<script>
const ID_TO_NAME={fire:'Fire_Bot',police:'Police_Bot',medical:'Med_Bot'};
const AGENT_IDS=['fire','police','medical'];

const GRAD={
  idle:'radial-gradient(circle at 35% 35%,#5bbfff,#1565c0 60%,#0d3a8a)',
  approved:'radial-gradient(circle at 35% 35%,#6ee7b7,#059669 60%,#064e3b)',
  vetoed:'radial-gradient(circle at 35% 35%,#fca5a5,#dc2626 60%,#7f1d1d)',
  commander:'radial-gradient(circle at 35% 35%,#7dd4ff,#1361c4 55%,#08266b)'
};
const BDR={idle:'#4aa3ee',approved:'#34d399',vetoed:'#f87171',commander:'#5bbfff'};
const SHD={
  idle:'0 0 0 6px rgba(74,163,238,.18),0 0 24px rgba(21,101,192,.22)',
  approved:'0 0 0 6px rgba(52,211,153,.22),0 0 28px rgba(5,150,105,.35)',
  vetoed:'0 0 0 6px rgba(248,113,113,.22),0 0 28px rgba(220,38,38,.35)',
  commander:'0 0 0 10px rgba(91,191,255,.18),0 0 40px rgba(21,97,196,.3)'
};
const UC={CRITICAL:'#dc2626',HIGH:'#ea580c',MEDIUM:'#ca8a04',LOW:'#16a34a','N/A':'#94a3b8'};

function getPos(id){
  const el=document.getElementById('ag-'+id);
  const wrap=document.getElementById('rt-canvas-wrap');
  if(!el||!wrap)return{x:0,y:0};
  const wr=wrap.getBoundingClientRect(),er=el.getBoundingClientRect();
  return{x:er.left+er.width/2-wr.left,y:er.top+er.height/2-wr.top};
}

function drawBg(){
  const cv=document.getElementById('rt-canvas');
  const wrap=document.getElementById('rt-canvas-wrap');
  cv.width=wrap.offsetWidth;cv.height=wrap.offsetHeight;
  const ctx=cv.getContext('2d'),W=cv.width,H=cv.height;
  ctx.clearRect(0,0,W,H);
  const cx=W/2,cy=H*.49;
  const r=Math.min(W,H)*.40;
  ctx.beginPath();ctx.arc(cx,cy,r,0,Math.PI*2);
  ctx.strokeStyle='rgba(74,163,238,.14)';ctx.lineWidth=1;
  ctx.setLineDash([5,5]);ctx.stroke();ctx.setLineDash([]);
  ctx.beginPath();ctx.arc(cx,cy,r*.54,0,Math.PI*2);
  ctx.strokeStyle='rgba(74,163,238,.07)';ctx.lineWidth=.8;ctx.stroke();
}

function clearSvg(){
  const svg=document.getElementById('rt-svg');
  while(svg.firstChild)svg.removeChild(svg.firstChild);
}

function makeDefs(svg){
  const defs=document.createElementNS('http://www.w3.org/2000/svg','defs');
  [['arrowBlue','#4aa3ee',1.5],['arrowActive','#1565c0',1.8],
   ['arrowGreen','#059669',1.8],['arrowRed','#dc2626',1.8]].forEach(([id,color,sw])=>{
    const mk=document.createElementNS('http://www.w3.org/2000/svg','marker');
    mk.setAttribute('id',id);mk.setAttribute('viewBox','0 0 10 10');
    mk.setAttribute('refX','8');mk.setAttribute('refY','5');
    mk.setAttribute('markerWidth','5');mk.setAttribute('markerHeight','5');
    mk.setAttribute('orient','auto-start-reverse');
    const p=document.createElementNS('http://www.w3.org/2000/svg','path');
    p.setAttribute('d','M2 1L8 5L2 9');p.setAttribute('fill','none');
    p.setAttribute('stroke',color);p.setAttribute('stroke-width',String(sw));
    mk.appendChild(p);defs.appendChild(mk);
  });
  svg.appendChild(defs);
}

function drawLine(svg,fromId,toId,opts){
  const from=getPos(fromId),to=getPos(toId);
  const dx=to.x-from.x,dy=to.y-from.y;
  const dist=Math.sqrt(dx*dx+dy*dy);
  if(dist<2)return;
  const r1=fromId==='commander'?50:42,r2=toId==='commander'?50:42;
  const x1=from.x+dx/dist*r1,y1=from.y+dy/dist*r1;
  const x2=to.x-dx/dist*r2,y2=to.y-dy/dist*r2;
  const line=document.createElementNS('http://www.w3.org/2000/svg','line');
  line.setAttribute('x1',x1);line.setAttribute('y1',y1);
  line.setAttribute('x2',x2);line.setAttribute('y2',y2);
  line.setAttribute('stroke',opts.color||'#c5dcf0');
  line.setAttribute('stroke-width',opts.width||'1.2');
  if(opts.opacity)line.setAttribute('stroke-opacity',opts.opacity);
  if(opts.dash)line.setAttribute('stroke-dasharray',opts.dash);
  if(opts.arrow){
    line.setAttribute('marker-end','url(#'+opts.arrow+')');
    line.setAttribute('marker-start','url(#'+opts.arrow+')');
  }
  if(opts.animated){
    const len=Math.sqrt((x2-x1)**2+(y2-y1)**2);
    line.setAttribute('stroke-dasharray','8 5');
    const anim=document.createElementNS('http://www.w3.org/2000/svg','animate');
    anim.setAttribute('attributeName','stroke-dashoffset');
    anim.setAttribute('from','0');anim.setAttribute('to',String(-len));
    anim.setAttribute('dur','0.75s');anim.setAttribute('repeatCount','indefinite');
    line.appendChild(anim);
  }
  svg.appendChild(line);
}

function drawStaticLines(){
  clearSvg();const svg=document.getElementById('rt-svg');makeDefs(svg);
  AGENT_IDS.forEach(id=>drawLine(svg,'commander',id,{color:'#c5dcf0',width:'1.2',dash:'4 4',arrow:'arrowBlue'}));
}

function drawProcessingLines(){
  clearSvg();const svg=document.getElementById('rt-svg');makeDefs(svg);
  AGENT_IDS.forEach(id=>drawLine(svg,'commander',id,{color:'#1565c0',width:'2.2',arrow:'arrowActive',animated:true,opacity:'0.85'}));
}

function drawResultLines(){
  clearSvg();const svg=document.getElementById('rt-svg');makeDefs(svg);
  AGENT_IDS.forEach(id=>{
    const name=ID_TO_NAME[id],st=AGENT_STATES[name];
    if(!st){drawLine(svg,'commander',id,{color:'#c5dcf0',width:'1',dash:'4 4',arrow:'arrowBlue'});return;}
    const v=st.status!=='approved';
    drawLine(svg,'commander',id,{color:v?'#dc2626':'#059669',width:'2',arrow:v?'arrowRed':'arrowGreen',opacity:'0.7'});
  });
}

function setNodeColor(id,scheme){
  const c=document.getElementById('circ-'+id);
  if(!c)return;
  c.style.background=GRAD[scheme];c.style.borderColor=BDR[scheme];c.style.boxShadow=SHD[scheme];
}

function applyProcessing(){
  ['commander',...AGENT_IDS].forEach(id=>{
    const c=document.getElementById('circ-'+id);
    const r=document.getElementById('ring-'+id);
    if(c)c.classList.add('processing');
    if(r)r.style.display='block';
  });
}

function applyResult(){
  AGENT_IDS.forEach(id=>{
    const name=ID_TO_NAME[id],st=AGENT_STATES[name];
    if(!st)return;
    const v=st.status!=='approved';
    setNodeColor(id,v?'vetoed':'approved');
    const uc=UC[st.urgency]||'#94a3b8';
    const sc=st.score!=null?' '+st.score.toFixed(1):'';
    const vt=v?'✕ VETO':'✓ OK',vc=v?'#dc2626':'#059669';
    const b=document.getElementById('badge-'+id);
    if(b){
      b.innerHTML='<span style="color:'+vc+';font-weight:800">'+vt+'</span>'
        +'<span style="color:'+uc+';margin-left:4px">'+st.urgency+sc+'</span>';
      b.style.display='flex';
    }
  });
  setNodeColor('commander','commander');
}

function init(){
  drawBg();
  if(PROCESSING){drawProcessingLines();applyProcessing();}
  else if(HAS_RESULT){drawResultLines();applyResult();}
  else{drawStaticLines();}
}

window.addEventListener('load',init);
window.addEventListener('resize',()=>{drawBg();init();});
</script>
</body>
</html>"""


def _build_network_html(result: dict | None, processing: bool) -> str:
    agent_states: dict = {}
    if result:
        for s in result["specialists"]:
            agent_states[s["name"]] = {
                "status":  s["status"],
                "urgency": s["urgency_label"],
                "score":   s["urgency_score"],
            }
    data = (
        "<script>"
        "const AGENT_STATES=" + json.dumps(agent_states) + ";"
        "const PROCESSING="   + ("true" if processing else "false") + ";"
        "const HAS_RESULT="   + ("true" if result else "false") + ";"
        "</script>"
    )
    return _NETWORK_HTML_TMPL.replace("%%DATA%%", data)


# ─────────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Command Core — Tactical",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# Session state  (preserves all required keys)
# ─────────────────────────────────────────────────────────────────────────────
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
if "_pending_input" not in st.session_state:
    st.session_state._pending_input = None


# ─────────────────────────────────────────────────────────────────────────────
# Backend  (preserved exactly from streamlit_app.py / v4)
# ─────────────────────────────────────────────────────────────────────────────
def _get_agent_status(agent_name: str, reviews: dict, veto_log: list) -> str:
    for entry in veto_log:
        if entry.get("agent") == agent_name and entry.get("stage") == "pre_screen":
            return "prescreen"
    if reviews.get(agent_name, {}).get("vetoed"):
        return "llmveto"
    return "approved"


def _run_agent(agent_type: str, prompt: str, history_context: str, llm_client) -> dict:
    agent = SpecialistFactory.create(agent_type, llm_client)
    response = agent.analyze(prompt, previous_findings=history_context)
    return {"name": agent.name, "response": response, "type": agent_type}


def process_event(event_text: str) -> None:
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
            r = future.result()
            agent_reports[r["name"]] = r["response"]

    commander = CommanderAgent(llm)
    import agents.commander_agent as _ca_module
    _orig_const = _ca_module.CONSTITUTION
    _orig_trig  = _ca_module.VETO_TRIGGERS
    _ca_module.CONSTITUTION  = st.session_state.constitution_text
    _ca_module.VETO_TRIGGERS = st.session_state.veto_triggers

    review_result = commander.review_and_synthesize(agent_reports)

    _ca_module.CONSTITUTION  = _orig_const
    _ca_module.VETO_TRIGGERS = _orig_trig

    reviews        = review_result["reviews"]
    final_plan     = review_result["final_plan"]
    veto_log       = review_result["veto_log"]
    urgency_scores = review_result.get("urgency_scores", {})
    conflicts      = review_result.get("conflicts", [])

    _ICON  = {"Fire_Bot": "🔥", "Police_Bot": "🚔", "Med_Bot": "🏥"}
    _BADGE = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "🟢"}

    specialist_entries = []
    for agent_name, report_text in agent_reports.items():
        review  = reviews.get(agent_name, {})
        urgency = urgency_scores.get(agent_name)
        status  = _get_agent_status(agent_name, reviews, veto_log)
        specialist_entries.append({
            "name":          agent_name,
            "icon":          _ICON.get(agent_name, "🤖"),
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

    # Build assistant message for chat history
    status_lines = [
        "- {icon} **{name}** {badge} {lbl}: {verdict}{reason}".format(
            icon=e["icon"], name=e["name"],
            badge=_BADGE.get(e["urgency_label"], "⚪"),
            lbl=e["urgency_label"],
            verdict="🔴 VETO" if e["status"] != "approved" else "✅ APPROVED",
            reason=(f" — {e['reason']}" if e["reason"] else ""),
        )
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
        clines = [
            f"  - **[{c.topic.upper()}]** `{c.agent_a}` ({c.stance_a}) vs "
            f"`{c.agent_b}` ({c.stance_b}) → ✅ **{c.winner}** — _{c.resolution_reason}_"
            for c in conflicts
        ]
        conflicts_section = "\n\n**⚔️ Conflict Resolutions:**\n" + "\n".join(clines)

    content = (
        "### 🎖️ Commander Review\n"
        + "\n".join(status_lines)
        + veto_section
        + conflicts_section
        + f"\n\n---\n### 🎯 Unified Command Decision\n{final_plan}"
    )
    st.session_state.chat_history.append({
        "role":        "assistant",
        "content":     content,
        "avatar":      "⚖️",
        "specialists": specialist_entries,
    })
    st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Run pending pipeline (two-render pattern for processing animation)
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.processing and st.session_state._pending_input:
    with st.spinner("⚡ Specialists analysing in parallel… Commander synthesising…"):
        process_event(st.session_state._pending_input)
    st.session_state._pending_input = None


# ─────────────────────────────────────────────────────────────────────────────
# Sidebar  (preserved from streamlit_app.py)
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("🛡️ Control Panel")

    if st.button("🗑️ New Incident", use_container_width=True):
        st.session_state.chat_history = []
        st.session_state.last_result  = None
        st.session_state.processing   = False
        st.session_state._pending_input = None
        st.rerun()

    st.markdown("---")

    with st.expander("⚖️ Edit Constitution", expanded=False):
        st.caption(
            "Modify rules directly. Changes apply to the **next** event. "
            "Keep the `RULE N:` prefix format."
        )
        edited_const = st.text_area(
            "Constitution Rules",
            value=st.session_state.constitution_text,
            height=250,
            label_visibility="collapsed",
            key="constitution_editor_v5",
        )
        if edited_const != st.session_state.constitution_text:
            st.session_state.constitution_text = edited_const
            st.success("✓ Constitution updated.")

    with st.expander("🔍 Edit Veto Triggers", expanded=False):
        st.caption(
            "JSON object — keys are phrases (case-insensitive), "
            "values are rule labels shown in the audit log."
        )
        triggers_json = json.dumps(st.session_state.veto_triggers, indent=2)
        edited_triggers = st.text_area(
            "Veto Triggers JSON",
            value=triggers_json,
            height=200,
            label_visibility="collapsed",
            key="triggers_editor_v5",
        )
        if st.button("💾 Save Triggers", use_container_width=True, key="save_trig_v5"):
            try:
                st.session_state.veto_triggers = json.loads(edited_triggers)
                st.success("✓ Triggers saved.")
            except json.JSONDecodeError as exc:
                st.error(f"Invalid JSON: {exc}")

    st.markdown("---")
    st.subheader("📁 Upload Field Report")
    st.caption(f"Accepted: .txt / .md — max {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")

    uploaded_file = st.file_uploader(
        "Upload report",
        type=["txt", "md"],
        label_visibility="collapsed",
        key="file_uploader_v5",
    )
    if uploaded_file is not None:
        file_bytes = uploaded_file.read()
        if len(file_bytes) > MAX_UPLOAD_BYTES:
            st.error(
                f"❌ File too large ({len(file_bytes)/(1024*1024):.2f} MB). "
                f"Max {MAX_UPLOAD_BYTES//(1024*1024)} MB."
            )
        else:
            file_content = file_bytes.decode("utf-8", errors="replace")
            if st.button("🚀 Process Report", use_container_width=True, key="proc_upload_v5"):
                st.session_state.processing = True
                st.session_state._pending_input = f"📄 FIELD REPORT UPLOADED:\n\n{file_content}"
                st.rerun()

    st.markdown("---")
    st.caption("**Urgency:** 🔴 Critical · 🟠 High · 🟡 Medium · 🟢 Low")


# ─────────────────────────────────────────────────────────────────────────────
# Main area
# ─────────────────────────────────────────────────────────────────────────────
st.title("⚖️ Command Core — Tactical")
st.caption("Consensus Engine · Constitutional AI · Parallel Specialist Analysis")

# ── Network diagram ───────────────────────────────────────────────────────────
components.html(
    _build_network_html(st.session_state.last_result, st.session_state.processing),
    height=500,
)

# ── Tactical details (latest result) ─────────────────────────────────────────
result = st.session_state.last_result
if result:
    ts = result.get("timestamp", "")

    # Agent status cards
    _URGENCY_HEX = {
        "CRITICAL": "#dc2626", "HIGH": "#ea580c",
        "MEDIUM":   "#ca8a04", "LOW":  "#16a34a", "N/A": "#94a3b8",
    }
    agent_order = ["Fire_Bot", "Police_Bot", "Med_Bot"]
    by_name     = {e["name"]: e for e in result["specialists"]}

    cols = st.columns(3, gap="small")
    for col, agent_name in zip(cols, agent_order):
        entry = by_name.get(agent_name)
        if not entry:
            continue
        is_vetoed  = entry["status"] != "approved"
        urg        = entry["urgency_label"]
        score      = entry.get("urgency_score")
        score_str  = f" {score:.1f}" if score is not None else ""
        bg         = "#fef2f2" if is_vetoed else "#f0fdf4"
        border     = "#fca5a5" if is_vetoed else "#86efac"
        vlabel     = "✕ VETOED"  if is_vetoed else "✓ APPROVED"
        vcolor     = "#dc2626"   if is_vetoed else "#059669"
        uc         = _URGENCY_HEX.get(urg, "#94a3b8")

        with col:
            st.markdown(
                f'<div style="background:{bg};border:1.5px solid {border};border-radius:10px;'
                f'padding:12px 14px;margin-bottom:4px;">'
                f'<div style="font-size:14px;font-weight:700;margin-bottom:6px;">'
                f'{entry["icon"]} {agent_name}</div>'
                f'<div style="color:{vcolor};font-size:11px;font-weight:700;letter-spacing:1px;">{vlabel}</div>'
                f'<div style="color:{uc};font-size:11px;margin-top:3px;font-weight:600;">{urg}{score_str}</div>'
                + (f'<div style="font-size:10px;color:#64748b;margin-top:4px;">{entry["reason"]}</div>'
                   if entry.get("reason") else "")
                + '</div>',
                unsafe_allow_html=True,
            )
            with st.expander(f"Full report — {agent_name}", expanded=False):
                st.markdown(entry["report"])

    # Commander decision card
    st.markdown(
        f'<div style="background:#eff6ff;border:2px solid #3b82f6;border-radius:12px;'
        f'padding:18px 22px;margin-top:14px;">'
        f'<div style="font-size:11px;font-weight:800;letter-spacing:1.5px;text-transform:uppercase;'
        f'color:#1e40af;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid #bfdbfe;">'
        f'⚖️ Unified Command Decision'
        f'<span style="font-size:10px;color:#93c5fd;margin-left:10px;font-weight:400;">{ts}</span></div>'
        f'<div style="font-size:15px;font-weight:600;color:#1e293b;line-height:1.7;white-space:pre-wrap;">'
        f'{result["final_plan"]}</div></div>',
        unsafe_allow_html=True,
    )

    # Veto audit log
    veto_log = result.get("veto_log", [])
    st.markdown(
        '<div style="margin-top:16px;font-size:11px;font-weight:700;letter-spacing:1.2px;'
        'text-transform:uppercase;color:#475569;margin-bottom:8px;">📋 Veto Audit Log</div>',
        unsafe_allow_html=True,
    )
    if veto_log:
        rows = ""
        for v in veto_log:
            stage       = v.get("stage", "")
            stage_label = "PRE-SCREEN" if stage == "pre_screen" else "LLM-REVIEW"
            stage_color = "#c2410c"    if stage == "pre_screen" else "#dc2626"
            rows += (
                f"<tr>"
                f"<td style='color:#94a3b8;font-variant-numeric:tabular-nums;padding:7px 10px;'>{ts}</td>"
                f"<td style='font-weight:600;padding:7px 10px;'>{v.get('agent','—')}</td>"
                f"<td style='color:{stage_color};font-weight:700;padding:7px 10px;'>{stage_label}</td>"
                f"<td style='padding:7px 10px;'>{v.get('reason','—')}</td>"
                f"</tr>"
            )
        st.markdown(
            '<table style="width:100%;border-collapse:collapse;font-size:12px;">'
            '<thead><tr style="background:#e8effe;">'
            + "".join(
                f'<th style="padding:8px 10px;text-align:left;border-bottom:2px solid #bfdbfe;'
                f'font-size:10px;color:#475569;letter-spacing:.5px;text-transform:uppercase;">{h}</th>'
                for h in ["Time", "Agent", "Stage", "Tactical Reason"]
            )
            + f'</tr></thead><tbody>{rows}</tbody></table>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<div style="font-size:12px;color:#94a3b8;padding:4px 0;">No vetoes recorded.</div>',
            unsafe_allow_html=True,
        )

    # Conflict resolution
    conflicts = result.get("conflicts", [])
    if conflicts:
        st.markdown(
            '<div style="margin-top:14px;font-size:11px;font-weight:700;letter-spacing:1.2px;'
            'text-transform:uppercase;color:#475569;margin-bottom:8px;">⚔️ Conflict Resolution</div>',
            unsafe_allow_html=True,
        )
        for c in conflicts:
            topic = c.topic.replace("_", " ").upper()
            st.markdown(
                f'<div style="background:#eef2ff;border:1px solid #c7d2fe;border-left:3px solid #6366f1;'
                f'border-radius:8px;padding:10px 14px;margin-bottom:8px;">'
                f'<div style="font-size:10px;font-weight:700;letter-spacing:1.5px;color:#4f46e5;'
                f'text-transform:uppercase;margin-bottom:5px;">⚑ {topic}</div>'
                f'<div style="font-size:12px;color:#334155;">'
                f'<strong>{c.agent_a}</strong> [{c.stance_a}] ⟷ '
                f'<strong>{c.agent_b}</strong> [{c.stance_b}]</div>'
                f'<div style="margin-top:4px;font-size:12px;">WINNER → '
                f'<strong style="color:#15803d;">{c.winner}</strong></div>'
                f'<div style="font-size:11px;color:#64748b;margin-top:3px;">↳ {c.resolution_reason}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

st.markdown("---")

# ── Chat history ──────────────────────────────────────────────────────────────
for message in st.session_state.chat_history:
    with st.chat_message(message["role"], avatar=message.get("avatar")):
        st.markdown(message["content"])
        if message["role"] == "assistant" and message.get("specialists"):
            st.markdown("**🔍 Specialist Reports:**")
            spec_cols = st.columns(len(message["specialists"]))
            for scol, entry in zip(spec_cols, message["specialists"]):
                lbl = entry["urgency_label"]
                verdict = "🔴" if entry["status"] != "approved" else "✅"
                with scol:
                    with st.expander(f"{entry['icon']} {entry['name']} {lbl} {verdict}"):
                        st.markdown(entry["report"])

# ── Chat input  (top-level — not inside columns or expanders) ─────────────────
if prompt := st.chat_input("Describe the incident…"):
    st.session_state.processing     = True
    st.session_state._pending_input = prompt
    st.rerun()

# ── Footer ────────────────────────────────────────────────────────────────────
st.caption(
    f"Last update: {datetime.now().strftime('%H:%M:%S')} · "
    "Parallel execution · Constitutional AI · Consensus Engine · "
    f"Upload limit: {MAX_UPLOAD_BYTES // (1024 * 1024)} MB"
)
