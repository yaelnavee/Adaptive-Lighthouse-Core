# Milestone 4 — The Consensus Engine: Implementation Summary

## Overview

Milestone 4 adds a structured, deterministic conflict-resolution layer between the specialist agents and the LLM commander. Instead of relying entirely on the LLM to figure out what to do when agents disagree, the system now pre-computes an **Urgency Score** for every agent's report and resolves contradictions algorithmically before the LLM sees the data. The LLM is then given binding instructions derived from this analysis, and it produces a single unified action plan — not three separate sub-reports.

---

## What Was Built and Why

### Problem being solved

In Milestones 1–3, the Commander's `FINAL_PLAN` was produced purely by the LLM with no structured priority enforcement. If Fire_Bot said "no entry" and Med_Bot said "enter immediately," the LLM might weigh them equally, pick one arbitrarily, or blend them into an incoherent compromise. The constitution provided rules in plain English, but there was no algorithmic layer to enforce the priority hierarchy **before** the LLM made its synthesis decision.

Additionally, the output was framed as three separate agent opinions rather than a single unified command order.

### What changed

A new deterministic engine — `ConsensusEngine` — runs as **Stage 1** of the Commander pipeline. It scores, detects, and resolves conflicts without any LLM call. Its output is serialised into a `CONSENSUS ANALYSIS` block injected into the LLM prompt as authoritative, binding guidance. The LLM's role narrows from "figure everything out" to "express the pre-resolved decision in natural language as one unified plan."

---

## Technical Decisions

### Deterministic-first, LLM-second

All conflict resolution logic is pure Python with no LLM calls. This means:
- Conflict resolution is fully unit-testable without API costs or flakiness.
- The LLM cannot override priority decisions — the consensus summary explicitly marks resolutions as "BINDING."
- Debugging is straightforward: the resolution reason is a plain string you can read in the UI.

### Three-level winner selection

`_pick_winner()` uses a strict waterfall:
1. **Urgency score gap > 0.5** — the higher-scoring agent wins.
2. **Tier priority** — LIFE_SAFETY (3) beats EVIDENCE (2) beats PROPERTY (1) when scores are close.
3. **Safety-first stance** — when everything else is equal, the restrictive/deny side wins. An unresolvable tie between two Life Safety agents where one says "no entry" and the other says "proceed" defaults to the conservative option.

The 0.5 gap threshold on scores prevents floating-point noise from triggering a score-based decision when agents are essentially tied.

### Keyword catalog covers both languages

The urgency keyword lists include both English and Hebrew terms for every severity level. This matters because the system is bilingual by design and the urgency scoring must behave consistently regardless of which language the agents respond in.

### `UrgencyScore` base values encode the constitution's priority hierarchy

| Tier | Base Score | Agents |
|---|---|---|
| LIFE_SAFETY | 5.0 | Fire_Bot, Med_Bot |
| EVIDENCE | 3.0 | Police_Bot |
| PROPERTY | 1.0 | (fallback for unknown agents) |

Even with zero keywords, a Life Safety agent always starts 2 points above an Evidence agent. This means a Police_Bot report about a minor procedural matter will never outrank a Fire_Bot report about an active hazard in the tier-based tie-break.

### Conflict patterns are phrase-based, not semantic

Conflict detection uses substring matching on predefined phrase lists rather than embedding similarity or LLM classification. This is intentional: it is fast, predictable, testable, and doesn't require an LLM call. The downside is that it can miss paraphrased conflicts or generate false positives on ambiguous phrasing. This is an acceptable trade-off for an MVP; see **Known Issues** below.

### `review_and_synthesize()` return dict is additive

The two new keys (`urgency_scores`, `conflicts`) were added to the existing return dict without removing anything. All Milestone 3 tests continue to pass unmodified because they only access `reviews`, `final_plan`, and `veto_log`.

---

## Files Changed

