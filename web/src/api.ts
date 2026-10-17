// Relative URLs on purpose: the page lives under Home Assistant's ingress path
// (/api/hassio_ingress/<token>/) and on http://127.0.0.1:8099 in SCREEN_DEV; `api/...`
// resolves against the page in both. Writes carry the CSRF token the inventory handed out.
import { editorLanguage, t } from "./i18n";

let csrf = "";
export function setCsrf(token: string) {
  csrf = token || "";
}

export async function api(path: string, options: RequestInit = {}): Promise<Response> {
  const response = await fetch(`api/${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Screen-CSRF": csrf,
      // The add-on writes its own texts, such as its labels and errors, in the editor's language (app 0.2.90).
      "X-ESP-Screens-Language": editorLanguage(),
      ...(options.headers as Record<string, string> | undefined),
    },
  });
  if (!response.ok) {
    // Any answer with a JSON {"error": "..."} says what went wrong, such as Home Assistant refusing an action (400) or
    // not answering in time (503, app 0.2.78); anything else, like an error page of the ingress proxy, gets this one.
    let message = t("editor.api.failed");
    try {
      const error = (await response.json())?.error;
      if (typeof error === "string" && error.trim()) message = error;
    } catch { /* not JSON (an error page of the proxy): the general message stands */ }
    throw new Error(message);
  }
  return response;
}

export const getJson = async <T = any>(path: string): Promise<T> => (await api(path)).json();
export const send = async <T = any>(path: string, method: string, body?: unknown, extra: RequestInit = {}): Promise<T> => {
  const response = await api(path, { method, body: body === undefined ? undefined : JSON.stringify(body), ...extra });
  const text = await response.text();
  return (text ? JSON.parse(text) : null) as T;
};
