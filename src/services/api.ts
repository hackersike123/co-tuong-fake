import { API_BASE_URL } from "../config/connection";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type ApiOptions = Omit<RequestInit, "body" | "headers"> & {
  body?: unknown;
  headers?: HeadersInit;
  token?: string;
};

export async function apiFetch<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const { body, headers: suppliedHeaders, token, ...init } = options;
  const headers = new Headers(suppliedHeaders);
  if (body !== undefined) headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers,
      credentials: "include",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError("Không thể kết nối tới máy chủ.", 0);
  }
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  let payload: unknown;
  try {
    payload = text ? JSON.parse(text) : null;
  } catch {
    payload = text;
  }
  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? (payload as { detail?: unknown }).detail
        : payload;
    const message =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail
              .map((item) =>
                item && typeof item === "object" && "msg" in item
                  ? String((item as { msg: unknown }).msg)
                  : String(item),
              )
              .join("; ")
          : `Máy chủ trả lỗi ${response.status}.`;
    throw new ApiError(message, response.status);
  }
  return payload as T;
}
