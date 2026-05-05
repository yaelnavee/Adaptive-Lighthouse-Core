"""
Command Core — Streamlit UI
============================
Milestone 3 — The Constitution: full integration of CommanderAgent with:
  - Parallel specialist analysis (ThreadPoolExecutor)
  - Two-stage Constitutional review (pre-screen + LLM)
  - Veto audit log display
  - Live Constitution editor in the sidebar (changes apply immediately)
  - Field report upload (max 2 MB)
"""

import streamlit as st
import sys
import os
import json
import concurrent.futures
from datetime import datetime

# Ensure project root is on the path when running from the ui/ directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.agent_factory import SpecialistFactory
from agents.commander_agent import CommanderAgent, CONSTITUTION, VETO_TRIGGERS
from llm.llm_client import LLMClient

# ---------------------------------------------------------------------------
# File upload limit (bytes) — change this constant to adjust
# ---------------------------------------------------------------------------
MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # 2 MB

# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Command Core — M3 Constitution",
    page_icon="⚖️",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------
if "llm" not in st.session_state:
    st.session_state.llm = LLMClient()

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Allow the Constitution text to be edited live without restarting the app
if "constitution_text" not in st.session_state:
    st.session_state.constitution_text = CONSTITUTION

if "veto_triggers" not in st.session_state:
    st.session_state.veto_triggers = dict(VETO_TRIGGERS)


# ---------------------------------------------------------------------------
# Helper: run a single specialist agent (used inside the thread pool)
# ---------------------------------------------------------------------------
def _run_agent(agent_type: str, prompt: str, history_context: str, llm_client) -> dict:
    """Instantiate an agent and return its name + response."""
    agent = SpecialistFactory.create(agent_type, llm_client)
    response = agent.analyze(prompt, previous_findings=history_context)
    return {"name": agent.name, "response": response, "type": agent_type}


# ---------------------------------------------------------------------------
# Core processing logic
# ---------------------------------------------------------------------------
def process_event(event_text: str):
    """
    1. Run all specialist agents in parallel.
    2. Pass their reports to CommanderAgent for constitutional review.
    3. Display granular results (per-agent status + veto log + final plan).
    """
    st.session_state.chat_history.append({"role": "user", "content": event_text})

    # Build conversation history context (excluding current message)
    history_context = "\n".join(
        f"{m['role']}: {m['content']}"
        for m in st.session_state.chat_history[:-1]
    )

    agent_types = ["fire", "police", "medical"]
    llm = st.session_state.llm

    # --- Stage 1: Parallel specialist analysis ---
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

    # --- Stage 2: Constitutional review ---
    # Patch the commander to use any live-edited constitution / triggers
    commander = CommanderAgent(llm)
    commander._live_constitution = st.session_state.constitution_text
    commander._live_triggers = st.session_state.veto_triggers

    # Monkey-patch CONSTITUTION and VETO_TRIGGERS for this run
    import agents.commander_agent as _ca_module
    original_constitution = _ca_module.CONSTITUTION
    original_triggers = _ca_module.VETO_TRIGGERS
    _ca_module.CONSTITUTION = st.session_state.constitution_text
    _ca_module.VETO_TRIGGERS = st.session_state.veto_triggers

    with st.spinner("⚖️ Commander reviewing against the Constitution..."):
        review_result = commander.review_and_synthesize(agent_reports)

    # Restore originals
    _ca_module.CONSTITUTION = original_constitution
    _ca_module.VETO_TRIGGERS = original_triggers

    # --- Build rich assistant message ---
    reviews = review_result["reviews"]
    final_plan = review_result["final_plan"]
    veto_log = review_result["veto_log"]

    # --- Build the specialist reports block (collapsible per agent) ---
    # Stored separately so the UI can render them as expanders
    agent_icons = {"Fire_Bot": "🔥", "Police_Bot": "🚔", "Med_Bot": "🏥"}

    specialist_entries = []
    for agent_name, report_text in agent_reports.items():
        review = reviews.get(agent_name, {})
        verdict_icon = "🔴 VETO" if review.get("vetoed") else "✅ APPROVED"
        reason = f" — {review.get('reason', '')}" if review.get("reason") else ""
        icon = agent_icons.get(agent_name, "🤖")
        specialist_entries.append({
            "name": agent_name,
            "icon": icon,
            "verdict": verdict_icon,
            "reason": reason,
            "report": report_text,
        })

    # Per-agent status summary (one line each, always visible)
    status_lines = [
        f"- {e['icon']} **{e['name']}**: {e['verdict']}{e['reason']}"
        for e in specialist_entries
    ]

    # Veto log block
    veto_section = ""
    if veto_log:
        veto_entries = "\n".join(
            f"  - [{v['stage'].upper()}] **{v['agent']}**: {v['reason']}"
            for v in veto_log
        )
        veto_section = f"\n\n**📋 Veto Audit Log:**\n{veto_entries}"

    # Specialist reports block (stored as JSON string, rendered as expanders in chat)
    import json as _json
    specialists_json = _json.dumps(specialist_entries)

    content = (
        "### 🎖️ Commander Review\n"
        + "\n".join(status_lines)
        + veto_section
        + f"\n\n---\n### 🗺️ Final Plan\n{final_plan}"
        + f"\n\n<!-- SPECIALISTS:{specialists_json} -->"
    )

    st.session_state.chat_history.append({
        "role": "assistant",
        "content": content,
        "avatar": "⚖️",
        "specialists": specialist_entries,
    })
    st.rerun()


