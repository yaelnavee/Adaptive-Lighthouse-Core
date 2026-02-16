# import sys
# import os

# # הוספת תיקיית השורש (CommandCore) לנתיב החיפוש של פייתון
# sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# import streamlit as st
# from agents.agent_factory import SpecialistFactory
# from llm.llm_client import LLMClient

# def run_streamlit():
#     st.set_page_config(page_title="Command Core - Adaptive Lighthouse", layout="wide")
    
#     st.title("🛡️ Command Core - Milestone 1")
#     st.sidebar.header("Agent Selection")
    
#     # אתחול ה-LLM
#     if 'llm' not in st.session_state:
#         st.session_state.llm = LLMClient()
    
#     # בחירת סוכן לפי דרישות Milestone 1 [cite: 23, 26]
#     agent_options = {"Fire_Bot": "fire", "Police_Bot": "police", "Med_Bot": "medical"}
#     selected_name = st.sidebar.selectbox("Choose a Specialist:", list(agent_options.keys()))
#     agent_type = agent_options[selected_name]
    
#     # יצירת הסוכן דרך ה-Factory
#     agent = SpecialistFactory.create(agent_type, st.session_state.llm)
    
#     st.write(f"### Chatting with: {agent.name} ({agent.role})")
#     st.info(f"**Persona:** {agent.persona}")

#     # ניהול היסטוריית הצ'אט
#     if "messages" not in st.session_state:
#         st.session_state.messages = []

#     for message in st.session_state.messages:
#         with st.chat_message(message["role"]):
#             st.markdown(message["content"])

#     # קלט משתמש [cite: 27]
#     if prompt := st.chat_input("Describe the emergency situation..."):
#         st.session_state.messages.append({"role": "user", "content": prompt})
#         with st.chat_message("user"):
#             st.markdown(prompt)

#         with st.chat_message("assistant"):
#             with st.spinner(f"{agent.name} is analyzing..."):
#                 response = agent.analyze(prompt)
#                 st.markdown(response)
        
#         st.session_state.messages.append({"role": "assistant", "content": response})

# if __name__ == "__main__":
#     run_streamlit()

import streamlit as st
import sys
import os

# תיקון נתיבים (כפי שעשינו קודם)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents.agent_factory import SpecialistFactory
from llm.llm_client import LLMClient

def run_round_table():
    st.set_page_config(page_title="Command Core - Round Table", layout="wide")
    st.title("🤝 Milestone 2: The Round Table")
    
    if 'llm' not in st.session_state:
        st.session_state.llm = LLMClient()

    st.sidebar.info("In this mode, all agents will analyze the situation sequentially to coordinate their response.")

    # תיבת הקלט המרכזית
    if prompt := st.chat_input("Describe the emergency situation (e.g., Gas leak at school)..."):
        st.chat_message("user").markdown(prompt)
        
        # יצירת הסוכנים
        factory = SpecialistFactory()
        fire = factory.create("fire", st.session_state.llm)
        police = factory.create("police", st.session_state.llm)
        medical = factory.create("medical", st.session_state.llm)
        
        agents = [fire, police, medical]
        shared_context = "" # זהו ה-Shared Context של Milestone 2

        # הלולאה המשותפת (The Loop)
        for agent in agents:
            with st.chat_message(agent.name):
                with st.spinner(f"{agent.name} is coordinating..."):
                    # הסוכן מקבל את הקלט + מה שקדם לו
                    response = agent.analyze(prompt, shared_context)
                    st.markdown(response)
                    
                    # עדכון ההקשר המשותף להמשך השרשרת
                    shared_context += f"\n--- {agent.name} Proposal ---\n{response}\n"

if __name__ == "__main__":
    run_round_table()