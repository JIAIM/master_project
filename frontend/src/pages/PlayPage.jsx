import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client.js";
import { useProctoring } from "../hooks/useProctoring.js";

const ATTENTION_LABEL = {
  ok: "Увага на екрані",
  distraction_warning: "Погляд поза екраном",
  face_not_detected: "Обличчя не видно",
  multiple_faces: "У кадрі кілька людей",
};
const TYPE_HINT = {
  single_choice: "Оберіть одну відповідь",
  true_false: "Це твердження правдиве чи ні?",
  multiple_choice: "Оберіть усі правильні відповіді",
};

const fmtScore = (v) => (Number.isInteger(v) ? v : v.toFixed(1));

function Timer({ deadlineMs, offsetMs, onExpire }) {
  const [now, setNow] = useState(Date.now() + offsetMs);
  const fired = useRef(false);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now() + offsetMs), 500);
    return () => clearInterval(t);
  }, [offsetMs]);
  const left = Math.max(0, deadlineMs - now);
  useEffect(() => {
    if (left === 0 && !fired.current) {
      fired.current = true;
      onExpire();
    }
  }, [left, onExpire]);
  const m = Math.floor(left / 60000);
  const s = Math.floor((left % 60000) / 1000);
  return <span className={`timer ${left < 60000 ? "low" : ""}`}>⏱ {m}:{String(s).padStart(2, "0")}</span>;
}

function Review({ result }) {
  return (
    <div className="stack">
      <div className="card center result-card">
        <div className="muted">Ваш результат</div>
        <div className="big">{fmtScore(result.score)} з {fmtScore(result.max_score)} балів</div>
        <div>Правильних відповідей: <strong>{result.correct_count}</strong> з {result.total}</div>
        {result.answered_count < result.total && (
          <div className="muted small">Без відповіді: {result.total - result.answered_count}</div>
        )}
      </div>
      {result.review ? result.review.map((q, i) => (
        <div key={q.question_id} className={`card review ${q.is_correct ? "ok" : "bad"}`}>
          <div className="review-head">
            <span className="q-num">{i + 1}</span>
            <strong>{q.text}</strong>
            <span className={`pill ${q.is_correct ? "ok" : "bad"}`}>{q.is_correct ? "правильно" : q.selected.length ? "неправильно" : "без відповіді"}</span>
          </div>
          <ul className="review-options">
            {q.options.map((o) => {
              const chosen = q.selected.includes(o.id);
              return (
                <li key={o.id} className={`${o.is_correct ? "correct" : ""} ${chosen && !o.is_correct ? "wrong" : ""}`}>
                  {o.is_correct ? "✓" : chosen ? "✗" : "•"} {o.text}
                  {chosen && <span className="muted small"> — ваша відповідь</span>}
                </li>
              );
            })}
          </ul>
          {q.explanation && <p className="explanation">{q.explanation}</p>}
        </div>
      )) : <p className="muted center">Викладач вирішив не показувати правильні відповіді.</p>}
    </div>
  );
}

