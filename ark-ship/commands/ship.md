---
description: "Ship flow: inventory → pipeline mapping → doc sync → security audit → syntax & test gate → commit → cleanup → self-review"
---

# /ship — Structured Pre-commit Ship Flow

Follow every step in order. Do NOT skip steps. If a step produces a BLOCKER, stop and fix it before continuing.

This flow assumes the project has a `.claude/pipelines.json` registry (see README for setup). If the registry does not exist yet, skip Steps 2-3's pipeline-specific parts and run the generic checklist instead — but consider setting one up afterward.

**Verify-as-you-go principle**: Step 4 is the FINAL syntax/build check, not the ONLY one. As you work, verify each file compiles/parses right after editing it — don't save all verification for the end. Catching a syntax error 5 files in is much cheaper than catching it after you've written 10 files that depend on the broken one.

---

## Step 0 — Inventory

```bash
git status --short
git diff --stat
git diff --cached --stat
```

Partition output into two buckets:
- **(a) This session's work** — files you modified in this conversation.
- **(b) Foreign / unrelated changes** — files you did not touch. Could be from another branch, person, or session.

Rules:
- NEVER stage foreign changes into your commit. Leave them alone.
- If zero changes exist, say "Nothing to ship" and stop.
- Note any foreign changes for Step 7.

**Multi-session awareness**: If you see foreign changes (bucket b), it means someone else (or another Claude session) is working in the same repo. This is normal but dangerous — mixing their half-done work into your commit is how silent bugs happen. Partition carefully. When in doubt about whether a file is yours, check `git log --oneline -1 <file>` or ask the user.

Print the partition to the user before moving on.

---

## Step 1 — Pipeline Mapping

Run the deterministic mapper — do not eyeball-glob:

```bash
git status --short | python3 .claude/scripts/map_pipelines.py
```

The mapper reads `.claude/pipelines.json`, matches changed files to pipelines via glob patterns, and outputs per-pipeline hit lists with docs and rules. Files in the "unregistered" bucket deserve consideration: should `pipelines.json` gain a new entry?

Filter the output down to THIS session's files (Step 0 partition).

Output: the list of touched pipelines, with their docs and rules.

If `pipelines.json` does not exist, manually determine what areas the changes touch (frontend / backend / database / infra / docs) and proceed.

---

## Step 2 — Documentation Sync (per touched pipeline)

For EACH touched pipeline, check its documentation layers (configured in `pipelines.json`):

### Layer 1 — Project docs (`docs` field)
For each doc file listed in the pipeline's `docs` array:
- Does the architecture / flow / API description still match the code after this change?
- Are constant tables, config references, or example outputs still accurate?
- Update stale docs NOW, before proceeding.

### Layer 2 — External docs (`external_docs` field, optional)
If the pipeline has external documentation (wiki, design docs, Notion, GitHub docs):
- Are invariants / state overviews / cross-system references still accurate?
- Does this change deserve a decision record or changelog entry?

### Layer 3 — Status tracking (`keywords` field)
If the project uses a memory system, task tracker, or changelog:
- Grep `keywords` against the tracking system. Does any entry need its status updated?
- If the project uses Claude Code memory: update BOTH the index line AND the body file (a common mistake is updating one but not the other).

### Signature change summary

If this change modifies any **public interface** (API endpoints, function signatures, database schema, config format, message contracts), generate a one-line summary per change:

```
Signature change [api]: POST /users now requires `email` field (was optional)
Signature change [database]: users table adds NOT NULL column `verified_at`
```

Include these in the commit message body (Step 5) and cross-check: does the corresponding doc actually describe the new signature, not just "something was updated"?

### Rules compliance (`rules` field)
Verify each rule listed for the pipeline was honored by this change. Rules are project-specific invariants — e.g., "migration files must be idempotent", "API changes need version bump".

Fix all sync gaps BEFORE proceeding.

---

## Step 2.4 — Data Contract Alignment

If this change touches a **data boundary** — any point where two systems exchange data under an agreed format — verify the contract is still honored.

