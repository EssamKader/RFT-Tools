# Token-Efficient Expansion — How to Add an Element Without Re-Reading Every Other One

Companion to `REUSE_GUIDELINES.md` and `docs/reuse-for-new-elements.md`. That
pair answers "is this piece of code reusable." This file answers a
different question: "how do we make sure that answer only ever gets worked
out ONCE, in writing, instead of being re-derived by reading source code
every time a new element starts."

Nothing here changes any detailing rule, spec, or architecture decision. It
is process only.

---

## The core problem this solves

The first time a new element needs to know whether a shared `RFT.lib`
module applies to it, the honest way to answer is to open the other
element's source and check. That is correct and expected — it is the
reuse audit working as intended.

The waste happens if the SAME question gets re-answered the SAME way for
the NEXT element too, because the first answer was only ever spoken in a
chat session and never written down anywhere the next session can find it.
A conclusion that lives only in a past conversation is invisible to a
fresh session and costs the same tokens to re-derive as if it had never
been worked out at all.

**Rule: every reuse conclusion is written down exactly once, as a
committed file. Every session after that cites the file. Nobody re-reads
source code to re-answer a question that already has a written answer.**

---

## 1. Reuse audits are a committed artifact, not a chat answer

When a new element's development needs to know whether an `RFT.lib`
module applies to it, the conclusion is recorded in
`docs/<element>/reuse-audit.md` before implementation proceeds — not left
to live only in that session's conversation.

**Format — keep it a table, not prose:**

```markdown
# Reuse Audit — <Element>

| Module | Status | Reason |
|---|---|---|
| `rft.core.spacing` | Reusable, confirmed | Vertical spacing math is dimension-agnostic. |
| `rft.core.anchorage` | NOT reused | <Element> has no supported/unsupported end condition; see spec §10. |
| `rft.core.stirrups` | Partial | Outer closed shape reusable; inner-tie subset logic is new (spec §6.2). |
```

Once this file exists, the NEXT element's session reads this one short
table instead of opening the current element's actual source files to
re-derive the same conclusions. If a later element needs to check
something this table doesn't cover, extend the table — don't re-audit
what's already answered.

**A "NOT reused" verdict must be checked against the resolved import
graph, not just the module's own import statements.** A real defect
surfaced during the column tool's development: `column_inputs.py` never
imports `anchorage.py` directly, but it imports `grades.py`, which imports
`guards.py`, which imports `anchorage.py` — so the non-reuse rule was
silently broken two hops away, and a guard checking only
`column_inputs.py`'s own AST passed anyway. When a reuse audit marks a
module "NOT reused," verify that empirically — `import the_module` and
check what actually landed in `sys.modules` — not by reading only that
one file's own `import` lines. The same standard applies to any guard
written to enforce a non-reuse rule: test the resolved dependency, not
the one file's source text.

---

## 2. `CONTEXT.md` stays layered — never let element-specific detail
   leak into the repo-root file

- **Repo-root `CONTEXT.md`**: rules that are true for every element,
  full stop (mutation-proven guards, pyRevit-extension-only, spec-is-
  source-of-truth, tag-means-verified). Nothing element-specific belongs
  here — the root file is loaded by Claude Code at the start of every
  session regardless of what's being worked on, so anything beam-only
  sitting in it is a cost paid on every column session too, forever.
- **`<Element>.extension/CONTEXT.md`**: standing rules specific to that
  one element (its non-reuse list, its open spec items, its own
  verification status).

If a rule ever applies to only one element, it belongs in that element's
own `CONTEXT.md`, never the root one. If it turns out to apply to a second
element too, promote it to root at that point — don't pre-emptively
generalize a rule to root before there are two elements that actually
need it.

---

## 3. Scope it in the ticket text — that's what actually reaches the
   implementer, not your orchestrating session

If you're running a delegation-based workflow (e.g. `ai-kaderskill`'s
Scope → ... → Implement → Review cycle), the implementer subagent in the
Implement phase does NOT inherit your orchestrating session's
conversation. It only receives what the ticket itself says. That means
the file-scoping instruction has to live in the **ticket text written
during To-Spec/To-Tickets**, not in something typed fresh at the start of
each session — there is no "start of session" for the subagent to hear it
at.

