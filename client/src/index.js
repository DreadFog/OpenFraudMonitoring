import { collect } from "./collect.js";
import { startHeartbeat } from "./heartbeat.js";

function init() {
  collect().then(sid => startHeartbeat(sid));
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
