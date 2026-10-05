import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client.js";

function LaunchPanel({ test, onCancel }) {
  const navigate = useNavigate();
  const [includeAi, setIncludeAi] = useState(!test.is_published);
  const [showReview, setShowReview] = useState(true);
  const [limitOn, setLimitOn] = useState(false);
  const [limitMin, setLimitMin] = useState(20);
  const [threshold, setThreshold] = useState(3);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const start = async () => {
    setError("");
    setBusy(true);
    try {
      const session = await api("/sessions", {
        method: "POST",
        body: {
          test_id: test.id,
          settings: {
            include_ai_verified: includeAi,
            show_review: showReview,
            time_limit_min: limitOn ? Number(limitMin) : null,
            distraction_threshold_sec: Number(threshold),
          },
        },
      });
      navigate(`/teacher/sessions/${session.id}`);
    } catch (e) {
      setError(e.message);
      setBusy(false);
    }
  };

  return (
    <div className="launch-panel">
      <h3>Запуск тесту «{test.title}»</h3>
      <label className="check-row">
        <input type="checkbox" checked={includeAi} onChange={(e) => setIncludeAi(e.target.checked)} />
        <span>Включати питання, перевірені лише ШІ <span className="muted small">(інакше — тільки затверджені вами)</span></span>
      </label>
      <label className="check-row">
        <input type="checkbox" checked={showReview} onChange={(e) => setShowReview(e.target.checked)} />
        <span>Після завершення показати студенту розбір із правильними відповідями</span>
      </label>
      <label className="check-row">
        <input type="checkbox" checked={limitOn} onChange={(e) => setLimitOn(e.target.checked)} />
        <span>Обмежити час</span>
        {limitOn && (
          <span className="row gap-sm">
            <input type="number" className="num" min={1} max={300} value={limitMin}
                   onChange={(e) => setLimitMin(e.target.value)} /> хв
          </span>
        )}
      </label>
      <label className="check-row">
        <span>Сигналізувати, якщо студент відволікся довше ніж</span>
        <input type="number" className="num" min={1} max={30} value={threshold}
               onChange={(e) => setThreshold(e.target.value)} /> с
      </label>
      {error && <div className="notice bad">⚠️ {error}</div>}
      <div className="row gap-sm">
        <button className="primary" onClick={start} disabled={busy}>{busy ? "Запуск…" : "Запустити й отримати PIN"}</button>
        <button onClick={onCancel} disabled={busy}>Скасувати</button>
      </div>
    </div>
  );
}

export default function TestsPage() {
  const [tests, setTests] = useState(null);
  const [error, setError] = useState("");
  const [launching, setLaunching] = useState(null);

  useEffect(() => {
    api("/tests").then(setTests).catch((e) => setError(e.message));
  }, []);

  return (
    <div className="stack">
      <div className="page-head">
        <h1>Мої тести</h1>
        <Link to="/teacher/generate" className="btn primary">+ Створити тест</Link>
      </div>
      {error && <div className="notice bad">⚠️ {error}</div>}
      {tests === null && <p className="muted">Завантаження…</p>}
      {tests?.length === 0 && (
        <div className="card empty">
          <p>Тестів ще немає.</p>
          <Link to="/teacher/generate" className="btn primary">Завантажити матеріал і згенерувати тест</Link>
        </div>
      )}
      {tests?.map((t) => (
        <div key={t.id} className="card test-card">
          <div className="test-card-main">
            <div>
              <Link to={`/teacher/tests/${t.id}`} className="test-title-link">{t.title}</Link>
              {t.is_published
                ? <span className="pill ok">переглянуто</span>
                : <span className="pill pending">питання ще не переглянуто</span>}
              <div className="muted small">
                {t.materials.length ? `Матеріали: ${t.materials.map((m) => m.title).join(", ")}` : "Без матеріалів"}
              </div>
            </div>
            <div className="row gap-sm">
              <Link to={`/teacher/tests/${t.id}`} className="btn">Питання</Link>
              <button className="primary" onClick={() => setLaunching(launching === t.id ? null : t.id)}>
                Запустити тест
              </button>
            </div>
          </div>
          {launching === t.id && <LaunchPanel test={t} onCancel={() => setLaunching(null)} />}
        </div>
      ))}
    </div>
  );
}
