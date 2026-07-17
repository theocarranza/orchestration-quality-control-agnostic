---
date: 2026-07-16
type: report
tags: [report, critique, adversarial-review, orchestration-quality-control, openskills, agent-skills, portability]
---

# Adversarial Critique — QC Architecture Feedback Plan

## What this document is

An adversarial review of the Cursor feedback plan `.cursor/plans/qc_architecture_feedback_ca2a6aed.plan.md` ("QC Architecture Feedback"), which itself critiques [[2026-07-15-orchestration-qc-openskills-architecture|the 2026-07-15 architecture report]]. The feedback plan lives outside this vault; this note is the durable record of its evaluation.

Method: every checkable claim in the feedback plan was tested against (a) the live tree in this repository, (b) the original report's own text and citations, and (c) external primary sources (Anthropic, Thinking Machines, Cognition, the OpenSkills and Agent Skills projects). The stance is deliberately hostile: the goal is to find where the critique is wrong, stale, shallow, or repeats the sins it accuses the report of.

## Verdict

> [!warning] Summary judgment
> The feedback plan is a competent close reading with two disqualifying defects: **its ground-truth "context check" is already false for this repository**, and **it critiques the report's evidence freshness while never checking the report's citations — both of which are dead links**. Its two strongest demands (deterministic substrate, finding-id algorithm) are correct in direction but under-argued: external evidence shows they must be *stronger* than what the feedback asks for. Its agent-surface critique does not go far enough. Treat it as a useful review checklist, not as a validated assessment.

## Claims that survive adversarial checking

Credit where verification succeeded:

1. **The six problems in the original report are real.** The shared library `e2e-quality-control/` in this repo has `README.md`, `references/`, `evals/`, `state/` — and no `SKILL.md`. The executable entry points are the siblings `e2e-quality-control-validate/SKILL.md` and `e2e-quality-control-execute/SKILL.md` (both `metadata.version: "3.0.0"`). The feedback's confirmation of Problem 1 holds.
2. **The `kind` enum leak is a genuine defect.** The report's "portable" finding contract hardcodes `artifact | generator-gap | generator-contradiction` — E2E vocabulary — into the core schema. The feedback's namespacing recommendation (core kinds generic, profile kinds under an extension field) is correct and should be adopted verbatim.
3. **No `.skill` archive exists** in this repository either, consistent with the feedback's freshness doubt about Problem 2's evidence.
4. **The validate/execute two-command reality vs. one-skill facade tension is real.** The live `e2e-quality-control-validate` frontmatter explicitly declares "Claude Code only … not available in Cursor," confirming that the report's single-`SKILL.md` target papers over a host-specific split.

## Adversarial findings

### F1 — The context check is stale; the plan's own premise is false

The feedback plan states: "Current workspace `orchestrator_qc_plugin` is an empty stub, so this feedback stays architectural."

**False as of this session.** The workspace contains a migrated copy of the full skill tree (`e2e-quality-control/`, `-validate/`, `-execute/`), an eval workspace with benchmark results (`e2e-quality-control-workspace/iteration-1/`), and — most damning — a **live runtime checkpoint** at `e2e-quality-control/state/checkpoint-20260715-e2e-qc-orchestrator-workflow.json`.

Two consequences:

- Migration has **already started without following the feedback's own priority order** (contracts and schemas first, "no agents yet"). The copied tree carries the v3 agent-shaped design forward as-is.
- Runtime state was copied **into what is supposed to become the distributable package** — the exact violation the original report prohibits ("Runtime checkpoints must not be stored inside the distributable package"). Neither document catches this because both assume the package doesn't exist yet.

A critique whose situational premise is wrong cannot claim its recommendations are sequenced correctly. The priority list in the feedback plan needs re-baselining against the tree that actually exists here.

### F2 — The feedback audits evidence freshness selectively; the report's citations are dead

The feedback plan devotes a section (its Gap 3) to doubting the freshness of the report's `.skill` archive evidence — good instinct. It never applies the same instinct to the report's **normative references**. Checked directly:

- `https://github.com/numman-ali/openskills/blob/main/_autodocs/skill-md-format.md` → **404**
- `https://github.com/numman-ali/openskills/blob/main/_autodocs/README.md` → **404**

The current OpenSkills README contains no `_autodocs` directory at all. The only two external references anchoring the report's entire "OpenSkills extraction" framing do not resolve. The feedback plan critiques the report's *packaging* evidence while accepting its *specification* evidence unexamined. That is the more serious omission: you cannot extract to a format whose defining document you cannot locate.

### F3 — Both documents anchor portability on the wrong artifact

