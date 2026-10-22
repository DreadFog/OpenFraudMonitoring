import React from "react";

export function entityUrl(type, value) {
  return `/intelligence?type=${encodeURIComponent(type)}&value=${encodeURIComponent(value)}`;
}

export function openEntityInNewTab(type, value) {
  window.open(entityUrl(type, value), "_blank", "noopener");
}

function parseIPv4(ip) {
  const parts = ip.split(".");
  if (parts.length !== 4) return null;
  const nums = [];
  for (const part of parts) {
    if (!/^\d{1,3}$/.test(part)) return null;
    const n = Number(part);
    if (n < 0 || n > 255) return null;
    nums.push(n);
  }
  return nums;
}

function expandIPv6(input) {
  const ip = input.toLowerCase();
  if (!ip.includes(":")) return null;
  if (ip.includes(".")) return null;
  const halves = ip.split("::");
  if (halves.length > 2) return null;

  const left = halves[0] ? halves[0].split(":").filter(Boolean) : [];
  const right = halves[1] ? halves[1].split(":").filter(Boolean) : [];

  for (const segment of [...left, ...right]) {
    if (!/^[0-9a-f]{1,4}$/.test(segment)) return null;
  }

  if (halves.length === 1) {
    if (left.length !== 8) return null;
    return left;
  }

  const missing = 8 - (left.length + right.length);
  if (missing <= 0) return null;
  return [...left, ...Array(missing).fill("0"), ...right];
}

export function isPrivateIp(ip) {
  if (!ip) return false;
  const cleaned = String(ip).trim().replace(/^\[(.*)\]$/, "$1");

  const v4 = parseIPv4(cleaned);
  if (v4) {
    const [a, b] = v4;
    return a === 10 || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168);
  }

  const v6 = expandIPv6(cleaned);
  if (v6) {
    const first = parseInt(v6[0], 16);
    return (first & 0xfe) === 0xfc;
  }

  return false;
}

export function isIpEntityType(type) {
  return type === "ipv4-addr" || type === "ipv6-addr";
}

export function fmtDate(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toISOString().replace("T", " ").slice(0, 19) + " UTC";
  } catch {
    return String(iso);
  }
}

export function ObjectLabel({ obj, onClick }) {
  if (!obj) return <span className="intel-muted">—</span>;
  const { stix_type, value, stix_object: r } = obj;
  const stix = r || {};
  const wrap = (content) => onClick
    ? <span
        className="intel-link"
        onClick={(e) => { e.stopPropagation(); onClick(stix_type, value); }}
        onAuxClick={(e) => {
          if (e.button === 1) { e.preventDefault(); e.stopPropagation(); openEntityInNewTab(stix_type, value); }
        }}
        onMouseDown={(e) => { if (e.button === 1) e.preventDefault(); }}
      >{content}</span>
    : <span>{content}</span>;
  if (stix_type === "indicator") return wrap(<><b>indicator</b> · {stix.name || stix.pattern || value}</>);
  if (stix_type === "malware") return wrap(<><b>malware</b> · {stix.name || value}</>);
  if (stix_type === "campaign") return wrap(<><b>campaign</b> · {stix.name || value}</>);
  if (stix_type === "intrusion-set") return wrap(<><b>intrusion-set</b> · {stix.name || value}</>);
  if (stix_type === "autonomous-system") return wrap(<><b>AS</b> · {stix.number ? `AS${stix.number}` : value} {stix.name ? `(${stix.name})` : ""}</>);
  if (stix_type === "location") return wrap(<><b>country</b> · {stix.name || value}</>);
  return wrap(<><b>{stix_type}</b> · {value}</>);
}

export const TYPE_LABELS = {
  "ipv4-addr": "IPv4 Address",
  "ipv6-addr": "IPv6 Address",
  "user-agent": "User Agent",
  "autonomous-system": "Autonomous System",
  location: "Country",
  indicator: "Indicator",
  malware: "Malware",
  campaign: "Campaign",
  "intrusion-set": "Intrusion Set",
};

export const TYPE_PLACEHOLDERS = {
  "ipv4-addr": "Enter an IPv4 address…",
  "ipv6-addr": "Enter an IPv6 address…",
  "user-agent": "Enter a user-agent string…",
  "autonomous-system": "Enter an AS number…",
  location: "Enter a country code (e.g. US)…",
  indicator: "Enter an indicator pattern…",
  malware: "Enter a malware name…",
  campaign: "Enter a campaign name…",
  "intrusion-set": "Enter an intrusion-set name…",
};
