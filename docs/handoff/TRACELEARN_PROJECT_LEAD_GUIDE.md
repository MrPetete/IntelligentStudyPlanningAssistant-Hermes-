# TraceLearn — Project Lead Guide

For the project owner (you). You designed the product, the architecture, the Hermes
agent, the scope, and every frozen decision. This guide defines how you should show
up during the 48-hour execution sprint so that strength becomes an advantage, not a
bottleneck.

---

## Recommended role: Hybrid Technical Lead + Coordinator

You are **not** a heads-down implementer, and you are **not** a hands-off PM. You are
the person who owns the spine of the system and keeps three people aligned around it.

### Your five responsibilities

1. **Own architecture decisions.** You are the final word on the frozen design. If a change is genuinely needed, it goes through `06_DECISION_REGISTER.md` — nothing drifts silently.
2. **Own the Agent/backend core.** Take the highest-leverage technical seam personally: the **orchestrator + the frozen contracts**. This is where your Hermes and architecture knowledge is irreplaceable.
3. **Maintain scope control.** Guard the MoSCoW list. Every proposed addition is measured against the 48-hour MVP and the demo. "Future" means documented, not built.
4. **Coordinate integration.** You own the integration order and the seam between A/B/C. Freeze the 3 JSON shapes in hour 1; sequence the real-LLM wiring; unblock whoever is stuck.
5. **Protect the demo narrative.** The grade is decided in ~5 minutes: evidence → decision → version → explanation → trace. Rehearse it; ensure the recorded fallback exists.

---

## The warning: do NOT become the only developer

You carry the most context, which makes it tempting to do everything. That is the
single biggest risk to this project — it creates a bottleneck and a single point of
failure. Actively push work out:

**Delegate:**
- **CRUD / routers / plumbing** → shared backend work, not your focus.
- **UI details** → Member B owns every screen and pixel.
- **Prompt refinement** → Member C owns the three generation prompts and their tuning.

**Keep for yourself:**
- **The Agent loop** — orchestrator, the decision point, the deterministic control split.
- **The contracts** — `schemas.py` shapes; freeze and publish them.
- **Integration** — order, seams, unblocking, and the demo.

---

## Practical stance during the sprint

- **Hour 1:** run the seed→simulate loop yourself, freeze the 3 shapes, publish them. This is the highest-leverage hour of the whole sprint.
- **Transfer context, don't hoard it.** The role packages and AI handoff prompts exist so A/B/C can operate without asking you constantly. Point people at them.
- **Say no on scope, yes on unblocking.** Your two most common sentences should be "that's Future — noted in the register" and "here's the shape you need."
- **Watch the critical path.** The agent loop is the deepest work and the demo's core. If it slips, invoke the failure plan (−25% / −50%) rather than cutting the trace.

If you do this well, you are not the busiest person on the team — you are the reason
the other two are never blocked and the demo tells one clean story.
