import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, download } from "../api/client.js";

const ALERT_LABEL = {
  distraction_warning: "погляд поза екраном",
  face_not_detected: "немає обличчя в кадрі",
  multiple_faces: "кілька облич у кадрі",
  tab_hidden: "перейшов на іншу вкладку",
  fullscreen_exit: "вийшов з повноекранного режиму",
  camera_denied: "заборонив доступ до камери",
  proctoring_unavailable: "прокторинг не запустився на пристрої",
};

const FLAG_LABEL = {
  too_easy: "занадто легке",
  too_hard: "занадто складне",
  low_discrimination: "слабко розрізняє сильних і слабких",
  negative_discrimination: "⚠ можлива помилка в ключі",
};

const fmtTime = (iso) => (iso ? new Date(iso).toLocaleTimeString("uk-UA", { hour: "2-digit", minute: "2-digit" }) : "—");
const fmtScore = (v) => (v == null ? "—" : Number.isInteger(v) ? v : v.toFixed(1));

const downloadCsv = (sessionId) => download(`/sessions/${sessionId}/results.csv`, `rezultaty_sesii_${sessionId}.csv`);

export default function SessionPage() {
  const { sessionId } = useParams();
  const [dash, setDash] = useState(null);
  const [events, setEvents] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [error, setError] = useState("");
  const [closing, setClosing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [d, ev] = await Promise.all([
        api(`/sessions/${sessionId}/dashboard`),
        api(`/sessions/${sessionId}/proctoring`),
      ]);
      setDash(d);
      setEvents(ev);
      setError("");
    } catch (e) {
      setError(e.message);
    }
  }, [sessionId]);

  const running = dash?.session.status === "running";
  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    if (!running) return undefined;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [running, load]);

  const finishedCount = dash?.participants.filter((p) => p.state === "finished").length ?? 0;
  useEffect(() => {
    if (!dash || finishedCount === 0) return;
    api(`/sessions/${sessionId}/analytics`).then(setAnalytics).catch(() => {});
  }, [sessionId, finishedCount, dash?.session.status]);

  const close = async () => {
    if (!window.confirm("Завершити тест для всіх? Хто не встиг — отримає бали за вже дані відповіді.")) return;
    setClosing(true);
    try {
      await api(`/sessions/${sessionId}/close`, { method: "POST" });
      await load();
    } catch (e) {
      setError(e.message);
    } finally {
      setClosing(false);
    }
  };

  if (!dash) {
    return <div className="card">{error ? <div className="notice bad">⚠️ {error}</div> : <p className="muted">Завантаження…</p>}</div>;
  }

  const { session, participants, total_questions: total } = dash;
  const finished = participants.filter((p) => p.state === "finished");
  const avg = finished.length ? finished.reduce((s, p) => s + p.score, 0) / finished.length : null;
  const maxScore = finished[0]?.max_score ?? total;
  const limit = session.settings?.time_limit_min;

  return (
    <div className="stack">
      <Link to="/teacher/results" className="back-link">← Усі результати</Link>
      {error && <div className="notice bad">⚠️ {error}</div>}

      <div className="card session-head">
        <div>
          <div className="muted small">Тест</div>
          <h1 style={{ margin: "2px 0 6px" }}>{dash.test_title}</h1>
          <div className="row gap-sm">
            {running ? <span className="pill ok status-pulse">Триває</span> : <span className="pill neutral">Завершено</span>}
            <span className="muted small">
              Питань: {total} · {limit ? `ліміт часу: ${limit} хв` : "без обмеження часу"} · почато о {fmtTime(session.started_at)}
              {session.finished_at && ` · завершено о ${fmtTime(session.finished_at)}`}
            </span>
          </div>
        </div>
        {running && (
          <div className="pin-box">
            <div className="muted small">PIN для студентів</div>
            <div className="pin">{session.pin_code}</div>
            <div className="muted small">Студенти відкривають {window.location.origin} і вводять PIN</div>
          </div>
        )}
      </div>

      <div className="stat-row">
        <div className="stat"><div className="stat-value">{participants.length}</div><div className="muted small">приєдналися</div></div>
        <div className="stat"><div className="stat-value">{participants.length - finished.length}</div><div className="muted small">проходять</div></div>
        <div className="stat"><div className="stat-value">{finished.length}</div><div className="muted small">завершили</div></div>
        <div className="stat"><div className="stat-value">{avg == null ? "—" : `${fmtScore(avg)} / ${fmtScore(maxScore)}`}</div><div className="muted small">середній бал</div></div>
      </div>

      <div className="row gap-sm">
        {running && (
          <button className="danger" onClick={close} disabled={closing}>
            {closing ? "Завершення…" : "Завершити тест для всіх"}
          </button>
        )}
        {finished.length > 0 && (
          <button onClick={() => downloadCsv(sessionId).catch((e) => setError(e.message))}>⬇ Завантажити результати (CSV)</button>
        )}
      </div>

      <div className="host-grid">
        <div className="card">
          <h3>Студенти</h3>
          <div className="table-wrap">
          <table className="table">
            <thead>
              <tr><th>Ім'я</th><th>Стан</th><th>Прогрес</th><th>Бали</th><th>Увага</th><th>Час</th></tr>
            </thead>
            <tbody>
              {participants.map((p) => (
                <tr key={p.participant_id} className={p.alert_active ? "row-alert" : ""}>
                  <td>
                    <strong>{p.display_name}</strong>
                    {p.camera_off && <div><span className="pill bad" title="Студент не дав доступу до камери або прокторинг не запустився">камера вимкнена</span></div>}
                  </td>
                  <td>{p.state === "finished" ? <span className="pill ok">завершив</span> : <span className="pill pending">проходить</span>}</td>
                  <td style={{ minWidth: 140 }}>
                    <div className="row gap-sm" style={{ flexWrap: "nowrap" }}>
                      <div className="bar small-bar grow"><div style={{ width: `${total ? (p.answered / total) * 100 : 0}%` }} /></div>
                      <span className="small muted">{p.answered}/{p.total}</span>
                    </div>
                  </td>
                  <td>{p.score == null ? "—" : <strong>{fmtScore(p.score)} / {fmtScore(p.max_score)}</strong>}</td>
                  <td>
                    {p.alert_active && <span className="alert-indicator" title="Зараз відволікся" />}
                    {p.distraction_count > 0 ? <span> {p.distraction_count}</span> : <span className="muted">0</span>}
                  </td>
                  <td className="small muted">{fmtTime(p.joined_at)}{p.finished_at && `–${fmtTime(p.finished_at)}`}</td>
                </tr>
              ))}
              {!participants.length && (
                <tr><td colSpan={6} className="muted center">Чекаємо на студентів… Покажіть їм PIN.</td></tr>
              )}
            </tbody>
          </table>
          </div>
        </div>

        <div className="card">
          <h3>Журнал прокторингу</h3>
          <ul className="alerts">
            {events.map((e) => (
              <li key={e.id}>
                <span className="muted small">{fmtTime(e.received_at)}</span>{" "}
                <strong>{e.display_name}</strong>: {ALERT_LABEL[e.event_type] ?? e.event_type}
                {e.duration_ms != null && <span className="muted"> ({Math.round(e.duration_ms / 1000)} с)</span>}
              </li>
            ))}
            {!events.length && <li className="muted">Порушень не зафіксовано</li>}
          </ul>
        </div>
      </div>

      {analytics && analytics.n_items > 0 && (
        <div className="card">
          <h3>Аналіз якості питань</h3>
          <p className="muted small">
            Завершених спроб: {analytics.n_participants} · надійність тесту KR-20:{" "}
            {analytics.kr20 != null ? analytics.kr20.toFixed(2) : "недостатньо даних"}
          </p>
          {analytics.n_participants < 5 && (
            <div className="notice info small">
              Статистика стає показовою від 5 завершених спроб. Поки що «частка правильних» відображає лише
              відповіді тих, хто вже завершив: 0% — ніхто не відповів правильно або питання пропустили,
              100% — усі відповіли правильно. Розрізнювальна здатність почне рахуватися з 5-ї спроби.
            </div>
          )}
          <div className="table-wrap">
          <table className="table">
            <thead>
              <tr><th>#</th><th>Питання</th><th>Частка правильних</th><th>Розрізнювальна здатність</th><th>Зауваження</th></tr>
            </thead>
            <tbody>
              {analytics.items.map((it) => (
                <tr key={it.question_id}>
                  <td>{it.position}</td>
                  <td className="truncate" title={it.text}>{it.text}</td>
                  <td>{it.p_value != null ? `${Math.round(it.p_value * 100)}%` : "—"}</td>
                  <td>{it.discrimination != null ? it.discrimination.toFixed(2) : "—"}</td>
                  <td className="small">
                    {it.flags.map((f) => FLAG_LABEL[f] ?? (f.startsWith("nonfunctional") ? "хибний варіант, який ніхто не обирає" : f)).join(", ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      )}
    </div>
  );
}
