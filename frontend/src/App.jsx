import React from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "./AuthContext";
import Dashboard from "./pages/Dashboard/Dashboard";
import SessionDetail from "./pages/SessionDetail/SessionDetail";
import Landing from "./pages/Landing/Landing";
import Intelligence from "./pages/Intelligence/Intelligence";
import Administration from "./pages/Logging/Logging";
import Login from "./pages/Login/Login";
import Profile from "./pages/Profile/Profile";
import NavHeader from "./components/NavHeader/NavHeader";
import "./App.css";

function ProtectedRoute({ children }) {
  const { isAuthenticated } = useAuth();
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return children;
}

function Chrome({ children }) {
  const { pathname } = useLocation();
  const { isAuthenticated } = useAuth();
  // Hide the global nav on the landing page and login page.
  const showNav = isAuthenticated && pathname !== "/" && pathname !== "/login";
  return (
    <>
      {showNav && <NavHeader />}
      {children}
    </>
  );
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
            <Route path="/admin" element={<ProtectedRoute><Administration /></ProtectedRoute>} />
            <Route path="/session/:fsid" element={<ProtectedRoute><SessionDetail /></ProtectedRoute>} />
            <Route path="/profile" element={<ProtectedRoute><Profile /></ProtectedRoute>} />
          </Routes>
        </Chrome>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
