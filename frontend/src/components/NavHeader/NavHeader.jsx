import React from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../AuthContext";
import { useUserSettings } from "../../hooks/useUserSettings";
import "./NavHeader.css";

const TABS = [
  { path: "/dashboard", label: "Dashboard" },
  { path: "/devices", label: "Devices" },
  { path: "/intelligence", label: "Intelligence" },
  { path: "/graph", label: "Graph" },
  { path: "/exports", label: "Exports" },
];

const ADMIN_TABS = [
  { path: "/admin", label: "Administration" },
  { path: "/rules", label: "Rules" },
];

export default function NavHeader() {
  const { pathname } = useLocation();
  const { user, logout } = useAuth();
  const { settings, loading, update } = useUserSettings();
  const navigate = useNavigate();
  const isAdmin = user?.role === "admin";
  const tabs = isAdmin ? [...TABS, ...ADMIN_TABS] : TABS;

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <nav className="nav-header">
      <Link to="/" className="nav-brand">
        <img src="/logo.png" alt="" className="nav-brand-logo" />
        OpenFraudMonitoring
      </Link>
      <div className="nav-tabs">
        {tabs.map((t) => (
          <Link
            key={t.path}
            to={t.path}
            className={`nav-tab ${pathname.startsWith(t.path) ? "nav-tab-active" : ""}`}
          >
            {t.label}
          </Link>
        ))}

      </div>
      <div className="nav-right">
        {user && <Link to="/profile" className="nav-user-link">{user.username}</Link>}
        {user && (
          <button
            type="button"
            className="nav-theme-switch"
            role="switch"
            aria-label="Light mode"
            aria-checked={settings?.appearance?.theme === "light"}
            title={`Switch to ${settings?.appearance?.theme === "light" ? "dark" : "light"} mode`}
            disabled={loading}
            onClick={() => update({ appearance: { theme: settings?.appearance?.theme === "light" ? "dark" : "light" } })}
          >
            <span className="nav-theme-thumb" aria-hidden="true">{settings?.appearance?.theme === "light" ? "☀" : "☾"}</span>
          </button>
        )}
        <a href="/demo.html" className="nav-demo" target="_blank" rel="noopener noreferrer">Demo</a>
        {user && (
          <button className="nav-logout" onClick={handleLogout}>
            Logout
          </button>
        )}
      </div>
    </nav>
  );
}
