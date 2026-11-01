import { buildWebSocketUrl, resolveApiBaseUrl } from "./api-base";

const browserOrigin = typeof window === "undefined" ? undefined : window.location.origin;

export const API_BASE_URL = resolveApiBaseUrl(import.meta.env.VITE_API_BASE_URL, browserOrigin);

export function websocketUrl(path: string) {
  return buildWebSocketUrl(API_BASE_URL, path, browserOrigin);
}

export const WEBSOCKET_CONNECTION_LABEL = "Kết nối WebSocket";
