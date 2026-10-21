# Working in Belay with Codex

Read `CLAUDE.md` once at task start; it is the shared ecosystem guidance.
Follow `CONTRIBUTING.md` for contribution, privacy, and verification rules.

## Keep context focused

- Confirm the checkout, branch, revision, and existing changes before editing.
  Preserve unrelated work and other chats' checkpoints.
- Start with the relevant source, callers, and tests. Read historical logs,
  other chats, or sibling repositories only to resolve a specific question.
- For a feature, reuse its existing issue/spec as the change record. Otherwise
  use `docs/development/change-template.md`; trivial corrections need no record.
- Compare the proposed design with current behavior and existing components
  before adding a feature. Record reuse, extension, or replacement and why.
- Work through one observable outcome at a time. Carry authorized work through
  relevant verification; don't expand into adjacent roadmap items.

## Verify and hand off

Use the commands and source map in `docs/development/codex-workflow.md`.
Run focused checks while editing and required checks before delivery. Repeat
checks when source changes or a new concern invalidates earlier evidence.
Keep failed, skipped, and unavailable checks visible; don't weaken gates to save
usage. A UI change also needs rendered interaction and layout inspection.

For substantial work, leave a short checkpoint in its change record: exact
checkout/revision, dirty files, decisions, verification, unresolved problems,
and the next concrete action. Recheck current state before using it later.

Fieldwork may help locate results and review notes. Read the underlying evidence
before relying on a result. Its review marks don't establish acceptance,
merge, deployment, or live readiness. Keep merge/release approval distinct.
