import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client.js";

export default function JoinPage() {
  const navigate = useNavigate();
  const [pin, setPin] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const data = await api("/sessions/join", {
        method: "POST",
        body: { pin: pin.trim(), display_name: name.trim() },
      });
      sessionStorage.setItem("player", JSON.stringify(data));
      navigate("/play");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card narrow">
      <h1>Пройти тест</h1>
      <p className="muted small">Введіть PIN, який показав викладач, і своє ім'я та прізвище.</p>
      <form onSubmit={submit} className="stack">
        <input
          className="pin-input" inputMode="numeric" maxLength={6} placeholder="PIN-код"
          value={pin} onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))} required
        />
        <input placeholder="Ім'я та прізвище" value={name} onChange={(e) => setName(e.target.value)} maxLength={100} required />
        {error && <div className="notice bad">⚠️ {error}</div>}
        <button className="primary big-btn" disabled={loading || pin.length !== 6 || !name.trim()}>
          {loading ? "Вхід…" : "Почати тест"}
        </button>
      </form>
      <p className="muted small">
        Під час тесту використовується камера для контролю уваги. Відео обробляється лише у вашому браузері
        й нікуди не передається — на сервер надходять тільки сигнали «відволікся / повернувся».
      </p>
    </div>
  );
}
