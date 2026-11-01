export type GameClockSnapshot = {
  redTimeMs: number;
  blackTimeMs: number;
  activeSide: "red" | "black";
  updatedAtMs: number;
  paused: boolean;
};

export function readGameClock(snapshot: GameClockSnapshot, nowMs: number) {
  const elapsedMs = snapshot.paused ? 0 : Math.max(0, nowMs - snapshot.updatedAtMs);
  return {
    redTimeMs: Math.max(0, snapshot.redTimeMs - (snapshot.activeSide === "red" ? elapsedMs : 0)),
    blackTimeMs: Math.max(
      0,
      snapshot.blackTimeMs - (snapshot.activeSide === "black" ? elapsedMs : 0),
    ),
  };
}

export function advanceGameClock(
  snapshot: GameClockSnapshot,
  activeSide: "red" | "black",
  updatedAtMs: number,
): GameClockSnapshot {
  return {
    ...readGameClock(snapshot, updatedAtMs),
    activeSide,
    updatedAtMs,
    paused: snapshot.paused,
  };
}
