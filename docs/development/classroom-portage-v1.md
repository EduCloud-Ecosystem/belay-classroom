# Classroom Portage integration checkpoint

Issue: https://github.com/EduCloud-Ecosystem/belay-classroom/issues/4
Program: https://github.com/EduCloud-Ecosystem/educloud/issues/56

Base `dba982c3a20241a14f1322fa3acf38261442ba88`, isolated worktree
`/Users/gregchism/dev/.educloud-worktrees/belay-classroom-classroom-full-stack-v1`,
branch `codex/classroom-full-stack-v1`. Original notebook checkout and original
Belay are unchanged. Current main includes the notebook branch; no upstream
Belay PR25 dependency was adopted.

The first outcome is one trusted classroom operation through the existing Portage
HTTP gateway. Reuse provider parsing/explicit repair and both existing ledgers;
extend provider selection, startup validation and operator configuration. Do not
create a replacement inference service or reservation authority.

The exact Portage dependency is `79742746b10ace18e498111dd5a8f3227edd995c` in a clean
detached worktree. See deployment/portage/README.md for reproducibility, limitations
and remaining integration boundaries. Runtime dependencies are fully version/hash
locked; the fresh environment used CPython3.12.13/macOS arm64, not an old venv.

Local synthetic evidence is in ignored `output/portage-integration/`: all initial
setup/expectation failures are retained alongside corrected results and JUnit.
The first fixtures used invalid short Portage IDs, attempted an unchanged policy
version, and expected the wrong exception for converted auth failures versus 429.
These were fixture failures, not accepted gateway results. No production policy
was relaxed. The initial full run retains its one new-test failure; the final
full run is recorded separately below. Checks run against temporary test databases.

Required validation: focused actual gateway tests, full SQLite suite, Ruff lint
and formatting, mypy; hosted PostgreSQL CI remains distinct. No UI changes in this
slice. No new model/cloud/production operation, private data, merge or deployment.

## Local result

Final focused: 16 passed, no failures/skips. Final full SQLite: 1,082 passed,
20 skipped, zero failures/errors (1,102 collected). Ruff lint and formatting pass;
mypy reports no issues in 185 files. The first full run had one new-test failure
and remains retained. Final version/hash-locked sync audited all 56 packages.

Skips include configured unavailable sibling schema/PostgreSQL/opt-in paths;
local SQLite is not PostgreSQL or live-model acceptance. Hosted PostgreSQL and
the new exact-Portage CI job remain required review evidence. No source changed
after the successful final checks. See deployment/portage/verification.json.

Next concrete slice: trusted Waypoint/Cairn learner binding and a newly bounded
classroom presenter path, then authenticated per-attempt receipt/status. Existing
OpenAI presenter grants, clocks, private records and historical acceptance are
not reused or promoted.