Data boundaries include:
- **API**: request/response schema (field names, types, required vs optional, enums)
- **Database**: column types, NOT NULL constraints, CHECK constraints, enum values
- **Inter-service**: message formats between frontend and backend, or between microservices
- **State machine**: valid state transitions (e.g., order status, user lifecycle)
- **Config**: .env keys, feature flags, compose service names

For each data boundary this change crosses, answer three questions:

1. **Contract honored?** Does the new code still produce/consume data in the agreed format? Watch for: renamed fields, changed types, new required fields without defaults, removed enum values, altered state transitions.

2. **All consumers updated?** If the contract DID change, are ALL systems on both sides of the boundary aware? A backend API change needs a frontend update. A DB schema change needs an ORM/model update. **List every consumer and verify each one.**

3. **Contract tested?** Is there a test, schema validation, or type check that would catch a future violation? If not, note it as a gap in the ship summary.

If a contract is broken and the other side is NOT updated → **BLOCKER**. Fix before proceeding.

If no data boundaries are touched, say so and move on.

---

## Step 2.5 — Code Review Gate

Trigger a code review recommendation if ANY of these conditions is true:
1. The diff touches **≥3 files**
2. The diff **spans multiple modules**
3. **Any touched pipeline has `criticality: "high"`** in `pipelines.json` — even a single-file change to a high-criticality pipeline (auth, database, payments) deserves review

If triggered and no code review was done this session, recommend running one now — it catches logic bugs and design drift that the security scan (Step 3) does not cover.

Skip for doc-only changes.

---

## Step 3 — Security Audit

Tell the user: "Starting security + robustness audit" — never run it silently.

If the project has a security auditor agent (`.claude/agents/security-auditor.md`), spawn it with:
- The Step 0 file list
- The **pipeline-specific rules** from Step 1's mapper output (the `RULE:` lines for each touched pipeline)

The auditor checks both its own universal checklist AND the pipeline rules. This way a database migration gets checked against "migrations must be idempotent" while a frontend change does not — and vice versa. The auditor reads the diff cold (no author bias) and returns `[BLOCKER|WARN|NOTE]` findings.

If no dedicated auditor agent exists, run the inline checklist below:

### Secrets & credentials
- [ ] No API keys, tokens, passwords, or connection strings hardcoded in source
- [ ] No `.env`, `.pem`, `.key`, credential files staged for commit
- [ ] No secrets in log/print/console statements
- [ ] Scan `git diff --cached` for high-entropy strings or patterns (`sk-`, `AKIA`, `ghp_`, `-----BEGIN`, `password=`)

### Injection & input handling
- [ ] No raw string interpolation in SQL (use parameterized queries)
- [ ] No unescaped user content in HTML templates (XSS)
- [ ] No `eval()` / `exec()` / `os.system()` / `subprocess(shell=True)` with user input
- [ ] No unsanitized file paths from user input (path traversal)

### Error handling
- [ ] Error responses don't expose stack traces, internal paths, or raw exceptions
- [ ] No `detail=str(e)`, `message: err.stack`, `res.send(error)` in user-facing handlers

### Network & access control
- [ ] New endpoints have auth checks (or explicit justification for being public)
- [ ] Service ports bind `127.0.0.1` unless intentionally public
- [ ] No debug routes, test endpoints, or dev backdoors left enabled
- [ ] CORS not set to `*` in production paths

