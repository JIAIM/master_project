import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client.js";

const MAX_QUESTIONS = 20;

const STATUS = {
  uploaded: { label: "У черзі на обробку", cls: "pending" },
  processing: { label: "Обробляється…", cls: "pending" },
  indexed: { label: "Готово", cls: "ok" },
  failed: { label: "Помилка обробки", cls: "bad" },
};

const JOB_STATUS = { pending: "у черзі", running: "генерується", completed: "завершено", failed: "помилка" };

function formatSize(bytes) {
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} МБ` : `${Math.max(1, Math.round(bytes / 1024))} КБ`;
}

function UploadZone({ onUploaded }) {
  const input = useRef(null);
  const [drag, setDrag] = useState(false);
  const [state, setState] = useState({ kind: "idle" }); // idle | uploading | done | error

  const upload = async (file) => {
    if (!file) return;
    const ext = file.name.split(".").pop().toLowerCase();
    if (!["pdf", "docx"].includes(ext)) {
      setState({ kind: "error", text: "Підтримуються лише файли PDF і DOCX" });
      return;
    }
    setState({ kind: "uploading", name: file.name });
    try {
      const form = new FormData();
      form.append("file", file);
      const material = await api("/materials", { method: "POST", form });
      setState({ kind: "done", text: `Файл «${file.name}» завантажено. Обробка триває до хвилини — статус видно в списку нижче.` });
      onUploaded(material.id);
    } catch (e) {
      const existing = e.data?.detail?.material_id;
      if (existing) onUploaded(existing);
      setState({ kind: "error", text: existing ? `${e.message} — його обрано у списку нижче.` : e.message });
    } finally {
      if (input.current) input.current.value = "";
    }
  };

  return (
    <div>
      <div
        className={`dropzone ${drag ? "drag" : ""} ${state.kind === "uploading" ? "busy" : ""}`}
        onClick={() => state.kind !== "uploading" && input.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files?.[0]); }}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && input.current?.click()}
      >
        <input ref={input} type="file" accept=".pdf,.docx" hidden onChange={(e) => upload(e.target.files?.[0])} />
        <div className="dropzone-icon">{state.kind === "uploading" ? <span className="spinner" /> : "📄"}</div>
        {state.kind === "uploading" ? (
          <div><strong>Завантаження «{state.name}»…</strong></div>
        ) : (
          <div>
            <strong>Перетягніть файл сюди або натисніть, щоб обрати</strong>
            <div className="muted small">PDF або DOCX, до 50 МБ</div>
          </div>
        )}
      </div>
      {state.kind === "done" && <div className="notice ok">✅ {state.text}</div>}
      {state.kind === "error" && <div className="notice bad">⚠️ {state.text}</div>}
    </div>
  );
}

function MaterialCard({ m, selected, onToggle }) {
  const st = STATUS[m.status] ?? { label: m.status, cls: "pending" };
  const ready = m.status === "indexed";
  return (
    <button
      type="button"
      className={`material-card ${selected ? "selected" : ""} ${ready ? "" : "not-ready"}`}
      onClick={() => ready && onToggle(m.id)}
      aria-pressed={selected}
      title={ready ? (selected ? "Натисніть, щоб прибрати з тесту" : "Натисніть, щоб додати до тесту") : "Матеріал ще не готовий"}
    >
      <span className="material-check">{selected ? "✓" : ""}</span>
      <span className="material-body">
        <span className="material-title">{m.title}</span>
        <span className="muted small">
          {m.original_filename} · {formatSize(m.file_size)}{ready ? ` · фрагментів: ${m.chunk_count}` : ""}
        </span>
        {m.status === "failed" && m.error_message && <span className="small bad-text">{m.error_message}</span>}
      </span>
      <span className={`pill ${st.cls} ${st.cls === "pending" ? "status-pulse" : ""}`}>{st.label}</span>
    </button>
  );
}

function Counter({ label, hint, value, onChange, max }) {
  const set = (v) => onChange(Math.max(0, Math.min(max, Number.isFinite(v) ? v : 0)));
  return (
    <div className="counter">
      <div>
        <div className="counter-label">{label}</div>
        <div className="muted small">{hint}</div>
      </div>
      <div className="counter-controls">
        <button type="button" onClick={() => set(value - 1)} disabled={value <= 0} aria-label="Менше">−</button>
        <input type="number" min={0} max={max} value={value} onChange={(e) => set(parseInt(e.target.value, 10))} />
        <button type="button" onClick={() => set(value + 1)} disabled={value >= max} aria-label="Більше">+</button>
      </div>
    </div>
  );
}

export default function GeneratePage() {
  const navigate = useNavigate();
  const [materials, setMaterials] = useState(null);
  const [selected, setSelected] = useState([]);
  const [error, setError] = useState("");

  const [testTitle, setTestTitle] = useState("");
  const [singleCount, setSingleCount] = useState(8);
  const [tfCount, setTfCount] = useState(2);
  const [difficulty, setDifficulty] = useState("mixed");
  const [topic, setTopic] = useState("");
  const [language, setLanguage] = useState("uk");

  const [job, setJob] = useState(null);
  const [creating, setCreating] = useState(false);
  const [createdTestId, setCreatedTestId] = useState(null);

  const loadMaterials = () => api("/materials").then(setMaterials).catch((e) => setError(e.message));
  useEffect(() => { loadMaterials(); }, []);

  // поки хоч один матеріал ще обробляється — оновлюємо список раз на 2 с
  const pending = materials?.some((m) => m.status === "uploaded" || m.status === "processing");
  useEffect(() => {
    if (!pending) return undefined;
    const t = setInterval(loadMaterials, 2000);
    return () => clearInterval(t);
  }, [pending]);

  useEffect(() => {
    if (!job || job.status === "completed" || job.status === "failed") return undefined;
    const t = setInterval(async () => {
      try { setJob(await api(`/generation-jobs/${job.id}`)); } catch (e) { setError(e.message); }
    }, 1500);
    return () => clearInterval(t);
  }, [job]);

  const onUploaded = (id) => {
    setSelected((prev) => (prev.includes(id) ? prev : [...prev, id]));
    loadMaterials();
  };
  const toggle = (id) => setSelected((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));

  const total = singleCount + tfCount;
  const readySelected = selected.filter((id) => materials?.find((m) => m.id === id)?.status === "indexed");
  const waitingSelected = selected.length - readySelected.length;
  const canGenerate = readySelected.length > 0 && total >= 1 && total <= MAX_QUESTIONS && !creating && !job;

  const generate = async (e) => {
    e.preventDefault();
    setError("");
    setCreating(true);
    let test = null;
    try {
      test = await api("/tests", {
        method: "POST",
        body: { title: testTitle.trim() || "Новий тест", material_ids: readySelected },
      });
      const newJob = await api(`/tests/${test.id}/generate`, {
        method: "POST",
        body: {
          single_choice_count: singleCount,
          true_false_count: tfCount,
          difficulty,
          language,
          ...(topic.trim() ? { topic: topic.trim() } : {}),
        },
      });
      setCreatedTestId(test.id);
      setJob(newJob);
    } catch (e2) {
      if (test) await api(`/tests/${test.id}`, { method: "DELETE" }).catch(() => {});
      setError(e2.message);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="stack">
      <div className="card">
        <h1>1. Навчальні матеріали</h1>
        <UploadZone onUploaded={onUploaded} />

        <div className="section-head">
          <h3>Ваші матеріали</h3>
          {materials?.length > 0 && <span className="muted small">Натисніть на готовий матеріал, щоб додати його до тесту</span>}
        </div>
        {materials === null && <p className="muted">Завантаження…</p>}
        {materials?.length === 0 && <p className="muted">Матеріалів ще немає — завантажте конспект лекцій вище.</p>}
        <div className="material-grid">
          {materials?.map((m) => (
            <MaterialCard key={m.id} m={m} selected={selected.includes(m.id)} onToggle={toggle} />
          ))}
        </div>
      </div>

      <form className="card stack" onSubmit={generate}>
        <h1>2. Параметри тесту</h1>
        <label className="field">
          <span>Назва тесту</span>
          <input placeholder="Наприклад: Модульний контроль — веб-фреймворки Go" value={testTitle}
                 onChange={(e) => setTestTitle(e.target.value)} />
        </label>

        <div className="counters">
          <Counter label="Вибір однієї відповіді" hint="4 варіанти, один правильний"
                   value={singleCount} onChange={setSingleCount} max={MAX_QUESTIONS} />
          <Counter label="Правда / неправда" hint="твердження, яке треба оцінити"
                   value={tfCount} onChange={setTfCount} max={MAX_QUESTIONS} />
          <div className={`counter-total ${total > MAX_QUESTIONS || total < 1 ? "bad-text" : ""}`}>
            <div>Разом: <strong>{total}</strong> з {MAX_QUESTIONS}</div>
            {total > MAX_QUESTIONS && <div className="small">Максимум — {MAX_QUESTIONS} питань за раз</div>}
          </div>
        </div>

        <div className="row gap">
          <label className="field">
            <span>Складність</span>
            <select value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
              <option value="mixed">Змішана</option>
              <option value="easy">Легка</option>
              <option value="medium">Середня</option>
              <option value="hard">Складна</option>
            </select>
          </label>
          <label className="field">
            <span>Мова питань</span>
            <select value={language} onChange={(e) => setLanguage(e.target.value)}>
              <option value="uk">Українська</option>
              <option value="en">English</option>
              <option value="pl">Polski</option>
            </select>
          </label>
        </div>

        <label className="field">
          <span>Тема, розділ або лекція <em className="muted">(необов'язково)</em></span>
          <input placeholder="Наприклад: «Лекція 3. Горутини та канали»" value={topic}
                 onChange={(e) => setTopic(e.target.value)} maxLength={300} />
          <span className="muted small">Якщо не вказати — питання рівномірно охоплять увесь матеріал.</span>
        </label>

        {error && <div className="notice bad">⚠️ {error}</div>}
        {readySelected.length === 0 && (
          <div className="muted small">
            {waitingSelected > 0 ? "Обраний матеріал ще обробляється — зачекайте статусу «Готово»." : "Оберіть хоча б один готовий матеріал у кроці 1."}
          </div>
        )}
        <button className="primary big-btn" disabled={!canGenerate}>
          {creating ? "Створення…" : `Згенерувати ${total} питань`}
        </button>
      </form>

      {job && (
        <div className="card">
          <h1>3. Генерація</h1>
          <div className="bar">
            <div style={{ width: `${job.total ? (job.completed / job.total) * 100 : 0}%` }} />
            <em>{job.completed}/{job.total}</em>
          </div>
          <div className="row gap small muted" style={{ marginTop: 8 }}>
            <span>Статус: {JOB_STATUS[job.status] ?? job.status}</span>
            <span>Прийнято: {job.verified_count}</span>
            <span>Відхилено: {job.rejected_count}</span>
            {job.failed_count > 0 && <span>Не вдалося згенерувати: {job.failed_count}</span>}
          </div>
          {job.status !== "completed" && job.status !== "failed" && (
            <p className="muted small">Можна не чекати на цій сторінці — тест з'явиться в розділі «Мої тести».</p>
          )}
          {job.error && <div className="notice bad">{job.error}</div>}
          {job.status === "completed" && (
            <button className="primary" style={{ marginTop: 12 }} onClick={() => navigate(`/teacher/tests/${createdTestId}`)}>
              Переглянути та відредагувати питання
            </button>
          )}
        </div>
      )}
    </div>
  );
}
