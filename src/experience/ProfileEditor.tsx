import { useEffect, useRef, useState, type FormEvent } from "react"
import { Button, InputField } from "@figma/astraui"
import { AlertCircle, Check, ShieldCheck, Upload } from "lucide-react"
import { Dialog, UserAvatar } from "../components"
import { useApp } from "../context"
import { playerInitials } from "../data"
import { useExperience } from "./Experience"
import { AvatarCropper } from "./AvatarCropper"
import {
  decodeAvatar,
  encodeAvatar,
  INITIAL_CROP,
  type AvatarCrop,
  type DecodedAvatar,
} from "./avatar"
import {
  normalizeProfileName,
  PROFILE_AVATARS,
  profileNameError,
  type ProfileTone,
} from "./profile-store"

export function ProfileEditor({ onClose }: { onClose: () => void }) {
  const { profileReady } = useExperience()
  if (!profileReady)
    return (
      <Dialog
        isOpen
        onClose={onClose}
        title="Chỉnh sửa hồ sơ đạo hữu"
        className="profile-editor-dialog"
        footer={
          <>
            <Button variant="neutral" onClick={onClose}>
              Hủy
            </Button>
            <Button disabled>Lưu thay đổi</Button>
          </>
        }
      >
        <div role="status" className="muted">
          Đang đọc hồ sơ lưu cục bộ...
        </div>
      </Dialog>
    )
  return <ProfileEditorForm onClose={onClose} />
}