### New: `CommandCore/consensus/__init__.py`
Empty package marker. Makes `from consensus.consensus_engine import ...` work from any file whose `sys.path` includes `CommandCore/`.

### New: `CommandCore/consensus/consensus_engine.py`

The entire Milestone 4 algorithmic core. Key public surface:

```python
class ConsensusEngine:
    def calculate_urgency_scores(agent_reports: dict) -> dict[str, UrgencyScore]
    def detect_conflicts(agent_reports, urgency_scores) -> list[ConflictReport]
    def resolve(agent_reports: dict) -> dict   # full pipeline
```

`resolve()` returns `{urgency_scores, conflicts, summary}` where `summary` is a formatted string ready to inject into the LLM prompt.

Module-level configuration tables (`AGENT_TIERS`, `TIER_BASE_SCORE`, `TIER_PRIORITY`, `_URGENCY_KEYWORDS`, `_CONFLICT_PATTERNS`) are all top-level dicts, making them easy to extend without touching logic code.

### Modified: `CommandCore/agents/commander_agent.py`

**What changed:**
- Added `from consensus.consensus_engine import ConsensusEngine` import.
- `CommanderAgent.__init__` now instantiates `self._consensus = ConsensusEngine()`.
- `review_and_synthesize()` gains Stage 1 (consensus) before the existing Stage 2 (pre-screen) and Stage 3 (LLM). Returns two new keys: `urgency_scores` and `conflicts`.
- Added `get_veto_log()` public method — was missing, causing a pre-existing test failure.
- `_build_review_prompt()` gains a third parameter `consensus_summary: str = ""` (default empty for backward compatibility). The consensus block is injected between the CONSTITUTION and SPECIALIST REPORTS sections. Pre-screen flagged agents now appear as `⚠️ PRE-SCREEN FLAGGED: <reason>` inline in the reports block — this fixes another pre-existing test failure.
- FINAL_PLAN format instruction updated to explicitly demand one unified command order, not three sub-reports.
- Mandatory logic item 7 added: "Follow the CONSENSUS ANALYSIS conflict resolutions. They are BINDING."

### Modified: `CommandCore/protocols/constitution.md`

**What changed:**  
Restructured to include the `RULE N:` prefix format that the Milestone 3 test suite required but the file never had. Rules 1–5 match the existing veto trigger labels exactly. Two new rules were added:

- **RULE 6**: Proportionality (already enforced in code, now formalised in the constitution).
- **RULE 7**: Conflict resolution priority hierarchy (Life Safety > Evidence > Property) — the foundational rule for the Consensus Engine.

The extended guidelines sections below the rules were updated to remove `[cite: N]` annotation artefacts and add the Milestone 4 single-plan mandate to Communication Standards.

This fix resolved 4 pre-existing test failures (`test_constitution_contains_all_rules`, `test_life_safety_rule_exists`, `test_responder_safety_rule_exists`, `test_medical_integrity_rule_exists`).

### Modified: `CommandCore/orchestrator/commander.py`

**What changed:**  
One-line fix: `result["final_plan"][cite: 5]` → `result["final_plan"]`. The `[cite: 5]` was a markdown footnote annotation that accidentally ended up in the Python source, making the file a syntax error at runtime.

### Modified: `CommandCore/ui/streamlit_app.py`

**What changed:**
- Page title and caption updated to "Milestone 4: Consensus Engine."
- `process_event()` extracts `urgency_scores` and `conflicts` from `review_result`.
- Each `specialist_entries` dict now includes `urgency_str` (e.g., ` 🔴 8.5`), `urgency_label`, and `urgency_score`.
- Status summary lines now display the urgency badge inline: `🔥 **Fire_Bot** 🔴 8.5: ✅ APPROVED`.
- New `conflicts_section` block renders a **Conflict Resolutions** panel showing topic, opposing stances, winner, and reason.
- Specialist expander headers now include the urgency badge alongside the verdict icon.
- Sidebar legend added explaining the four urgency colours.
- "Final Plan" section renamed to "Unified Command Decision."

