import { useEffect, useRef, type Dispatch, type SetStateAction } from "react"
import { Button, InputField } from "@figma/astraui"
import { RotateCcw, RotateCw } from "lucide-react"
import { useExperience } from "./Experience"
import { getCultivationRank } from "../ranks"
import {
  cropGeometry,
  drawAvatar,
  INITIAL_CROP,
  type AvatarCrop,
  type DecodedAvatar,
} from "./avatar"

const PREVIEW_SIZE = 512
const clamp = (value: number) => Math.max(-1, Math.min(1, value))

/** Inline controls only: the profile form owns the draft and its save action. */
export function AvatarCropper({
  image,
  crop,
  onChange,
  onError,
  disabled,
}: {
  image: DecodedAvatar
  crop: AvatarCrop
  onChange: Dispatch<SetStateAction<AvatarCrop>>
  onError: (message: string) => void
  disabled: boolean
}) {
  const { demoElo } = useExperience()
  const rank = getCultivationRank(demoElo)
  const canvas = useRef<HTMLCanvasElement>(null)
  const drag = useRef<{
    x: number
    y: number
    cropX: number
    cropY: number
  } | null>(null)
  useEffect(() => {
    if (!canvas.current) return
    try {
      drawAvatar(canvas.current, image, crop)
    } catch (error) {
      onError(
        error instanceof Error ? error.message : "Chưa thể xem trước ảnh.",
      )
    }
  }, [image, crop, onError])
  return (
    <div className="profile-crop-controls">
      <div
        className={`profile-crop-frame rank-framed cultivation-${rank.index}`}
      >
        <div className="avatar-crop-window">
          <canvas
            ref={canvas}
            width={PREVIEW_SIZE}
            height={PREVIEW_SIZE}
            className="avatar-crop-canvas"
            role="img"
            aria-label="Xem trước ảnh đại diện đã cắt và xoay"
            onPointerDown={(event) => {
              if (disabled) return
              drag.current = {
                x: event.clientX,
                y: event.clientY,
                cropX: crop.x,
                cropY: crop.y,
              }
              event.currentTarget.setPointerCapture(event.pointerId)
            }}
            onPointerMove={(event) => {
              const origin = drag.current
              if (!origin || disabled) return
              const geometry = cropGeometry(image, crop, PREVIEW_SIZE)
              const scale =
                PREVIEW_SIZE / event.currentTarget.getBoundingClientRect().width
              onChange((previous) => ({
                ...previous,
                x: geometry.maxX
                  ? clamp(
                      origin.cropX +
                        ((event.clientX - origin.x) * scale) / geometry.maxX,
                    )
                  : 0,
                y: geometry.maxY
                  ? clamp(
                      origin.cropY +
                        ((event.clientY - origin.y) * scale) / geometry.maxY,
                    )
                  : 0,
              }))
            }}
            onPointerUp={() => {
              drag.current = null
            }}
            onPointerCancel={() => {
              drag.current = null
            }}
          />
        </div>
      </div>
      <span className="tiny muted">
        Kéo ảnh để căn vị trí. Khung cảnh giới nằm bên ngoài, không được ghép
        vào ảnh lưu.
      </span>
      <InputField
        label="Phóng to"
        aria-label="Phóng to ảnh đại diện"
        type="range"
        min="1"
        max="3"
        step=".05"
        value={String(crop.zoom)}
        disabled={disabled}
        onChange={(value) =>
          onChange((previous) => ({ ...previous, zoom: Number(value) }))
        }
      />
      <div className="avatar-position-fields">
        <InputField
          label="Vị trí ngang"
          aria-label="Vị trí ngang của ảnh"
          type="range"
          min="-100"
          max="100"
          value={String(Math.round(crop.x * 100))}
          disabled={disabled}
          onChange={(value) =>
            onChange((previous) => ({ ...previous, x: Number(value) / 100 }))
          }
        />
        <InputField
          label="Vị trí dọc"
          aria-label="Vị trí dọc của ảnh"
          type="range"
          min="-100"
          max="100"
          value={String(Math.round(crop.y * 100))}
          disabled={disabled}
          onChange={(value) =>
            onChange((previous) => ({ ...previous, y: Number(value) / 100 }))
          }
        />
      </div>
      <div className="avatar-rotate-controls">
        <Button
          type="button"
          variant="neutral"
          size="small"
          disabled={disabled}
          iconStart={<RotateCcw size={16} />}
          onClick={() =>
            onChange((previous) => ({
              ...previous,
              rotation: (previous.rotation + 270) % 360,
              x: 0,
              y: 0,
            }))
          }
        >
          Xoay trái
        </Button>
        <Button
          type="button"
          variant="neutral"
          size="small"
          disabled={disabled}
          iconStart={<RotateCw size={16} />}
          onClick={() =>
            onChange((previous) => ({
              ...previous,
              rotation: (previous.rotation + 90) % 360,
              x: 0,
              y: 0,
            }))
          }
        >
          Xoay phải
        </Button>
        <Button
          type="button"
          variant="subtle"
          size="small"
          disabled={disabled}
          onClick={() => onChange({ ...INITIAL_CROP })}
        >
          Căn giữa
        </Button>
      </div>
    </div>
  )
}
