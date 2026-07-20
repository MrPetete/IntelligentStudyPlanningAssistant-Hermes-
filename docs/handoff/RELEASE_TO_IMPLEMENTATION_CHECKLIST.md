# TraceLearn — Release-to-Implementation Checklist

The gate between the (frozen) architecture phase and the 48-hour implementation sprint.
Work top to bottom. Do not begin feature work until Foundation and Environment are green.

---

## Foundation

- [ ] **Docs frozen** — `00`–`06` present and internally consistent; HTML roadmap reflects the 48-hour sprint (not a 2-week plan).
- [ ] **Decision register updated** — `06_DECISION_REGISTER.md` current; all locked decisions and rejected ideas recorded; open items (framework, UI-chrome language, thresholds) noted.
- [ ] **Code seed available** — `app/backend/` present with agent layer, routers, models, schemas, seed; `app/frontend/` scaffold notes present.
- [ ] **Team packages prepared** — three ZIPs built and integrity-checked; handoff docs (`SONNET_IMPLEMENTATION_HANDOFF.md`, `GPT_WORK_IMPLEMENTATION_HANDOFF.md`) available.

## Environment

- [ ] **Python setup** — Python 3.11+; virtual environment created in `app/backend`.
- [ ] **Dependencies installed** — `pip install -r requirements.txt` succeeds (requires network/PyPI access).
- [ ] **Node setup** — Node 18+ available for the Vue 3 scaffold (Member B).
- [ ] **Database verified** — `uvicorn main:app --reload` starts; `/health` and `/docs` load; SQLite `tracelearn.db` is created on startup.
- [ ] **Seed simulation works** — `python -m seed.seed` then `python -m seed.simulate 1` produces a Version 2 plan **and** an `agent_decision` with an ordered tool trace. *(The one path unverified offline — verify first.)*
- [ ] **Pure tests pass** — `python tests/test_triggers_validator.py` (triggers + validator).

## Team

- [ ] **Member A package delivered** — `TraceLearn_MemberA_Agent_Backend.zip` (this is the project lead / Member A — same person on a 3-person team).
- [ ] **Member B package delivered** — `TraceLearn_MemberB_Frontend_Product.zip` + `START_IMPLEMENTATION_CHECKLIST.md`.
- [ ] **Member C package delivered** — `TraceLearn_MemberC_Data_Material_Testing.zip` + `START_IMPLEMENTATION_CHECKLIST.md`.

## Hour-1 shared decisions to record (in `06_DECISION_REGISTER.md`)

- [ ] Frontend framework confirmed (Vue 3).
- [ ] UI-chrome language chosen (monolingual per D19).
- [ ] Trigger threshold values (or keep config defaults for the sprint).

## Green-light condition

Foundation ✅ + Environment ✅ (especially the seed→simulate loop) + packages delivered
= cleared to start the sprint. Member A verifies the loop and freezes contracts in hour 1;
Members B and C start immediately against mocks and pure-function tests.
