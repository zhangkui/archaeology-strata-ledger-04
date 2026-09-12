import { NavLink, Route, Routes, Navigate } from "react-router-dom";
import { useState } from "react";
import SitesPage from "./pages/SitesPage";
import SiteDetailPage from "./pages/SiteDetailPage";
import TrenchPage from "./pages/TrenchPage";
import AuditPage from "./pages/AuditPage";

export default function App() {
  const [actor, setActor] = useState(() => localStorage.getItem("actor") || "director-li");

  return (
    <div className="layout">
      <nav className="sidebar">
        <h1>考古发掘<br />层位证据链系统</h1>
        <NavLink to="/sites" className={({ isActive }) => (isActive ? "active" : "")}>
          遗址与探方
        </NavLink>
        <NavLink to="/audit" className={({ isActive }) => (isActive ? "active" : "")}>
          审计事件流
        </NavLink>
        <div className="actor">
          当前记录人
          <input
            value={actor}
            onChange={(e) => {
              setActor(e.target.value);
              localStorage.setItem("actor", e.target.value);
            }}
          />
        </div>
      </nav>
      <main>
        <Routes>
          <Route path="/" element={<Navigate to="/sites" replace />} />
          <Route path="/sites" element={<SitesPage />} />
          <Route path="/sites/:siteId" element={<SiteDetailPage />} />
          <Route path="/sites/:siteId/trenches/:trenchId" element={<TrenchPage />} />
          <Route path="/audit" element={<AuditPage />} />
        </Routes>
      </main>
    </div>
  );
}
