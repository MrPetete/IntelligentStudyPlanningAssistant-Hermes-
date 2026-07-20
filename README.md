# TraceLearn

**Material-Grounded Personal Learning Path Agent**

TraceLearn transforms a learner's goal and learning materials into an
executable roadmap, then continuously improves that roadmap using real
learning evidence while explaining every change. The product is **the
trace**: evidence → Hermes Agent decision → new plan version → written
explanation → version history.

This is a university internship project. The architecture is **frozen** —
see `docs/foundation/` before changing anything structural.

## Read first

1. `docs/foundation/01_SHARED_CONTEXT.md` — product foundation, frozen loop, glossary
2. `docs/foundation/02_AGENT_BACKEND_CONTEXT.md` — schema, the 7 tools, triggers, validator
3. `docs/foundation/06_DECISION_REGISTER.md` — locked decisions, rejected ideas
4. `docs/handoff/SONNET_IMPLEMENTATION_HANDOFF.md` — implementation entry point

## Repository layout

```
TraceLearn/
├── README.md
├── docs/
│   ├── foundation/     product + agent + data + decision docs (00–06)
│   ├── handoff/        AI-assistant handoff packages, checklists, project-lead guide
│   └── roadmap/        team roadmap (HTML)
├── backend/            FastAPI app, Hermes Agent, SQLModel schema, seed + tests
│   ├── agent/          7 tools, triggers, validator, orchestrator, llm_client
│   ├── routers/        REST endpoints
│   ├── seed/           seed.py / simulate.py — demo loop without live LLM or HTTP
│   └── tests/          unit tests for triggers.py / validator.py (pure, no DB/LLM)
├── frontend/           Vue 3 scaffold notes + API contract (Member B)
├── data/               reserved for future material/sample datasets
└── .gitignore
```

## Running the backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows PowerShell (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt

uvicorn main:app --reload           # http://127.0.0.1:8000/health, /docs

python tests/test_triggers_validator.py   # pure unit tests, no DB/LLM
python -m seed.seed                       # goal + concepts + Roadmap V1
python -m seed.simulate 1                 # inject failure -> Agent -> V2
```

`MOCK_LLM = True` in `backend/config.py` means no API keys or network access
are needed for any of this. See `backend/README_BACKEND_SEED.md` for the full
file-by-file breakdown of what's implemented vs. stubbed vs. deliberately not
built.

## What must never change without team discussion

1. The 7-tool set (5 read, 2 write) and the 2-write-tool limit.
2. Deterministic orchestration — never free-form autonomous tool looping.
3. The append-only `plan_versions` invariant.
4. The concept-map-as-spine design and `canonical_term` as the join key.
5. Recording an `agent_decisions` row on every invocation, including `no_change`.
6. The MVP scope fence: no RAG, no OCR, no multi-document, no full UI i18n, no
   multi-agent system.

See `docs/foundation/06_DECISION_REGISTER.md` for the complete list and the
reasoning behind each.
