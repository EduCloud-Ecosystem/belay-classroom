// SPDX-License-Identifier: AGPL-3.0-only
import test from "node:test";
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {createRequire} from "node:module";
import {mountPanel} from "../panel.mjs";
const {JSDOM} = createRequire(import.meta.url)("jsdom");
const html = await readFile(new URL("../panel.html", import.meta.url), "utf8");
const tick = () => new Promise(resolve => setImmediate(resolve));
async function page(initial = "off") {
  const dom = new JSDOM(html, {url: "chrome-extension://synthetic/panel.html"});
  let state = {version: 1, status: initial, windowId: initial === "off" ? null : 7, expiresAt: initial === "off" ? null : Date.now() + 600000, signal: false};
  let poll;
  const messages = [];
  const chrome = {runtime: {sendMessage: async message => { messages.push(message); if (message.type === "delete") state = {version: 1, status: "off", windowId: null, expiresAt: null, signal: false}; return {state: {...state}}; }}, permissions: {request: async () => false}, windows: {getCurrent: async () => ({id: 7})}};
  const mounted = await mountPanel({document: dom.window.document, window: dom.window, chrome, setInterval: fn => { poll = fn; return 1; }, clearInterval: () => {}});
  const $ = id => dom.window.document.getElementById(id);
  return {dom, $, messages, close() { mounted.destroy(); dom.window.close(); }, external(value) { state = value; poll(); }, async click(id) { $(id).click(); await tick(); }, async choice(name) { dom.window.document.querySelector(`[data-choice="${name}"]`).click(); await tick(); }};
}
test("cross-panel deletion into off clears existing reflection, without clearing every off poll", async () => {
  const p = await page("active");
  try {
    await p.choice("connected"); p.$("context").value = "PRIVATE_REFLECTION";
    p.external({version: 1, status: "off", windowId: null, expiresAt: null, signal: false}); await tick();
    assert.equal(p.$("context").value, ""); assert.equal(p.$("coaching").hidden, true);
    await p.choice("connected"); p.$("context").value = "OFF_COACHING_STAYS_TRANSIENT";
    p.external({version: 1, status: "off", windowId: null, expiresAt: null, signal: false}); await tick();
    assert.equal(p.$("context").value, "OFF_COACHING_STAYS_TRANSIENT");
    assert.doesNotMatch(JSON.stringify(p.messages), /PRIVATE|COACHING|context|reflection/);
  } finally { p.close(); }
});
test("new session, expiry and page reload clear reflection; no text is messaged or restored", async () => {
  const p = await page("active");
  try {
    await p.choice("connected"); p.$("context").value = "PRIVATE_BEFORE_NEW_SESSION";
    p.external({version: 1, status: "active", windowId: 8, expiresAt: Date.now() + 500000, signal: false}); await tick();
    assert.equal(p.$("context").value, "");
    await p.choice("connected"); p.$("context").value = "PRIVATE_BEFORE_EXPIRY";
    p.external({version: 1, status: "expired", windowId: null, expiresAt: null, signal: false}); await tick();
    assert.equal(p.$("context").value, "");
    await p.choice("connected"); p.$("context").value = "PRIVATE_BEFORE_RELOAD";
    p.dom.window.dispatchEvent(new p.dom.window.Event("pagehide"));
    assert.equal(p.$("context").value, "");
    const reloaded = await page("active");
    try { assert.equal(reloaded.$("context").value, ""); assert.equal(reloaded.$("plan-text").textContent, ""); } finally { reloaded.close(); }
    assert.doesNotMatch(JSON.stringify(p.messages), /PRIVATE|context|reflection/);
  } finally { p.close(); }
});
test("challenge, unrelated and skip are voluntary; reviewed plan is explicit and delete clears all fields", async () => {
  const p = await page();
  try {
    await p.choice("challenge"); assert.match(p.$("outcome").textContent, /cannot establish AI use/);
    await p.choice("unrelated"); assert.match(p.$("outcome").textContent, /No explanation is needed/);
    await p.choice("skip"); assert.match(p.$("outcome").textContent, /grades are unaffected/);
    await p.choice("connected"); p.$("context").value = "SYNTHETIC_PRIVATE"; await p.click("next");
    p.$("need").selectedIndex = 1; await p.click("next");
    p.$("alternative").selectedIndex = 1; await p.click("next");
    p.$("correction").selectedIndex = 2; await p.click("next");
    p.$("if").value = "stuck"; p.$("then").value = "ask for a hint"; await p.click("next");
    assert.equal(p.$("plan").hidden, true);
    p.$("reviewed").checked = true; await p.click("next"); assert.equal(p.$("plan").hidden, false);
    await p.click("delete");
    for (const id of ["context", "why", "if", "then"]) assert.equal(p.$(id).value, "");
    assert.equal(p.$("plan-text").textContent, "");
    assert.doesNotMatch(JSON.stringify(p.messages), /SYNTHETIC_PRIVATE|ask for a hint/);
  } finally { p.close(); }
});
