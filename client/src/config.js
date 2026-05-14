/**
 * OFM client configuration.
 *
 * OFM_SERVER_URL and FPSCANNER_KEY are injected at build time by Vite.
 */
const SERVER = typeof __OFM_SERVER_URL__ !== "undefined" ? __OFM_SERVER_URL__ : "";

export const CFG = {
  serverUrl:              SERVER,
  collectEndpoint:        `${SERVER}/api/initial`,
  heartbeatEndpoint:      `${SERVER}/api/heartbeat`,
  behavioralEventEndpoint: `${SERVER}/api/behavioral_event`,
  heartbeatMs:            30_000,
};
