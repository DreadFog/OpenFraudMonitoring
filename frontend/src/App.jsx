import React from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Dashboard from "./Dashboard";
import SessionDetail from "./SessionDetail";
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
