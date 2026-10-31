function defaultApiBaseUrl() {
  if (typeof window === "undefined") return "http://127.0.0.1:8000";
  return `${window.location.protocol}//${window.location.hostname}:8000`;
}

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || defaultApiBaseUrl()).replace(
  /\/$/,
  "",
);

export function websocketUrl(path: string) {
  const url = new URL(path.replace(/^\//, ""), `${API_BASE_URL}/`);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

export const WEBSOCKET_CONNECTION_LABEL = "Kết nối WebSocket";
export const DEMO_CONNECTION_LABEL = "Bản demo cũ — chưa kết nối";
