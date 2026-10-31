import assert from "node:assert/strict";
import test from "node:test";
import { buildWebSocketUrl, resolveApiBaseUrl } from "../../src/config/api-base";

test("supports a same-origin API when its build-time setting is empty", () => {
  assert.equal(resolveApiBaseUrl("", "https://ky.example"), "");
  assert.equal(
    buildWebSocketUrl("", "/api/v1/rooms/ws", "https://ky.example"),
    "wss://ky.example/api/v1/rooms/ws",
  );
});

test("uses an explicitly configured API origin", () => {
  assert.equal(
    resolveApiBaseUrl("https://api.example/", "https://ky.example"),
    "https://api.example",
  );
  assert.equal(
    buildWebSocketUrl("https://api.example", "/api/v1/rooms/ws"),
    "wss://api.example/api/v1/rooms/ws",
  );
});

test("falls back to the local backend in development", () => {
  assert.equal(resolveApiBaseUrl(undefined), "http://127.0.0.1:8000");
  assert.equal(resolveApiBaseUrl(undefined, "http://localhost:8443"), "http://localhost:8000");
});