**Template — build this into the ticket body itself, not a separate
message:**

```
This is an `element:<name>` ticket.

Relevant files:
- specs/<element>-rft-detailing.md (§<section>)
- RFT.lib/rft/core/<specific module>.py
- <Element>.extension/CONTEXT.md

Do NOT open any other element's `.extension/` folder unless this ticket
explicitly requires a reuse check against docs/<element>/reuse-audit.md.
If the audit doesn't yet cover a module you need, say so and stop —
don't read the other element's source to answer it inline.
```

If you're NOT running a delegation-based workflow — a plain Claude Code
or claude.ai session doing the implementation directly — the same
template still applies, just typed at the start of that session instead
of embedded in a ticket, since there the session IS the thing doing the
work and does need telling directly.

Either way, the last line matters: it tells whoever's implementing to
surface a gap in the audit as a question, rather than quietly doing the
expensive cross-element read itself and moving on.

---

## 4. Session/context boundaries — match them to how implementation
   actually happens, not to a fixed rule

There is no single right answer here independent of your workflow; the
two paths below produce genuinely different correct behavior.

**If a delegation skill handles implementation (e.g. `ai-kaderskill`
Phase 7):** don't manually end and restart the orchestrating session
between tickets. The orchestrator's whole value is the continuity it
holds — the open ticket list, triage labels, decisions already made in
this run's Wayfinder phase — and restarting throws that away. The
skill's own answer to rising context is explicit: run `/compact`
instead of ending the session, preserving `CONTEXT.md` and this run's
Wayfinder decisions. The reason this doesn't cost what it looks like it
should: implementation itself already runs in the subagent's own
separate context (Phase 7 delegates, it doesn't implement in the main
thread), so the orchestrating thread was never carrying five tickets'
worth of coding detail in the first place — only their ticket text and
outcomes.

