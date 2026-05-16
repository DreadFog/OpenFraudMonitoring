import React from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../AuthContext";
import "./NavHeader.css";

const TABS = [
  { path: "/dashboard", label: "Dashboard" },
  { path: "/intelligence", label: "Intelligence" },
  { path: "/exports", label: "Exports" },
];

const ADMIN_TABS = [
  { path: "/admin", label: "Administration" },
  { path: "/rules", label: "Rules" },
];

export default function NavHeader() {
  const { pathname } = useLocation();
  const { user, logout } = useAuth();
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
