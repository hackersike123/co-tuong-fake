export function resolveApiBaseUrl(configured: string | undefined, browserOrigin?: string): string {
  if (configured !== undefined) return configured.trim().replace(/\/+$/, "");
  if (!browserOrigin) return "http://127.0.0.1:8000";
  const origin = new URL(browserOrigin);
  return `${origin.protocol}//${origin.hostname}:8000`;
}

export function buildWebSocketUrl(
  apiBaseUrl: string,
  path: string,
  browserOrigin?: string,
): string {
  const base = apiBaseUrl || browserOrigin || "http://127.0.0.1:8000";
  const url = new URL(path.replace(/^\/+/, ""), `${base.replace(/\/+$/, "")}/`);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}
