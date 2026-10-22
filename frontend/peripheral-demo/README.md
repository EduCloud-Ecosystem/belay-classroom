# Optional browser check-in and private coaching demo

This standalone Chromium Manifest V3 extension implements one synthetic flow:
explicit consent → matching mock site in the selected focused window → neutral
check-in → voluntary context/need → permitted alternative → correction or
disclosure choice → student-reviewed if/then plan. Scripted questions need no
model. It extends the coaching intent in the external
`execution/peripheral-coaching-plan.md`; it does not connect to Belay's backend,
identity, course state, research records, grading or submission.

## Run locally

1. From this directory run `node mock-server.cjs`. It binds only
   `http://127.0.0.1:8769`; it has no input form, model, request log or external
   resources. Stop it with Ctrl-C after the demonstration.
2. In a separate synthetic Chromium profile, open `chrome://extensions`, enable
   Developer mode, choose **Load unpacked**, and select this directory. Pin the
   extension so its ON/PAUS/END/OFF badge is visible. Do not enable incognito.
3. Click the extension's action to open its control tab. Read the notice, tick
   the consent box, choose **Start in this window**, and accept Chrome's optional
   permission prompt for the declared loopback mock site. Declining keeps
   collection off; coaching remains available.
4. Open the mock-site link. A background tab, another window, or an unfocused
   selected window must not produce a signal. Activate the mock tab in the
   selected focused window, then return to the control tab. Explore unrelated,
   permitted use, challenge or skip, or choose the guided private reflection.
5. Pause/resume, revoke, then delete. Revoke removes the optional host permission.
   Delete clears the session key and reflection; uninstall the unpacked extension
   and close the synthetic profile when done.

The only optional host permission is `http://127.0.0.1:8769/*`. The worker compares
the exact origin, never a prefix or title. No `tabs`, `history`, `scripting`,
`activeTab`, content script, externally connectable route or web-accessible
resource is declared. Chrome's permission grants capabilities beyond what this
implementation uses; the extension neither reads page content nor changes it.
See the official [Tabs API](https://developer.chrome.com/docs/extensions/reference/api/tabs)
and [runtime permission API](https://developer.chrome.com/docs/extensions/reference/api/permissions).

## Data and authority

Collection is off initially and requires an explicit student choice. It covers
one normal window and one fixed mock origin for at most ten minutes. The absolute
expiry never renews on resume. Worker restart pauses; browser session storage
does not survive browser restart. Missing time is unknown, with no inferred dwell
duration, attention, copying, AI use, intent or misconduct.

Checking consent prepares a volatile, single-use worker nonce for that window,
valid for sixty seconds. Start requests the native permission synchronously in
its own gesture, then must consume that exact intent. Revoke/delete in any panel
invalidates it globally; restart also loses it. A stale or cancelled grant is
removed unless a newer accepted/paused session owns it. Native permission-added
events and the pending-intent expiry alarm also clean abandoned late grants,
without depending on the original panel remaining open. The nonce is not stored.

The five-field `chrome.storage.session` record is exactly `version`, `status`,
`windowId`, `expiresAt`, `signal`. It contains one origin-free boolean, no visit
list or count. It is restricted to trusted extension contexts. No local/sync
storage, server, log or export is used. URL origins are compared transiently;
paths, queries, fragments, titles, content, screenshots and clipboard are not
retained or transmitted by the extension. Browser navigation itself still has
the browser's ordinary behavior. No claim about the browser's own history or
OS-level erasure is made.

Reflection text remains only in the control page's form/DOM memory. It never
enters extension messages or storage. Closing/reloading, expiry, revocation or
deletion clears it. No transcript, sharing button, export, notification, grade,
instructor feed, sanction, model call or unattended follow-up exists. Challenge,
skip and permitted/unrelated use require no explanation. Use fictional text for
screenshots/videos, which are separate operator-created evidence.

This is not an authenticated course lease or device-wide collector. It does not
claim cross-browser coverage, detection accuracy, learning efficacy, institutional
approval or real-student readiness. Required course declarations stay separate.

## Verify

From the repository root, dependency-free hermetic collector/manifest checks:

```sh
node --test frontend/peripheral-demo/tests/collector.test.mjs
```

The additional DOM checks use the existing frontend `jsdom` dependency (run
`npm ci` in `frontend/` in a fresh development/CI environment):

```sh
node --test frontend/peripheral-demo/tests/collector.test.mjs frontend/peripheral-demo/tests/panel.test.mjs
```

Real isolated Chromium acceptance uses existing Playwright and a **real native
permission prompt**. It does not mock the extension API or pregrant permissions.
The operator must click **Allow** in the synthetic Chromium window within sixty
seconds. The headless variant cannot complete that native prompt and is not an
acceptance substitute. No download/install is performed by this script.

```sh
NODE_PATH=/path/to/existing/node_modules \
BELAY_CHROMIUM_EXECUTABLE=/absolute/path/to/existing/chromium \
BELAY_HEADED=1 \
BELAY_EVIDENCE_DIRECTORY=/absolute/new/evidence-directory \
node frontend/peripheral-demo/tests/browser.cjs
```

`BELAY_CHROMIUM_EXECUTABLE` can be omitted when Playwright's matching Chromium
is already installed. The evidence directory must be fresh; omit it to use a new
OS temporary directory. The script preserves screenshots, synthetic video and a
content-free `result.json`, closes its exact browser/server, and deletes its
temporary browser profile. It tests actual optional permission, foreground and
window negative controls, transient coaching, reviewed-plan gating, phone layout,
pause/resume expiry, permission removal and deletion. The video captures page
content; the native Chrome permission sheet is outside that page recording.

## Checkpoint

Checkout `/Users/gregchism/dev/belay-classroom`, branch
`codex/notebook-classroom`, base `90491e9b05c866bb5982ecf7a4b7be3aacb82f0b`.
All implementation/test files for this component are inside this directory;
concurrent NHANES backend/shared frontend changes belong to the root operator.
No commit/push or existing notebook runtime is changed by this component.
Sixteen focused hermetic collector/DOM tests passed. A real headed Chromium MV3
run passed with a native optional-permission prompt accepted through CUA, actual
background-tab and other-focused-window negative controls, selected-window
foreground signal, voluntary coaching and reviewed plan, no reflection in
extension storage/messages, pause/resume without expiry renewal, revoke/delete,
and desktop/390px layout inspection. The final synthetic screenshots/video and
content-free receipts are outside the repository under
`execution/verification/peripheral-demo-v1/`. The browser, mock server and
temporary profile were cleaned up. Earlier headless permission timeouts and one
video-export failure are retained separately; they are not successful checks.
Full repository CI and presenter integration remain root-owned. These results
establish only the described synthetic extension/coaching flow.
