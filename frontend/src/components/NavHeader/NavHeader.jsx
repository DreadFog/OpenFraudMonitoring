import React from "react";
import { Link, useLocation } from "react-router-dom";
import "./NavHeader.css";

const TABS = [
  { path: "/dashboard", label: "Dashboard" },
  { path: "/intelligence", label: "Intelligence" },
  { path: "/logging", label: "Logging" },
];

export default function NavHeader() {
  const { pathname } = useLocation();
  return (
    <nav className="nav-header">
      <Link to="/" className="nav-brand">
        <img src="/logo.png" alt="" className="nav-brand-logo" />
        OpenFraudMonitoring
      </Link>
      <div className="nav-tabs">
        {TABS.map((t) => (
          <Link
            key={t.path}
            to={t.path}
            className={`nav-tab ${pathname.startsWith(t.path) ? "nav-tab-active" : ""}`}
          >
            {t.label}
          </Link>
        ))}
      </div>
      <a href="/demo.html" className="nav-demo" target="_blank" rel="noopener noreferrer">Demo</a>
    </nav>
  );
}
