export type RoomCodeJoinPayload = {
  room_code: string;
  participant_name: string;
  password?: string;
};

export function buildRoomCodeJoinPayload(
  code: string,
  participantName: string,
  password?: string,
): RoomCodeJoinPayload {
  return {
    room_code: code.trim().toUpperCase(),
    participant_name: participantName,
    ...(password ? { password } : {}),
  };
}
