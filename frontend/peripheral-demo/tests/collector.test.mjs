// SPDX-License-Identifier: AGPL-3.0-only
import test from "node:test";
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {createCollector, emptyState, matchesOrigin, HOST_PERMISSION, STORAGE_KEY, TTL_MS, validState} from "../collector.mjs";

function fixture(stored) {
  let time = 100000, allowed = false, focused = true, tab;
  const memory = stored ? {[STORAGE_KEY]: structuredClone(stored)} : {};
  const badges = [], requests = [], alarms = [];
  const api = {
    storage: {session: {
      setAccessLevel: async value => assert.deepEqual(value, {accessLevel: "TRUSTED_CONTEXTS"}),
      get: async () => structuredClone(memory),
      set: async value => { Object.assign(memory, structuredClone(value)); },
      remove: async key => { delete memory[key]; }
    }},
    permissions: {contains: async value => { assert.deepEqual(value, {origins: [HOST_PERMISSION]}); return allowed; }, remove: async () => { allowed = false; return true; }},
    windows: {get: async id => ({id, focused, incognito: false, type: "normal"})},
    tabs: {query: async query => { requests.push(query); return tab ? [tab] : []; }},
    alarms: {create: async (...args) => { alarms.push(args); }, clear: async () => true},
    action: {setBadgeText: async value => { badges.push(value.text); }, setBadgeBackgroundColor: async () => {}, setTitle: async () => {}}
  };
  return {api, memory, badges, requests, alarms, clock: () => time,
    advance: ms => { time += ms; }, permit: () => { allowed = true; }, allowed: () => allowed, blur: () => { focused = false; },
    tab: (url, windowId = 7, active = true) => { tab = {url, windowId, active, title: "NEVER_COLLECT_TITLE"}; }};
}
async function started() {
  const f = fixture();
  const c = createCollector(f.api, f.clock); await c.ready;
  const intent = (await c.command({type: "begin_start", windowId: 7})).intent;
  f.permit();
  const state = await c.command({type: "start", windowId: 7, intent: intent.nonce});
  assert.equal(state.status, "active");
  return {f, c, state};
}

