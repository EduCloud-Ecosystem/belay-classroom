// SPDX-License-Identifier: AGPL-3.0-only
import {createCollector} from "./collector.mjs";
const collector = createCollector(chrome);
const panel = chrome.runtime.getURL("panel.html");
chrome.action.onClicked.addListener(tab => {
  if (!tab.incognito && Number.isSafeInteger(tab.windowId)) chrome.tabs.create({windowId: tab.windowId, url: panel});
});
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  // Only this installed extension's own page can operate its consent session.
  if (sender.id !== chrome.runtime.id || sender.url !== panel) return false;
  collector.command(message).then(result => {
    const {intent, ...state} = result;
    respond({state, ...(intent ? {intent} : {})});
  });
  return true;
});
chrome.tabs.onActivated.addListener(() => { void collector.observe(); });
chrome.tabs.onUpdated.addListener(() => { void collector.observe(); });
chrome.windows.onFocusChanged.addListener(() => { void collector.observe(); });
chrome.windows.onRemoved.addListener(id => { void collector.windowRemoved(id); });
chrome.permissions.onRemoved.addListener(() => { void collector.permissionRemoved(); });
chrome.permissions.onAdded.addListener(() => { void collector.permissionAdded(); });
chrome.alarms.onAlarm.addListener(alarm => {
  if (["belay-peripheral-expiry", "belay-peripheral-consent-expiry"].includes(alarm.name)) void collector.command({type: "get"});
});
