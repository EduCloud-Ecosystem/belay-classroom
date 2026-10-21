# Belay Classroom source provenance

Created on 21 October 2026 at Greg Chism's request as a private repository under EduCloud-Ecosystem. GitHub repository: https://github.com/EduCloud-Ecosystem/belay-classroom.

This is an independent source fork of public Belay, preserving Git history and upstream licenses. GitHub does not represent it as a private fork-network relationship. `origin` is the new repository; `upstream` is https://github.com/EduCloud-Ecosystem/belay.git.

The baseline is `92a1d3546798cf9e232a207fc0d7c42d4fb4ca6c`, the still-open [Belay PR14](https://github.com/EduCloud-Ecosystem/belay/pull/14), based on `89f25971749f9b6c557fc49ab6beaf4a9909bb95`. This deliberately retains the authorization/accounting interfaces already used by the classroom source. It does not imply that PR14 was merged or accepted upstream.

All 39 modified/untracked classroom and guidance files were copied byte-for-byte from the frozen B1 worktree before repository identity, workflow and provenance documentation changed. The original worktree and primary Belay checkout were preserved. No credentials, local databases or runtime outputs were copied.

Verification is reported in [the current change record](classroom-b1.md). Initial source import, passing component checks, live-provider transport and an accepted integrated classroom demonstration are different states. Original failure evidence is retained in the coordinator's private execution directory. Upstream contribution and privacy rules still apply; every new commit uses DCO sign-off and preserves SPDX/license boundaries.

Workflow source: Codex chat `01a15cf9-64a0-7683-9f29-89a92360516e`. Reuse concise component guides, explicit commands and focused handoffs. Leave model settings unchanged; measure usage/rework before claiming efficiency gains.
