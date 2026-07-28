# TraceLearn

**Material-Grounded Personal Learning Path Agent**

*English version below. 中文版本见文末 [中文说明](#中文说明)。*

---

## English

TraceLearn is a full-stack AI application built as a university production
internship project. It turns a learner's goal (and, optionally, their own
study material) into an executable learning roadmap, then evolves that
roadmap over time using real learning evidence — while always explaining
*why* the plan changed.

Most "AI study planner" tools stop at generating a plan once. TraceLearn's
differentiator is the trace itself: every plan change is triggered by
evidence (missed tasks, quiz results, time spent), reasoned about by an
agent, checked by a deterministic validator, and recorded with a
human-readable explanation and a full version history. The plan can always
answer the question "why did this change?"

This is a 3-person team project (Member A / B / C — see
[Team & division of labor](#team--division-of-labor) below).

### What it does

1. **Set a goal** — learner enters a goal, a deadline, and how many hours a
   day they can study (optionally in Chinese or English).
2. **Upload material (optional)** — a PDF or TXT file of study material. If
   no file is uploaded, the system still works by generating concepts from
   the goal topic itself.
3. **Confirm the concept map** — the system extracts a list of concepts from
   the material (or goal), and the learner reviews/edits it before anything
   else happens. This confirmed concept map is the backbone of the whole
   system — every diagnostic question, task, and piece of evidence is tied
   to a concept.
4. **Take an initial diagnostic** — a short quiz that produces a per-concept
   mastery estimate.
5. **Get Roadmap V1** — a day-by-day study plan generated from the goal,
   deadline, and diagnostic results.
6. **Study and record evidence** — the learner checks off tasks, takes
   checkpoint quizzes, and generates learning evidence as they go.
7. **The agent watches, not micromanages** — a set of deterministic rules
   (falling behind schedule, low mastery, failed quiz, etc.) decides *when*
   to wake the agent up. The agent (Hermes) then reads the evidence and
   decides whether the plan needs to change, and if so, proposes a new one.
8. **Every plan version is kept, never overwritten** — a new version is
   created (with a written explanation tied to the evidence that triggered
   it), and the learner can view the full version history and diff between
   versions.

### Architecture at a glance

```
Vue 3 frontend  <---REST/JSON--->  FastAPI backend  --->  SQLite
(Vite, ECharts,                    (SQLModel, deterministic       |
 vue-router, i18n)                  triggers + validator)         v
                                          |                  Hermes Agent
                                          |                  (7 tools: 5 read,
                                          v                   2 write; tool-
                                    Agent Decision Log        calling LLM)
                                    (append-only history)
```

Key design principles (frozen — see
[docs/foundation/06_DECISION_REGISTER.md](docs/foundation/06_DECISION_REGISTER.md)
for the full reasoning):

- **Deterministic code decides *when* and *whether it's valid*; the LLM only
  decides *what* and *why*.** The agent never runs unbounded — a
  deterministic trigger layer decides when to wake it, and a deterministic
  validator checks every plan it proposes before it's saved.
- **The agent's write access is small and guarded.** Only 7 tools exist: 5
  read-only (learner state, current plan, progress summary, evidence since
  last plan, material search) and 2 write (create a new plan version, record
  a decision). There is no tool that can directly edit progress or delete
  history.
- **Plan versions are append-only.** A replan always creates a new version
  linked to its parent; nothing is ever overwritten.
- **Every agent invocation is logged**, including when it decides nothing
  needs to change (`no_change` is a valid, recorded outcome).
- **The concept map is the spine of the system.** Materials, diagnostics,
  tasks, and evidence are all connected through concepts. The English
  `canonical_term` of a concept never changes even when the UI language
  does — only the learner-facing explanation text is localized (English/
  Chinese).

### Repository layout

```
TraceLearn/
├── README.md                  you are here
├── docs/
│   ├── foundation/             product, agent/backend, frontend, data
│   │                           contracts + the decision register (00-06)
│   ├── handoff/                AI-assisted development handoff docs
│   └── roadmap/                team roadmap (HTML)
├── backend/                    FastAPI app, Hermes Agent, SQLModel schema
│   ├── agent/                  7 tools, triggers, validator, orchestrator,
│   │                           replan scheduling, LLM client (mock + real)
│   ├── routers/                REST endpoints (goals, concepts, diagnostic,
│   │                           plan, evidence, decisions)
│   ├── seed/                   seed.py / simulate.py — demo the full evidence
│   │                           -> agent -> new plan loop without a live LLM
│   └── tests/                  backend test scripts (see backend/tests/)
├── frontend/                   Vue 3 + Vite + ECharts app
│   └── src/
│       ├── views/               Onboarding, Home, Roadmap, Dashboard,
│       │                        VersionHistory, DecisionView
│       ├── components/          CheckpointQuiz, ConceptTag, OfflineBanner
│       └── mock/                in-browser mock backend for frontend-only dev
├── data/                        reserved for material/sample datasets
├── docker-compose.yml           run backend + frontend together
├── .env / .env.example          LMU AI key + config (git-ignored — copy the example)
└── .gitignore
```

### Running it

#### Option 1 — local dev, no Docker (fastest for backend work)

```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows PowerShell (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt

uvicorn main:app --reload           # http://127.0.0.1:8000/health, /docs

python -m seed.seed                 # creates a demo goal + concepts + Roadmap V1
python -m seed.simulate 1           # injects a failure -> Agent -> new plan version
```

`MOCK_LLM=true` (the default) means none of this needs an API key or network
access — every LLM-backed step returns deterministic canned output. This is
also what the seed/simulate demo path relies on. See
`backend/README_BACKEND_SEED.md` for a full file-by-file breakdown of what's
real, what's stubbed, and what's deliberately not built.

In a separate terminal, run the frontend:

```bash
cd frontend
npm install
npm run dev                         # http://127.0.0.1:5173/
```

#### Option 2 — Docker Compose (backend + frontend together)

```bash
cp .env.example .env                # fill in ANTHROPIC_API_KEY etc. if using a real LLM
docker compose up --build

# Backend:  http://127.0.0.1:8000/health, /docs
# Frontend: http://127.0.0.1:5173/
```

To run the frontend fully offline against its built-in mock server instead of
the real backend, set `VITE_USE_REAL=false` in `frontend/.env`.

> **Known limitation:** under Docker, the SQLite database and uploaded files
> currently live inside the container filesystem rather than the mounted
> `./data` volume, so they reset on `docker compose down`/`--build`. This
> does not affect the local (non-Docker) `uvicorn` workflow. Tracked as a
> known issue, not yet fixed.

### What must never change without team discussion

1. The 7-tool set (5 read, 2 write) and the 2-write-tool limit.
2. Deterministic orchestration — never free-form autonomous tool looping.
3. The append-only `plan_versions` invariant.
4. The concept-map-as-spine design and `canonical_term` as the join key.
5. Recording an `agent_decisions` row on every invocation, including `no_change`.
6. The MVP scope fence: no RAG, no OCR, no multi-document, no full UI i18n, no
   multi-agent system, no authentication.

See `docs/foundation/06_DECISION_REGISTER.md` for the complete list and the
reasoning behind each.

### Team & division of labor

| Member | Role | Owns |
|---|---|---|
| Member A | Backend + Hermes Agent (technical lead) | `backend/agent/`, `backend/routers/`, `backend/models.py`/`schemas.py`/`db.py`/`config.py`/`main.py`, agent + decision-register docs |
| Member B | Frontend + Product | `frontend/src/views/`, `frontend/src/components/`, `frontend/src/api.js`, `frontend/src/i18n.js`, frontend product docs |
| Member C | Data / Material / Testing | `backend/ingestion.py`, `backend/storage.py`, `backend/seed/`, material-related tests, data contract docs |

See `docs/foundation/` for each member's detailed contract and
`docs/foundation/06_DECISION_REGISTER.md` for how responsibilities were
scoped up front so the three tracks could be built in parallel.

---

## 中文说明

TraceLearn（学迹）是一个作为大学生产实习项目开发的全栈人工智能应用。它将学习者的目标（以及可选的学习材料）转化为一份可执行的学习路线图，随后利用真实的学习证据持续调整这份路线图，并始终解释"计划为什么会变化"。

市面上大多数"AI学习计划"工具只做到一次性生成计划就结束了。TraceLearn的差异化之处在于"追溯"本身：每一次计划调整都由具体证据触发（如任务遗漏、测验结果、学习用时），经智能体推理判断，再由确定性校验器把关，最终以可读的解释文字与完整的版本历史记录下来。学习者随时可以回答"这个计划为什么变了"这个问题。

本项目由3人小组共同完成（Member A / B / C，具体分工见下方"团队与分工"）。

### 项目功能

1. **设定目标**——学习者输入学习目标、截止时间，以及每天可投入的学习时长（可选择中文或英文界面）。
2. **上传材料（可选）**——上传PDF或TXT格式的学习材料。若不上传材料，系统仍可基于目标主题本身生成概念图谱，流程不会中断。
3. **确认概念图谱**——系统从材料（或目标主题）中抽取一组概念，学习者需先审核/修改后才能进入后续环节。这份经确认的概念图谱是整个系统的核心骨架——每一道诊断题、每一项任务、每一条学习证据都与具体概念相关联。
4. **进行初始诊断**——一次简短测验，得到各概念的掌握度评估。
5. **获得第一版学习路线图**——根据目标、截止时间与诊断结果生成的按天拆分的学习计划。
6. **学习并记录证据**——学习者完成任务打卡、参加检查点测验，持续产生学习证据。
7. **智能体只在必要时介入，而非事事插手**——一组确定性规则（如进度滞后、掌握度过低、测验失败等）决定何时唤醒智能体。智能体（Hermes）随后读取证据，判断计划是否需要调整，若需要则提出新的计划。
8. **每一版计划都会被保留，绝不覆盖**——重新规划总是生成一个新版本（并附带与触发证据相关联的调整理由说明），学习者可以查看完整的版本历史与版本间的差异对比。

### 架构概览

```
Vue 3 前端       <---REST/JSON--->    FastAPI 后端        --->   SQLite
（Vite、ECharts、                    （SQLModel，确定性             |
 vue-router、i18n）                   触发条件+校验器）             v
                                            |                Hermes 智能体
                                            |                （7个工具：5只读、
                                            v                 2可写；具备工具
                                     智能体决策日志            调用能力的大语言模型）
                                     （只增不改的历史记录）
```

关键设计原则（已冻结——完整推理见
[docs/foundation/06_DECISION_REGISTER.md](docs/foundation/06_DECISION_REGISTER.md)）：

- **确定性代码决定"何时"与"是否合法"，大语言模型只决定"是什么"与"为什么"。** 智能体不会无限制地自主运行——由确定性的触发层判断何时唤醒智能体，由确定性的校验器在保存前检查它提出的每一份计划。
- **智能体的写权限收窄且受控。** 全系统仅有7个工具：5个只读（学习者状态、当前计划、进度摘要、上一版本之后的新证据、材料检索）与2个可写（创建新计划版本、记录一次决策）。不存在任何可以直接修改进度或删除历史记录的工具。
- **计划版本只增不改。** 每次重新规划都会生成与父版本关联的新版本，任何内容都不会被覆盖。
- **每一次智能体调用都会被记录**，包括判断"无需调整"的情况（`no_change`本身就是一个有效且被记录的结果）。
- **概念图谱是全系统的核心连接线。** 材料、诊断、任务与证据都通过概念相互关联。概念的英文规范术语（`canonical_term`）不随界面语言切换而改变，只有面向学习者的说明文字会做中英本地化。

### 目录结构

```
TraceLearn/
├── README.md                  当前文件
├── docs/
│   ├── foundation/             产品、智能体/后端、前端、数据契约
│   │                           以及决策登记表（00-06）
│   ├── handoff/                AI协作开发交接文档
│   └── roadmap/                团队路线图（HTML）
├── backend/                    FastAPI应用、Hermes智能体、SQLModel数据模型
│   ├── agent/                  7个工具、触发条件、校验器、调度器、
│   │                           重新规划调度、LLM客户端（模拟+真实）
│   ├── routers/                REST接口（目标、概念、诊断、
│   │                           计划、证据、决策）
│   ├── seed/                   seed.py / simulate.py——无需真实LLM即可
│   │                           演示"证据->智能体->新计划"完整链路
│   └── tests/                  后端测试脚本（见backend/tests/）
├── frontend/                   Vue 3 + Vite + ECharts应用
│   └── src/
│       ├── views/               引导页、主页、路线图、仪表盘、
│       │                        版本历史、决策详情
│       ├── components/          检查点测验、概念标签、离线提示条
│       └── mock/                供前端独立开发使用的浏览器内模拟后端
├── data/                        预留给材料/示例数据集
├── docker-compose.yml           同时启动后端与前端
├── .env / .env.example          LMU AI密钥与配置（已加入git忽略——请复制示例文件）
└── .gitignore
```

### 运行方式

#### 方式一——本地开发，不使用Docker（后端开发最快捷）

```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows PowerShell（macOS/Linux：source .venv/bin/activate）
pip install -r requirements.txt

uvicorn main:app --reload           # http://127.0.0.1:8000/health, /docs

python -m seed.seed                 # 创建演示目标+概念+第一版路线图
python -m seed.simulate 1           # 注入一次失败证据 -> 智能体 -> 生成新计划版本
```

`MOCK_LLM=true`（默认值）意味着以上流程都不需要任何API密钥或网络连接——每一个依赖大语言模型的环节都会返回确定性的预设结果，seed/simulate演示流程正是依赖这一点。完整的"哪些是真实实现、哪些是占位、哪些故意未实现"清单见 `backend/README_BACKEND_SEED.md`。

另开一个终端运行前端：

```bash
cd frontend
npm install
npm run dev                         # http://127.0.0.1:5173/
```

#### 方式二——使用Docker Compose（同时启动后端与前端）

```bash
cp .env.example .env                # 如需使用真实LLM，填入ANTHROPIC_API_KEY等配置
docker compose up --build

# 后端：http://127.0.0.1:8000/health, /docs
# 前端：http://127.0.0.1:5173/
```

若想让前端完全脱离真实后端、只对接内置的模拟服务器运行，在 `frontend/.env` 中设置 `VITE_USE_REAL=false`。

> **已知局限：** 目前在Docker环境下，SQLite数据库与上传文件实际保存在容器内部文件系统中，而非挂载的 `./data` 卷，因此在执行 `docker compose down`/`--build` 后会丢失。该问题不影响本地（非Docker）直接运行 `uvicorn` 的方式。这是已记录的已知问题，尚未修复。

### 不可随意变更的设计原则（需团队讨论后才能改动）

1. 7个工具的设定（5只读、2可写）以及"最多2个写工具"的限制。
2. 确定性编排——绝不允许自由形式的自主工具循环。
3. `plan_versions` 只增不改的不变性。
4. 概念图谱作为核心骨架、`canonical_term` 作为跨语言连接键的设计。
5. 每次调用都要记录一条 `agent_decisions`，包括"无需调整"的情况。
6. MVP范围边界：不做RAG检索、不做OCR、不支持多文档、不做完整界面多语言、不做多智能体系统、不做用户认证。

完整清单与每一条背后的理由见 `docs/foundation/06_DECISION_REGISTER.md`。

### 团队与分工

| 成员 | 角色 | 负责范围 |
|---|---|---|
| Member A | 后端 + Hermes智能体（技术负责人） | `backend/agent/`、`backend/routers/`、`backend/models.py`/`schemas.py`/`db.py`/`config.py`/`main.py`、智能体与决策登记相关文档 |
| Member B | 前端 + 产品 | `frontend/src/views/`、`frontend/src/components/`、`frontend/src/api.js`、`frontend/src/i18n.js`、前端产品相关文档 |
| Member C | 数据/材料处理 + 测试 | `backend/ingestion.py`、`backend/storage.py`、`backend/seed/`、材料相关测试、数据契约相关文档 |

每位成员的详细契约见 `docs/foundation/`，三条开发线如何提前划分职责以支持并行开发，见 `docs/foundation/06_DECISION_REGISTER.md`。
