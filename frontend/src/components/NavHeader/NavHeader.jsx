import React from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../AuthContext";
import "./NavHeader.css";

const TABS = [
  { path: "/dashboard", label: "Dashboard" },
  { path: "/intelligence", label: "Intelligence" },
  { path: "/logging", label: "Logging" },
];

export default function NavHeader() {
  const { pathname } = useLocation();
  const { user, logout } = useAuth();
  const navigate = useNavigate();

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
        {TABS.map((t) => (
          <Link
            key={t.path}
            to={t.path}
            className={`nav-tab ${pathname.startsWith(t.path) ? "nav-tab-active" : ""}`}
          >
            {t.label}
          </Link>
        ))}
        {user?.role === "admin" && (
          <Link
            to="/users"
            className={`nav-tab ${pathname.startsWith("/users") ? "nav-tab-active" : ""}`}
          >
            Users
          </Link>
        )}
      </div>
      <div className="nav-right">
        {user && <span className="nav-user">{user.username}</span>}
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
