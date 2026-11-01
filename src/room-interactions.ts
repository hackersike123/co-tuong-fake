export type PlayerRole = "player1" | "player2";

export function requiresRoomExitConfirmation(
  currentPage: string,
  nextPage: string,
  roomActive: boolean,
  gameMode: string,
): boolean {
  const leavingActiveRoom =
    roomActive && (currentPage === "waiting" || (currentPage === "game" && gameMode === "online"));
  const remainsInRoom =
    roomActive &&
    (nextPage === "waiting" ||
      (nextPage === "game" && (currentPage === "waiting" || gameMode === "online")));
  return leavingActiveRoom && !remainsInRoom && currentPage !== nextPage;
}

export function isCurrentIncomingCall<T>(
  status: string,
  activeCall: T | null,
  expectedCall: T,
): boolean {
  return status === "incoming" && activeCall === expectedCall;
}

export function canContinueCallAfterMediaPrompt(gameEnded: boolean, socketOpen: boolean): boolean {
  return !gameEnded && socketOpen;
}

export function trackPendingRequest<T>(
  pending: Set<Promise<unknown>>,
  request: Promise<T>,
): Promise<T> {
  pending.add(request);
  void request.then(
    () => pending.delete(request),
    () => pending.delete(request),
  );
  return request;
}

export async function waitForPendingRequests(pending: Set<Promise<unknown>>): Promise<void> {
  while (pending.size > 0) await Promise.allSettled([...pending]);
}

export function isOtherPlayerRole(localRole: string, eventRole: string | undefined): boolean {
  return (
    (localRole === "player1" || localRole === "player2") &&
    (eventRole === "player1" || eventRole === "player2") &&
    localRole !== eventRole
  );
}

export function shouldApplyAuthRefresh(
  requestEpoch: number,
  currentEpoch: number,
  logoutInProgress: boolean,
): boolean {
  return !logoutInProgress && requestEpoch === currentEpoch;
}