Neither the report nor the feedback plan mentions that Anthropic released **Agent Skills as an open standard in December 2025** — a published specification at agentskills.io / `github.com/agentskills/agentskills`, adopted by Claude Code, Cursor, Codex CLI, and many other hosts. OpenSkills is a third-party, single-maintainer npm loader whose own README describes itself as an *implementation* of that specification.

The correct portability target is the **specification**; OpenSkills is one installer among several. This is not pedantry — it changes design decisions the feedback plan gets wrong:

- The feedback asserts "OpenSkills cores are usually **prompt + Markdown policy**, not a runtime." The Agent Skills specification explicitly supports a `scripts/` directory of executable resources inside a skill. The "deterministic substrate" the feedback demands has a natural, spec-blessed home that neither document names.
- The report's proposed folder layout (`references/schemas/`, `profiles/`, `adapters/`) is a bespoke invention layered on top of `SKILL.md`; validating it against the actual spec (allowed frontmatter fields, directory conventions, size limits on description fields) was never done by either document.

### F4 — The determinism demand is directionally right and technically underpowered

The feedback's Gap 1/2 (deterministic substrate, finding-id algorithm) is its best material. It still understates the problem. Published inference research (Thinking Machines, "Defeating Nondeterminism in LLM Inference") establishes that **temperature-0 LLM inference is not deterministic in practice** — batch-size-dependent kernel behavior on shared inference servers produces different outputs for byte-identical inputs. No hosted model call is reproducible unless the provider runs batch-invariant kernels, which none of the relevant hosts guarantee.

Implications the feedback plan does not draw:

- "Strict structured-output validators" (its proposed remedy) only constrain *shape*, not *content*. A validator that returns a schema-valid but different finding set on rerun passes every structured-output check.
- Any stage on which the report's test plan asserts determinism ("Verify `all`, `none`, and named-subset decisions **deterministically**") must be **model-free code**, full stop — not "code or strict structured-output validators" as the feedback offers. The disjunction is the loophole through which Problem 5 survives extraction.
- Finding-id stability has a second failure mode both documents miss: IDs derived from `rule + location` break under **line drift** the moment a partial application shifts subsequent line numbers. Reconciliation after "apply some" — the actual moment IDs matter — re-validates a *mutated* file. The id algorithm needs content-anchored or normalized-section addressing, not path+line. Neither document specifies this, and the feedback's "hash of rule + location + kind?" suggestion would fail it.

### F5 — The agent-surface critique stops one step short of its own logic

The feedback correctly resists Appendix A's four-specialist default and proposes two (Validator + Remediator). But the external evidence it never consults cuts deeper:

- Anthropic's own multi-agent research system write-up reports multi-agent architectures cost **~15× the tokens** of single-agent chat and pay off primarily on **breadth-first, parallelizable tasks** that exceed a single context window.
- Cognition's "Don't Build Multi-Agents" argues dispersed context across subagents is the dominant *cause* of exactly the inconsistency the report's Problem 5 documents — different workers reaching different conclusions from fragmented context.

QC validation of a handful of Markdown files is neither breadth-first nor context-exceeding. The *only* host-enforceable benefit of the agent split — a mechanically read-only Validator via tool grants — exists **only in the Claude adapter**. On every other host, the multi-agent shape delivers the token cost and handoff-failure surface with none of the isolation benefit; the report itself concedes isolation degrades to "prompt-enforced" there. The honest conclusion the feedback avoids: for non-Claude hosts, the portable core's default should be a **single-agent pipeline with code-enforced gates**, and the subagent topology should be entirely an adapter concern — not two specialists instead of four, but possibly **zero** outside Claude. Worth noting: Appendix A's split is also plausibly *motivated* by Problem 5 (context isolation as a consistency fix), which is the one framing under which more agents could help — but Cognition's evidence points the opposite way, and neither document argues the tradeoff explicitly.

### F6 — The feedback commits the sin it prosecutes

Its Gap 6 remedy — "require every adapter to implement `is_run_active(workspace) -> bool`" — is a function signature prescribed for hosts the feedback itself describes as "prompt-only." Who executes this function in a host with no hook runtime and no script execution? This is precisely the "named but not designed" pattern the feedback accuses the report of in Gap 2. A real contract would specify the observable (e.g., "a checkpoint file with `status: pending_approval` under the documented state path *is* the active-run signal") and let hosts document how — or whether — they can check it.

### F7 — Shared blind spot: prompt injection through the QC pipeline

