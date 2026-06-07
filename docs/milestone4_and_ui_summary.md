# Command Core — Complete Implementation Reference
## Milestones 1–4 · UI Redesign · Architecture · Operations Guide

> Last updated: 2026-06-05  
> Branch: `main` — 69 unit tests passing, 0 failing

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Milestone 1 — Specialist Agents](#2-milestone-1--specialist-agents)
3. [Milestone 2 — The Round Table (Parallel Execution)](#3-milestone-2--the-round-table-parallel-execution)
4. [Milestone 3 — Constitutional AI](#4-milestone-3--constitutional-ai)
5. [Milestone 4 — The Consensus Engine](#5-milestone-4--the-consensus-engine)
6. [UI Redesign — streamlit_app_v2.py](#6-ui-redesign--streamlit_app_v2py)
7. [Bug Fixes Log](#7-bug-fixes-log)
8. [Test Suite Reference](#8-test-suite-reference)
9. [How to Run Locally](#9-how-to-run-locally)
10. [Configuration Reference](#10-configuration-reference)

---

## 1. Architecture Overview

Command Core is a multi-agent Constitutional AI system for emergency response coordination. It routes a natural-language incident description through three specialist agents (Fire_Bot, Med_Bot, Police_Bot), applies two-stage constitutional review, and synthesizes a single unified action plan.

### Processing pipeline (per incident)

```
User Input
    │
    ├─── Gibberish check (BaseAgent._is_gibberish)
    │
    ▼
ThreadPoolExecutor  ─────────────────────────────────────────────────
│  Fire_Bot.analyze()    │  Police_Bot.analyze()  │  Med_Bot.analyze()
│  (LLM call)            │  (LLM call)            │  (LLM call)
└────────────────────────┴────────────────────────┴─────────────────
    │
    ▼  agent_reports: dict[str, str]
    │
    ├─ Stage 1: ConsensusEngine.resolve()          [deterministic, no LLM]
    │     • calculate_urgency_scores()  → UrgencyScore per agent (1–10)
    │     • detect_conflicts()          → list[ConflictReport]
    │     • _build_summary()            → string injected into LLM prompt
    │
    ├─ Stage 2: CommanderAgent._pre_screen_vetoes() [deterministic, no LLM]
    │     • keyword scan against VETO_TRIGGERS dict
    │     • writes pre_screen entries to veto_log
    │
    └─ Stage 3: CommanderAgent LLM call            [one LLM call]
          • prompt = CONSTITUTION + consensus_summary + reports (with flags)
          • parses REVIEW: block → reviews dict
          • parses FINAL_PLAN: block → unified action plan string
          • writes llm_review entries to veto_log
```

### Module map

```
CommandCore/
├── agents/
│   ├── base_agent.py          # ABC: prompt builder, language/gibberish detection
│   ├── fire_agent.py          # FireAgent(BaseAgent)
│   ├── medical_agent.py       # MedicalAgent(BaseAgent)
│   ├── police_agent.py        # PoliceAgent(BaseAgent)
│   ├── agent_factory.py       # SpecialistFactory.create(type, llm)
│   └── commander_agent.py     # CommanderAgent: two-stage veto + LLM synthesis
│
├── consensus/
│   └── consensus_engine.py    # ConsensusEngine: urgency scoring + conflict resolution
│
├── llm/
│   └── llm_client.py          # Groq API wrapper (llama-3.3-70b-versatile, temp=0.2)
│
├── protocols/
│   ├── constitution.md        # RULE 1–7: machine-readable constitutional rules
│   ├── fire_protocol.md       # Fire_Bot domain protocol (RAG document)
│   ├── med_protocol.md        # Med_Bot domain protocol
│   └── police_protocol..md    # Police_Bot domain protocol
│
├── orchestrator/
│   └── commander.py           # CLI entry point (non-Streamlit)
│
├── ui/
│   ├── streamlit_app.py       # Original Streamlit UI (Milestone 4 baseline)
│   ├── streamlit_app_v2.py    # Dark tactical redesign (see §6)
│   └── rag_utils.py           # Protocol file loading utilities
│
└── tests/
    ├── test_agents.py          # 16 tests: factory, prompts, gibberish, language
    ├── test_commander.py       # 18 tests: pre-screen, LLM parsing, veto log, constitution
    ├── test_consensus_engine.py # 28 tests: urgency, conflicts, resolution, integration
    ├── test_constitution.py    # 4 tests: live editing of constitution and triggers
    ├── test_system.py          # 6 integration tests (require live GROQ_API_KEY)
    └── test_vulnerabilities.py # 5 tests: prompt injection, domain boundaries, context
```

### External dependencies

| Package | Purpose |
|---------|---------|
| `groq` | LLM API (llama-3.3-70b-versatile) |
| `streamlit==1.30.0` | Web UI |
| `python-dotenv` | `.env` loading for `GROQ_API_KEY` |
| `langchain-community`, `faiss-cpu`, `pypdf` | RAG / protocol file loading |
| `langgraph` | Agent flow infrastructure |

---

## 2. Milestone 1 — Specialist Agents

**Goal:** Create three independent specialist agents that analyze emergency incidents within their domain and respond in the same language as the input.

### What was built

**`BaseAgent` (abstract base class)**  
All three specialists inherit from `BaseAgent`, which provides:

- `build_prompt(user_input, previous_findings)` — assembles the full LLM prompt with domain protocol, language mandate, coordination context, and output constraints.
- `_detect_language(text)` — regex check for Unicode Hebrew block `[֐-׿]`; returns `"HEBREW"` or `"ENGLISH"`.
- `_is_gibberish(text)` — returns `True` if the input contains fewer than 2 readable Hebrew or Latin characters. Prevents tactical responses to random noise.
- `analyze(user_input, previous_findings)` — gibberish-gates the input, then calls `llm.generate(prompt)`.

**Three specialist agents**

| Agent | File | Role |
|-------|------|------|
| `Fire_Bot` | `fire_agent.py` | Firefighting Expert — hot zone, perimeter, hazmat |
| `Med_Bot` | `medical_agent.py` | Medical Response Expert — triage, treatment, evacuation |
| `Police_Bot` | `police_agent.py` | Law Enforcement Expert — perimeter security, traffic, crowd control |

Each agent loads its domain protocol from a markdown file in `protocols/` at construction time. If the file is missing, a fallback string is used (graceful degradation).

**`SpecialistFactory`**  
`SpecialistFactory.create(agent_type, llm_client)` accepts `"fire"`, `"medical"`, or `"police"` (case-insensitive) and returns the appropriate agent instance. Raises `ValueError` for unknown types.

### Key design decisions

- **Language mandate is hard-coded before the LLM sees the input.** The `ABSOLUTE LANGUAGE MANDATE` line appears at the top of every prompt — before any persona, protocol, or task description. This prevents the LLM from drifting to English on Hebrew inputs.
- **Protocol files are separate from code.** Each agent's operational rules live in a markdown file, allowing domain experts to update protocols without touching Python.
- **Gibberish gate is deterministic.** The 2-character threshold (`< 2` readable chars) was tuned to accept very short valid inputs (`"אש"` = fire) while rejecting symbols-only and digits-only noise.

---

## 3. Milestone 2 — The Round Table (Parallel Execution)

**Goal:** Run all three specialists in parallel rather than sequentially, and give each agent visibility into others' findings via a shared coordination context.

### What was built

- **Parallel execution via `ThreadPoolExecutor`** — all three `agent.analyze()` calls are submitted as futures and collected as they complete. Results are not order-dependent.
- **Coordination context injection** — `build_prompt()` accepts `previous_findings: str`. When non-empty, this block is labeled `COORDINATION CONTEXT` and treated as ground truth inside the prompt. Agents are instructed to align their zone decisions with what others have already established.
- **Multi-turn session history** — the Streamlit UI maintains `chat_history` in `st.session_state`, prepending recent exchanges as context for subsequent incidents.
- **Field report upload** — `.txt` and `.md` files up to 2 MB can be uploaded via the sidebar and processed identically to typed input.

### Key design decisions

- Because agents run truly in parallel, they do not see each other's output. The coordination context only carries **history from previous incidents**, not from other agents in the same call. This avoids race conditions and keeps the parallel speedup real.
- The `previous_findings` parameter defaults to `""`, so `BaseAgent` prompts work identically whether context is available or not. When empty, the prompt reads "You are the FIRST responder. Set the baseline."

---

## 4. Milestone 3 — Constitutional AI

**Goal:** Add a two-stage review layer that vetoes agent reports violating constitutional rules before the final plan is issued.

### What was built

**`CommanderAgent`** with a two-stage pipeline:

1. **Pre-screen (deterministic)** — `_pre_screen_vetoes(agent_reports)` scans every agent report for phrases listed in `VETO_TRIGGERS`. Matches are logged as `{stage: "pre_screen", agent, reason}` entries. This is a case-insensitive substring scan; no LLM call.

2. **LLM constitutional review** — `_build_review_prompt()` assembles a prompt containing the full `CONSTITUTION` text, all agent reports (with pre-screen flags injected inline as `⚠️ PRE-SCREEN FLAGGED: <reason>`), and 8 mandatory logic rules covering anti-hallucination, tactical expertise boundaries, radius synchronization, HAZMAT safety, proportionality, and language matching.

**`CONSTITUTION`** — loaded from `protocols/constitution.md` at module import. Contains 7 machine-readable rules (`RULE N: <text>`) followed by extended human-readable guidelines.

**`VETO_TRIGGERS`** — a module-level `dict` mapping detection phrases to rule labels:

```python
VETO_TRIGGERS = {
    "enter unstable":         "RULE 2 — Team ordered into unstable structure",
    "unstable building":      "RULE 2 — Team ordered into unstable structure",
    "enter the hot zone":     "RULE 5 — Unauthorised hot-zone entry without Fire_Bot clearance",
    "evidence first":         "RULE 3 — Evidence collection before life-safety response",
    "experimental treatment": "RULE 4 — Experimental/invented medical protocol",
    "פינוי מיידי":            "RULE 5 — Unauthorized hot-zone entry before clearance",
    "נכנסים לפינוי":          "RULE 5 — Unauthorized hot-zone entry before clearance",
    "אירוע רב נפגעים":        "RULE 6 — Disproportional response to minor incident",
    "mci":                    "RULE 6 — Disproportional response to minor incident",
    "פינוי של כל השכונה":     "RULE 6 — Disproportional response to minor incident",
}
```

**Live editing** — both `CONSTITUTION` and `VETO_TRIGGERS` are module-level globals, allowing the Streamlit sidebar to monkey-patch them around each `review_and_synthesize()` call. This enables per-session customization without restarting the app.

**Veto audit log** — `get_veto_log()` returns the accumulated list of all pre-screen and LLM-review veto events from the most recent call, with `stage`, `agent`, and `reason` fields.

### Key design decisions

- **Two-stage architecture separates speed from depth.** Pre-screen catches obvious keyword violations in microseconds. The LLM review catches subtle violations (e.g., hallucinated hazards, disproportional responses) that no phrase list can enumerate. Running pre-screen first means the LLM sees `PRE-SCREEN FLAGGED` annotations and is less likely to approve what the deterministic layer already rejected.
- **Anti-hallucination is a first-class rule.** The Commander prompt explicitly instructs the LLM to veto any agent that invents hazards, victims, or locations not present in the input. Without this, agents occasionally fabricate casualties from benign descriptions.
- **"Tactical expertise" is a carve-out from hallucination.** Safety perimeters (e.g., "50m standoff distance") and equipment choices are considered domain expertise, not hallucination, and the Commander is explicitly told not to veto them.

---

## 5. Milestone 4 — The Consensus Engine

**Commit:** `8abb7de`  
**Goal:** Add a deterministic pre-processing layer that scores urgency, detects inter-agent conflicts, and resolves them algorithmically before the LLM synthesis call.

### Problem being solved

In Milestones 1–3, if Fire_Bot said "no entry" and Med_Bot said "enter immediately," the LLM might weigh them equally, pick arbitrarily, or produce an incoherent blend. The Constitution provided rules in plain English, but there was no algorithmic enforcement of the priority hierarchy *before* the LLM decision. The output was also structured as three separate sub-reports rather than a single command order.

### What was built

#### `ConsensusEngine` (`consensus/consensus_engine.py`)

**Stage 1 of the Commander pipeline — runs before any LLM call.**

```python
class ConsensusEngine:
    def calculate_urgency_scores(agent_reports) -> dict[str, UrgencyScore]
    def detect_conflicts(agent_reports, urgency_scores) -> list[ConflictReport]
    def resolve(agent_reports) -> dict  # full pipeline: scores + conflicts + summary
```

**Urgency scoring** — each agent report receives a score from 1.0 to 10.0:

```
score = tier_base_score + Σ(keyword_weight × occurrences)
```

| Tier | Base score | Agents |
|------|-----------|--------|
| `LIFE_SAFETY` | 5.0 | Fire_Bot, Med_Bot |
| `EVIDENCE` | 3.0 | Police_Bot |
| `PROPERTY` | 1.0 | Unknown agents |

Keyword weights by severity level:

| Level | Weight | Example terms (EN/HE) |
|-------|--------|----------------------|
| CRITICAL | +2.0 | trapped, casualties, explosion, toxic / נפגעים, פיצוץ |
| HIGH | +1.0 | fire, evacuate, hazmat, rescue / שריפה, פינוי, חירום |
| MEDIUM | +0.3 | perimeter, secure, contain / קורדון, ניטור |
| LOW | −0.5 | minor, contained, clear / קטן, שולי, תקין |

Score is clamped to `[1.0, 10.0]`. Labels: CRITICAL ≥ 7.0, HIGH ≥ 5.0, MEDIUM ≥ 3.0, LOW < 3.0.

**Conflict detection** — phrase-based, three topics:

| Topic | Opposing stances |
|-------|-----------------|
| `zone_access` | `allow` vs `deny` |
| `road_status` | `open` vs `closed` |
| `evacuation` | `proceed` vs `hold` |

Each topic has a phrase list for each stance in both English and Hebrew. Every pair of agents taking opposing stances on the same topic produces a `ConflictReport`.

**Conflict resolution — three-level waterfall** (`_pick_winner`):

1. **Urgency score gap > 0.5** — higher-scoring agent wins; reason cites the scores.
2. **Tier priority** — LIFE_SAFETY (3) > EVIDENCE (2) > PROPERTY (1) when scores are close; reason cites the tiers.
3. **Safety-first stance** — when tier and score are equal, the restrictive side wins (`deny`, `closed`, `hold`); reason cites the principle.
4. **Total tie** — defaults to the first agent; reason notes the tie.

The 0.5 gap threshold prevents floating-point noise from triggering score-based decisions when agents are essentially equal.

**Consensus summary** — `_build_summary()` serializes urgency scores and conflict resolutions into a plain-text block:

```
CONSENSUS ANALYSIS (pre-computed — treat as authoritative):

URGENCY SCORES:
  Fire_Bot: 8.5/10 [CRITICAL] (tier: LIFE_SAFETY)
  ...

CONFLICT RESOLUTIONS (BINDING — follow these exactly):
  [ZONE_ACCESS] Fire_Bot(deny) vs Med_Bot(allow) → WINNER: Fire_Bot
  — Higher urgency score (8.5 vs 5.0)
```

This block is injected into the Commander's LLM prompt between the CONSTITUTION and SPECIALIST REPORTS sections, labeled `BINDING`.

#### Data classes

```python
@dataclass
class UrgencyScore:
    agent: str
    score: float          # 1.0–10.0
    tier: str
    matched_keywords: list[str]
    label: str            # property: CRITICAL/HIGH/MEDIUM/LOW

@dataclass
class ConflictReport:
    topic: str            # e.g. "zone_access"
    agent_a: str
    stance_a: str         # e.g. "allow"
    agent_b: str
    stance_b: str         # e.g. "deny"
    score_a: float
    score_b: float
    winner: str
    resolution_reason: str
```

#### Changes to `CommanderAgent`

- `__init__` now instantiates `self._consensus = ConsensusEngine()`.
- `review_and_synthesize()` runs consensus as Stage 1, returning two new keys: `urgency_scores` and `conflicts`.
- `_build_review_prompt()` gains a `consensus_summary` parameter (default `""`).
- Mandatory logic rule 7 added: *"Follow the CONSENSUS ANALYSIS conflict resolutions. They are BINDING."*
- `get_veto_log()` public method added (was missing, causing pre-existing test failures).
- Flagged reports now show `⚠️ PRE-SCREEN FLAGGED: <reason>` inline in the prompt body.
- FINAL_PLAN format instruction now explicitly demands one unified command order.

#### Changes to `streamlit_app.py`

- `process_event()` extracts `urgency_scores` and `conflicts` from `review_result`.
- Each specialist entry now carries `urgency_str`, `urgency_label`, `urgency_score`.
- Status summary lines display urgency badges inline.
- New Conflict Resolutions panel renders topic, opposing stances, winner, and reason.
- Specialist expander headers include the urgency badge.
- Page renamed to "Unified Command Decision."
- Sidebar urgency legend added.

### Technical decisions

**Deterministic-first, LLM-second** — all conflict resolution is pure Python with no API calls. This makes every resolution fully unit-testable without API costs, and means the LLM cannot override priority decisions (they arrive as "BINDING" in the prompt).

**Additive return dict** — the two new keys were added to the existing dict. All Milestone 3 tests continue to pass unmodified because they only access `reviews`, `final_plan`, and `veto_log`.

**Known limitations**

- Conflict detection uses substring matching — paraphrased conflicts (e.g., "the area is safe for movement") are missed.
- Urgency scoring ignores negation — "no casualties" still scores a keyword bonus.
- The module-global monkey-patch for live constitution editing is not safe under concurrent Streamlit sessions.
- The three conflict topics (`zone_access`, `road_status`, `evacuation`) cover the most common cases but not all: decontamination order, triage priority, and resource allocation are not yet modeled.

### Test results

| Phase | Tests collected | Passed | Failed |
|-------|----------------|--------|--------|
| Before Milestone 4 | 36 | 29 | 7 |
| After Milestone 4 | 64 | 64 | 0 |
| After v2 UI (current) | 69 | 69 | 0 |

---

## 6. UI Redesign — streamlit_app_v2.py

**File:** `CommandCore/ui/streamlit_app_v2.py`  
**Streamlit version:** 1.30.0  
**Backend:** Identical to `streamlit_app.py` — all logic in `process_event()`, `CommanderAgent`, and `ConsensusEngine` is unchanged.

### Design goals

- Three-column fixed-height layout with per-column internal scroll — no full-page scroll during analysis.
- Distinct visual language for each veto state (three states, not two).
- Constitution rules visible as a live tree, not buried in a sidebar text box.
- Veto triggers managed as interactive chips — no raw JSON editing.
- Dark tactical theme appropriate for an emergency coordination context.

### Layout

```
┌─ Sidebar ────┬─ Left (1.0) ─────────┬─ Center (1.4) ────────┬─ Right (1.2) ────────┐
│              │ [INCIDENT INPUT]      │  🔥 Fire_Bot           │  DISPATCH            │
│ Rule toggles │ Language LED          │    CRITICAL 8.5        │  ─────────────────   │
│              │ ▶ DISPATCH button     │    ✓ APPROVED          │  (military telegram) │
│ Trigger chips│                       │                        │                      │
│              │ Constitution Tree     │  🏥 Med_Bot            │  Veto Audit Log      │
│ File upload  │  ❤️ R-1 ●●           │    HIGH 6.0            │  table               │
│              │  🏗️ R-2 ●●           │    ✕ LLM VETO          │                      │
│              │  ...                  │                        │  Conflict Panel      │
│              │                       │  🚔 Police_Bot         │  cards               │
│              │ Session history       │    MEDIUM 4.2          │                      │
│              │                       │    ✓ APPROVED          │                      │
└──────────────┴───────────────────────┴────────────────────────┴──────────────────────┘
```

Column widths: `st.columns([1, 1.4, 1.2], gap="small")`

### Left column — Incident & Status Feed

**Incident input** — `st.text_area` styled with monospace font (`Roboto Mono`), dark background (`#0d1117`), blue focus ring.

**Language LED** — reads the current textarea content in real-time (on every Streamlit rerun triggered by input change) via `_detect_language()`. Three states:
- HEB: blue LED dot with glow, `HEB` label
- ENG: green LED dot with glow, `ENG` label
- Neutral (empty input): gray, `---` label

**DISPATCH button** — `type="primary"`, disabled when textarea is empty. Gradient blue, uppercase monospace font, glows on hover.

**Constitution Tree** — parses `RULE N:` lines from the live constitution text in session state. Displays each rule as a badge row with an icon, number, and truncated rule text. Rules light up differently depending on analysis state:
- No analysis yet: dimmed monochrome
- After analysis, rule not triggered: active (muted green border)
- After analysis, rule referenced in veto log: vetoed (red border + text)
- Rule disabled via sidebar toggle: 30% opacity

**Session history** — last 6 user inputs shown as small monospace previews at the bottom.

### Center column — Operational Analysis

Three agent cards, styled by domain:

| Agent | Card accent | Name color |
|-------|------------|-----------|
| Fire_Bot | Muted orange border (`#c2410c`) | `#fb923c` |
| Med_Bot | Dark teal border (`#0e7490`) | `#22d3ee` |
| Police_Bot | Dark blue border (`#1d4ed8`) | `#60a5fa` |

Each card shows:

1. **Agent icon + name + urgency badge** — badge CSS class chosen by label: `u-critical`, `u-high`, `u-medium`, `u-low`.

2. **Status chip** — three distinct states rendered as colored pill badges:

   | State | Trigger condition | Color |
   |-------|------------------|-------|
   | `✓ APPROVED` | No veto entries for this agent | Dark green (`#052e16` bg, `#4ade80` text) |
   | `⚠ PRE-SCREEN VETO` | `veto_log` entry with `stage == "pre_screen"` for this agent | Dark orange (`#431407` bg, `#fdba74` text) |
   | `✕ LLM VETO` | `veto_log` entry with `stage == "llm_review"` or `reviews[agent]["vetoed"]` | Dark red (`#450a0a` bg, `#fca5a5` text) |

   Each chip has a glowing dot matching its color.

3. **Veto reason** — shown below the status chip if non-empty.

4. **Expandable report** — `st.expander()` with the full raw agent report rendered in monospace.

### Right column — Command Output & Audit

**Military dispatch** — the `final_plan` string is wrapped in a styled box:
- Dark near-black background (`#0a0f14`)
- Amber top border (`#f59e0b`) as a dispatch separator
- Monospace body text in off-white
- Header line: `COMMAND CORE // PRIORITY DISPATCH // HH:MM:SS`

**Veto Audit Log** — an HTML table (`veto-table` CSS class) with columns: Time | Agent | Stage | Tactical Reason. Stage labels: `PRE-SCREEN` (orange) and `LLM-REVIEW` (red). Rows have a subtle hover effect.

**Conflict Resolution panel** — one card per `ConflictReport`, showing topic, both agents and their stances, the winner (green), and the resolution reason in muted text. Purple left border matches the arbitration theme.

### Sidebar — Professional Controls

**Rule Management Grid** — each of the 7 constitution rules is displayed as two stacked lines (rule number + short text preview) with a `st.toggle()` aligned right. Toggling a rule off removes its `RULE N:` line from the constitution text before it is passed to `CommanderAgent`. Enabled states are stored in `st.session_state.rule_enabled`.

**Trigger Chip Manager** — `VETO_TRIGGERS` is rendered as a list of two-column rows: the phrase (blue) + its rule label on the left, and a `×` delete button on the right. Deletion is immediate (removes from `st.session_state.veto_triggers` and reruns). An "Add Trigger" expander contains two text inputs (phrase + rule label) and an Add button with validation — prevents the syntax errors that were possible with the raw JSON textarea in v1.

**File upload** — unchanged from v1.

### Visual theme

```css
Background:       #0d1117   (GitHub dark — near-black blue)
Panel cards:      #161b22   (slightly lighter)
Borders:          #21262d / #30363d
Body text:        #c9d1d9
Muted text:       #8b949e
Fonts:            'Inter' (UI) + 'Roboto Mono' (data/labels/dispatch)
Accent — amber:   #f59e0b   (dispatch header)
Accent — blue:    #58a6ff   (links, active states)
```

### How to run both versions

```bash
cd CommandCore
source venv/bin/activate

# Original UI (Milestone 4 baseline)
streamlit run ui/streamlit_app.py

# Tactical redesign
streamlit run ui/streamlit_app_v2.py
```

Both versions share all backend logic and session state is independent between them (separate browser tabs or separate `streamlit run` processes).

---

## 7. Bug Fixes Log

The following bugs were identified and fixed during this session. They are ordered by commit.

### Fix 1 — `get_veto_log()` missing from `CommanderAgent`
**Commit:** `8abb7de`  
**Symptom:** `AttributeError: 'CommanderAgent' object has no attribute 'get_veto_log'` when tests called this method.  
**Root cause:** The method was referenced in tests but never implemented — `_veto_log` was a private attribute with no public accessor.  
**Fix:** Added `def get_veto_log(self) -> list: return self._veto_log` to `CommanderAgent`.

### Fix 2 — `constitution.md` used markdown headers instead of `RULE N:` format
**Commit:** `8abb7de`  
**Symptom:** Four test failures: `test_constitution_contains_all_rules`, `test_life_safety_rule_exists`, `test_responder_safety_rule_exists`, `test_medical_integrity_rule_exists`.  
**Root cause:** The file used `## 1. Hierarchy of Life Safety` style headings. Tests and the Commander prompt parser expected `RULE 1:`, `RULE 2:`, etc.  
**Fix:** Restructured `protocols/constitution.md` to lead with `RULE 1:` through `RULE 7:` in machine-readable format, followed by the existing extended guidelines.

### Fix 3 — `PRE-SCREEN FLAGGED` not injected into LLM prompt
**Commit:** `8abb7de`  
**Symptom:** `test_flagged_agent_marked_in_prompt` failed — the test asserted `"PRE-SCREEN FLAGGED"` was in the prompt, but `_build_review_prompt()` was not inserting it.  
**Root cause:** `_build_review_prompt()` accepted a `pre_screen` dict parameter but only used it to list which agents were flagged in a separate section — it did not annotate the individual report lines.  
**Fix:** Inline annotation added in the report block: each report line now appends `⚠️ PRE-SCREEN FLAGGED: <reason>` when the agent was pre-screen flagged.

### Fix 4 — Syntax error in `orchestrator/commander.py`
**Commit:** `8abb7de`  
**Symptom:** `SyntaxError` when importing or running the orchestrator module.  
**Root cause:** A markdown footnote annotation `[cite: 5]` was accidentally left inside a Python string subscript: `result["final_plan"][cite: 5]`.  
**Fix:** Removed the annotation; corrected to `result["final_plan"]`.

### Fix 5 — Gibberish detection rejected valid Hebrew
**Commits:** `db5cf53`, `726fbc6`  
**Symptom:** Hebrew inputs like `"אש"` (fire) were flagged as gibberish and returned the "input unclear" message instead of a tactical response.  
**Root cause:** The original gibberish check required at least 3 characters total. Hebrew letters `[֐-׿]` are single codepoints and a two-letter Hebrew word like `"אש"` was below the threshold.  
**Fix:** Changed the threshold to `< 2` readable *letters* (Hebrew or Latin), ensuring any two-character Hebrew word passes. The detection is now: `len(re.findall(r'[֐-׿a-zA-Z]', stripped)) < 2`.

### Fix 6 — Language detection inconsistency in mixed-language reports
**Commit:** `726fbc6`  
**Symptom:** When specialist agents returned mixed Hebrew/English text, the Commander's gibberish target language was wrong — sometimes producing an English "unclear" message for a Hebrew incident.  
**Root cause:** The language decision in `_build_review_prompt()` counted raw character occurrences (`english_chars >= hebrew_chars`) but all reports were concatenated including boilerplate English from agent templates.  
**Fix:** The condition was tightened to only use `UNCLEAR_RESPONSE_EN` when English characters outnumber Hebrew characters or when `"Incomprehensible input"` appears in the reports block, correctly detecting the dominant language in ambiguous cases.

---

## 8. Test Suite Reference

### Run all unit tests (no API key required)

```bash
cd CommandCore
source venv/bin/activate
python -m pytest tests/test_agents.py tests/test_commander.py \
    tests/test_consensus_engine.py tests/test_constitution.py \
    tests/test_vulnerabilities.py -v
```

Expected output: **69 passed in ~0.1s**

### Run integration tests (requires `GROQ_API_KEY`)

```bash
python -m pytest tests/test_system.py -v
```

These make live LLM calls and may take 15–60 seconds. They test:
- Gibberish rejection
- Radius conflict resolution (Fire_Bot authority)
- Hebrew language consistency
- Multi-turn context persistence
- Minor incident proportionality (no MCI for trash fires)
- Hazmat RULE 5 enforcement (Med_Bot veto on unauthorized hot-zone entry)

### Test file overview

| File | Tests | Requires API | What it covers |
|------|-------|-------------|----------------|
| `test_agents.py` | 16 | No | Factory, prompt structure, language mandate, gibberish gate, brevity constraints |
| `test_commander.py` | 18 | No | Pre-screen keyword matching, LLM response parsing, veto log integrity, constitution sanity, prompt format |
| `test_consensus_engine.py` | 28 | No | Urgency scoring tiers, keyword bonuses, score clamping, Hebrew detection, conflict detection, resolution waterfall, full pipeline |
| `test_constitution.py` | 4 | No | Live CONSTITUTION editing, live VETO_TRIGGERS editing |
| `test_vulnerabilities.py` | 5 | No | Prompt injection resistance, domain boundaries, massive context handling |
| `test_system.py` | 6 | **Yes** | End-to-end LLM behavior across six real scenarios |

---

## 9. How to Run Locally

### Prerequisites

- Python 3.12+
- A [Groq API key](https://console.groq.com) (free tier is sufficient)

### Setup

```bash
# Clone (if not already cloned)
git clone https://github.com/yaelnavee/Adaptive-Lighthouse-Core.git
cd Adaptive-Lighthouse-Core/CommandCore

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate          # Linux/macOS
# venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt

# Configure API key
echo "GROQ_API_KEY=your_key_here" > .env
```

### Launch the original UI

```bash
streamlit run ui/streamlit_app.py
```

Opens at `http://localhost:8501`

### Launch the dark tactical redesign

```bash
streamlit run ui/streamlit_app_v2.py
```

Opens at `http://localhost:8501`

### Run the test suite

```bash
# Unit tests only (no API key)
python -m pytest tests/test_agents.py tests/test_commander.py \
    tests/test_consensus_engine.py tests/test_constitution.py \
    tests/test_vulnerabilities.py -v

# Full suite including integration (requires .env with GROQ_API_KEY)
python -m pytest tests/ -v --ignore=tests/test_system.py   # skip integration
python -m pytest tests/ -v                                  # all tests
```

### CLI usage (non-Streamlit)

```bash
python main.py
```

Runs a simple terminal loop that processes incidents and prints the commander's response. Uses the same `LLMClient` and `CommanderAgent` as the UI.

---

## 10. Configuration Reference

### `GROQ_API_KEY` (required)

Set in `CommandCore/.env`:
```
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx
```

The `LLMClient` raises `ValueError` at startup if this is missing.

### LLM parameters (`llm/llm_client.py`)

| Parameter | Value | Notes |
|-----------|-------|-------|
| Model | `llama-3.3-70b-versatile` | Best publicly available Llama model via Groq |
| Temperature | `0.2` | Low — maximizes constitutional rule adherence |
| Max tokens | `500` | Sufficient for a unified plan; Hebrew responses historically needed more than the original 300 |

### Constitution (`protocols/constitution.md`)

Edit this file to add, modify, or remove constitutional rules. The format `RULE N: <text>` on its own line is machine-readable. Rules with this format are:
- Loaded into `CONSTITUTION` at module import
- Displayed as the Constitution Tree in `streamlit_app_v2.py`
- Individually toggleable via the sidebar in `streamlit_app_v2.py`

### Veto triggers (`agents/commander_agent.py` → `VETO_TRIGGERS`)

The default triggers are defined in code. They can be overridden at runtime via:
- `streamlit_app.py` sidebar: raw JSON text area
- `streamlit_app_v2.py` sidebar: chip manager (add/remove individual triggers without JSON syntax)
- Tests: `ca_module.VETO_TRIGGERS = {...}` (patch in setUp / restore in tearDown)

### Urgency scoring weights (`consensus/consensus_engine.py`)

The keyword catalog (`_URGENCY_KEYWORDS`) and conflict phrase patterns (`_CONFLICT_PATTERNS`) are top-level dicts. Add new terms without touching any logic code — the engine loops over these dictionaries dynamically.

### Conflict topics (`consensus/consensus_engine.py` → `_CONFLICT_PATTERNS`)

New conflict topics can be added by extending `_CONFLICT_PATTERNS`:

```python
"decontamination": {
    "required": ["decontamination required", "decon before entry", "טיהור נדרש"],
    "not_required": ["no decon needed", "area is clean", "ניקוי לא נדרש"],
}
```

The stance keys determine which names appear in `ConflictReport.stance_a` / `stance_b`. Stances whose names appear in `_SAFETY_STANCES` are treated as conservative in the safety-first tie-break.
