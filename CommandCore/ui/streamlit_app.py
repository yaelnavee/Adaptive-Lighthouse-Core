import streamlit as st
import sys
import os
from datetime import datetime

# הוספת תיקיית השורש ל-path כדי לאפשר ייבוא מודולים [cite: 132, 175]
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from agents.agent_factory import SpecialistFactory
from llm.llm_client import LLMClient

# הגדרות עמוד
st.set_page_config(page_title="Command Core - Adaptive Lighthouse", page_icon="🛡️", layout="wide")

# אתחול רכיבי הליבה
llm_client = LLMClient()
agent_types = ["fire", "police", "medical"]

# ניהול זיכרון המערכת (Session State) 
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# --- Sidebar: הגדרות וניהול צ'אט ---
with st.sidebar:
    st.title("🛡️ Control Panel")
    st.markdown("---")
    
    # כפתור לפתיחת צ'אט חדש (איפוס זיכרון) [cite: 40, 55]
    if st.button("🗑️ Start New Chat", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()
    
    st.markdown("---")
    st.info("**Milestone 2.5:** Continuous Chat Mode Enabled. The agents now remember previous updates.")

# --- תצוגת הצ'אט המצטבר ---
st.title("⚓ Adaptive Lighthouse - Command Core")
st.subheader("Multi-Agent Strategic Orchestrator")

# הצגת הודעות מההיסטוריה [cite: 182]
for message in st.session_state.chat_history:
    with st.chat_message(message["role"], avatar=message.get("avatar")):
        st.markdown(message["content"])

# --- קלט משתמש והרצת סוכנים ---
if prompt := st.chat_input("Enter emergency updates or a new scenario..."):
    
    # 1. הוספת הודעת המשתמש להיסטוריה והצגתה
    st.session_state.chat_history.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 2. הכנת ה-Shared Context (כל ההיסטוריה עד כה) [cite: 130, 232]
    # אנחנו מאחדים את כל השיחה כדי שהסוכן יבין את השתלשלות האירועים
    full_conversation_context = "\n".join([
        f"{m['role'].upper()}: {m['content']}" for m in st.session_state.chat_history
    ])

    # 3. הרצת שרשרת הסוכנים (Sequential Chain) [cite: 222, 248]
    # כל אחד מקבל את ההקשר המלא של כל מה שנאמר
    shared_context = "" # הקשר שמצטבר *בתוך* הסבב הנוכחי
    
    with st.spinner("Agents are synchronizing response..."):
        for agent_type in agent_types:
            # יצירת הסוכן דרך ה-Factory [cite: 146, 191]
            agent = SpecialistFactory.create(agent_type, llm_client)
            
            # ניתוח האירוע בהתבסס על כל היסטוריית הצ'אט והחלטות הסבב הנוכחי [cite: 220, 221]
            response = agent.analyze(prompt, previous_findings=shared_context)
            
            # עדכון ההקשר עבור הסוכן הבא בטור
            shared_context += f"\n--- {agent.name} Findings ---\n{response}\n"
            
            # שמירה והצגת התשובה בצ'אט
            agent_data = {"role": "assistant", "content": f"**{agent.name}**: {response}", "avatar": "🤖"}
            st.session_state.chat_history.append(agent_data)
            
            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(agent_data["content"])

# --- Footer ---
st.markdown("---")
st.caption(f"Last updated: {datetime.now().strftime('%H:%M:%S')} | System: Sequential Multi-Agent RAG")