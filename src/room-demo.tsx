import { useState } from "react";
import { Badge, Button, IconButton } from "@figma/astraui";
import {
  Maximize2,
  Mic,
  MicOff,
  Minimize2,
  PhoneOff,
  Video,
  VideoOff,
  WifiOff,
} from "lucide-react";
import { Heading, IconAction, UserAvatar } from "./components";
import { useApp } from "./context";
import { DEMO_CONNECTION_LABEL } from "./config/connection";
import { playerInitials } from "./data";

export function DemoMatchmakingNotice() {
  return (
    <div className="demo-matchmaking-notice" role="note">
      <WifiOff size={16} />
      <span>Bản demo — chưa ghép trận với máy chủ</span>
    </div>
  );
}

export function DemoConnectionStatus() {
  return (
    <div className="connection-status" role="status">
      <span className="demo-connection-label">
        <WifiOff size={14} />
        {DEMO_CONNECTION_LABEL}
      </span>
    </div>
  );
}

/** Display-only controls: no socket, media stream, or permission request. */
export function DemoCallPanel() {
  const { username, profileTone, activeRoom, isHost } = useApp();
  const [active, setActive] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [microphone, setMicrophone] = useState(false);
  const [camera, setCamera] = useState(false);
  const [ended, setEnded] = useState(false);
  const opponent = isHost ? "ThanhPhong" : activeRoom.host;

  function endDemo() {
    setActive(false);
    setExpanded(false);
    setMicrophone(false);
    setCamera(false);
    setEnded(true);
  }

  return (
    <section className="surface demo-call-panel" aria-label="Gọi video và micro mô phỏng">
      <div className="between">
        <Heading level={3}>Video và micro</Heading>
        <Badge label="Mô phỏng" variant="secondary" />
      </div>
      <div className="small muted">Không truy cập thiết bị, thu âm hay truyền hình ảnh.</div>
      {active ? (
        <>
          <div className="between">
            <span className="small muted" role="status">
              Đang mở giao diện mô phỏng
            </span>
            <IconAction
              label={expanded ? "Thu gọn video mô phỏng" : "Mở rộng video mô phỏng"}
              icon={expanded ? <Minimize2 size={17} /> : <Maximize2 size={17} />}
              onClick={() => setExpanded((value) => !value)}
            />
          </div>
          {expanded && (
            <div className="demo-video-grid">
              <div className="demo-video-tile">
                <UserAvatar initials={playerInitials(opponent)} tone="blue" elo={activeRoom.elo} />
                <span className="demo-video-name">{opponent}</span>
                <span className="tiny muted">Khung đối thủ · mô phỏng</span>
              </div>
              <div className="demo-video-tile">
                {camera ? (
                  <span className="demo-camera-preview">
                    <Video size={26} />
                    <span className="tiny">Hình ảnh mô phỏng</span>
                  </span>
                ) : (
                  <UserAvatar initials={playerInitials(username)} tone={profileTone} current />
                )}
                <span className="demo-video-name">Bạn</span>
                <span className="tiny muted">Camera {camera ? "bật" : "tắt"} · mô phỏng</span>
              </div>
            </div>
          )}
          <div className="demo-call-controls">
            <IconButton
              variant="neutral"
              icon={microphone ? <Mic size={18} /> : <MicOff size={18} />}
              aria-label={`${microphone ? "Tắt" : "Bật"} micro (mô phỏng)`}
              title={`${microphone ? "Tắt" : "Bật"} micro (mô phỏng)`}
              aria-pressed={microphone}
              onClick={() => setMicrophone((value) => !value)}
            />
            <IconButton
              variant="neutral"
              icon={camera ? <Video size={18} /> : <VideoOff size={18} />}
              aria-label={`${camera ? "Tắt" : "Bật"} camera (mô phỏng)`}
              title={`${camera ? "Tắt" : "Bật"} camera (mô phỏng)`}
              aria-pressed={camera}
              onClick={() => setCamera((value) => !value)}
            />
            <IconButton
              variant="subtle"
              className="demo-call-end"
              icon={<PhoneOff size={18} />}
              aria-label="Kết thúc mô phỏng cuộc gọi"
              title="Kết thúc mô phỏng cuộc gọi"
              onClick={endDemo}
            />
          </div>
          <div className="tiny muted" role="status">
            Micro {microphone ? "bật" : "tắt"} · camera {camera ? "bật" : "tắt"} — chỉ mô phỏng.
          </div>
        </>
      ) : (
        <>
          {ended && (
            <span className="small muted" role="status">
              Đã kết thúc mô phỏng.
            </span>
          )}
          <Button
            variant="neutral"
            className="demo-call-start"
            iconStart={<Video size={16} />}
            onClick={() => {
              setActive(true);
              setEnded(false);
            }}
          >
            Bắt đầu gọi video (mô phỏng)
          </Button>
        </>
      )}
    </section>
  );
}
