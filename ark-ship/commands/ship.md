---
description: "Ship flow: inventory → pipeline mapping → doc sync → security audit → syntax check → commit → cleanup → self-review"
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

## Step 4 — Syntax & Build Verification

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

Run related tests if they exist. At minimum, run tests in the same directory as the changed files.

State what was checked and the result — honestly. Don't claim "all checks pass" without actually running them.

---

## Step 5 — Commit

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
Open items: <anything from Steps 2/6/7, or "None">
```
