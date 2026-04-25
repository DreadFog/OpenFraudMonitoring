// OFM_SERVER_URL is injected at build time by Vite (see vite.config.js).
// Empty string = same-origin; set to "https://ofm.example.com" for remote.
const SERVER = typeof __OFM_SERVER_URL__ !== "undefined" ? __OFM_SERVER_URL__ : "";

export const CFG = {
  serverUrl:         SERVER,
  endpoint:          `${SERVER}/api/collect`,
  heartbeatEndpoint: `${SERVER}/api/heartbeat`,
  heartbeatMs:       30_000,
  sessionKey:        "__fp_sid",
  deviceIdKey:       "__fp_did",
  version:           "2.0.0",
  ipApiUrl:          "https://ifconfig.me/all.json",
};
