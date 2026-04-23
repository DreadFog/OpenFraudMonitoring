import { safe } from "../helpers.js";

export function collectWebRTC() {
  return new Promise(resolve => {
    const ips = new Set();
    const timer = setTimeout(() => resolve([...ips]), 1500);
    const ok = safe(() => {
      const pc = new RTCPeerConnection({ iceServers: [] });
      pc.createDataChannel("");
      pc.createOffer().then(o => pc.setLocalDescription(o)).catch(() => {});
      pc.onicecandidate = e => {
        if (!e || !e.candidate) { clearTimeout(timer); resolve([...ips]); return; }
        const m = /([0-9]{1,3}(?:\.[0-9]{1,3}){3}|[a-f0-9:]{3,}(?::[a-f0-9:]+)+)/i.exec(e.candidate.candidate);
        if (m) ips.add(m[1]);
      };
      return true;
    });
    if (!ok) { clearTimeout(timer); resolve([]); }
  });
}
