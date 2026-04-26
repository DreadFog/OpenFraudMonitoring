/**
 * IP Extension — collects the visitor's public IP address.
 *
 * Extension interface:
 *   name    – unique identifier
 *   collect – async function called once during fingerprint collection
 */

const IP_API_URL = "https://ifconfig.me/all.json";

export default {
  name: "ip",

  async collect() {
    try {
      const r = await fetch(IP_API_URL, { method: "GET", mode: "cors" });
      const data = await r.json();
      return {
        ip: data.ip_addr || null,
        country: null,
        city: null,
      };
    } catch {
      return { ip: null, country: null, city: null };
    }
  },
};
