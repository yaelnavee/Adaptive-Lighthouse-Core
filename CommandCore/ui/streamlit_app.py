import streamlit as st
import sys
import os
import concurrent.futures
from datetime import datetime

# הוספת תיקיית השורש לנתיב החיפוש
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.agent_factory import SpecialistFactory
from llm.llm_client import LLMClient

# --- הגדרות עמוד ---
st.set_page_config(page_title="Command Core - Parallel Mode", page_icon="⚡", layout="wide")

# אתחול ה-LLM
if 'llm' not in st.session_state:
    st.session_state.llm = LLMClient()

# ניהול היסטוריית הצ'אט
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# --- פונקציית עזר להרצת סוכן בודד במקביל ---
def run_agent(agent_type, prompt, history_context, llm_client):
    agent = SpecialistFactory.create(agent_type, llm_client)
    # שליחת כל ההיסטוריה + הקלט הנוכחי לניתוח
    response = agent.analyze(prompt, previous_findings=history_context)
    return {"name": agent.name, "response": response, "type": agent_type}

# --- לוגיקת עיבוד מרכזית (מפעילה את הסוכנים) ---
def process_event(event_text):
    """מפעילה את כל הסוכנים במקביל עבור אירוע מסוים (טקסט או קובץ)"""
    st.session_state.chat_history.append({"role": "user", "content": event_text})
    
    # בניית ההקשר מההיסטוריה (ללא ההודעה האחרונה שרק נוספה)
    history_context = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.chat_history[:-1]])
    
    agent_types = ["fire", "police", "medical"]
    current_llm = st.session_state.llm

    with st.spinner("All agents analyzing in parallel..."):
        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = [
                executor.submit(run_agent, at, event_text, history_context, current_llm) 
                for at in agent_types
            ]
            
            for future in concurrent.futures.as_completed(futures):
                try:
                    res = future.result()
                    display_content = f"**{res['name']}**: {res['response']}"
                    st.session_state.chat_history.append({
                        "role": "assistant", 
                        "content": display_content, 
                        "avatar": "🤖"
                    })
                except Exception as e:
                    st.error(f"Error in agent execution: {e}")
    st.rerun()

# --- Sidebar: ניהול וקבצים ---
with st.sidebar:
    st.title("🛡️ Control Panel")
    if st.button("🗑️ Start New Chat", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()
    
    st.markdown("---")
    st.subheader("📁 Upload Field Report")
    uploaded_file = st.file_uploader("Upload .txt or .md reports", type=["txt", "md"])
    
    if uploaded_file is not None:
        # קריאת תוכן הקובץ
        file_content = uploaded_file.read().decode("utf-8")
        if st.button("🚀 Process Report", use_container_width=True):
            # הזרקת תוכן הקובץ כאירוע חדש
            formatted_report = f"📄 **FIELD REPORT UPLOADED:**\n\n{file_content}"
            process_event(formatted_report)

# --- תצוגת הצ'אט ---
st.title("🛡️ Command Core: Parallel Analysis")

for message in st.session_state.chat_history:
    with st.chat_message(message["role"], avatar=message.get("avatar")):
        st.markdown(message["content"])

# --- קלט משתמש רגיל ---
if prompt := st.chat_input("Enter situation update..."):
    process_event(prompt)

st.markdown("---")
st.caption(f"Last update: {datetime.now().strftime('%H:%M:%S')} | Parallel Execution Mode")