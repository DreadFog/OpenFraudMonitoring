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
  captureFormValues:      true,  // Set to true to capture form field values (emails, passwords, etc)
  // Capture the actual copied/pasted clipboard text. Injected at build time via
  // the OFM_CAPTURE_CLIPBOARD build argument; defaults to false for privacy.
  captureClipboard:       typeof __OFM_CAPTURE_CLIPBOARD__ !== "undefined" ? __OFM_CAPTURE_CLIPBOARD__ : false,
};
