import { CFG } from "../config.js";

export function fetchPublicIP() {
  return new Promise(resolve => {
    fetch(CFG.ipApiUrl, { method: "GET", mode: "cors" })
      .then(r => r.json())
      .then(data => {
        resolve({
          ip:      data.ip_addr || null,
          country: null,
          city:    null,
        });
      })
      .catch(() => resolve({ ip: null, country: null, city: null }));
  });
}
