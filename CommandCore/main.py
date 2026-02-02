from agents.agent_factory import SpecialistFactory
from llm.llm_client import LLMClient

def main():
    llm = LLMClient()
    
    print("\n" + "="*40)
    print("  COMMAND CORE - MILESTONE 1")
    print("="*40)
    
    # תפריט בחירת סוכן לפי האיפיון
    print("\nSelect Specialist:")
    print("1. Fire_Bot")
    print("2. Police_Bot")
    print("3. Med_Bot")
    choice = input("\nEnter choice (1-3): ")

    mapping = {"1": "fire", "2": "police", "3": "medical"}
    agent_type = mapping.get(choice)

    if not agent_type:
        print("Invalid selection.")
        return

    agent = SpecialistFactory.create(agent_type, llm)
    print(f"\n--- Chatting with {agent.name} ---")

    while True:
        user_input = input(f"\n[{agent.name}] Describe the situation (or 'q' to quit): ")
        if user_input.lower() == 'q':
            break
            
        print("\nAnalyzing...")
        response = agent.analyze(user_input)
        print(f"\nResponse:\n{response}")

if __name__ == "__main__":
    main()