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

const OFFLINE = "Немає з'єднання з сервером. Перевірте інтернет і спробуйте ще раз.";

async function send(url, options) {
  try {
    return await fetch(url, options);
  } catch {
    throw new ApiError(OFFLINE, 0, null);
  }
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
  const res = await send(API_URL + path, { method, headers, body: payload });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401 && auth && token) {
      logout();
      if (window.location.pathname.startsWith("/teacher")) {
        window.location.href = "/login";
        throw new ApiError("Сеанс завершився — увійдіть знову", 401, data);
      }
    }
    throw new ApiError(errorMessage(data, res.status), res.status, data);
  }
  return data;
}

export async function download(path, fallbackName) {
  const res = await send(API_URL + path, { headers: { Authorization: `Bearer ${getToken()}` } });
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new ApiError(errorMessage(data, res.status) || "Не вдалося завантажити файл", res.status, data);
  }
  const cd = res.headers.get("Content-Disposition") || "";
  const utf = /filename\*=UTF-8''([^;]+)/.exec(cd);
  const name = utf ? decodeURIComponent(utf[1]) : fallbackName;
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

function saveAuth(data) {
  localStorage.setItem("token", data.access_token);
  localStorage.setItem("user", JSON.stringify(data.user));
  return data.user;
}

export async function login(email, password) {
  const form = new URLSearchParams({ username: email, password });
  const res = await send(API_URL + "/auth/login", { method: "POST", body: form });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new ApiError(errorMessage(data, res.status), res.status, data);
  return saveAuth(data);
}

export async function register(payload) {
  return saveAuth(await api("/auth/register", { method: "POST", body: payload, auth: false }));
}
