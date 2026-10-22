// SPDX-License-Identifier: AGPL-3.0-only
export const ORIGIN = "http://127.0.0.1:8769";
export const HOST_PERMISSION = ORIGIN + "/*";
export const TTL_MS = 10 * 60 * 1000;
export const STORAGE_KEY = "belayPeripheralSessionV1";
const statuses = new Set(["off", "active", "paused", "expired", "revoked", "unavailable"]);
export const emptyState = () => ({version: 1, status: "off", windowId: null, expiresAt: null, signal: false});

export function validState(value) {
  return value && Object.keys(value).sort().join() === "expiresAt,signal,status,version,windowId" &&
    value.version === 1 && statuses.has(value.status) && typeof value.signal === "boolean" &&
    (value.windowId === null || Number.isSafeInteger(value.windowId) && value.windowId >= 0) &&
    (value.expiresAt === null || Number.isSafeInteger(value.expiresAt) && value.expiresAt > 0) &&
    (!["active", "paused"].includes(value.status) || value.windowId !== null && value.expiresAt !== null);
}

export function matchesOrigin(url) {
  // The browser exposes a URL under the optional host permission. Read only its
  // origin here; never retain or send the URL, path, query, title or content.
  try { return new URL(url).origin === ORIGIN; } catch { return false; }
}

