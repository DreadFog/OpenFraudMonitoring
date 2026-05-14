import React, { useState, useRef, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import { api } from "../../api";
import "./IpIntelPopover.css";

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

  for (const seg of [...left, ...right]) {
    if (!/^[0-9a-f]{1,4}$/.test(seg)) return null;
  }

  if (halves.length === 1) {
    if (left.length !== 8) return null;
    return left;
  }

  const missing = 8 - (left.length + right.length);
  if (missing <= 0) return null;
  return [...left, ...Array(missing).fill("0"), ...right];
}

function isPrivateIp(ip) {
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

function fmtDate(iso) {
  if (!iso) return null;
  try {
    return new Date(iso).toISOString().slice(0, 10);
  } catch {
    return null;
  }
}

export default function IpIntelPopover({ ip }) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0 });
  const btnRef = useRef(null);
  const popoverRef = useRef(null);
  const privateIp = isPrivateIp(ip);

  const updatePos = useCallback(() => {
    if (!btnRef.current) return;
    const rect = btnRef.current.getBoundingClientRect();
    setPos({ top: rect.bottom + 6, left: rect.left });
  }, []);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handleOutside = (e) => {
      if (
        btnRef.current?.contains(e.target) ||
        popoverRef.current?.contains(e.target)
      ) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", handleOutside);
    return () => document.removeEventListener("mousedown", handleOutside);
  }, [open]);

  const handleClick = async (e) => {
    e.stopPropagation();
    e.preventDefault();
    if (open) {
      setOpen(false);
      return;
    }
    updatePos();
    setOpen(true);
    if (privateIp) return;
    if (data) return;
    setLoading(true);
    try {
      const result = await api.getIpIntel(ip);
      setData(result);
    } catch {
      setData({ error: true });
    } finally {
      setLoading(false);
    }
  };

  if (!ip) return null;

  // Extract malware names from relationships
  const malwareEntries = [];
  if (data?.found && data.relationships) {
    for (const r of data.relationships) {
      const src = r.source || {};
      const tgt = r.target || {};
      if (src.stix_type === "malware") {
        malwareEntries.push({ name: src.raw?.name || src.value, date: fmtDate(r.start_time || r.created_at_platform) });
      } else if (tgt.stix_type === "malware") {
        malwareEntries.push({ name: tgt.raw?.name || tgt.value, date: fmtDate(r.start_time || r.created_at_platform) });
      }
    }
  }

  const popover = open ? createPortal(
    <div
      className="ip-intel-popover"
      ref={popoverRef}
      style={{ top: pos.top, left: pos.left }}
      onClick={(e) => e.stopPropagation()}
    >
      <div className="ip-intel-popover-header">{ip}</div>
      {privateIp && (
        <div className="ip-intel-popover-body ip-intel-muted">
          Private IP address. Intelligence lookup is skipped.
        </div>
      )}
      {loading && <div className="ip-intel-popover-body ip-intel-loading">Loading…</div>}
      {data?.error && <div className="ip-intel-popover-body ip-intel-muted">Failed to load</div>}
      {data && !privateIp && !data.error && !data.found && (
        <div className="ip-intel-popover-body ip-intel-muted">No intelligence cached</div>
      )}
      {data?.found && !privateIp && (
        <div className="ip-intel-popover-body">
          <div className="ip-intel-row">
            <span className="ip-intel-label">AS</span>
            <span className="ip-intel-value">
              {data.autonomous_system
                ? `${data.autonomous_system.raw?.number ? `AS${data.autonomous_system.raw.number}` : ""} ${data.autonomous_system.raw?.name || data.autonomous_system.value || ""}`.trim()
                : "—"}
            </span>
          </div>
          <div className="ip-intel-row">
            <span className="ip-intel-label">Country</span>
            <span className="ip-intel-value">
              {data.country?.raw?.name || data.country?.value || "—"}
            </span>
          </div>
          {malwareEntries.length > 0 && (
            <div className="ip-intel-malware-section">
              <span className="ip-intel-label">Malware</span>
              {malwareEntries.map((m, i) => (
                <div key={i} className="ip-intel-malware-item">
                  <span className="ip-intel-malware-name">{m.name}</span>
                  {m.date && <span className="ip-intel-malware-date">{m.date}</span>}
                </div>
              ))}
            </div>
          )}
          {malwareEntries.length === 0 && (
            <div className="ip-intel-row">
              <span className="ip-intel-label">Malware</span>
              <span className="ip-intel-value ip-intel-muted">None</span>
            </div>
          )}
        </div>
      )}
    </div>,
    document.body
  ) : null;

  return (
    <span className="ip-intel-wrap" onClick={(e) => e.stopPropagation()}>
      <button
        className="ip-intel-lens"
        ref={btnRef}
        onClick={handleClick}
        title="View IP intelligence"
        type="button"
      >
        🔍
      </button>
      {popover}
    </span>
  );
}
