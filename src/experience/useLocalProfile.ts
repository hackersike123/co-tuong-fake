import { useCallback, useEffect, useRef, useState } from "react"
import {
  DEFAULT_PROFILE,
  normalizeProfileName,
  profileStorageError,
  readProfile,
  writeProfile,
  type ProfileRecord,
} from "./profile-store"

export type LocalProfile = ProfileRecord & { imageUrl: string | null }
export type ProfileSaveResult = {
  ok: boolean
  error?: string
}

export function useLocalProfile() {
  const [profile, setProfile] = useState<LocalProfile>({
    ...DEFAULT_PROFILE,
    imageUrl: null,
  })
  const [profileReady, setProfileReady] = useState(false)
  const [profileWarning, setProfileWarning] = useState("")
  const mounted = useRef(false)
  const saving = useRef(false)
  const sessionNameRevision = useRef(0)

  useEffect(() => {
    mounted.current = true
    let cancelled = false
    const revision = sessionNameRevision.current
    void readProfile().then(({ profile: record, warning }) => {
      if (cancelled) return
      const imageUrl = record.image ? URL.createObjectURL(record.image) : null
      setProfile((previous) => ({
        ...record,
        name:
          sessionNameRevision.current === revision
            ? record.name
            : previous.name,
        imageUrl,
      }))
      setProfileWarning(warning)
      setProfileReady(true)
    })
    return () => {
      cancelled = true
      mounted.current = false
    }
  }, [])

  useEffect(
    () => () => {
      if (profile.imageUrl) URL.revokeObjectURL(profile.imageUrl)
    },
    [profile.imageUrl],
  )

  // Existing demo registration can still set a session name without saving a profile.
  const setDemoName = useCallback((name: string) => {
    sessionNameRevision.current++
    setProfile((previous) => ({ ...previous, name: name.trim() }))
  }, [])

  const saveProfile = useCallback(
    async (record: ProfileRecord): Promise<ProfileSaveResult> => {
      if (saving.current)
        return { ok: false, error: "Hồ sơ đang được lưu. Vui lòng chờ." }
      saving.current = true
      let imageUrl: string | null = null
      try {
        const value = {
          name: normalizeProfileName(record.name),
          tone: record.tone,
          image: record.image,
        }
        imageUrl = value.image ? URL.createObjectURL(value.image) : null
        await writeProfile(value)
        if (mounted.current) {
          sessionNameRevision.current++
          setProfile({ ...value, imageUrl })
          setProfileWarning("")
        } else if (imageUrl) {
          URL.revokeObjectURL(imageUrl)
        }
        return { ok: true }
      } catch (error) {
        if (imageUrl) URL.revokeObjectURL(imageUrl)
        return { ok: false, error: profileStorageError(error) }
      } finally {
        saving.current = false
      }
    },
    [],
  )

  return { profile, profileReady, profileWarning, saveProfile, setDemoName }
}
