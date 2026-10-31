const stored = sessionStorage.getItem("cronjovi-token");
const fromUrl = new URLSearchParams(location.hash.slice(1)).get("token");
const token = fromUrl || stored || "";
if (fromUrl) {
  sessionStorage.setItem("cronjovi-token", fromUrl);
  history.replaceState(null, "", location.pathname);
}

export async function api(method, path, body, headers = {}) {
  let response;
  try {
    response = await fetch(`/api${path}`, {
      method,
      headers: { "X-CronJovi-Token": token, "Content-Type": "application/json", ...headers },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    dispatchEvent(new CustomEvent("cronjovi-connection", { detail: false }));
    throw new Error("Cron Jovi's background service stopped responding");
  }
  dispatchEvent(new CustomEvent("cronjovi-connection", { detail: true }));
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw Object.assign(new Error(data.error || `Request failed (${response.status})`), { changed: data.changed });
  }
  return data;
}

export const get = (path) => api("GET", path);
export const post = (path, body = {}) => api("POST", path, body);
export const put = (path, body, stamp) => api("PUT", path, body, stamp ? { "If-Match": stamp } : {});
export const del = (path) => api("DELETE", path);
