import assert from "node:assert/strict";
import test from "node:test";
import { advanceGameClock, readGameClock, type GameClockSnapshot } from "../../src/game-clock";

const start = (activeSide: "red" | "black" = "red", paused = false): GameClockSnapshot => ({
  redTimeMs: 60_000,
  blackTimeMs: 60_000,
  activeSide,
  updatedAtMs: 1_000,
  paused,
});

test("counts down only the active player's clock", () => {
  assert.deepEqual(readGameClock(start("red"), 2_250), {
    redTimeMs: 58_750,
    blackTimeMs: 60_000,
  });
  assert.deepEqual(readGameClock(start("black"), 2_250), {
    redTimeMs: 60_000,
    blackTimeMs: 58_750,
  });
});

test("does not count down while the game is paused", () => {
  assert.deepEqual(readGameClock(start("red", true), 20_000), {
    redTimeMs: 60_000,
    blackTimeMs: 60_000,
  });
});

test("clamps expired clocks and ignores negative elapsed time", () => {
  assert.deepEqual(readGameClock({ ...start(), redTimeMs: 400 }, 2_000), {
    redTimeMs: 0,
    blackTimeMs: 60_000,
  });
  assert.deepEqual(readGameClock(start(), 500), {
    redTimeMs: 60_000,
    blackTimeMs: 60_000,
  });
});

test("charges the previous side and resets the incoming side to the per-turn limit", () => {
  const next = advanceGameClock({ ...start("red"), blackTimeMs: 12_000 }, "black", 6_000, 60_000);
  assert.deepEqual(next, {
    redTimeMs: 55_000,
    blackTimeMs: 60_000,
    activeSide: "black",
    updatedAtMs: 6_000,
    paused: false,
  });
  assert.deepEqual(readGameClock(next, 7_000), {
    redTimeMs: 55_000,
    blackTimeMs: 59_000,
  });
  const redTurn = advanceGameClock(next, "red", 11_000, 60_000);
  assert.deepEqual(redTurn, {
    redTimeMs: 60_000,
    blackTimeMs: 55_000,
    activeSide: "red",
    updatedAtMs: 11_000,
    paused: false,
  });
});