export default function PlayPage() {
  const creds = useMemo(() => {
    try { return JSON.parse(sessionStorage.getItem("player")); } catch { return null; }
  }, []);
  const token = creds?.token;

  const [data, setData] = useState(null);
  const [answers, setAnswers] = useState({});
  const [saving, setSaving] = useState({});      // qid -> "saving" | "saved" | "error"
  const [error, setError] = useState("");
  const [finishing, setFinishing] = useState(false);
  const [offset, setOffset] = useState(0);
  const lastQuestion = useRef(null);

  const load = useCallback(async () => {
    try {
      const st = await api(`/play/${token}`, { auth: false });
      setData(st);
      setAnswers(st.answers || {});
      setOffset(st.server_time_ms - Date.now());
    } catch (e) {
      setError(e.message);
    }
  }, [token]);

  useEffect(() => { if (token) load(); }, [token, load]);

  // Раз на 30 с перевіряємо, чи викладач не закрив сесію
  const inProgress = data?.state === "in_progress";
  useEffect(() => {
    if (!inProgress) return undefined;
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [inProgress, load]);

  const { videoRef, status: camStatus, attention } = useProctoring({
    enabled: !!token && inProgress,
    thresholdSec: data?.distraction_threshold_sec ?? 3,
    onEvent: (e) => {
      api(`/play/${token}/proctoring`, {
        method: "POST", auth: false, body: { ...e, question_id: lastQuestion.current },
      }).catch(() => {});
    },
  });

  const choose = async (q, optionId) => {
    lastQuestion.current = q.id;
    const current = answers[q.id] || [];
    const next = q.type === "multiple_choice"
      ? (current.includes(optionId) ? current.filter((x) => x !== optionId) : [...current, optionId])
      : [optionId];
    setAnswers((a) => ({ ...a, [q.id]: next }));
    setSaving((s) => ({ ...s, [q.id]: "saving" }));
    try {
      await api(`/play/${token}/answers/${q.id}`, { method: "PUT", auth: false, body: { option_ids: next } });
      setSaving((s) => ({ ...s, [q.id]: "saved" }));
    } catch (e) {
      setSaving((s) => ({ ...s, [q.id]: "error" }));
      setError(e.message);
      if (e.status === 409) load(); // сесію закрили або час вийшов — підтягнемо підсумок
    }
  };

  const finish = useCallback(async (force = false) => {
    const unanswered = data.questions.filter((q) => !(answers[q.id] || []).length).length;
    if (!force && unanswered > 0 &&
        !window.confirm(`Ви не відповіли на ${unanswered} з ${data.questions.length} питань. Завершити тест?`)) return;
    setFinishing(true);
    try {
      await api(`/play/${token}/finish`, { method: "POST", auth: false });
      await load();
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) {
      setError(e.message);
    } finally {
      setFinishing(false);
    }
  }, [data, answers, token, load]);

  const onExpire = useCallback(() => finish(true), [finish]);

  if (!creds) {
    return (
      <div className="card narrow center">
        <p>Спершу введіть PIN тесту.</p>
        <Link to="/" className="btn primary">До входу</Link>
      </div>
    );
  }
  if (!data) {
    return <div className="card narrow">{error ? <div className="notice bad">⚠️ {error}</div> : <p className="muted">Завантаження тесту…</p>}</div>;
  }

  const answeredCount = data.questions.filter((q) => (answers[q.id] || []).length).length;

  return (
    <div className="play">
      <div className="play-header card">
        <div>
          <div className="muted small">{data.display_name}</div>
          <strong>{data.test_title}</strong>
        </div>
        {inProgress && (
          <div className="row gap">
            <span>Відповіли: <strong>{answeredCount}</strong> з {data.questions.length}</span>
            {data.deadline_ms && <Timer deadlineMs={data.deadline_ms} offsetMs={offset} onExpire={onExpire} />}
          </div>
        )}
      </div>

      {error && <div className="notice bad">⚠️ {error}</div>}

      {inProgress && (
        <aside className={`camera attention-${attention}`}>
          <video ref={videoRef} muted playsInline />
          <div className="camera-status">
            {camStatus === "loading" && "Запуск камери…"}
            {camStatus === "denied" && "Доступ до камери заборонено — викладач це побачить"}
            {camStatus === "error" && "Не вдалося запустити розпізнавання"}
            {camStatus === "ready" && ATTENTION_LABEL[attention]}
          </div>
          {!document.fullscreenElement && (
            <button className="small-btn" onClick={() => document.documentElement.requestFullscreen?.()}>
              На весь екран
            </button>
          )}
        </aside>
      )}

      {inProgress ? (
        <div className="stack">
          {data.questions.map((q, i) => {
            const chosen = answers[q.id] || [];
            const multi = q.type === "multiple_choice";
            return (
              <div key={q.id} className={`card question ${chosen.length ? "answered" : ""}`}>
                <div className="question-head">
                  <span className="q-num">{i + 1}</span>
                  <div className="grow">
                    <div className="question-text">{q.text}</div>
                    <div className="muted small">{TYPE_HINT[q.type]}</div>
                  </div>
                  <span className="save-state small">
                    {saving[q.id] === "saving" && "збереження…"}
                    {saving[q.id] === "saved" && "✓ збережено"}
                    {saving[q.id] === "error" && <span className="bad-text">не збережено</span>}
                  </span>
                </div>
                <div className={`answer-list ${q.type === "true_false" ? "tf" : ""}`}>
                  {q.options.map((o) => (
                    <label key={o.id} className={`answer ${chosen.includes(o.id) ? "chosen" : ""}`}>
                      <input
                        type={multi ? "checkbox" : "radio"}
                        name={`q-${q.id}`}
                        checked={chosen.includes(o.id)}
                        onChange={() => choose(q, o.id)}
                      />
                      <span>{o.text}</span>
                    </label>
                  ))}
                </div>
              </div>
            );
          })}
          <div className="card finish-bar">
            <span>Відповіли на <strong>{answeredCount}</strong> з {data.questions.length} питань</span>
            <button className="primary big-btn" onClick={() => finish(false)} disabled={finishing}>
              {finishing ? "Завершення…" : "Завершити тест"}
            </button>
          </div>
        </div>
      ) : (
        <>
          {!data.session_open && data.result && data.result.answered_count < data.result.total && (
            <p className="muted center small">Тест завершено викладачем або через ліміт часу.</p>
          )}
          {data.result && <Review result={data.result} />}
        </>
      )}
    </div>
  );
}
