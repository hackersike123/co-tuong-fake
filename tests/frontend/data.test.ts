import assert from "node:assert/strict";
import test from "node:test";
import { mergeRoomSummary, parseReplayMoves } from "../../src/data";

test("merges authoritative player names and ratings from a room snapshot", () => {
  const room = {
    id: "3",
    name: "Public room",
    host: "Guest",
    initials: "GU",
    elo: null,
    seconds: 30,
    players: 1,
    private: false,
    playing: false,
    spectators: true,
    tone: "sage",
    player2Name: null,
    player2Elo: null,
  };
  const updated = mergeRoomSummary(room, {
    room_name: "Public room",
    host_name: "Red guest",
    host_elo: null,
    player2_name: "Black guest",
    player2_elo: null,
    player_count: 2,
    status: "playing",
    is_public: true,
    allow_spectators: true,
  });

  assert.equal(updated.host, "Red guest");
  assert.equal(updated.player2Name, "Black guest");
  assert.equal(updated.players, 2);
  assert.equal(updated.playing, true);
  assert.equal(updated.elo, null);
  assert.equal(updated.player2Elo, null);
});

test("clears stale second-player details when the authoritative room is empty", () => {
  const room = {
    id: "3",
    name: "Public room",
    host: "Red guest",
    initials: "RG",
    elo: null,
    seconds: 30,
    players: 2,
    private: false,
    playing: true,
    spectators: true,
    tone: "sage",
    player2Name: "Old player",
    player2Elo: 1400,
  };
  const updated = mergeRoomSummary(room, {
    player2_name: null,
    player2_elo: null,
    player_count: 1,
    status: "waiting",
  });

  assert.equal(updated.player2Name, null);
  assert.equal(updated.player2Elo, null);
  assert.equal(updated.players, 1);
  assert.equal(updated.playing, false);
});

test("parses the server's numbered coordinate notation into alternating moves", () => {
  const moves = parseReplayMoves("1. a6-a5 1... a3-a4");
  assert.deepEqual(
    moves.map(({ side, fromX, fromY, toX, toY }) => ({ side, fromX, fromY, toX, toY })),
    [
      { side: "red", fromX: 0, fromY: 6, toX: 0, toY: 5 },
      { side: "black", fromX: 0, fromY: 3, toX: 0, toY: 4 },
    ],
  );
});

test("removes a captured piece while building replay positions", () => {
  const moves = parseReplayMoves("1. e6-e5 1... e3-e4 2. e5-e4");
  assert.equal(moves.length, 3);
  assert.equal(moves[2].side, "red");
  assert.equal(moves[2].pieceId, "red-p4");
});

test("rejects malformed coordinates and moves by the wrong side", () => {
  assert.throws(() => parseReplayMoves("1. z6-z5"), /không hợp lệ/i);
  assert.throws(() => parseReplayMoves("1. a6-a5 1... a3-a4 2. a4-a3"), /không hợp lệ/i);
});
