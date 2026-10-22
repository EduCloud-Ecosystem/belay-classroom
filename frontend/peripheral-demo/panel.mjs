// SPDX-License-Identifier: AGPL-3.0-only
import {HOST_PERMISSION} from "./collector.mjs";
export async function mountPanel({document, window, chrome, setInterval = window.setInterval.bind(window), clearInterval = window.clearInterval.bind(window)}) {
  const $ = id => document.getElementById(id);
  let state, step = 0, startTicket = 0, pending = false, preparedIntent = null;
  const fields = ["context", "need", "why", "alternative", "correction", "if", "then"];
  function clearReflection(message = "Reflection cleared. Nothing was saved or shared.") {
    for (const id of fields) $(id).value = "";
    $("reviewed").checked = false;
    $("plan-text").textContent = "";
    $("coaching").hidden = true; $("plan").hidden = true; $("choices").hidden = false;
    $("outcome").textContent = message;
    step = 0;
  }
  function render(value) {
    const changedSession = state && (state.windowId !== value.windowId || state.expiresAt !== value.expiresAt);
    if (state && ((["expired", "revoked", "unavailable", "off"].includes(value.status) && state.status !== value.status) || changedSession)) clearReflection();
    state = value;
    $("badge").textContent = value.status.toUpperCase();
    $("status").textContent = value.status === "active" || value.status === "paused"
      ? `${value.status === "active" ? "Active" : "Paused"} · selected window ${value.windowId} · ends ${new Date(value.expiresAt).toLocaleTimeString()}. No unobserved interval is inferred.`
      : ({off: "Off. Coaching and ordinary course help do not require collection.", expired: "Expired. Collection and the old session have ended; reflection was cleared.", revoked: "Revoked. Collection stopped and the optional permission was removed.", unavailable: "Coverage unavailable. Collection stopped and reflection was cleared. Check Chrome permissions if removal was interrupted."}[value.status]);
    $("start").disabled = pending || !preparedIntent || !$("consent").checked || ["active", "paused"].includes(value.status);
    $("pause").disabled = value.status !== "active";
    $("resume").disabled = value.status !== "paused";
    $("observation").hidden = !value.signal;
  }
  async function request(type, extra = {}) {
    try {
      const reply = await chrome.runtime.sendMessage({type, ...extra});
      if (!reply?.state) throw new Error("unavailable");
      render(reply.state);
      return reply;
    } catch {
      render({status: "unavailable", signal: false});
      return null;
    }
  }
  const send = async (type, extra = {}) => (await request(type, extra))?.state;
  $("consent").addEventListener("change", async () => {
    const ticket = ++startTicket;
    const previous = preparedIntent; preparedIntent = null;
    if (state) render(state);
    if (previous) await send("cancel_start", {intent: previous.nonce});
    if (!$("consent").checked) return;
    const window = await chrome.windows.getCurrent();
    const reply = await request("begin_start", {windowId: window.id});
    if (reply?.intent && ticket === startTicket && $("consent").checked) preparedIntent = reply.intent;
    else if (reply?.intent) await send("cancel_start", {intent: reply.intent.nonce});
    if (state) render(state);
  });
  $("start").addEventListener("click", async () => {
    if (!$("consent").checked || pending || !preparedIntent) return;
    const ticket = ++startTicket, intent = preparedIntent;
    preparedIntent = null; pending = true; render(state);
    // Invoke synchronously within this actual Start gesture. The worker intent
    // was prepared by the preceding consent-checkbox gesture, without a grant.
    const permissionRequest = chrome.permissions.request({origins: [HOST_PERMISSION]});
    try {
      const granted = await permissionRequest;
      if (granted && ticket === startTicket) {
        const accepted = await send("start", {windowId: intent.windowId, intent: intent.nonce});
        if (accepted?.status !== "active") $("outcome").textContent = "That consent intent ended or was revoked. Collection has not started; choose a fresh session explicitly.";
      } else {
        await send("cancel_start", {intent: intent.nonce});
        $("outcome").textContent = "Permission declined or consent cancelled. Collection stays off; private coaching is still available.";
      }
    } catch {
      await send("cancel_start", {intent: intent.nonce});
      $("outcome").textContent = "Permission unavailable. Collection has not started.";
    }
    finally { pending = false; if (state) render(state); }
  });
  for (const type of ["pause", "resume", "revoke", "delete"]) $(type).addEventListener("click", async () => {
    ++startTicket;
    if (["revoke", "delete"].includes(type)) { preparedIntent = null; $("consent").checked = false; clearReflection(); }
    await send(type);
  });
  function showStep() {
    $("coaching").hidden = false; $("plan").hidden = true; $("choices").hidden = true;
    for (const fieldset of document.querySelectorAll("[data-step]")) fieldset.hidden = Number(fieldset.dataset.step) !== step;
    $("progress").textContent = `STEP ${step + 1} OF 5 · OPTIONAL`;
    $("next").textContent = step === 4 ? "Review my plan" : "Continue";
    $("back").disabled = step === 0;
    document.querySelector(`[data-step="${step}"]`).querySelector("textarea,select")?.focus();
  }
  document.querySelectorAll("[data-choice]").forEach(button => button.addEventListener("click", () => {
    clearReflection("");
    if (button.dataset.choice === "connected") showStep();
    else $("outcome").textContent = {
      unrelated: "Understood. A site visit does not establish a connection to your task. No explanation is needed.",
      permitted: "Understood. Permitted use needs no correction here. Follow the actual assignment's separate disclosure rules.",
      challenge: "Your challenge is valid. This signal cannot establish AI use, intent or misconduct. Nothing is reported; you may pause, revoke or delete it.",
      skip: "Skipped. Your access and grades are unaffected; nothing was saved."
    }[button.dataset.choice];
  }));
  $("back").addEventListener("click", () => { if (step > 0) { step--; showStep(); } });
  $("next").addEventListener("click", () => {
    const required = {1: "need", 2: "alternative", 3: "correction"}[step];
    if (required && !$(required).value) { $("outcome").textContent = "Choose an option, or skip and clear. No explanation is required."; $(required).focus(); return; }
    $("outcome").textContent = "";
    if (step < 4) { step++; showStep(); return; }
    if (!$("if").value.trim() || !$("then").value.trim() || !$("reviewed").checked) {
      $("outcome").textContent = "Review your own if/then plan and check the choice box, or dismiss it."; return;
    }
    $("plan-text").textContent = `If ${$("if").value.trim()}, then I choose to ${$("then").value.trim()}.`;
    $("coaching").hidden = true; $("plan").hidden = false;
  });
  $("revise").addEventListener("click", () => { $("reviewed").checked = false; showStep(); });
  for (const id of ["dismiss", "clear-plan"]) $(id).addEventListener("click", () => clearReflection());
  window.addEventListener("pagehide", () => clearReflection(""));
  await send("get");
  // No text or DOM is sent: this polls only the five-field session state.
  const timer = setInterval(() => { void send("get"); }, 1000);
  return {destroy() { clearInterval(timer); clearReflection(""); }};
}
if (globalThis.document && globalThis.chrome) await mountPanel({document, window, chrome});
