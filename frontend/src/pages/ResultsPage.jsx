import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client.js";

const fmtDate = (iso) =>
  new Date(iso).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
const fmtScore = (v) => (v == null ? "—" : Number.isInteger(v) ? v : v.toFixed(1));

export default function ResultsPage() {
  const [sessions, setSessions] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api("/sessions").then(setSessions).catch((e) => setError(e.message));
  }, []);

  return (
    <div className="stack">
      <div className="page-head"><h1>Результати</h1></div>
      <p className="muted small">Усі проведені тести. Результати зберігаються назавжди — їх можна переглянути й завантажити в CSV.</p>
      {error && <div className="notice bad">⚠️ {error}</div>}
      {sessions === null && <p className="muted">Завантаження…</p>}
      {sessions?.length === 0 && <div className="card empty"><p>Ще не проведено жодного тесту.</p></div>}
      {sessions?.length > 0 && (
        <div className="card">
          <table className="table">
            <thead>
              <tr><th>Дата</th><th>Тест</th><th>Стан</th><th>Студентів</th><th>Середній бал</th><th></th></tr>
            </thead>
            <tbody>
              {sessions.map((s) => (
                <tr key={s.id}>
                  <td className="small">{fmtDate(s.started_at || s.created_at)}</td>
                  <td><strong>{s.test_title}</strong></td>
                  <td>{s.status === "running" ? <span className="pill ok">триває · PIN {s.pin_code}</span> : <span className="pill neutral">завершено</span>}</td>
                  <td>{s.finished} / {s.participants}</td>
                  <td>{s.avg_score == null ? "—" : `${fmtScore(s.avg_score)} / ${fmtScore(s.max_score)}`}</td>
                  <td><Link to={`/teacher/sessions/${s.id}`}>Детальніше →</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