# ---------------------------------------------------------------------------
# Sidebar — Control Panel, Constitution editor, file upload
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("🛡️ Control Panel")

    if st.button("🗑️ New Incident", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()

    st.markdown("---")

    # --- Live Constitution Editor ---
    with st.expander("⚖️ Edit Constitution", expanded=False):
        st.caption(
            "Modify rules directly. Changes apply to the **next** event processed. "
            "Keep the `RULE N:` prefix format for tests to pass."
        )
        edited_constitution = st.text_area(
            "Constitution Rules",
            value=st.session_state.constitution_text,
            height=250,
            label_visibility="collapsed",
        )
        if edited_constitution != st.session_state.constitution_text:
            st.session_state.constitution_text = edited_constitution
            st.success("✓ Constitution updated.")

    # --- Veto Trigger Editor ---
    with st.expander("🔍 Edit Veto Triggers", expanded=False):
        st.caption(
            "JSON object — keys are phrases to detect (case-insensitive), "
            "values are rule labels shown in the audit log."
        )
        triggers_json = json.dumps(st.session_state.veto_triggers, indent=2)
        edited_triggers = st.text_area(
            "Veto Triggers JSON",
            value=triggers_json,
            height=200,
            label_visibility="collapsed",
        )
        if st.button("💾 Save Triggers", use_container_width=True):
            try:
                parsed = json.loads(edited_triggers)
                st.session_state.veto_triggers = parsed
                st.success("✓ Triggers saved.")
            except json.JSONDecodeError as exc:
                st.error(f"Invalid JSON: {exc}")

    st.markdown("---")

    # --- Field Report Upload (max 2 MB) ---
    st.subheader("📁 Upload Field Report")
    st.caption(f"Accepted: .txt / .md — max {MAX_UPLOAD_BYTES // (1024*1024)} MB")

    uploaded_file = st.file_uploader(
        "Upload report",
        type=["txt", "md"],
        label_visibility="collapsed",
    )

    if uploaded_file is not None:
        # Enforce size limit
        file_bytes = uploaded_file.read()
        if len(file_bytes) > MAX_UPLOAD_BYTES:
            size_mb = len(file_bytes) / (1024 * 1024)
            st.error(
                f"❌ File too large ({size_mb:.2f} MB). "
                f"Maximum allowed size is {MAX_UPLOAD_BYTES // (1024*1024)} MB."
            )
        else:
            file_content = file_bytes.decode("utf-8", errors="replace")
            if st.button("🚀 Process Report", use_container_width=True):
                formatted_report = f"📄 **FIELD REPORT UPLOADED:**\n\n{file_content}"
                process_event(formatted_report)

# ---------------------------------------------------------------------------
# Main chat area
# ---------------------------------------------------------------------------
st.title("⚖️ Command Core — Constitutional AI")
st.caption("Milestone 3: The Constitution | Parallel Execution + Veto Engine")

for message in st.session_state.chat_history:
    # Strip the hidden specialist data marker before rendering markdown
    display_content = message["content"]
    if "<!-- SPECIALISTS:" in display_content:
        display_content = display_content[:display_content.rfind("\n\n<!-- SPECIALISTS:")]

    with st.chat_message(message["role"], avatar=message.get("avatar")):
        st.markdown(display_content)

        # Render per-agent collapsible reports for assistant messages
        if message["role"] == "assistant" and message.get("specialists"):
            st.markdown("**🔍 Specialist Reports (expand to read each analysis):**")
            cols = st.columns(len(message["specialists"]))
            for col, entry in zip(cols, message["specialists"]):
                verdict_color = "🔴" if "VETO" in entry["verdict"] else "✅"
                with col:
                    with st.expander(f"{entry['icon']} {entry['name']} {verdict_color}"):
                        st.markdown(entry["report"])

if prompt := st.chat_input("Describe the incident..."):
    process_event(prompt)

st.markdown("---")
st.caption(
    f"Last update: {datetime.now().strftime('%H:%M:%S')} | "
    "Parallel execution + Constitutional AI | "
    f"Upload limit: {MAX_UPLOAD_BYTES // (1024*1024)} MB"
)
