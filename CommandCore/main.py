import os
from dotenv import load_dotenv

# ניסיון לייבא ספריות RAG - אם אין API נשתמש במימוש חלופי
try:
    from langchain_community.document_loaders import TextLoader
    from langchain_text_splitters import CharacterTextSplitter
    from langchain_openai import OpenAIEmbeddings, ChatOpenAI
    from langchain_community.vectorstores import FAISS
    from langchain.chains import RetrievalQA
    HAS_LANGCHAIN = True
except ImportError:
    HAS_LANGCHAIN = False

load_dotenv()

class MockAgentChain:
    """מחלקה המדמה סוכן RAG להרצה ללא API"""
    def __init__(self, agent_name):
        self.agent_name = agent_name

    def invoke(self, user_input):
        # תשובות מבוססות על אפיון Milestone 1 [cite: 29, 30]
        responses = {
            "Fire_Bot": "Extinguish immediately.",
            "Police_Bot": "Secure perimeter, check for evidence.",
            "Med_Bot": "Assess casualties and prioritize medical evacuation (Triage)."
        }
        
        # הדמיה של שליפה מהפרוטוקול
        return {"result": responses.get(self.agent_name, "I am a specialist agent ready to assist.")}

class AgentFactory:
    def __init__(self, model_name="gpt-4o"):
        self.api_key = os.getenv("OPENAI_API_KEY")
        if self.api_key:
            self.llm = ChatOpenAI(model_name=model_name, temperature=0)
            self.embeddings = OpenAIEmbeddings()
        else:
            print("\n[!] No API Key found. Running in MOCK MODE (Simulation).")

    def create_specialist(self, name, protocol_path):
        # אם אין API, נחזיר סוכן דמה
        if not self.api_key:
            return MockAgentChain(name)

        # לוגיקת RAG אמיתית (Milestone 1) [cite: 12]
        loader = TextLoader(protocol_path, encoding='utf-8')
        documents = loader.load()
        text_splitter = CharacterTextSplitter(chunk_size=500, chunk_overlap=50)
        texts = text_splitter.split_documents(documents)
        vectorstore = FAISS.from_documents(texts, self.embeddings)
        
        return RetrievalQA.from_chain_type(
            llm=self.llm,
            chain_type="stuff",
            retriever=vectorstore.as_retriever(),
            verbose=False
        )

def run_console_app():
    factory = AgentFactory()
    
    # הגדרת 3 הסוכנים הנדרשים [cite: 23]
    agents_config = {
        "1": {"name": "Fire_Bot", "path": "knowledge_base/protocols/fire_manual.md"},
        "2": {"name": "Police_Bot", "path": "knowledge_base/protocols/police_manual.md"},
        "3": {"name": "Med_Bot", "path": "knowledge_base/protocols/med_manual.md"}
    }

    print("\n" + "="*40)
    print("  The Command Core - Milestone 1 Console")
    print("="*40)
    
    while True:
        print("\nSelect an Agent Expert:")
        for key, info in agents_config.items():
            print(f"{key}. {info['name']}")
        print("q. Exit")
        
        choice = input("\nYour choice: ")
        
        if choice.lower() == 'q':
            break
        
        if choice in agents_config:
            selected = agents_config[choice]
            print(f"\n--- Initializing {selected['name']}... ---")
            
            # יצירת הסוכן (אמיתי או דמה בהתאם ל-API)
            agent_chain = factory.create_specialist(selected['name'], selected['path'])
            
            user_input = input(f"Command Input (e.g., 'There is a burning car'): ")
            
            # הרצת השאילתה 
            response = agent_chain.invoke(user_input)
            print(f"\n[{selected['name']} Response]: {response['result']}")
        else:
            print("Invalid choice, try again.")

if __name__ == "__main__":
    run_console_app()