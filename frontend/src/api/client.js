export const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(message, status, data) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

export const getToken = () => localStorage.getItem("token");
export const getUser = () => {
  try { return JSON.parse(localStorage.getItem("user")); } catch { return null; }
};
export const logout = () => { localStorage.removeItem("token"); localStorage.removeItem("user"); };

function errorMessage(data, status) {
  const d = data?.detail;
  if (typeof d === "string") return d;
  if (d?.message) return d.message;
  if (Array.isArray(d)) return d.map((x) => String(x.msg).replace(/^Value error,\s*/, "")).join("; ");
  if (status >= 500) return "Помилка на сервері — спробуйте ще раз або зверніться до адміністратора";
  return `Помилка ${status}`;
}

export async function api(path, { method = "GET", body, form, auth = true } = {}) {
  const headers = {};
  const token = getToken();
  if (auth && token) headers.Authorization = `Bearer ${token}`;
  let payload;
  if (form) payload = form;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(API_URL + path, { method, headers, body: payload });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401 && auth) logout();
    throw new ApiError(errorMessage(data, res.status), res.status, data);
  }
  return data;
}

function saveAuth(data) {
  localStorage.setItem("token", data.access_token);
  localStorage.setItem("user", JSON.stringify(data.user));
  return data.user;
}

export async function login(email, password) {
  const form = new URLSearchParams({ username: email, password });
  const res = await fetch(API_URL + "/auth/login", { method: "POST", body: form });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(errorMessage(data, res.status), res.status, data);
  return saveAuth(data);
}

export async function register(payload) {
  return saveAuth(await api("/auth/register", { method: "POST", body: payload, auth: false }));
}
