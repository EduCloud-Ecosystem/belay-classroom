/* SPDX-License-Identifier: AGPL-3.0-only
 * Explicit learner actions only. No polling, model calls, browser storage or detectors.
 */
(function () {
  "use strict";
  window.BelayClassroom = {
    mount({container, base, context, onRetry}) {
      let epoch = 0, requestSequence = 0, key = null, state = null, busy = false;
      const status = document.createElement("p");
      status.setAttribute("tabindex", "-1");
      status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
      const content = document.createElement("div");
      const heading = document.createElement("h3"); heading.textContent = "Private classroom guidance";
      container.replaceChildren(heading, status, content);
      function active() {
        const value = context();
        const supported = [
          ["info511-lab3-q4-synthetic", "info511-lab3-q4-synthetic-v1"],
          ["info511-nhanes-wrangling", "info511-nhanes-wrangling-v1"]
        ];
        return value?.learner_id && supported.some(([id, version]) =>
          value.exercise_id === id && value.exercise_version === version) ? value : null;
      }
      function currentKey() { return JSON.stringify([base(), active()]); }
      function clear() {
        epoch++; requestSequence++; key = currentKey(); state = null; busy = false;
        content.replaceChildren(); status.textContent = ""; container.hidden = !active();
      }
      async function request(body) {
        const value = active();
        if (!value) return;
        const mine = epoch, originalKey = currentKey(), sequence = ++requestSequence;
        const stale = () => mine !== epoch || originalKey !== currentKey() || sequence !== requestSequence;
        try {
        const headers = await window.BelayAuth.headers(base());
        if (stale()) return;
        const path = "/api/classroom/" + encodeURIComponent(value.exercise_id) + "/" + encodeURIComponent(value.exercise_version);
        const response = await fetch(base() + path, {
          method:body ? "POST" : "GET", headers, credentials:window.BelayAuth.credentials?.(base()) || "omit", cache:"no-store",
          redirect:"error", body:body ? JSON.stringify(body) : undefined
        });
        const result = await response.json();
        if (stale()) return;
        if (!response.ok) throw new Error(result.detail?.code || "Guidance unavailable");
        state = result; draw(); return true;
        } catch (error) { if (stale()) return; throw error; }
      }
      async function refresh() {
        if (key !== currentKey()) clear();
        if (!active() || busy) return;
        const mine = epoch, originalKey = currentKey();
        try { await request(); }
        catch (_) { if (mine !== epoch || originalKey !== currentKey()) return; state = null; content.replaceChildren(); status.textContent = "Private guidance unavailable. Continue independent work; tutoring still requires current permission and checkpoints."; refreshControl(); }
      }
      function button(label, action, values = {}) {
        const b = document.createElement("button");
        b.type = "button"; b.textContent = label; b.disabled = busy;
        b.addEventListener("click", async () => {
          if (busy || !state) return;
          busy = true;
          content.querySelectorAll("button").forEach(item => { item.disabled = true; });
          const revision = state.revision, mine = epoch, originalKey = currentKey();
          try {
            const confirmed = await request({request_id:crypto.randomUUID().replaceAll("-", ""),
              expected_revision:revision, action, ...values});
            if (confirmed && mine === epoch && originalKey === currentKey()) {
              status.textContent += " Action recorded; your notebook is unchanged.";
              status.focus?.();
              if (action === "retry") onRetry?.();
            }
          } catch (_) {
            if (mine !== epoch || originalKey !== currentKey()) return;
            status.textContent = "Action not confirmed. Refresh guidance before retrying; no automatic retry was sent.";
          } finally { if (mine === epoch && originalKey === currentKey()) { busy = false; content.querySelectorAll("button").forEach(item => { item.disabled = false; }); } }
        });
        content.appendChild(b);
      }
      function paragraph(text) {
        const p = document.createElement("p"); p.textContent = text; content.appendChild(p);
      }
      function draw() {
        content.replaceChildren();
        status.textContent = "Optional monitoring: " + state.monitor + ".";
        paragraph(state.notice);
        paragraph("Checkpoint records presence only; it does not assess authorship or understanding.");
        if (!state.checkpoint) button("I wrote my schema and observational-unit prediction", "checkpoint", {schema_present:true, unit_present:true});
        else paragraph("Prediction checkpoint recorded.");
        if (state.monitor === "active") button("Pause optional tracking", "pause");
        else if (state.monitor === "full") paragraph("Optional tracking stopped because its private buffer is full. Revoke to clear the buffer before enabling again.");
        else button("Enable optional tracking with this notice", "enable", {notice_version:state.notice_version});
        button("Revoke optional tracking and clear its records", "revoke");
        button("Declare: I used no AI assistance", "declaration", {declaration:"no_ai"});
        button("Declare: I used AI assistance", "declaration", {declaration:"ai_assisted"});
        paragraph(state.declaration ? "Assistance declaration: " + state.declaration : "Reminder: an assistance declaration is still required. No AI is a valid choice.");
        for (const [id, alert] of Object.entries(state.alerts)) {
          paragraph("Private guidance: " + (state.guidance[alert.rule] || "Review the assignment policy.") + " Status: " + alert.state + ".");
          if (state.monitor === "active") {
            button("I opened this guidance", "guidance_opened", {alert_id:id});
            button("Challenge this alert", "challenge", {alert_id:id});
            button("I will retry with permitted hints", "retry", {alert_id:id});
          }
        }
        refreshControl();
      }
      function refreshControl() {
        const refreshButton = document.createElement("button");
        refreshButton.type = "button"; refreshButton.textContent = "Refresh guidance";
        refreshButton.addEventListener("click", refresh); content.appendChild(refreshButton);
      }
      clear();
      return {refresh, clear};
    }
  };
})();