function ProfileEditorForm({ onClose }: { onClose: () => void }) {
  const { notify } = useApp()
  const { profile, demoElo, saveProfile, profileWarning } = useExperience()
  const [name, setName] = useState(profile.name)
  const [tone, setTone] = useState<ProfileTone>(profile.tone)
  const [useUpload, setUseUpload] = useState(Boolean(profile.image))
  const [sourceImage, setSourceImage] = useState<DecodedAvatar | null>(null)
  const [newUpload, setNewUpload] = useState(false)
  const [crop, setCrop] = useState<AvatarCrop>({ ...INITIAL_CROP })
  const [pending, setPending] = useState(false)
  const [saving, setSaving] = useState(false)
  const [fileError, setFileError] = useState("")
  const [saveError, setSaveError] = useState("")
  const requestGeneration = useRef(0)
  const picker = useRef<HTMLDivElement>(null)
  useEffect(
    () => () => {
      requestGeneration.current++
    },
    [],
  )
  useEffect(() => () => sourceImage?.dispose(), [sourceImage])

  const canonicalName = normalizeProfileName(name)
  const nameError = profileNameError(name)
  const cropChanged =
    crop.zoom !== INITIAL_CROP.zoom ||
    crop.rotation !== INITIAL_CROP.rotation ||
    crop.x !== INITIAL_CROP.x ||
    crop.y !== INITIAL_CROP.y
  const changed =
    canonicalName !== profile.name ||
    tone !== profile.tone ||
    useUpload !== Boolean(profile.image) ||
    (useUpload && (newUpload || cropChanged))
  const valid =
    !nameError &&
    !fileError &&
    (!useUpload || Boolean(sourceImage || profile.image))
  const canSave = changed && valid && !pending && !saving

  function selectPreset(value: ProfileTone) {
    requestGeneration.current++
    setTone(value)
    setUseUpload(false)
    setSourceImage(null)
    setNewUpload(false)
    setCrop({ ...INITIAL_CROP })
    setPending(false)
    setFileError("")
    setSaveError("")
  }

  async function selectFile(file: File, isNew = true) {
    const generation = ++requestGeneration.current
    setPending(true)
    setFileError("")
    setSaveError("")
    try {
      const decoded = await decodeAvatar(file)
      if (generation !== requestGeneration.current) {
        decoded.dispose()
        return
      }
      setSourceImage(decoded)
      setCrop({ ...INITIAL_CROP })
      setNewUpload(isNew)
      setUseUpload(true)
    } catch (error) {
      if (generation === requestGeneration.current)
        setFileError(
          error instanceof Error ? error.message : "Ảnh chưa hợp lệ.",
        )
    } finally {
      if (generation === requestGeneration.current) setPending(false)
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!canSave) return
    setSaving(true)
    setSaveError("")
    try {
      let image = useUpload ? profile.image : null
      if (useUpload && sourceImage && (newUpload || cropChanged))
        image = await encodeAvatar(sourceImage, crop)
      const result = await saveProfile({ name: canonicalName, tone, image })
      if (!result.ok) {
        setSaveError(result.error || "Chưa thể lưu hồ sơ.")
        return
      }
      notify(
        "Đã lưu tên và ảnh đại diện cục bộ trên trình duyệt. Không gửi lên máy chủ.",
      )
      onClose()
    } catch (error) {
      setSaveError(
        error instanceof Error
          ? error.message
          : "Không thể xử lý ảnh. Vui lòng thử lại.",
      )
    } finally {
      setSaving(false)
    }
  }

  const close = () => {
    if (!saving) onClose()
  }
  return (
    <Dialog
      isOpen
      onClose={close}
      title="Chỉnh sửa hồ sơ đạo hữu"
      size="medium"
      className="profile-editor-dialog"
      footer={
        <>
          <Button
            type="button"
            variant="neutral"
            onClick={close}
            disabled={saving}
          >
            Hủy
          </Button>
          <Button
            type="submit"
            form="profile-edit-form"
            iconStart={<Check size={16} />}
            disabled={!canSave}
          >
            {saving ? "Đang lưu..." : "Lưu thay đổi"}
          </Button>
        </>
      }
    >
      <form
        id="profile-edit-form"
        className="form-stack avatar-editor"
        onSubmit={submit}
        aria-busy={saving}
      >
        <div className="profile-local-note">
          <ShieldCheck size={18} />
          <span>
            Hồ sơ demo chỉ lưu trên trình duyệt này. Chọn ảnh, căn chỉnh và đổi
            tên trước khi lưu một lần.
          </span>
        </div>
        {profileWarning && (
          <div className="error-message" role="alert">
            {profileWarning}
          </div>
        )}
        <section
          className="profile-avatar-section"
          aria-label="Chọn ảnh đại diện"
        >
          <div className="form-label">Avatar có sẵn</div>
          <div className="avatar-options profile-preset-options">
            {PROFILE_AVATARS.map((option) => {
              const selected = !useUpload && tone === option.tone
              return (
                <Button
                  type="button"
                  variant="subtle"
                  key={option.tone}
                  className={`avatar-choice ${selected ? "avatar-chosen" : ""}`}
                  aria-label={`Chọn avatar có sẵn màu ${option.label}`}
                  aria-pressed={selected}
                  disabled={saving}
                  onClick={() => selectPreset(option.tone)}
                >
                  <UserAvatar
                    initials={playerInitials(name)}
                    tone={option.tone}
                    image={null}
                    elo={demoElo}
                    className="edit-avatar profile-preset-avatar"
                  />
                  {selected && (
                    <span className="avatar-check" aria-hidden="true">
                      <Check size={12} />
                    </span>
                  )}
                </Button>
              )
            })}
          </div>
          <div ref={picker} className="profile-upload-control">
            <Button
              type="button"
              variant="neutral"
              iconStart={<Upload size={16} />}
              disabled={pending || saving}
              onClick={() =>
                picker.current
                  ?.querySelector<HTMLInputElement>('input[type="file"]')
                  ?.click()
              }
            >
              Chọn ảnh từ thiết bị
            </Button>
            <InputField
              className="avatar-file-picker"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              tabIndex={-1}
              aria-label="Chọn ảnh đại diện từ thiết bị"
              aria-describedby={
                fileError ? "profile-file-error" : "profile-file-help"
              }
              aria-invalid={Boolean(fileError)}
              disabled={pending || saving}
              onInput={(event) => {
                const file = event.currentTarget.files?.[0]
                if (file) void selectFile(file)
                event.currentTarget.value = ""
              }}
            />
            <span id="profile-file-help" className="tiny muted">
              JPG, PNG hoặc WebP · tối đa 5 MB · không tải lên máy chủ
            </span>
            {fileError && (
              <div
                id="profile-file-error"
                className="error-message"
                role="alert"
              >
                <AlertCircle size={16} />
                {fileError}
              </div>
            )}
            {pending && (
              <span className="small muted" role="status">
                Đang đọc ảnh trên thiết bị...
              </span>
            )}
          </div>
          <div
            className="profile-avatar-preview"
            aria-label="Xem trước avatar đang chọn"
          >
            {sourceImage && useUpload ? (
              <AvatarCropper
                image={sourceImage}
                crop={crop}
                onChange={setCrop}
                onError={setFileError}
                disabled={saving}
              />
            ) : (
              <UserAvatar
                initials={playerInitials(name)}
                tone={tone}
                image={useUpload ? profile.imageUrl : null}
                elo={demoElo}
                className="profile-large-avatar"
              />
            )}
            <span className="small muted" role="status">
              {useUpload
                ? newUpload || cropChanged
                  ? "Ảnh đang chỉnh sửa · chưa lưu"
                  : "Ảnh đang lưu cục bộ"
                : "Đang chọn avatar có sẵn"}
            </span>
          </div>
          {useUpload && profile.image && !sourceImage && (
            <Button
              type="button"
              variant="subtle"
              size="small"
              disabled={pending || saving}
              onClick={() => {
                const image = profile.image!
                const extension =
                  image.type === "image/jpeg" ? "jpg" : image.type.split("/")[1]
                void selectFile(
                  new File([image], `avatar.${extension}`, {
                    type: image.type,
                  }),
                  false,
                )
              }}
            >
              Cắt/xoay ảnh đang dùng
            </Button>
          )}
          {useUpload && (
            <Button
              type="button"
              variant="subtle"
              size="small"
              disabled={saving}
              onClick={() => selectPreset(tone)}
            >
              {newUpload ? "Bỏ ảnh vừa chọn" : "Xóa ảnh đang lưu cục bộ"}
            </Button>
          )}
        </section>
        <div>
          <InputField
            label="Tên kỳ thủ"
            aria-label="Tên kỳ thủ"
            aria-invalid={Boolean(nameError)}
            aria-describedby={
              nameError ? "profile-name-error" : "profile-name-help"
            }
            value={name}
            onChange={setName}
            maxLength={24}
            disabled={saving}
            placeholder="Tên của bạn trên Kỳ Tiên Hội"
          />
          {nameError ? (
            <div
              id="profile-name-error"
              className="error-message profile-field-error"
              role="alert"
            >
              {nameError}
            </div>
          ) : (
            <div id="profile-name-help" className="tiny muted mt-xs">
              3–24 ký tự · {canonicalName.length}/24
            </div>
          )}
        </div>
        <span className="tiny muted">
          Chọn “Hủy” để bỏ toàn bộ bản nháp. Kể cả xóa ảnh cũng chỉ áp dụng sau
          khi chọn “Lưu thay đổi”.
        </span>
        {saveError && (
          <div className="error-message" role="alert">
            <AlertCircle size={16} />
            {saveError}
          </div>
        )}
      </form>
    </Dialog>
  )
}
