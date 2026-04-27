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

# אתחול ה-LLM בתהליך הראשי
if 'llm' not in st.session_state:
    st.session_state.llm = LLMClient()

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# --- פונקציית עזר להרצת סוכן בודד ---
# הוספנו את llm_client כפרמטר פונקציה במקום לגשת ל-session_state
def run_agent(agent_type, prompt, history_context, llm_client):
    agent = SpecialistFactory.create(agent_type, llm_client)
    response = agent.analyze(prompt, previous_findings=history_context)
    return {"name": agent.name, "response": response, "type": agent_type}

# --- Sidebar ---
with st.sidebar:
    st.title("⚡ Parallel Control")
    if st.button("🗑️ Start New Chat", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()
    st.markdown("---")
    st.info("**Architecture:** Parallel (MoE). Fix: Context injection for worker threads.")

# --- תצוגת הצ'אט ---
st.title("🛡️ Command Core: Parallel Analysis")

for message in st.session_state.chat_history:
    with st.chat_message(message["role"], avatar=message.get("avatar")):
        st.markdown(message["content"])

# --- קלט וביצוע מקבילי ---
if prompt := st.chat_input("Enter situation update..."):
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # בניית הקשר היסטורי
    history_context = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.chat_history[:-1]])
    
    agent_types = ["fire", "police", "medical"]
    
    # שליפת ה-LLM מה-session_state בתהליך הראשי
    current_llm = st.session_state.llm

    with st.spinner("All agents analyzing in parallel..."):
        with concurrent.futures.ThreadPoolExecutor() as executor:
            # הזרקת ה-current_llm כארגומנט נוסף לכל סוכן
            futures = [
                executor.submit(run_agent, at, prompt, history_context, current_llm) 
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
                    with st.chat_message("assistant", avatar="🤖"):
                        st.markdown(display_content)
                except Exception as e:
                    st.error(f"Error in agent execution: {e}")

st.markdown("---")
st.caption(f"Last sync: {datetime.now().strftime('%H:%M:%S')} | Parallel Execution with Thread Safety")