import { CFG } from "./config.js";
import { now } from "./helpers.js";
import { beh, trackNavigation } from "./behavior.js";
import { send } from "./send.js";

export function startHeartbeat(sid) {
  function beat() {
    trackNavigation();
    const snapshot = {
      session:   sid,
      timestamp: now(),
      url:       location.href,
      behavior: {
        mouseMoves:       beh.mouseMoves.splice(0),
        clicks:           beh.clicks.splice(0),
        keydowns:         beh.keydowns.splice(0),
        touches:          beh.touches.splice(0),
        scrolls:          beh.scrolls.splice(0),
        copyPastes:       beh.copyPastes.splice(0),
        navigationEvents: beh.navigationEvents.splice(0),
      },
    };
    send(CFG.heartbeatEndpoint, snapshot);
  }

  beat();
  setInterval(beat, CFG.heartbeatMs);
}
