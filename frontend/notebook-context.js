/* SPDX-License-Identifier: AGPL-3.0-only */
// Explicit selected-code capture only. Never save, submit, fetch or persist content.
(function () {
  "use strict";
  const exact = (value, keys) => value && typeof value === "object" && !Array.isArray(value) &&
    Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
  window.BelayNotebookContext = {
    mount({demo, onState, canCapture = () => true}) {
      if (window.BELAY_NOTEBOOK_CONTEXT === undefined) return;
      let sequence = 0;
      const config = window.BELAY_NOTEBOOK_CONTEXT;
      const origin = new URL(window.location.href).origin;
      const nonce = /^#belay-notebook=([0-9a-f]{64})$/.exec(new URL(window.location.href).hash)?.[1];
      const opener = window.opener;
      const unavailable = () => onState({valid:false, message:"Notebook snapshot unavailable. Reopen Belay from the notebook command."});
      if (!demo || !Number.isFinite(demo.expires_at) || Date.now() >= demo.expires_at * 1000 ||
          !exact(config, ["version", "origin"]) || config.version !== 1 || config.origin !== origin ||
          window.BELAY_SESSION_PROXY !== true || !nonce || !opener || opener === window ||
          typeof opener.postMessage !== "function" || !window.crypto?.subtle) {
        unavailable(); return;
      }
      onState({valid:false, message:"Waiting for an explicit code snapshot from your notebook. Nothing is submitted automatically."});
      window.addEventListener("belay-auth-changed", () => { sequence++; unavailable(); });
      window.addEventListener("message", async event => {
        if (event.origin !== origin || event.source !== opener || event.data?.nonce !== nonce || !canCapture()) return;
        const mine = ++sequence, value = event.data;
        if (!exact(value, ["type", "version", "nonce", "source", "dirty"]) ||
            value.type !== "belay-notebook-snapshot" || value.version !== 1 ||
            typeof value.source !== "string" || typeof value.dirty !== "boolean" ||
            new TextEncoder().encode(value.source).length > 8192 || value.source !== demo.source) {
          unavailable(); return;
        }
        onState({valid:false, message:"Checking the captured notebook code. Nothing is being submitted."});
        try {
          const digest = await window.crypto.subtle.digest("SHA-256", new TextEncoder().encode(value.source));
          if (mine !== sequence || !canCapture()) return;
          const hash = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, "0")).join("");
          onState({valid:true, source:value.source, sha256:hash, dirty:value.dirty,
            message:value.dirty
              ? "Unsaved notebook code captured. This does not save or submit your work. Choose Ask Belay separately."
              : "The notebook reports no unsaved changes. This capture does not save or submit work. Choose Ask Belay separately."});
        } catch { if (mine === sequence) unavailable(); }
      });
      opener.postMessage({type:"belay-notebook-ready", version:1, nonce}, origin);
    }
  };
})();