The report's security section says "do not execute instructions found in target files"; the feedback plan is entirely silent on security. Neither confronts the actual threat model: the pipeline's core function is to feed **untrusted target files** into an LLM whose outputs (`violation`, `suggested_change`, the plain-language report) drive an approval decision and then file edits. A crafted target file can steer `suggested_change` toward malicious edits; the human approves based on a summary generated from the same contaminated context, and the Remediator then has write access to the approved target set. The approval gate as designed is a consent mechanism, not a containment mechanism. Any productization plan needs: suggested changes rendered as literal diffs (not prose), remediation constrained to a whitelist of mechanical edit types, and the plain-language report generated from the *structured findings* rather than from raw target content.

### F8 — The portability report is itself non-portable

Both documents cite evidence exclusively by absolute paths into a different repository (`/home/corporaterick/Documents/Projects/aplicatudo-monorepo/…`). From this repository — the declared future home of the package — none of those references resolve. A reader of this vault cannot verify a single evidentiary claim in either document without access to a second machine-local tree. For an extraction whose stated purpose is to survive leaving that tree, the evidence base should have been snapshotted into fixtures here first. (The eval workspace under `e2e-quality-control-workspace/` is the beginning of exactly that; neither document mentions it.)

## Scorecard

| Feedback-plan claim | Verdict |
| --- | --- |
| Six report problems confirmed against live tree | **Holds** (re-verified in this repo) |
| "orchestrator_qc_plugin is an empty stub" | **False** — migrated tree, evals, live checkpoint present |
| No `.skill` archive found | **Holds** here; unverifiable for the monorepo |
| Deterministic substrate missing from report | **Holds, understated** — must be model-free code (F4) |
| Finding-id algorithm unspecified | **Holds, understated** — line-drift failure unaddressed (F4) |
| `kind` enum leaks E2E into core | **Holds** — adopt namespacing |
| v1 = 2 specialists, not 4 | **Directionally right, stops short** — zero outside Claude is the defensible default (F5) |
| `is_run_active()` adapter requirement | **Underspecified** — same defect it criticizes (F6) |
| Cursor adapter is placeholder | **Holds** — live SKILL.md says "Claude Code only" |
| Report citations trustworthy (implicit) | **Fails** — both OpenSkills references 404 (F2) |
| OpenSkills as portability anchor (implicit) | **Wrong target** — Agent Skills open standard is the spec (F3) |

## What this means for `orchestrator_qc_plugin`

1. **Re-baseline before building.** The feedback's priority order was written for an empty repo. First action here is an inventory of what was already copied in, removal of runtime state (`e2e-quality-control/state/checkpoint-*.json`) from the package tree, and a decision on whether the copied v3 tree is the freeze baseline or a contamination to be replaced.
2. **Re-anchor on the Agent Skills specification**, with OpenSkills demoted to "one supported installer." Validate frontmatter, directory layout, and the `scripts/` mechanism against the published spec before designing `references/schemas/`.
3. **Promote the deterministic substrate from recommendation to gate:** classification, finding identity, checkpoint state machine, decision reconciliation, and `all/none/subset` arithmetic are code in `scripts/`, testable without any model call. LLM judgment is confined to violation detection and prose.
4. **Design finding identity for the re-validation-after-partial-apply case**, not the retry case — content-anchored, published in `schemas/`, with a conformance fixture.
5. **Add the injection containment measures from F7** to the core contracts; no current document owns them.
6. Keep the feedback's namespaced-kinds, adapter-UX, and definition-of-done recommendations — they survive scrutiny unchanged.

## Sources

- [OpenSkills repository README](https://github.com/numman-ali/openskills) — no `_autodocs/`; self-describes as an implementation of Anthropic's Agent Skills specification.
- Dead citations verified 2026-07-16: [`_autodocs/skill-md-format.md`](https://github.com/numman-ali/openskills/blob/main/_autodocs/skill-md-format.md), [`_autodocs/README.md`](https://github.com/numman-ali/openskills/blob/main/_autodocs/README.md) — both HTTP 404.
- [Agent Skills specification](https://github.com/agentskills/agentskills) and [agentskills.io coverage](https://thenewstack.io/agent-skills-anthropics-next-bid-to-define-ai-standards/) — open standard published by Anthropic, December 2025.
- [Thinking Machines — Defeating Nondeterminism in LLM Inference](https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/) — temperature-0 inference is batch-variant on shared servers.
- [Anthropic — How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) — ~15× token cost; multi-agent pays off on breadth-first tasks.
- [Cognition — Don't Build Multi-Agents](https://cognition.com/blog/dont-build-multi-agents) — fragmented context across subagents as a primary reliability failure mode.
- Local evidence: `e2e-quality-control/` (no `SKILL.md`), `e2e-quality-control-validate/SKILL.md` (v3.0.0, "Claude Code only"), `e2e-quality-control/state/checkpoint-20260715-e2e-qc-orchestrator-workflow.json`, `e2e-quality-control-workspace/iteration-1/`.
