// SPDX-License-Identifier: AGPL-3.0-only
// Real isolated Chromium MV3 smoke/render check; never attaches to a user profile.
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const {chromium} = require("playwright");
const {start} = require("../mock-server.cjs");

async function main() {
  const temporary = process.env.BELAY_EVIDENCE_DIRECTORY || await fs.mkdtemp(path.join(os.tmpdir(), "belay-peripheral-"));
  if (process.env.BELAY_EVIDENCE_DIRECTORY) await fs.mkdir(temporary, {mode: 0o700});
  const extension = path.resolve(__dirname, "..");
  let context, server, page, result, video, videoPath;
  const requests = [], errors = [];
  try {
    server = await start();
    context = await chromium.launchPersistentContext(path.join(temporary, "profile"), {
      channel: "chromium", executablePath: process.env.BELAY_CHROMIUM_EXECUTABLE || undefined,
      headless: process.env.BELAY_HEADED !== "1", viewport: {width: 1100, height: 900},
      recordVideo: {dir: path.join(temporary, "video"), size: {width: 1100, height: 900}},
      args: [`--disable-extensions-except=${extension}`, `--load-extension=${extension}`, "--disable-background-networking"]
    });
    context.on("request", request => { if (!request.url().startsWith("chrome-extension:") && !request.url().startsWith("http://127.0.0.1:8769")) requests.push(request.url().split("/")[0]); });
    const worker = context.serviceWorkers()[0] || await context.waitForEvent("serviceworker", {timeout: 10000});
    const id = new URL(worker.url()).host;
    page = await context.newPage();
    video = page.video();
    page.on("pageerror", () => errors.push("page_error"));
    await page.goto(`chrome-extension://${id}/panel.html`);
    await page.getByText("Off. Coaching and ordinary course help do not require collection.", {exact: true}).waitFor();
    await page.screenshot({path: path.join(temporary, "desktop-off.png"), fullPage: true});
    await page.locator("#consent").check();
    await page.getByRole("button", {name: "Start in this window", exact: true}).click();
    await page.locator("#badge").filter({hasText: /^ACTIVE$/}).waitFor({timeout: process.env.BELAY_HEADED === "1" ? 60000 : 10000});
    const session = await worker.evaluate(async () => (await chrome.storage.session.get("belayPeripheralSessionV1")).belayPeripheralSessionV1);
    assert.equal(session.status, "active");
    assert.equal(await worker.evaluate(() => chrome.permissions.contains({origins: ["http://127.0.0.1:8769/*"]})), true);
    // Actual background tab in the selected window: no signal.
    const newMock = context.waitForEvent("page");
    await worker.evaluate(windowId => chrome.tabs.create({windowId, active: false, url: "http://127.0.0.1:8769/a-private-path?q=NEVER_STORE#private-fragment"}), session.windowId);
    const mock = await newMock; await mock.waitForLoadState();
    await page.waitForTimeout(250); // Let real asynchronous Chrome tab/focus events settle.
    assert.equal((await worker.evaluate(async () => (await chrome.storage.session.get("belayPeripheralSessionV1")).belayPeripheralSessionV1)).signal, false);
    // Actual focused mock tab in a different window: original window unfocused.
    const other = await worker.evaluate(() => chrome.windows.create({type: "normal", focused: true, url: "http://127.0.0.1:8769"}));
    await page.waitForFunction(async id => !(await chrome.windows.get(id)).focused, session.windowId);
    await page.waitForTimeout(250);
    assert.equal((await worker.evaluate(async () => (await chrome.storage.session.get("belayPeripheralSessionV1")).belayPeripheralSessionV1)).signal, false);
    await worker.evaluate(id => chrome.windows.remove(id), other.id);
    await mock.bringToFront();
    await page.waitForFunction(async () => (await chrome.runtime.sendMessage({type: "get"}))?.state.signal);
    await page.bringToFront();
    await page.locator("#observation").waitFor();
    await page.getByRole("button", {name: "Challenge the observation", exact: true}).click();
    assert.match(await page.locator("#outcome").innerText(), /cannot establish AI use/);
    await page.getByRole("button", {name: "Unrelated to my task", exact: true}).click();
    assert.match(await page.locator("#outcome").innerText(), /No explanation is needed/);
    await page.getByRole("button", {name: "Explore a task-related need", exact: true}).click();
    await page.locator("#context").fill("SYNTHETIC_PRIVATE_REFLECTION: I was unsure about the observational unit.");
    await page.locator("#next").click();
    await page.locator("#need").selectOption({label: "A small course example"});
    await page.locator("#why").fill("SYNTHETIC_PRIVATE_REFLECTION: An example would help.");
    await page.locator("#next").click();
    await page.locator("#alternative").selectOption({label: "Ask Belay for a peer hint, separately"});
    await page.locator("#next").click();
    await page.locator("#correction").selectOption({label: "Review my required assistance declaration"});
    await page.locator("#next").click();
    await page.locator("#if").fill("I am stuck on a join");
    await page.locator("#then").fill("write my prediction and ask for a peer hint");
    await page.locator("#next").click();
    assert.equal(await page.locator("#plan").isVisible(), false); // Review is explicit.
    await page.locator("#reviewed").check();
    await page.locator("#next").click();
    await page.locator("#plan").waitFor();
    await page.screenshot({path: path.join(temporary, "desktop-plan.png"), fullPage: true});
    const storage = await worker.evaluate(async () => ({session: await chrome.storage.session.get(null), local: await chrome.storage.local.get(null), sync: await chrome.storage.sync.get(null)}));
    assert.doesNotMatch(JSON.stringify(storage), /SYNTHETIC|private-path|NEVER_STORE|http|url|title|plan|reflection/i);
    assert.deepEqual(storage.local, {}); assert.deepEqual(storage.sync, {});
    await page.setViewportSize({width: 390, height: 844});
    await page.screenshot({path: path.join(temporary, "phone-plan.png"), fullPage: true});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.getByRole("button", {name: "Pause", exact: true}).click();
    await page.locator("#badge").filter({hasText: /^PAUSED$/}).waitFor();
    await page.getByRole("button", {name: "Resume", exact: true}).click();
    await page.locator("#badge").filter({hasText: /^ACTIVE$/}).waitFor();
    assert.equal((await worker.evaluate(async () => (await chrome.storage.session.get("belayPeripheralSessionV1")).belayPeripheralSessionV1)).expiresAt, session.expiresAt);
    await page.getByRole("button", {name: "Revoke permission", exact: true}).click();
    await page.locator("#badge").filter({hasText: /^REVOKED$/}).waitFor();
    assert.equal(await page.locator("#context").inputValue(), "");
    assert.equal(await page.locator("#plan-text").innerText(), "");
    assert.equal(await worker.evaluate(() => chrome.permissions.contains({origins: ["http://127.0.0.1:8769/*"]})), false);
    await page.getByRole("button", {name: "Delete session and reflection", exact: true}).click();
    await page.locator("#badge").filter({hasText: /^OFF$/}).waitFor();
    assert.deepEqual(await worker.evaluate(() => chrome.storage.session.get(null)), {});
    await page.reload();
    assert.equal(await page.locator("#context").inputValue(), "");
    assert.deepEqual(errors, []); assert.deepEqual(requests, []);
    result = {result: "PASS", evidence_directory: temporary, real_mv3: true, real_optional_permission: true, background_tab_negative: true, other_focused_window_negative: true, selected_focused_window_positive: true, reflection_stored: false, external_page_requests: 0, model_calls: 0, pause_resume_preserves_expiry: true, revoke_permission_removed: true, delete_session_empty: true, screenshots: ["desktop-off.png", "desktop-plan.png", "phone-plan.png"]};
    videoPath = await video.path();
  } catch (error) {
    if (page && !page.isClosed()) {
      await page.screenshot({path: path.join(temporary, "failure.png"), fullPage: true});
      process.stderr.write(JSON.stringify({evidence_directory: temporary, badge: await page.locator("#badge").innerText(), status: await page.locator("#status").innerText(), outcome: await page.locator("#outcome").innerText(), errors}) + "\n");
    }
    throw error;
  } finally {
    if (context) await context.close();
    if (server) await new Promise(resolve => server.close(resolve));
    await fs.rm(path.join(temporary, "profile"), {recursive: true, force: true});
  }
  await fs.copyFile(videoPath, path.join(temporary, "presenter-flow.webm"));
  result.video = "presenter-flow.webm";
  result.browser_closed = true; result.mock_server_closed = true; result.temporary_profile_removed = true;
  await fs.writeFile(path.join(temporary, "result.json"), JSON.stringify(result, null, 2) + "\n", {mode: 0o600, flag: "wx"});
  process.stdout.write(JSON.stringify(result) + "\n");
}
main().catch(error => { process.stderr.write(String(error.stack) + "\n"); process.exitCode = 1; });
