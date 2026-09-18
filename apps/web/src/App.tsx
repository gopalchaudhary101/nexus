import { useEffect } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { getToken } from "./lib/api";
import Layout from "./components/Layout";
import LandingPage from "./pages/LandingPage";
import DashboardPage from "./pages/DashboardPage";
import CommandCenterPage from "./pages/CommandCenterPage";
import AgentTracePage from "./pages/AgentTracePage";
import DocumentsPage from "./pages/DocumentsPage";
import KnowledgeGraphPage from "./pages/KnowledgeGraphPage";
import DataLabPage from "./pages/DataLabPage";
import RagEvalPage from "./pages/RagEvalPage";
import ApprovalsPage from "./pages/ApprovalsPage";
import RiskCenterPage from "./pages/RiskCenterPage";
import PrivacyPage from "./pages/PrivacyPage";
import NotFoundPage from "./pages/NotFoundPage";

function RequireAuth({ children }: { children: React.ReactElement }) {
  const token = getToken();
  if (!token) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  const token = getToken();
  useEffect(() => {
    // 401 handling: drop stale tokens
    const onUnauthorized = () => {
      if (!getToken()) return;
      import("./lib/api").then(({ clearToken }) => {
        clearToken();
        window.location.href = "/login";
      });
    };
    window.addEventListener("nexus:unauthorized", onUnauthorized);
    return () => window.removeEventListener("nexus:unauthorized", onUnauthorized);
  }, []);

  return (
    <Routes>
      <Route path="/login" element={token ? <Navigate to="/" replace /> : <LandingPage />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="agents" element={<CommandCenterPage />} />
        <Route path="trace" element={<AgentTracePage />} />
        <Route path="documents" element={<DocumentsPage />} />
        <Route path="graph" element={<KnowledgeGraphPage />} />
        <Route path="datalab" element={<DataLabPage />} />
        <Route path="rag-eval" element={<RagEvalPage />} />
        <Route path="approvals" element={<ApprovalsPage />} />
        <Route path="risk" element={<RiskCenterPage />} />
        <Route path="privacy" element={<PrivacyPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
