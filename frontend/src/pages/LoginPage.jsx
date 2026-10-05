import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { login, register } from "../api/client.js";

export default function LoginPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: "", password: "", full_name: "" });
  const [error, setError] = useState("");
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    try {
      const user = mode === "login"
        ? await login(form.email, form.password)
        : await register({ ...form, role: "teacher" });
      if (user.role === "student") {
        setError("Це обліковий запис студента. Студенти входять у тест за PIN-кодом.");
        return;
      }
      navigate("/teacher");
      window.location.reload(); // оновити шапку
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div className="card narrow">
      <h1>{mode === "login" ? "Вхід викладача" : "Реєстрація викладача"}</h1>
      <form onSubmit={submit} className="stack">
        {mode === "register" && (
          <input placeholder="ПІБ" value={form.full_name} onChange={set("full_name")} required minLength={2} />
        )}
        <input type="email" placeholder="Email" value={form.email} onChange={set("email")} required />
        <input type="password" placeholder="Пароль (мін. 8 символів)" value={form.password}
               onChange={set("password")} required minLength={8} maxLength={72} />
        {error && <div className="error">{error}</div>}
        <button className="primary">{mode === "login" ? "Увійти" : "Зареєструватися"}</button>
      </form>
      <button className="link" onClick={() => setMode(mode === "login" ? "register" : "login")}>
        {mode === "login" ? "Немає акаунта? Зареєструватися" : "Вже є акаунт? Увійти"}
      </button>
    </div>
  );
}
