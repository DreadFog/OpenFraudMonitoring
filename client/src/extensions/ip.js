/**
 * IP Extension — collects the visitor's public IP address.
 *
 * Extension interface:
 *   name    – unique identifier
 *   collect – async function called once during fingerprint collection
 */

const IP_API_URL = "https://ifconfig.co/json";

export default {
  name: "ip",

  async collect() {
    try {
      const r = await fetch(IP_API_URL, { method: "GET", mode: "cors" });
      const data = await r.json();
      return {
        ip: data.ip || null,
        country: data.country || null,
        country_iso: data.country_iso || null,
        city: data.city || null,
        asn: data.asn || null,
        asn_org: data.asn_org || null,
      };
    } catch {
      return { ip: null, country: null, country_iso: null, city: null, asn: null, asn_org: null };
    }
  },
};