### Robustness
- [ ] No blocking I/O inside locks or mutexes (use short timeout + skip)
- [ ] Batch / scan jobs have memory bounds (don't OOM a small server)
- [ ] Import paths verified — `from x.y import z` actually resolves (grep for the definition)

Verdict:
- Any `[BLOCKER]` → fix, then re-audit. Do not commit with known blockers.
- `[WARN/NOTE]` → judge and explicitly accept or fix, with stated reason.

---

## Step 4 — Syntax, Build & Test Gate

Run language-appropriate checks on ALL changed files:

| Language | Check |
|----------|-------|
| Python | `python -m py_compile <file>` per changed `.py` |
| TypeScript | `npx tsc --noEmit` or project typecheck script |
| JavaScript | Project lint (`npm run lint`, `eslint`) |
| Go | `go vet ./...` |
| Rust | `cargo check` |
| Java/Kotlin | `./gradlew compileJava` (watch memory on small servers) |
| Docker | `docker compose config -q` if compose files changed |
| YAML/JSON | Parse-validate changed files |

If any check fails → fix before continuing.

**Smoke test**: Beyond syntax, verify the changed code path doesn't crash on import or startup. For backend changes, confirm the server can start. For frontend changes, confirm the dev server renders the changed page. State what was smoked and the result.

**Test gate**: If the project has a test suite, pick the tier that matches what actually changed — and state in the ship summary which tier you picked and why. The real cost of always running everything isn't wall-clock; it's the attention spent parsing unrelated failures and arguing about whose red is whose.

1. **Skip** — the diff is docs / comments / log-wording only: no executable code, no config the runtime reads. Syntax checks + smoke are enough. Stronger still: if you can prove the compiled artifacts are byte-identical to the pre-change tree (e.g. comparing compiled code objects), cite that proof.
2. **Targeted (default)** — run the tests that own the changed code: the test files registered for the touched modules/pipelines, plus any test that imports or asserts on the changed symbols. Locate them by grepping for the symbols, not by filename resemblance — tests whose names don't match the module are exactly the ones a name-based mapping misses. A red in a targeted run is by definition yours: fix it. There is no "someone else's red" exemption here.
3. **Full** — required when the change touches a contract (function signature, API endpoint, DB schema), a config/serialization format, template or prompt text that tests assert on, a cross-module refactor, a migration, or the test files themselves.

**Full-run reds follow "no new reds", not "all green".** In repos with parallel sessions or people, some failures predate your change. Attribute every failure mechanically — re-run the exact failing test on the unchanged tree at the same HEAD:

- **New red** (fails with your change, passes without) → halt; fix before commit.
- **Pre-existing red** (fails identically without your change) → does not block this ship. List the failing tests plus the clean-tree reproduction in the ship summary, and make sure an owner or tracked task exists for them. Attribution must be reproduction evidence — never the impression that "this one isn't mine". That impression is exactly the self-serving judgment a shipping agent must not make alone.

**Precondition for the narrow tiers**: something out-of-band still runs the full suite on a schedule (CI, a daily cron with alerting on state flips). If nothing does, keep running the full suite at every ship — the gate is the only net you have.

- **Don't let one broken file mask the whole suite.** A single import/collection error can abort the entire run before any test executes (pytest: pass `--continue-on-collection-errors`), and that failure looks identical to "the suite never ran". The error still fails the gate — the flag only stops it from hiding the other results.
- **Report proof of execution.** Include the tier picked, pass/fail/skip counts, and wall time in the ship summary even when green — when "failed" and "never ran" look the same, the numbers are the evidence.

If there is no test suite, say so explicitly in the ship summary rather than silently skipping.

State what was checked and the result — honestly. Don't claim "all checks pass" without actually running them.

---

## Step 4.5 — Squash-on-ship prep (optional, for session-branch workflows)

**When this applies**: You committed incrementally during work — either directly on a session branch or inside a per-session worktree — and the mainline should record ONE milestone commit per shipped unit rather than the full incremental trail. **Skip this step** if you did not commit during work (dirty tree at ship time → go straight to Step 5's commit sub-steps), or if this repo is low-volume enough that every incremental commit stands on its own.

The idea: preserve the incremental commits as a **history branch** for audit and blame drill-down, and squash them into ONE milestone commit on mainline. Mainline stays legible; the detail is preserved on a side branch.

Assumes: session work happened on a branch you own (e.g., `session-<TAG>`), rebased onto `origin/main` is safe (no shared collaborators mid-branch), and force-pushing your own session branch is acceptable.

### 4.5.a Fetch and auto-rebase onto mainline

```
git fetch origin main
git rebase origin/main
```

If rebase conflicts → **abort ship**, resolve conflicts manually in the working tree, then retry `/ship`. Do NOT auto-continue — a half-rebased state is not shippable, and silent conflict resolution hides real intent collisions.

### 4.5.b Count commits ahead

```
N=$(git rev-list --count origin/main..HEAD)
```

- **N=0** → error "nothing to ship (0 commits ahead of mainline)". Abort.
- **N=1** → skip squash logic (single commit already IS the milestone). Optionally do 4.5.d for archival consistency, then jump to Step 5's push.
- **N>1** → continue with 4.5.c–e.

### 4.5.c Net-zero diff detection (N>1)

```
git diff origin/main..HEAD --quiet
```

Exit 0 means the commits mutually revert — N commits, zero net change. Warn: "N=X commits, diff net-zero. Push milestone anyway? [y/N]" default No. Answer No → abort (the "shipment" is empty). Answer Yes → continue, and flag it in the ship summary as an exploratory milestone (explicit user override, recorded so future audits see this wasn't a bug).

### 4.5.d Push history branch (all N ≥ 1)

```
git push origin <session-branch>:refs/heads/history/session-<TAG>
```

Preserves the pre-squash commit trail for audit / blame drill-down. Push even for N=1 so every ship has a corresponding history branch — mainline `Session:` trailers stay grep-symmetric (every trailer resolves to a real branch).

Retention: history branches accumulate. Add a periodic prune (e.g., a weekly cron that deletes `history/session-*` refs older than N months, with a `keep/` prefix as opt-out). Otherwise `refs/heads` grows unboundedly.

### 4.5.e Squash into one milestone (N>1 only)

Capture the pre-squash range for the trailer:
```
FIRST_SHA=$(git log --format=%h origin/main..HEAD | tail -1)
LAST_SHA=$(git log --format=%h -1 HEAD)
LAST_MSG=$(git log --format=%B -1 HEAD)
```

Soft-reset to mainline (keeps changes staged in one lump) and commit as one milestone with trailers:
```
git reset --soft origin/main
git commit --edit -m "$LAST_MSG

Squashes: $FIRST_SHA..$LAST_SHA ($N commits)
Session: <TAG>"
```

The editor pops so you can revise the milestone message. Defaulting to the last commit's message is usually right — the last commit tends to summarize the final landed state — but revise freely if the last message reads as a fixup rather than a milestone.

The `Squashes:` and `Session:` trailers give grep-free provenance: mainline commits point back to their history branch and their commit range, so a future `git log --grep='Session: <TAG>'` finds the milestone and the trailer body names the branch that holds the detail.

### 4.5.f Verify before Step 5

```
git log HEAD -1 --format="%h %s"
git log HEAD -1 --format="%B" | tail -5
```

Expected:
- HEAD is **exactly 1 commit ahead** of `origin/main`
- Message contains `Squashes:` and `Session:` trailers
- Subject is descriptive (not `tmp:`, `wip`, or a placeholder)

Any mismatch → abort ship, fix manually, retry.

---

## Step 5 — Commit

> **If Step 4.5 ran**: the milestone commit is already composed. Skip sub-steps 5a–5d and jump to the push discussion at the end of 5e — Step 5 becomes just "push the milestone Step 4.5 produced, after asking the user".

### 5a. Stage explicitly
`git add <file>` for each file individually. NEVER `git add .` or `git add -A` — those pick up unintended files.

### 5b. Verify staging
`git status` — confirm only this change's files are staged. Unstage anything unexpected.

### 5c. Commit message
- **First line**: imperative mood, ≤72 chars, states WHAT + WHY (not HOW)
- **Body** (optional): context that is not obvious from the diff — design tradeoffs, what was intentionally left out, what depends on this change

### 5d. One logical unit = one commit
Finish a coherent piece of work before committing. Anti-patterns:
- `fix A` → `fix A again` → `actually fix A this time` (碎 commit 链 — should have been one commit)
- Committing half a feature, then scrambling to add the other half
- Mixing a bug fix with an unrelated refactor in the same commit

If you realize mid-session you have two unrelated changes, split them into two commits.

### 5e. Commit
If a pre-commit hook fails: fix the issue, re-stage, create a NEW commit. Do NOT `--amend` (that modifies the previous commit, which may not be yours).

Push is a SEPARATE decision — ask the user before pushing.

---

## Step 6 — Post-commit Cleanup

```bash
git status --short
```

Three outcomes:

| Outcome | Action |
|---------|--------|
| **(a) Clean** | Working tree clean. Proceed to Step 7. |
| **(b) Your leftovers** | Files you forgot. Add a follow-up commit or explicitly report what's left and why. Nothing "small" silently stays — not a config tweak, not a doc update, not a cleanup. If it's yours, commit it or explain why you're leaving it. |
| **(c) Foreign changes** | Not yours. Report them to the user but don't touch them. Mention who/what they might belong to if you can tell. |

If Step 2 promised doc/status updates, verify they actually landed — grep the updated line, don't just trust your memory that you did it. A common failure mode: you updated a doc body but forgot to update the corresponding index/reference that points to it, leaving them out of sync.

---

## Step 7 — Self-Review (the two questions)

Before reporting "done," answer two questions **honestly and thoroughly**. These catch a class of problems that tests and audits cannot: hidden assumptions and missing work.

### Question 1 — Hidden assumptions
> "Is there anything I assumed the user already knows, and just ran with it without telling them?"

You are looking for decisions you made silently. Examples:
- "I chose fallback strategy X without asking — the user may have preferred Y"
- "I assumed the migration runs before the new code deploys"
- "I assumed this endpoint is internal-only and skipped rate limiting"
- "I drew a scope boundary here (only touched file A, not B) without explaining why"
- "I assumed existing tests cover the behavior I changed"

List every instance. If none, say so.

### Question 2 — Uncovered work
> "Is there extra work that this flow didn't execute, but now — looking at the finished change — I think should be done?"

You are looking for work that fell outside the steps above but matters. Examples:
- "This change affects the caching layer, but we never discussed cache invalidation"
- "I see a related function in another file that probably needs the same fix"
- "The deploy config may need updating but I didn't check"
- "There are stale comments in a neighboring file that now describe old behavior"

Don't say "I think it's fine." Run commands, grep for related code, show evidence — or say what you DIDN'T check.

If either question surfaces issues, report them with severity and recommended action. Do NOT fix silently — list them for the user to decide.

### Feedback loop — growing smarter

If either question produced a non-trivial finding, consider: **should this become a rule?**

For example, if Question 2 surfaced "this change affects caching but we didn't check TTL" and the project has a `caching` or `api` pipeline, propose adding a rule like `"Changes touching cached endpoints must verify TTL and invalidation logic"` to that pipeline's `rules` array in `pipelines.json`.

Don't add rules silently — propose them to the user in the ship summary. The user decides whether to adopt. Over time, each ship makes the next ship smarter because the rules accumulate real lessons.

---

## Ship Summary

```
Shipped:    <one-line description>
Commit:     <hash>
Pipelines:  <touched pipelines from Step 1>
Docs:       <what was updated in Step 2, or "no updates needed">
Audit:      <PASS/FAIL + finding count>
Syntax:     <what was checked, result>
Tests:      <tier picked (skip/targeted/full) + pass/fail/skip counts + wall time, or "no suite">
Open items: <anything from Steps 2/6/7, or "None">
```

**Additional fields when Step 4.5 ran (squash-on-ship workflow):**

```
Session:    <TAG>                                        # session/branch identifier
Squashed:   N commits → 1 milestone                      # or "N=1 direct, no squash"
History:    origin/history/session-<TAG>                 # detail archive branch
```

If Step 4.5.c net-zero override was accepted, append to the `Shipped:` line: `(net-zero diff milestone, accepted by user override)` — never let an empty-effect milestone slip into the log unmarked.
