import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, download } from "../api/client.js";

const downloadExport = (testId, format, answers) =>
  download(`/tests/${testId}/export?format=${format}&answers=${answers}`, `test_${testId}.${format}`);

function ExportBar({ testId, disabled, savedFormUrl }) {
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [form, setForm] = useState(null);

  const createForm = async () => {
    setBusy("gform");
    setError("");
    try {
      setForm(await api(`/tests/${testId}/google-form`, { method: "POST" }));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  };
  const run = async (format, answers) => {
    setBusy(`${format}-${answers}`);
    setError("");
    try {
      await downloadExport(testId, format, answers);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy("");
    }
  };
  const btn = (format, answers, label) => (
    <button onClick={() => run(format, answers)} disabled={disabled || !!busy}>
      {busy === `${format}-${answers}` ? "Формування…" : label}
    </button>
  );
  return (
    <div className="export-bar">
      <div className="small"><strong>Завантажити тест</strong> <span className="muted">— затверджені й перевірені ШІ питання</span></div>
      <div className="row gap-sm">
        {btn("docx", false, "Word — для студентів")}
        {btn("docx", true, "Word — з відповідями")}
        {btn("pdf", false, "PDF — для студентів")}
        {btn("pdf", true, "PDF — з відповідями")}
        <button onClick={createForm} disabled={disabled || !!busy}>
          {busy === "gform" ? "Створення форми… (до хвилини)" : "Створити Google Форму"}
        </button>
      </div>
      {form && (
        <div className="notice ok">
          ✅ Google Форму створено:{" "}
          <a href={form.edit_url} target="_blank" rel="noreferrer">редагувати форму</a>
          {" · "}
          <a href={form.respond_url} target="_blank" rel="noreferrer">посилання для студентів</a>
          {form.shared === "link" && (
            <div className="small">
              Ваш email не є Google-акаунтом, тому редагування відкрито для всіх, хто має посилання «редагувати»
              — не поширюйте його, давайте студентам лише посилання для проходження.
            </div>
          )}
        </div>
      )}
      {!form && savedFormUrl && (
        <div className="small muted">
          Для цього тесту вже є Google Форма: <a href={savedFormUrl} target="_blank" rel="noreferrer">відкрити</a>
          {" "}(нове створення зробить ще одну форму)
        </div>
      )}
      {error && <div className="notice bad">⚠️ {error}</div>}
    </div>
  );
}

const STATUS_LABEL = {
  draft: "чернетка", ai_verified: "перевірено ШІ", approved: "затверджено",
  ai_rejected: "відхилено ШІ", archived: "в архіві",
};
const DIFFICULTY_LABEL = { easy: "легка", medium: "середня", hard: "складна" };
const AI_ACTIONS = [
  { value: "regenerate", label: "Перегенерувати повністю" },
  { value: "simplify", label: "Спростити" },
  { value: "complicate", label: "Ускладнити" },
  { value: "rephrase", label: "Переформулювати" },
  { value: "improve_distractors", label: "Покращити варіанти-пастки" },
];
const SCORE_LABEL = {
  grounding_score: "Заземленість у матеріалі", distractor_quality: "Якість пасток", clarity: "Ясність формулювання",
};

function emptyDraft(q) {
  return {
    text: q.text,
    explanation: q.explanation || "",
    options: q.options.map((o) => ({ text: o.text, is_correct: o.is_correct })),
  };
}

function QuestionCard({ question, onChanged, testId }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(() => emptyDraft(question));
  const [saving, setSaving] = useState(false);
  const [busyAction, setBusyAction] = useState("");
  const [instruction, setInstruction] = useState("");
  const [aiAction, setAiAction] = useState("regenerate");
  const [detail, setDetail] = useState(null);
  const [showDetail, setShowDetail] = useState(false);
  const [error, setError] = useState("");

  const startEdit = () => { setDraft(emptyDraft(question)); setEditing(true); setError(""); };
  const cancelEdit = () => { setEditing(false); setError(""); };

  const saveEdit = async () => {
    setSaving(true);
    setError("");
    try {
      await api(`/questions/${question.id}`, {
        method: "PATCH",
        body: { text: draft.text, explanation: draft.explanation, options: draft.options },
      });
      setEditing(false);
      await onChanged();
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const approve = async () => {
    setBusyAction("approve");
    setError("");
    try {
      await api(`/questions/${question.id}/approve`, { method: "POST" });
      await onChanged();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyAction("");
    }
  };

  const runAi = async () => {
    setBusyAction(aiAction);
    setError("");
    try {
      await api(`/questions/${question.id}/transform`, {
        method: "POST",
        body: { action: aiAction, instruction: instruction.trim() || undefined, language: "uk" },
      });
      setInstruction("");
      await onChanged();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyAction("");
    }
  };

  const remove = async () => {
    setBusyAction("delete");
    setError("");
    try {
      await api(`/questions/${question.id}`, { method: "DELETE" });
      await onChanged();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyAction("");
    }
  };

  const toggleDetail = async () => {
    if (!showDetail && !detail) {
      try {
        setDetail(await api(`/questions/${question.id}`));
      } catch (e) {
        setError(e.message);
      }
    }
    setShowDetail((v) => !v);
  };

  const busy = busyAction !== "";

  return (
    <div className="card question-card">
      <div className="row" style={{ justifyContent: "space-between", alignItems: "flex-start" }}>
        <div className="row gap-sm">
          <span className={`status status-q-${question.status}`}>{STATUS_LABEL[question.status] || question.status}</span>
          <span className="status">{DIFFICULTY_LABEL[question.difficulty] || question.difficulty}</span>
          {question.version > 1 && <span className="muted small">версія {question.version}</span>}
        </div>
        <button className="link small-btn" onClick={toggleDetail}>
          {showDetail ? "Сховати деталі перевірки ШІ" : "Чому так? (деталі перевірки ШІ)"}
        </button>
      </div>

      {!editing ? (
        <>
          <p className="question-text-edit">{question.text}</p>
          <ul className="host-options">
            {question.options.map((o) => (
              <li key={o.id} className={`host-option ${o.is_correct ? "correct" : ""}`}>{o.text}</li>
            ))}
          </ul>
          {question.explanation && <p className="muted small">Пояснення: {question.explanation}</p>}
        </>
      ) : (
        <div className="stack">
          <textarea
            className="edit-textarea"
            value={draft.text}
            onChange={(e) => setDraft({ ...draft, text: e.target.value })}
            rows={2}
          />
          {draft.options.map((o, i) => (
            <div key={i} className="row gap-sm">
              <input
                type={question.type === "multiple_choice" ? "checkbox" : "radio"}
                name={`correct-${question.id}`}
                checked={o.is_correct}
                onChange={(e) => {
                  const single = question.type !== "multiple_choice";
                  const options = draft.options.map((opt, j) => ({
                    ...opt,
                    is_correct: j === i ? e.target.checked : (single ? false : opt.is_correct),
                  }));
                  setDraft({ ...draft, options });
                }}
                title="Правильна відповідь"
              />
              <input
                className="grow"
                value={o.text}
                onChange={(e) => {
                  const options = [...draft.options];
                  options[i] = { ...options[i], text: e.target.value };
                  setDraft({ ...draft, options });
                }}
              />
            </div>
          ))}
          <input
            placeholder="Пояснення (необов'язково)"
            value={draft.explanation}
            onChange={(e) => setDraft({ ...draft, explanation: e.target.value })}
          />
          <div className="row gap-sm">
            <button className="primary" disabled={saving} onClick={saveEdit}>
              {saving ? "Збереження…" : "Зберегти зміни"}
            </button>
            <button onClick={cancelEdit} disabled={saving}>Скасувати</button>
          </div>
        </div>
      )}

      {showDetail && (
        <div className="verification-panel">
          <p className="muted small"><strong>Цитата-обґрунтування з матеріалу:</strong> «{question.source_quote || detail?.source_quote || "—"}»</p>
          {!detail && <p className="muted small">Завантаження…</p>}
          {detail?.verifications?.length > 0 ? (
            <ul className="list">
              {detail.verifications.map((v, i) => (
                <li key={i} className="list-item verification-item">
                  <div className="stack" style={{ width: "100%" }}>
                    <div className="row gap-sm">
                      <strong>Спроба {v.attempt}</strong>
                      <span className={v.verdict === "passed" ? "status status-q-approved" : "status status-q-ai_rejected"}>
                        {v.verdict === "passed" ? "пройшла" : "не пройшла"}
                      </span>
                      {v.critic_model && <span className="muted small">{v.critic_model}</span>}
                    </div>

                    {v.scores?.stage === "rules" && v.scores.rule_issues?.length > 0 && (
                      <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
                        {v.scores.rule_issues.map((ri, j) => <li key={j}>{ri.message}</li>)}
                      </ul>
                    )}

                    {v.scores?.critic && (
                      <div className="row gap small muted">
                        {Object.entries(SCORE_LABEL).map(([k, label]) => (
                          <span key={k}>{label}: {v.scores.critic[k]?.toFixed?.(2) ?? "—"}</span>
                        ))}
                      </div>
                    )}
                    {v.scores?.critic?.issues?.length > 0 && (
                      <ul className="small" style={{ margin: 0, paddingLeft: 18 }}>
                        {v.scores.critic.issues.map((iss, j) => <li key={j}>{iss}</li>)}
                      </ul>
                    )}
                    {v.scores?.critic?.suggestions && (
                      <p className="small muted">Порада ШІ: {v.scores.critic.suggestions}</p>
                    )}

                    {v.scores?.solver && (
                      <p className="small muted">
                        Незалежний «студент-ШІ» {v.scores.solver_agrees ? "погодився з ключем" : "НЕ погодився з ключем"}
                        {" "}(впевненість {(v.scores.solver.confidence * 100).toFixed(0)}%): {v.scores.solver.reasoning}
                      </p>
                    )}

                    {v.scores?.stage === "llm_error" && v.critique && (
                      <p className="small error" style={{ margin: 0 }}>{v.critique}</p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          ) : (detail && <p className="muted small">Журнал перевірки порожній (питання створене вручну).</p>)}
        </div>
      )}

      {error && <div className="error">{error}</div>}

      <div className="row gap-sm question-actions">
        {!editing && <button onClick={startEdit} disabled={busy}>Редагувати вручну</button>}
        {question.status !== "approved" && (
          <button onClick={approve} disabled={busy}>
            {busyAction === "approve" ? "…" : "Схвалити"}
          </button>
        )}
        <button className="danger" onClick={remove} disabled={busy}>
          {busyAction === "delete" ? "…" : "Видалити"}
        </button>
      </div>

      <div className="ai-action-row">
        <select value={aiAction} onChange={(e) => setAiAction(e.target.value)} disabled={busy}>
          {AI_ACTIONS.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
        </select>
        <input
          placeholder="Додаткова інструкція для ШІ (необов'язково)"
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          disabled={busy}
          className="grow"
          maxLength={500}
        />
        <button className="primary" onClick={runAi} disabled={busy}>
          {busy && busyAction === aiAction ? "ШІ працює…" : "Застосувати ШІ"}
        </button>
      </div>
    </div>
  );
}

export default function TestEditorPage() {
  const { testId } = useParams();
  const navigate = useNavigate();
  const [test, setTest] = useState(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [showRejected, setShowRejected] = useState(false);
  const [title, setTitle] = useState("");

  const load = async () => {
    try {
      const t = await api(`/tests/${testId}`);
      setTest(t);
      setTitle(t.title);
    } catch (e) {
      setError(e.message);
    }
  };

  useEffect(() => { load(); }, [testId]);

  const saveTitle = async () => {
    if (!test || title.trim() === test.title) return;
    try {
      await api(`/tests/${testId}`, { method: "PATCH", body: { title: title.trim() } });
      await load();
    } catch (e) {
      setError(e.message);
    }
  };

  const finishTest = async () => {
    setSaving(true);
    setError("");
    try {
      await api(`/tests/${testId}/questions/approve-verified`, { method: "POST" });
      await api(`/tests/${testId}`, { method: "PATCH", body: { is_published: true } });
      await load();
      setSaved(true);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  if (!test) {
    return <div className="card">{error ? <div className="error">{error}</div> : <p>Завантаження…</p>}</div>;
  }

  const visible = test.questions.filter((q) => showRejected || q.status !== "ai_rejected");
  const counts = test.questions.reduce((acc, q) => ({ ...acc, [q.status]: (acc[q.status] || 0) + 1 }), {});
  const readyCount = (counts.approved || 0) + (counts.ai_verified || 0);

  return (
    <div className="stack">
      <div className="card">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <Link to="/teacher" className="link">← Мої тести</Link>
        </div>
        <input
          className="test-title-input"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onBlur={saveTitle}
        />
        <div className="muted small">
          Матеріали: {test.materials.map((m) => m.title).join(", ") || "—"}
        </div>
        <div className="row gap small" style={{ marginTop: 8 }}>
          <span>Усього питань: {test.questions.length}</span>
          <span>Затверджено: {counts.approved || 0}</span>
          <span>Перевірено ШІ: {counts.ai_verified || 0}</span>
          <span>Відхилено ШІ: {counts.ai_rejected || 0}</span>
        </div>
        {error && <div className="error">{error}</div>}
        {saved && <div className="banner">Тест збережено. Питання, перевірені ШІ, затверджено автоматично.</div>}
        <div className="row gap-sm" style={{ marginTop: 12 }}>
          <button className="primary" onClick={finishTest} disabled={saving || readyCount === 0}>
            {saving ? "Збереження…" : "Зберегти тест"}
          </button>
          <Link to="/teacher" className="muted small" style={{ alignSelf: "center" }}>
            (щоб запустити сесію — поверніться до «Мої тести»)
          </Link>
        </div>
        {readyCount === 0 && (
          <p className="muted small" style={{ marginTop: 6 }}>
            Ще немає жодного питання, готового до збереження — перевірені ШІ або затверджені вручну.
          </p>
        )}
        <ExportBar testId={testId} disabled={readyCount === 0} savedFormUrl={test.google_form_url} />
      </div>

      {(counts.ai_rejected || 0) > 0 && (
        <label className="row gap-sm">
          <input type="checkbox" checked={showRejected} onChange={(e) => setShowRejected(e.target.checked)} />
          Показати відхилені ШІ питання ({counts.ai_rejected})
        </label>
      )}

      {visible.length === 0 && <p className="muted">Питань поки немає.</p>}
      {visible.map((q) => (
        <QuestionCard key={q.id} question={q} testId={testId} onChanged={load} />
      ))}
    </div>
  );
}
