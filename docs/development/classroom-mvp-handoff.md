# Belay classroom MVP handoff

The synthetic technical demonstration is implemented. It combines a governed
live tutoring test, a rendered private-remediation interface, and a connected
Cairn/Waypoint submission and scripted-review test under one frozen assignment
contract. These are distinct evidence paths: the browser uses an explicitly
labeled prepared hint card; the separate one-job provider path used OpenAI.
This is a runnable operator demonstration, not a standing student service.

## What works

| Capability | Observed result |
| --- | --- |
| Independent route | Prediction reminder, presence checkpoint, no-AI declaration and monitoring off; no provider attempts for Alice. |
| Private remediation | Bob enabled tracking, encountered the hints-only rule, acknowledged and challenged the private alert, chose retry, then explicitly requested permitted hints. No punishment or automatic grade action. |
| Pause and revoke | Pause prevented new optional events; revoke cleared alerts/events while retaining required checkpoint and declaration. |
| Real provider | One governed queued job completed four OpenAI requests, reporting 7,742 tokens; no retry or unknown accounting. Released output was inspected as hints only. |
| Isolated checker | Two actual confined containers distinguished incomplete from preserved-cell output and were removed. This is not adversarial grading. |
| Submission | Both synthetic learners submitted four saved files through preview, confirmation and a committed receipt. CSV checks, persisted scripted review and matching export passed. |
| Recovery | A saved reply survived reload and was deleted. An accepted unsaved request survived deliberate response loss and reload without creating a second job. |
| Display | Belay branding, desktop layout and a 390px phone layout inspected; no horizontal overflow in that phone view. |
| Teardown | Owned listeners/containers stopped; temporary cloud API-key file removed; private execution and dialogue content deleted; authority revoked and accounting/deletion fences retained. |

The course CSV is a nine-cell synthetic substitute. Original course-data rights
remain unresolved. Notebook files were submitted; an actual Jupyter kernel and
live workspace execution were not demonstrated. The review actor was an
automated synthetic fixture, not a human instructor. Full screen-reader,
keyboard and phone-task acceptance are still required.

The backend at `6c01829` passed full lint/format/types and both database CI gates
in run `39692080492`. The final display-only commit is reviewed by the same
required checks on [PR1](https://github.com/EduCloud-Ecosystem/belay-classroom/pull/1).
The [change record](classroom-b1.md) retains failures, exact boundaries and
operator evidence locations. No backend source/profile change followed the live
test. Successful unchanged live/CW1 tests need no paid rerun for display copy.

## Full EduCloud implementation, in order

1. **Course identity and authority.** Connect campus sign-in and enrollment to
   Waypoint, Cairn, Belay and workspace roles. Test allowed, denied and revoked
   access across all routes and exports. Replace operator-issued synthetic grants.
2. **Real learning workspace.** Connect authenticated Jupyter/course workspaces.
   Prove save, kernel execution, exact-revision submission, reopen and export.
   Use the same assignment/version and assistance-declaration contract.
3. **Scoped external tools.** Implement an EduCloud-owned MCP client boundary
   with task-selected tools, course membership, server authorization, quotas,
   deadlines, bounded results and provenance. Begin with Exa public discovery
   and one authorized MESA course-material list/read/search capability. The
   connected Exa smoke passed; application MCP integration and MESA access did
   not. Keep deterministic internal checks as direct calls. Treat tool output
   as untrusted data; never forward private monitoring, guidance or grade authority.
4. **Operational persistence.** Qualify shared transactional storage, backup and
   restore, deletion and revoked-authority preservation, cleanup while services
   are stopped, provider reconciliation, capacity limits and supervised recovery.
   Do not put live SQLite on shared/network storage. Name a service owner and
   budget owner before a classroom deployment.
5. **Human classroom pilot.** Have an instructor assess actual submitted
   evidence and teaching behavior. Complete keyboard, screen-reader, phone and
   classroom-load journeys with a small consented pilot before broader adoption.
6. **Optional device-wide monitoring.** The MVP observes explicit application
   actions. A wider device collector is a separate extension requiring explicit
   permissions, a visible scope/notice, pause/revoke/delete and exclusion of
   activity outside the grant. Start with inexpensive, verifiable structured
   events; do not infer misconduct or authorship from screenshots or behavior.

MESA supplies reusable data/research tools through MCP; EduCloud retains course
authority and Belay retains private tutoring/remediation. A broad MESA tool
catalog is not a grant to use its write, ACL, job or resource-management tools.
Test denied/revoked access and outages before enabling a real collection.

## Budget and release

Testing is within the authorized $20 envelope. Holds total $5.46, leaving $14.54
unallocated; actual provider/operational invoices remain unreconciled. The live
ledger's $0.007742 estimate is not a billed-cost claim. No new droplet or Modal
resource was provisioned. No institutional resource or real student data was used.

PR review/merge and deployment remain separate decisions. The demonstration
does not establish institutional approval, student readiness or teaching efficacy.