test("off by default; no permission or tab read until explicit consent command", async () => {
  const f = fixture(), c = createCollector(f.api, f.clock); await c.ready;
  assert.deepEqual(await c.command({type: "get"}), emptyState());
  await c.observe(); assert.equal(f.requests.length, 0);
  assert.equal((await c.command({type: "start", windowId: 7})).status, "unavailable");
  assert.equal(f.requests.length, 0);
});
test("exact origin, not prefix, title, path or query; one closed origin-free signal", async () => {
  assert.equal(matchesOrigin("http://127.0.0.1:8769/private?q=NEVER_STORE#secret"), true);
  for (const url of ["https://127.0.0.1:8769", "http://127.0.0.1:8770", "http://127.0.0.1.evil:8769", "http://localhost:8769", "not a URL"]) assert.equal(matchesOrigin(url), false);
  const {f, c} = await started();
  f.tab("http://127.0.0.1:8769/private?q=NEVER_STORE#secret");
  assert.equal((await c.observe()).signal, true);
  assert.equal(validState(f.memory[STORAGE_KEY]), true);
  assert.doesNotMatch(JSON.stringify(f.memory), /NEVER|http|url|title|private|secret/i);
  assert.deepEqual(f.requests, [{active: true, windowId: 7}]);
  await c.observe(); assert.equal(f.requests.length, 1); // No growing history.
});
test("background tab, other window and unfocused window produce no signal", async () => {
  const {f, c} = await started();
  f.tab("http://127.0.0.1:8769", 7, false); assert.equal((await c.observe()).signal, false);
  f.tab("http://127.0.0.1:8769", 9); assert.equal((await c.observe()).signal, false);
  f.blur(); f.tab("http://127.0.0.1:8769"); assert.equal((await c.observe()).signal, false);
});
test("pause/resume preserves original ten-minute expiry; no late observation or renewal", async () => {
  const {f, c, state} = await started();
  assert.equal(state.expiresAt, f.clock() + TTL_MS);
  assert.equal((await c.command({type: "pause"})).status, "paused");
  f.tab("http://127.0.0.1:8769"); await c.observe(); assert.equal(f.requests.length, 0);
  f.advance(1000); assert.equal((await c.command({type: "resume"})).expiresAt, state.expiresAt);
  f.advance(TTL_MS); assert.equal((await c.observe()).status, "expired");
  assert.equal((await c.command({type: "get"})).signal, false);
  assert.equal((await c.command({type: "resume"})).status, "unavailable");
});
test("revoke and delete stop, clear signal, remove permission; removal callback cannot reactivate", async () => {
  const {f, c} = await started(); f.tab("http://127.0.0.1:8769"); await c.observe();
  assert.equal((await c.command({type: "revoke"})).status, "revoked");
  assert.equal((await c.permissionRemoved()).status, "revoked");
  assert.equal((await c.observe()).signal, false);
  assert.equal((await c.command({type: "delete"})).status, "off");
  assert.deepEqual(f.memory, {});
});
test("permission loss, window closure, browser API error and malformed command fail closed", async () => {
  for (const mode of ["permission", "window", "api", "extra"]) {
    const {f, c} = await started();
    let result;
    if (mode === "permission") result = await c.permissionRemoved();
    if (mode === "window") result = await c.windowRemoved(7);
    if (mode === "api") { f.api.windows.get = async () => { throw new Error("private browser detail"); }; result = await c.observe(); }
    if (mode === "extra") result = await c.command({type: "start", windowId: 7, source: "NEVER_STORE"});
    assert.equal(result.status, "unavailable"); assert.equal(result.signal, false);
    assert.doesNotMatch(JSON.stringify(f.memory), /private browser|NEVER_STORE/);
  }
});
test("worker restart pauses; expiry remains fixed, with no inferred time or automatic resume", async () => {
  const stored = {version: 1, status: "active", windowId: 7, expiresAt: 500000, signal: true};
  const f = fixture(stored); f.permit();
  const c = createCollector(f.api, f.clock); await c.ready;
  const state = await c.command({type: "get"}); assert.equal(state.status, "paused");
  assert.equal(state.expiresAt, stored.expiresAt); await c.observe(); assert.equal(f.requests.length, 0);
  assert.equal((await c.command({type: "resume"})).status, "active");
});
test("pause immediately invalidates an async foreground read already in progress", async () => {
  const {f, c} = await started(); f.tab("http://127.0.0.1:8769");
  let release, entered;
  const inside = new Promise(resolve => { entered = resolve; });
  const original = f.api.tabs.query;
  f.api.tabs.query = async (...args) => { entered(); await new Promise(resolve => { release = resolve; }); return original(...args); };
  const observed = c.observe(); await inside;
  const paused = c.command({type: "pause"}); release();
  assert.equal((await observed).signal, false); assert.equal((await paused).status, "paused");
});
test("manifest grants no broad tab/content/history permissions or server connection", async () => {
  const manifest = JSON.parse(await readFile(new URL("../manifest.json", import.meta.url)));
  assert.equal(manifest.manifest_version, 3);
  assert.deepEqual(manifest.permissions, ["storage", "alarms"]);
  assert.deepEqual(manifest.optional_host_permissions, [HOST_PERMISSION]);
  for (const name of ["content_scripts", "externally_connectable", "web_accessible_resources", "host_permissions"]) assert.equal(manifest[name], undefined);
  assert.match(manifest.content_security_policy.extension_pages, /connect-src 'none'/);
  const worker = await readFile(new URL("../worker.mjs", import.meta.url), "utf8");
  assert.match(worker, /sender.id !== chrome.runtime.id \|\| sender.url !== panel/);
});
test("deferred permission after another panel revoke/delete cannot restart or leave unowned grant", async () => {
  for (const action of ["revoke", "delete"]) {
    const f = fixture(), c = createCollector(f.api, f.clock); await c.ready;
    const old = (await c.command({type: "begin_start", windowId: 7})).intent;
    await c.command({type: action});
    f.permit(); // Native prompt resolves late in the original panel.
    const result = await c.command({type: "start", windowId: 7, intent: old.nonce});
    assert.equal(result.status, action === "delete" ? "off" : "revoked");
    assert.equal(f.allowed(), false);
    assert.equal((await c.observe()).signal, false);
  }
});
test("obsolete intent cleanup never removes a newer accepted session's permission", async () => {
  const f = fixture(), c = createCollector(f.api, f.clock); await c.ready;
  const old = (await c.command({type: "begin_start", windowId: 7})).intent;
  await c.command({type: "delete"});
  const fresh = (await c.command({type: "begin_start", windowId: 7})).intent;
  f.permit();
  const accepted = await c.command({type: "start", windowId: 7, intent: fresh.nonce});
  assert.equal(accepted.status, "active");
  assert.equal((await c.command({type: "start", windowId: 7, intent: old.nonce})).status, "active");
  await c.command({type: "cancel_start", intent: old.nonce});
  assert.equal(f.allowed(), true);
  assert.equal((await c.command({type: "get"})).expiresAt, accepted.expiresAt);
});
test("expired intent, wrong window and worker restart invalidate pending consent", async () => {
  for (const fault of ["expired", "window", "restart"]) {
    const f = fixture(); let c = createCollector(f.api, f.clock); await c.ready;
    const old = (await c.command({type: "begin_start", windowId: 7})).intent;
    if (fault === "expired") f.advance(60000);
    if (fault === "restart") { c = createCollector(f.api, f.clock); await c.ready; }
    f.permit();
    const state = await c.command({type: "start", windowId: fault === "window" ? 8 : 7, intent: old.nonce});
    assert.equal(state.status, "off"); assert.equal(f.allowed(), false);
  }
});
test("native late-grant event is cleaned without relying on the original panel to finish", async () => {
  const f = fixture(), c = createCollector(f.api, f.clock); await c.ready;
  await c.command({type: "begin_start", windowId: 7});
  await c.command({type: "delete"});
  f.permit(); await c.permissionAdded();
  assert.equal(f.allowed(), false);
  const intent = (await c.command({type: "begin_start", windowId: 7})).intent;
  f.permit(); await c.permissionAdded(); assert.equal(f.allowed(), true);
  f.advance(60000); await c.command({type: "get"}); assert.equal(f.allowed(), false);
  assert.equal((await c.command({type: "start", windowId: 7, intent: intent.nonce})).status, "off");
});
