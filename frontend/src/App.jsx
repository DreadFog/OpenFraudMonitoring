import React from "react";
import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import Dashboard from "./pages/Dashboard/Dashboard";
import SessionDetail from "./pages/SessionDetail/SessionDetail";
import Landing from "./pages/Landing/Landing";
import Intelligence from "./pages/Intelligence/Intelligence";
import Logging from "./pages/Logging/Logging";
import NavHeader from "./components/NavHeader/NavHeader";
import "./App.css";

function Chrome({ children }) {
  const { pathname } = useLocation();
  // Hide the global nav on the landing page (it has its own hero).
  const showNav = pathname !== "/";
  return (
    <>
      {showNav && <NavHeader />}
      {children}
    </>
  );
}

function App() {
  return (
    <BrowserRouter>
      <Chrome>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/intelligence" element={<Intelligence />} />
          <Route path="/logging" element={<Logging />} />
          <Route path="/session/:fsid" element={<SessionDetail />} />
        </Routes>
      </Chrome>
    </BrowserRouter>
  );
}

export default App;
