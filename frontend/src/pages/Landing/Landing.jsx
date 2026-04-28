import React from "react";
import { Link } from "react-router-dom";
import "./Landing.css";

const TILES = [
  {
    path: "/dashboard",
    title: "Dashboard",
    description: "Live session monitoring, risk scoring and configurable widgets.",
    icon: "📊",
  },
  {
    path: "/intelligence",
    title: "Intelligence",
    description: "Browse cached threat intel — search any IP and view its STIX context.",
    icon: "🔍",
  },
  {
    path: "/logging",
    title: "Logging",
    description: "Queue depths, connector health and recent error logs.",
    icon: "📡",
  },
];

export default function Landing() {
  return (
    <div className="landing">
      <header className="landing-hero">
        <h1>OpenFraudMonitoring</h1>
        <p>Browser fingerprinting, behavioral signals and threat intelligence.</p>
      </header>
      <div className="landing-tiles">
        {TILES.map((t) => (
          <Link key={t.path} to={t.path} className="landing-tile">
            <div className="landing-tile-icon">{t.icon}</div>
            <h2>{t.title}</h2>
            <p>{t.description}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
