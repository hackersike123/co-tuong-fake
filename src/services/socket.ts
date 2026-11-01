import { websocketUrl } from "../config/connection";

type RpcResponse<T> = {
  id: string | null;
  event: string;
  ok: boolean;
  data?: T;
  error?: { status?: number; detail?: unknown };
};

type PendingRequest = {
  resolve: (value: unknown) => void;
  reject: (error: Error) => void;
  timeout: ReturnType<typeof setTimeout>;
};

export class WebSocketRpcError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "WebSocketRpcError";
  }
}

export class WebSocketRpcClient {
  private socket: WebSocket | null = null;
  private connecting: Promise<void> | null = null;
  private readonly pending = new Map<string, PendingRequest>();
  private nextId = 0;

  constructor(private readonly url = websocketUrl("/api/v1/ws")) {}

  async request<T>(
    event: string,
    data: Record<string, unknown> = {},
    timeoutMs = 30_000,
  ): Promise<T> {
    await this.connect();
    const socket = this.socket;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      throw new WebSocketRpcError("Kết nối WebSocket đã đóng.");
    }

    const id = globalThis.crypto?.randomUUID?.() || `rpc-${Date.now()}-${++this.nextId}`;
    return new Promise<T>((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(id);
        reject(new WebSocketRpcError("Máy chủ không phản hồi kịp thời."));
      }, timeoutMs);
      this.pending.set(id, { resolve: (value) => resolve(value as T), reject, timeout });
      try {
        socket.send(JSON.stringify({ id, event, data }));
      } catch (error) {
        clearTimeout(timeout);
        this.pending.delete(id);
        reject(error instanceof Error ? error : new Error("Không gửi được yêu cầu."));
      }
    });
  }

  close() {
    this.socket?.close(1000, "Application closed");
    this.socket = null;
    this.connecting = null;
    this.rejectPending(new WebSocketRpcError("Kết nối WebSocket đã đóng."));
  }

  private connect(): Promise<void> {
    if (this.socket?.readyState === WebSocket.OPEN) return Promise.resolve();
    if (this.connecting) return this.connecting;

    this.connecting = new Promise<void>((resolve, reject) => {
      const socket = new WebSocket(this.url);
      this.socket = socket;
      let settled = false;
      socket.onopen = () => {
        settled = true;
        resolve();
      };
      socket.onmessage = (message) => this.onMessage(message);
      socket.onerror = () => {
        if (!settled) {
          settled = true;
          reject(new WebSocketRpcError("Không thể kết nối tới máy chủ WebSocket."));
        }
      };
      socket.onclose = (event) => {
        if (!settled) {
          settled = true;
          reject(
            new WebSocketRpcError(event.reason || "Máy chủ từ chối kết nối WebSocket.", event.code),
          );
        }
        if (this.socket === socket) this.socket = null;
        this.connecting = null;
        this.rejectPending(
          new WebSocketRpcError(event.reason || "Kết nối WebSocket bị ngắt.", event.code),
        );
      };
    }).finally(() => {
      if (this.socket?.readyState !== WebSocket.OPEN) this.connecting = null;
    });
    return this.connecting;
  }

  private onMessage(message: MessageEvent<string>) {
    let response: RpcResponse<unknown>;
    try {
      response = JSON.parse(message.data) as RpcResponse<unknown>;
    } catch {
      return;
    }
    if (!response.id) return;
    const request = this.pending.get(response.id);
    if (!request) return;
    clearTimeout(request.timeout);
    this.pending.delete(response.id);
    if (response.ok) request.resolve(response.data);
    else {
      request.reject(
        new WebSocketRpcError(
          typeof response.error?.detail === "string"
            ? response.error.detail
            : "Yêu cầu không hợp lệ.",
          response.error?.status,
        ),
      );
    }
  }

  private rejectPending(error: Error) {
    for (const request of this.pending.values()) {
      clearTimeout(request.timeout);
      request.reject(error);
    }
    this.pending.clear();
  }
}
