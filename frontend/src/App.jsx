import React from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "./AuthContext";
import Dashboard from "./pages/Dashboard/Dashboard";
import SessionDetail from "./pages/SessionDetail/SessionDetail";
import Devices from "./pages/Devices/Devices";
import DeviceDetail from "./pages/DeviceDetail/DeviceDetail";
import Landing from "./pages/Landing/Landing";
import Intelligence from "./pages/Intelligence/Intelligence";
import Graph from "./pages/Graph/Graph";
import ExportsPage from "./pages/Exports/Exports";
import Administration from "./pages/Logging/Logging";
import RulesPage from "./pages/Rules/Rules";
import Login from "./pages/Login/Login";
import Profile from "./pages/Profile/Profile";
import NavHeader from "./components/NavHeader/NavHeader";
import { useUserSettings } from "./hooks/useUserSettings";
import { api } from "./api";
import "./App.css";

function ProtectedRoute({ children }) {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return children;
}

function AdminRoute({ children }) {
  const { isAuthenticated, user } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  if (user?.role !== "admin") return <Navigate to="/dashboard" replace />;
  return children;
}

function Chrome({ children }) {
  const { pathname } = useLocation();
  const { isAuthenticated } = useAuth();
  // Hide the global nav on the landing page and login page.
  const showNav = isAuthenticated && pathname !== "/" && pathname !== "/login";
  return (
    <>
      {isAuthenticated && <Appearance />}
      {showNav && <NavHeader />}
      {children}
    </>
  );
}

function Appearance() {
  const { settings } = useUserSettings();
  const [contentWidthPercent, setContentWidthPercent] = React.useState(100);

  React.useEffect(() => {
    const loadWidth = () => api.getGlobalSettings()
      .then((globalSettings) => setContentWidthPercent(Number(globalSettings["layout.content_width_percent"]) || 100))
      .catch(() => {});
    loadWidth();
    window.addEventListener("ofm:global-settings-updated", loadWidth);
    return () => window.removeEventListener("ofm:global-settings-updated", loadWidth);
  }, []);

  React.useEffect(() => {
    document.documentElement.dataset.theme = settings?.appearance?.theme === "light" ? "light" : "dark";
    document.documentElement.dataset.widgetColors = settings?.appearance?.widgetColors || "blue";
    document.documentElement.style.setProperty("--content-max-width", `${contentWidthPercent}%`);
  }, [settings?.appearance?.theme, settings?.appearance?.widgetColors, contentWidthPercent]);
  React.useEffect(() => () => {
    delete document.documentElement.dataset.theme;
    delete document.documentElement.dataset.widgetColors;
    document.documentElement.style.removeProperty("--content-max-width");
  }, []);
  return null;
}

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Chrome>
          <Routes>
            <Route path="/" element={<ProtectedRoute><Landing /></ProtectedRoute>} />
            <Route path="/login" element={<Login />} />
            <Route path="/dashboard" element={<ProtectedRoute><Dashboard /></ProtectedRoute>} />
            <Route path="/intelligence" element={<ProtectedRoute><Intelligence /></ProtectedRoute>} />
            <Route path="/graph" element={<ProtectedRoute><Graph /></ProtectedRoute>} />
            <Route path="/exports" element={<ProtectedRoute><ExportsPage /></ProtectedRoute>} />
            <Route path="/admin" element={<ProtectedRoute><Administration /></ProtectedRoute>} />
            <Route path="/rules" element={<AdminRoute><RulesPage /></AdminRoute>} />
            <Route path="/session/:fsid" element={<ProtectedRoute><SessionDetail /></ProtectedRoute>} />
            <Route path="/devices" element={<ProtectedRoute><Devices /></ProtectedRoute>} />
            <Route path="/device/:id" element={<ProtectedRoute><DeviceDetail /></ProtectedRoute>} />
            <Route path="/profile" element={<ProtectedRoute><Profile /></ProtectedRoute>} />
          </Routes>
        </Chrome>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
