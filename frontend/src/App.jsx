import React from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Dashboard from "./pages/Dashboard/Dashboard";
import SessionDetail from "./pages/SessionDetail/SessionDetail";
import "./App.css";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/session/:fsid" element={<SessionDetail />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
