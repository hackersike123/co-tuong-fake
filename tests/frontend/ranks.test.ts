import assert from "node:assert/strict";
import test from "node:test";
import { resolveDisplayedElo } from "../../src/ranks";

test("does not show a local default Elo for a guest player", () => {
  assert.equal(
    resolveDisplayedElo({ current: true, signedIn: false, currentElo: 1000, playerElo: 1000 }),
    null,
  );
});

test("uses the server Elo for a signed-in current player", () => {
  assert.equal(
    resolveDisplayedElo({ current: true, signedIn: true, currentElo: 1475, playerElo: 1000 }),
    1475,
  );
});

test("uses the supplied server rating for an opponent", () => {
  assert.equal(
    resolveDisplayedElo({ current: false, signedIn: true, currentElo: 1475, playerElo: 1320 }),
    1320,
  );
});