### New: `CommandCore/tests/test_consensus_engine.py`

28 new unit tests across four classes:

| Class | Coverage |
|---|---|
| `TestUrgencyScoreCalculation` | Tier baseline, keyword bonuses, score clamping, Hebrew detection, label thresholds, matched keyword recording |
| `TestConflictDetection` | No-conflict aligned case, zone_access detection, road_status detection, winner is always one of the two agents, reason is non-empty |
| `TestConflictResolution` | Score-based winner, tier tier-break (LIFE_SAFETY > EVIDENCE), safety-first stance tie-break (deny/closed/hold), end-to-end detected conflict resolution |
| `TestResolveIntegration` | Required keys, every agent scored, summary contains all names, no-conflict message, conflict-present message, correct types returned |

---

## Test Results

### Before Milestone 4 (baseline)

```
36 collected
29 passed, 7 failed
```

Failures were all pre-existing bugs in the Milestone 3 codebase:
- `get_veto_log()` missing from `CommanderAgent`
- `constitution.md` using markdown `## N.` headers instead of `RULE N:` format
- `_build_review_prompt()` not including `PRE-SCREEN FLAGGED` in the prompt output
- Syntax error in `orchestrator/commander.py`

### After Milestone 4

```
64 collected
64 passed, 0 failed
```

All 7 pre-existing failures are fixed. 28 new consensus engine tests added.

---

## Known Issues and Future Improvements

### Conflict detection is phrase-based, not semantic

The current implementation matches literal substrings from a fixed phrase list. If an agent says "the area is safe for personnel to move through," this will not match the `allow` side of `zone_access` even though it means the same thing. Conversely, a report saying "there is no hot zone to worry about" could accidentally match "no" + partial strings.

**Improvement:** Replace substring matching with an LLM-powered stance classifier for conflict detection, or use embeddings to match paraphrased phrases. Since the ConsensusEngine has a clean interface (`calculate_urgency_scores` / `detect_conflicts` / `resolve`), this can be swapped in without touching the rest of the pipeline.

### Urgency scoring ignores report context

Currently, every matching keyword adds its weight regardless of negation. "There are no casualties" would still score a bonus for "casualties." A simple negation check (look for "no", "not", "none" before the keyword) would improve accuracy.

### Conflict patterns only cover three topics

The three topics (`zone_access`, `road_status`, `evacuation`) cover the most common emergency conflicts. Additional topics worth adding:
- `decontamination_order`: agents disagreeing on whether decon is required before action
- `triage_priority`: agents disagreeing on which casualty to treat first
- `resource_allocation`: competing requests for the same resource (e.g., a single rescue team)

### ConsensusEngine is not multilingual for conflict patterns

The urgency keyword catalog is bilingual (English + Hebrew). The conflict phrase lists are also bilingual. However, they are maintained as two separate lists within the same array rather than a structured bilingual resource. As the app expands to other languages, this approach will not scale — a proper i18n approach for the phrase catalogs would be needed.

### `review_and_synthesize()` returns raw `UrgencyScore` and `ConflictReport` dataclass objects

Callers (like the Streamlit UI) receive live dataclass instances. This is convenient but means any code that tries to JSON-serialize the full result dict (e.g., storing chat history) would need to convert them first. The UI currently handles this by extracting only scalar fields before storing in `specialist_entries`. A cleaner approach would be to have `review_and_synthesize()` serialize these to plain dicts at the boundary.

### The Streamlit monkey-patch for live constitution editing is fragile

The live constitution editor in the sidebar works by monkey-patching `_ca_module.CONSTITUTION` around the `review_and_synthesize()` call. This is a shared-state hack that could produce incorrect results under concurrent users (Streamlit can run multiple sessions in the same process). For production use, the constitution and triggers should be passed explicitly as arguments rather than read from module globals.
