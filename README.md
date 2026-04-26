# Adaptive-Lighthouse-Core

**Multi-Agent Decision Orchestrator for Emergency Response**

## 📖 Overview
[cite_start]Command Core is a hierarchical AI system designed to assist human commanders in making tactical decisions during complex emergency situations[cite: 6, 8]. [cite_start]Built on a **Multi-Agent Architecture**, the system coordinates specialized AI experts to provide a synchronized, ethical, and efficient response plan[cite: 6, 9].

[cite_start]The project utilizes a **Mixture of Experts (MoE)** approach combined with **RAG (Retrieval-Augmented Generation)** to ensure every recommendation is grounded in official operational protocols[cite: 14, 19].

---

## 🚀 Current Progress: Milestones 1 & 2

### Milestone 1: "The Specialist"
* [cite_start]**Domain Experts:** Implementation of dedicated agents for Fire, Police, and Medical response[cite: 27, 35, 96].
* [cite_start]**Protocol-Driven (RAG):** Agents' knowledge is decoupled from the code and stored in external Markdown files, allowing for easy updates to emergency doctrines[cite: 89, 90, 94].
* **Modular Architecture:** Built using Object-Oriented Programming (OOP) and the **Factory Design Pattern** for seamless scalability.

### Milestone 2: "The Round Table"
* [cite_start]**Sequential Collaboration:** Agents now operate in a "Round Table" discussion where each specialist "hears" and builds upon the findings of the previous agent[cite: 38, 39, 109].
* [cite_start]**Shared Context Logic:** Implementation of a synchronization loop that passes a "Coordination Context" between agents to prevent conflicting instructions[cite: 113, 114, 116].
* **Language Matching:** Automatic detection of the user's language (Hebrew/English) to ensure consistent and professional responses.
* **Actionable Outputs:** Refined Prompt Engineering to ensure short, direct, and practical bullet points instead of long theoretical explanations.

---

## 🛠️ Tech Stack
* **LLM:** Groq LPU Inference Engine (Model: `llama-3.3-70b-versatile`) for near-instant response times.
* **Framework:** Python, Streamlit (Web UI), and LangGraph (Agent orchestration logic).
* [cite_start]**Knowledge Base:** Markdown-based professional emergency protocols[cite: 92, 94].
* **Security:** `python-dotenv` for secure API key management.

---

## 📂 Project Structure
```text
CommandCore/
├── agents/             # Agent logic, BaseAgent, and SpecialistFactory
├── protocols/          # Markdown files containing emergency doctrines (RAG source)
├── llm/                # API client for Groq communication
├── ui/                 # Streamlit web interface
├── .env                # Private API keys (not tracked in Git)
├── main.py             # Milestone 1 CLI interface
└── requirements.txt    # Project dependencies
