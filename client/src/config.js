/**
 * OFM client configuration.
 *
 * OFM_SERVER_URL and FPSCANNER_KEY are injected at build time by Vite.
 */
const SERVER = typeof __OFM_SERVER_URL__ !== "undefined" ? __OFM_SERVER_URL__ : "";

export const CFG = {
  serverUrl:         SERVER,
  collectEndpoint:   `${SERVER}/api/collect`,
  heartbeatEndpoint: `${SERVER}/api/heartbeat`,
  heartbeatMs:       30_000,
};