**If there is no delegation layer** — a single continuous session doing
both planning and implementation itself — the original concern still
applies: a session that's already worked through several unrelated
tickets is resending all of that history on every turn. There, starting
fresh per ticket (pointed at the ticket's own scoped file list, per §3)
is the cheaper path.

**Either way:** a genuinely continuous piece of work — spec negotiation,
debugging one issue across several turns, one ticket's Implement+Review
pair — stays in one session/one subagent call. The distinction is never
about fragmenting related work; it's about not letting UNRELATED work
accumulate in a context that doesn't need it.

---

## 5. Point at functions and line ranges, not whole files

When you need Claude to check something specific ("does `spacing.py`'s
`vertical_spacing_mm` function handle a column-sized input"), name the
function. Asking it to "review `spacing.py`" when only one function
matters means reading the whole file, docstrings and all, to answer a
question that only needed ten lines.

---

## 6. `.claude/agents/` — hard-scope it, don't just ask nicely

A prompt-level scope (§3) can still be ignored if a task seems to
genuinely require looking further. A **subagent** configured with
restricted file/tool access cannot open what it isn't given access to,
regardless of what the task seems to need. If a per-element subagent is
worth setting up, its config should:

- Restrict file read/write access to `RFT.lib/` + that element's own
  `.extension/` folder + `specs/<element>-*.md` + `docs/<element>/`.
- Explicitly exclude other elements' `.extension/` folders.
- Be invoked for any ticket labeled with that element.

This is the only mechanism here that enforces scope structurally rather
than by instruction — worth building out once there are three or more
elements and the discipline of re-typing the §3 template every session
starts to feel repetitive.

---

## 7. Build the single-source-of-truth module BEFORE the second consumer
   exists, not after

The beam tool's costliest bug (`ZONE_LAYOUT_FLAGS` drifting between the
report and the placer) happened because two consumers each independently
called the same underlying logic, and quietly diverged. The fix —
`core.plan` as the one object both the report and the placer read from —
was written after the fact, as a repair.

The cheap version of this fix is doing it BEFORE the second consumer is
written at all. Check this the moment an element has a report/preview
working and placement code is about to start: is there already one
composing module (a `<element>_plan.py`-equivalent) that both will read
from, or does the report call several core modules directly and the
about-to-be-written placer plan to call the same several modules
independently? If it's the latter, write the composing module first —
one ticket, before either consumer touches it again — rather than letting
two independent call sites exist even temporarily. Retrofitting this
after both consumers already exist costs far more than building it before
the second one does.

---

## 8. A tracer bullet only verifies what it actually executed

A tracer bullet that reads Revit state and rolls back every write (a
`SubTransaction` that's aborted, for example) has proven the READ side —
orientation, neighbour search, parameter values. It has proven NOTHING
about whether a WRITE (creating and keeping a `Rebar` element, an array,
a multi-loop set) behaves the same way. These are different classes of
API risk, and a "tracer bullet done, mechanics proven" note in a
verification doc should say which side it covers. Before any placement
code is written against an assumption about write behavior, run a
second, separate tracer bullet that performs the actual write and keeps
it (does not roll back) — don't let a read-only tracer bullet's success
be read as covering the write path too.

---

## Quick checklist — starting work on a new or existing element

- [ ] Does `docs/<element>/reuse-audit.md` exist? If not and this ticket
      needs a reuse answer, create it as part of this ticket — don't
      answer the question in chat only.
- [ ] For every "NOT reused" verdict in that audit, has it been checked
      against the resolved import graph (actually import the module and
      inspect `sys.modules`), not just that module's own import
      statements?
- [ ] Is everything element-specific in `<Element>.extension/CONTEXT.md`,
      not the root one?
- [ ] Does the ticket text (or, with no delegation layer, the session
      prompt) name the specific files relevant to this ticket, and
      explicitly forbid reading other elements' source?
- [ ] Running a delegation skill? Don't restart the orchestrating
      session between tickets — use `/compact` if context is climbing.
      No delegation layer? Start fresh per ticket instead.
- [ ] If a subagent exists for this element, is the ticket routed to it?
- [ ] If this ticket is the first placement/write code for an element
      that already has a report, does a single composing "plan" module
      exist for both to share — built now, not retrofitted later?
- [ ] If this ticket relies on an earlier tracer bullet, did that tracer
      bullet actually exercise a write (kept, not rolled back), or only
      a read? Don't treat a read-only proof as covering write behavior.

---

## Status in this repo, at the time this file was committed

Recorded once so the next session reads a line here instead of re-deriving it.

| Item | State |
|---|---|
| §1 `docs/<element>/reuse-audit.md` | **Exists** for the column (`docs/column/reuse-audit.md`). The beam predates the practice and has none; it is the audited-against element, not the auditing one, so one is only needed if a third element asks a question the column's table does not already answer. |
| §1 resolved-import-graph check | **Open defect — #99.** `column_inputs.py` reaches `anchorage.py` two hops away through `grades` → `guards`, and the guard that was supposed to forbid it reads only `column_inputs.py`'s own AST. This is the exact failure §1 describes, and it is ticketed rather than fixed here. |
| §2 layered `CONTEXT.md` | **Done in this commit.** The beam's standing rules moved out of the root file into `SimpleBeamRFT.extension/CONTEXT.md`; the root file now carries only the five repo-wide rules and the routing table. |
| §3 ticket-level file scoping | **Not yet in the ticket template.** Tickets name their spec sections but do not carry the "do not open another element's `.extension/`" line. |
| §6 `.claude/agents/` hard scoping | **Partial.** `implementer.md` exists and is beam-shaped; it is scoped by instruction, not by restricted tool access. The threshold this file names — three elements — has not been reached. |
| §7 single composing module | **Not yet needed, and about to be.** The column has a Review report (#91) and a sketch (#90) reading `column_spacing`, `column_layout`, `column_tie_levels` and `column_ties` directly. There is no placer yet, so the composing module can still be built **before** the second consumer exists rather than retrofitted after — which is what this section asks for. |
| §8 read-only vs write tracer bullet | **Read side only.** #69 proved reads inside a rolled-back `SubTransaction`. **Nothing has proven a kept write**, and no placement code exists yet. |
