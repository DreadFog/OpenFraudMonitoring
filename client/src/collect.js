import { CFG } from "./config.js";
import { now, safe } from "./helpers.js";
import { getSession } from "./session.js";
import { collectNavigator, collectOperatingSystem } from "./collectors/navigator.js";
import { collectScreen } from "./collectors/screen.js";
import { collectTimezone } from "./collectors/timezone.js";
import { collectCanvas } from "./collectors/canvas.js";
import { collectWebGL } from "./collectors/webgl.js";
import { collectAudio } from "./collectors/audio.js";
import { collectNetwork } from "./collectors/network.js";
import { collectStorage } from "./collectors/storage.js";
import { collectBotSignals } from "./collectors/botsignals.js";
import { collectAPIs } from "./collectors/apis.js";
import { collectWebRTC } from "./collectors/webrtc.js";
import { fetchPublicIP } from "./collectors/ip.js";
import { generateDeviceID } from "./deviceid.js";
import { send } from "./send.js";

export async function collect() {
  const sid = getSession();
  const t0  = now();

  const [audio, webrtcIPs, publicIP] = await Promise.all([
    collectAudio(),
    collectWebRTC(),
    fetchPublicIP(),
  ]);

  const fingerprint = {
    session:         sid,
    version:         CFG.version,
    timestamp:       t0,
    url:             location.href,
    referrer:        document.referrer,
    title:           document.title,
    navigator:       collectNavigator(),
    screen:          collectScreen(),
    timezone:        collectTimezone(),
    operatingSystem: collectOperatingSystem(),
    canvas:          collectCanvas(),
    webgl:           collectWebGL(),
    audio,
    network:         collectNetwork(),
    storage:         collectStorage(),
    botSignals:      collectBotSignals(),
    apis:            collectAPIs(),
    webrtcIPs,
    publicIP,
    timing: {
      collectionMs: now() - t0,
      domReady:     safe(() => Math.round(performance.timing.domContentLoadedEventEnd - performance.timing.navigationStart)),
      load:         safe(() => Math.round(performance.timing.loadEventEnd - performance.timing.navigationStart)),
    },
  };

  fingerprint.deviceID = generateDeviceID(fingerprint);
  send(CFG.endpoint, fingerprint);
  return sid;
}
