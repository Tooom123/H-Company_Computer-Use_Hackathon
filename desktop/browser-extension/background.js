// Relays the boxes from content.js to the H Companion desktop app. Only the service worker may reach 127.0.0.1
// (pages on https cannot). If the app is not running, the request fails silently.
const APP = "http://127.0.0.1:8770/targets";

chrome.runtime.onMessage.addListener((msg, sender) => {
  if (!msg || msg.type !== "hcs-targets" || !sender.tab) return;
  fetch(APP, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-HCS-Targets": "1" },
    body: JSON.stringify({ tab: sender.tab.id, targets: msg.targets }),
  }).catch(() => {});
});