export function createCollector(api, now = Date.now) {
  let state = emptyState(), generation = 0, tail = Promise.resolve(), pendingIntent = null;
  const permission = {origins: [HOST_PERMISSION]};
  const copy = () => ({...state});
  const queue = task => {
    const result = tail.then(task);
    tail = result.catch(() => {});
    return result;
  };
  async function publish() {
    await api.action.setBadgeText({text: {active: state.signal ? "?" : "ON", paused: "PAUS", expired: "END", unavailable: "STOP"}[state.status] || "OFF"});
    await api.action.setBadgeBackgroundColor({color: state.status === "active" ? "#275b4d" : "#65594d"});
    await api.action.setTitle({title: "Belay optional check-in · " + state.status + (state.signal ? " · possible check-in, not proof of use" : "")});
    await api.storage.session.set({[STORAGE_KEY]: copy()});
  }
  async function expire() {
    if (pendingIntent && now() >= pendingIntent.expiresAt) {
      pendingIntent = null;
      await removeUnownedPermission();
    }
    if (state.expiresAt !== null && now() >= state.expiresAt && ["active", "paused"].includes(state.status)) {
      generation++;
      state = {...emptyState(), status: "expired"};
      await publish();
    }
  }
  const ready = queue(async () => {
    await api.storage.session.setAccessLevel({accessLevel: "TRUSTED_CONTEXTS"});
    const stored = (await api.storage.session.get(STORAGE_KEY))[STORAGE_KEY];
    if (validState(stored)) state = {...stored};
    // Worker suspension/restart is a coverage gap, never an observed interval.
    if (state.status === "active") state.status = "paused";
    await expire();
    await removeUnownedPermission();
    await publish();
  });
  async function failClosed() {
    generation++;
    pendingIntent = null;
    state = {...emptyState(), status: "unavailable"};
    try { await publish(); await removeUnownedPermission(); } catch { /* No content or exception text is logged. */ }
    return copy();
  }
  async function removeUnownedPermission() {
    // A late permission grant must not outlive its cancelled intent. A newer
    // accepted session, including an explicitly paused one, owns its grant.
    if (!["active", "paused"].includes(state.status)) await api.permissions.remove(permission);
  }
  async function command(message) {
    // Invalidate pending observations immediately, before the async queue drains.
    if (message?.type !== "get") generation++;
    return queue(async () => {
      await ready;
      await expire();
      const fields = Object.keys(message || {}).sort().join();
      const shapes = {get: "type", begin_start: "type,windowId", start: "intent,type,windowId", cancel_start: "intent,type", pause: "type", resume: "type", revoke: "type", delete: "type"};
      if (!message || fields !== shapes[message.type]) throw new Error("invalid command");
      if (message.type === "get") return copy();
      if (message.type === "begin_start") {
        if (!Number.isSafeInteger(message.windowId) || message.windowId < 0 ||
            ["active", "paused"].includes(state.status)) throw new Error("start unavailable");
        const window = await api.windows.get(message.windowId);
        if (window.incognito || window.type !== "normal" || !window.focused) throw new Error("window unavailable");
        pendingIntent = {nonce: crypto.randomUUID(), windowId: message.windowId, expiresAt: now() + 60000};
        await api.alarms.create("belay-peripheral-consent-expiry", {when: pendingIntent.expiresAt});
        return {...copy(), intent: {...pendingIntent}};
      }
      if (message.type === "cancel_start") {
        if (pendingIntent?.nonce === message.intent) {
          pendingIntent = null;
          await api.alarms.clear("belay-peripheral-consent-expiry");
        }
        await removeUnownedPermission();
        return copy();
      }
      if (message.type === "start") {
        if (!pendingIntent || message.intent !== pendingIntent.nonce || message.windowId !== pendingIntent.windowId ||
            now() >= pendingIntent.expiresAt || ["active", "paused"].includes(state.status)) {
          await removeUnownedPermission();
          return copy();
        }
        pendingIntent = null; // Consume once, before any asynchronous permission check.
        await api.alarms.clear("belay-peripheral-consent-expiry");
        const window = await api.windows.get(message.windowId);
        if (window.incognito || window.type !== "normal" || !window.focused || !await api.permissions.contains(permission)) {
          await removeUnownedPermission(); return copy();
        }
        state = {version: 1, status: "active", windowId: message.windowId, expiresAt: now() + TTL_MS, signal: false};
        await api.alarms.create("belay-peripheral-expiry", {when: state.expiresAt});
      } else if (message.type === "pause" && state.status === "active") {
        state.status = "paused";
      } else if (message.type === "resume" && state.status === "paused") {
        if (!await api.permissions.contains(permission)) throw new Error("permission unavailable");
        const window = await api.windows.get(state.windowId);
        if (window.incognito || window.type !== "normal") throw new Error("window unavailable");
        state.status = "active"; // Original expiry is never renewed.
      } else if (["revoke", "delete"].includes(message.type)) {
        pendingIntent = null; // Invalidates pending consent in every open panel.
        state = {...emptyState(), status: message.type === "revoke" ? "revoked" : "off"};
        await publish(); // Stop before asking Chrome to remove the permission.
        await api.alarms.clear("belay-peripheral-expiry");
        await api.alarms.clear("belay-peripheral-consent-expiry");
        const removed = await api.permissions.remove(permission);
        if (!removed && await api.permissions.contains(permission)) throw new Error("permission removal unconfirmed");
        if (message.type === "delete") await api.storage.session.remove(STORAGE_KEY);
        return copy();
      } else throw new Error("transition unavailable");
      await publish();
      return copy();
    }).catch(failClosed);
  }
  function observe() {
    const ticket = ++generation;
    return queue(async () => {
      await ready;
      await expire();
      if (state.status !== "active" || state.signal || ticket !== generation) return copy();
      if (!await api.permissions.contains(permission)) return failClosed();
      const window = await api.windows.get(state.windowId);
      if (!window.focused || window.incognito) return copy();
      const tabs = await api.tabs.query({active: true, windowId: state.windowId});
      const matching = tabs.length === 1 && tabs[0].active && tabs[0].windowId === state.windowId && matchesOrigin(tabs[0].url);
      // A focus/tab/pause/revoke change invalidates an in-flight browser read.
      const stillFocused = (await api.windows.get(state.windowId)).focused;
      await expire();
      if (matching && stillFocused && ticket === generation && state.status === "active") {
        state.signal = true; // One bounded, origin-free boolean; no visit history/duration.
        await publish();
      }
      return copy();
    }).catch(failClosed);
  }
  function permissionRemoved() {
    generation++;
    return queue(async () => {
      await ready;
      return ["active", "paused"].includes(state.status) ? failClosed() : copy();
    });
  }
  function permissionAdded() {
    generation++;
    return queue(async () => {
      await ready; await expire();
      // Handles a late native grant even if its original panel has closed.
      if (!pendingIntent) await removeUnownedPermission();
      return copy();
    }).catch(failClosed);
  }
  function windowRemoved(id) {
    generation++;
    return queue(async () => { await ready; if (id === state.windowId) return failClosed(); return copy(); });
  }
  return {ready, command, observe, permissionRemoved, permissionAdded, windowRemoved};
}
