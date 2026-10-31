import assert from "node:assert/strict";
import test from "node:test";
import {
  canContinueCallAfterMediaPrompt,
  isCurrentIncomingCall,
  isOtherPlayerRole,
  requiresRoomExitConfirmation,
  shouldApplyAuthRefresh,
  trackPendingRequest,
  waitForPendingRequests,
} from "../../src/room-interactions";
import { buildRoomCodeJoinPayload } from "../../src/room-join";

test("confirms only navigation that leaves an active online room", () => {
  assert.equal(requiresRoomExitConfirmation("waiting", "home", true, "online"), true);
  assert.equal(requiresRoomExitConfirmation("game", "rooms", true, "online"), true);
  assert.equal(requiresRoomExitConfirmation("waiting", "game", true, "online"), false);
  assert.equal(requiresRoomExitConfirmation("waiting", "game", true, "ai"), false);
  assert.equal(requiresRoomExitConfirmation("game", "home", true, "ai"), false);
  assert.equal(requiresRoomExitConfirmation("rooms", "home", false, "online"), false);
  assert.equal(requiresRoomExitConfirmation("game", "game", true, "online"), false);
});

test("accepts only the same incoming call after the media prompt resolves", () => {
  const firstCall = { from_role: "player1", mode: "video" };
  const nextCall = { from_role: "player1", mode: "video" };
  assert.equal(isCurrentIncomingCall("incoming", firstCall, firstCall), true);
  assert.equal(isCurrentIncomingCall("idle", firstCall, firstCall), false);
  assert.equal(isCurrentIncomingCall("incoming", nextCall, firstCall), false);
  assert.equal(isCurrentIncomingCall("incoming", null, firstCall), false);
});

test("does not start media after the game ends or the room socket closes", () => {
  assert.equal(canContinueCallAfterMediaPrompt(false, true), true);
  assert.equal(canContinueCallAfterMediaPrompt(true, true), false);
  assert.equal(canContinueCallAfterMediaPrompt(false, false), false);
});

test("shows draw responses only to the other player", () => {
  assert.equal(isOtherPlayerRole("player1", "player2"), true);
  assert.equal(isOtherPlayerRole("player1", "player1"), false);
  assert.equal(isOtherPlayerRole("spectator", "player1"), false);
  assert.equal(isOtherPlayerRole("player1", undefined), false);
});

test("does not apply refresh responses from before logout or a newer login", () => {
  assert.equal(shouldApplyAuthRefresh(4, 4, false), true);
  assert.equal(shouldApplyAuthRefresh(4, 5, false), false);
  assert.equal(shouldApplyAuthRefresh(4, 4, true), false);
});

test("waits for outstanding refresh requests before logout", async () => {
  const pending = new Set<Promise<unknown>>();
  let resolveRequest!: () => void;
  const refreshRequest = new Promise<void>((resolve) => {
    resolveRequest = resolve;
  });
  trackPendingRequest(pending, refreshRequest);
  let logoutReady = false;
  const drain = waitForPendingRequests(pending).then(() => {
    logoutReady = true;
  });

  await Promise.resolve();
  assert.equal(logoutReady, false);
  resolveRequest();
  await drain;
  assert.equal(logoutReady, true);
  assert.equal(pending.size, 0);
});

test("includes an optional room password in the normalized code-join payload", () => {
  assert.deepEqual(buildRoomCodeJoinPayload("  a7k2q9 ", "Guest"), {
    room_code: "A7K2Q9",
    participant_name: "Guest",
  });
  assert.deepEqual(buildRoomCodeJoinPayload("a7k2q9", "Guest", "secret phrase"), {
    room_code: "A7K2Q9",
    participant_name: "Guest",
    password: "secret phrase",
  });
});
