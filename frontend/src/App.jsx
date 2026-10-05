import { Navigate, NavLink, Route, Routes, Link } from "react-router-dom";
import { getUser, logout } from "./api/client.js";
import JoinPage from "./pages/JoinPage.jsx";
import PlayPage from "./pages/PlayPage.jsx";
import LoginPage from "./pages/LoginPage.jsx";
import TestsPage from "./pages/TestsPage.jsx";
import GeneratePage from "./pages/GeneratePage.jsx";
import TestEditorPage from "./pages/TestEditorPage.jsx";
import SessionPage from "./pages/SessionPage.jsx";
import ResultsPage from "./pages/ResultsPage.jsx";

function RequireTeacher({ children }) {
  const user = getUser();
  if (!user || (user.role !== "teacher" && user.role !== "admin")) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  const user = getUser();
  return (
    <div className="app">
      <header className="topbar">
        <Link to={user ? "/teacher" : "/"} className="brand">EduTest</Link>
        <nav>
          {user ? (
            <>
              <NavLink to="/teacher" end>Мої тести</NavLink>
              <NavLink to="/teacher/generate">Створити тест</NavLink>
              <NavLink to="/teacher/results">Результати</NavLink>
              <span className="muted">{user.full_name}</span>
              <button className="link" onClick={() => { logout(); window.location.href = "/"; }}>Вийти</button>
            </>
          ) : (
            <Link to="/login">Вхід для викладача</Link>
          )}
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<JoinPage />} />
          <Route path="/play" element={<PlayPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/teacher" element={<RequireTeacher><TestsPage /></RequireTeacher>} />
          <Route path="/teacher/generate" element={<RequireTeacher><GeneratePage /></RequireTeacher>} />
          <Route path="/teacher/tests/:testId" element={<RequireTeacher><TestEditorPage /></RequireTeacher>} />
          <Route path="/teacher/sessions/:sessionId" element={<RequireTeacher><SessionPage /></RequireTeacher>} />
          <Route path="/teacher/results" element={<RequireTeacher><ResultsPage /></RequireTeacher>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}
