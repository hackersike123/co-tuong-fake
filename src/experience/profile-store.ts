import { AVATAR_MAX_BYTES } from "./avatar";

export const PROFILE_AVATARS = [
  { tone: "sage", label: "xanh lá" },
  { tone: "sand", label: "nâu" },
  { tone: "blue", label: "xanh lam" },
  { tone: "rose", label: "đỏ" },
] as const;
export type ProfileTone = (typeof PROFILE_AVATARS)[number]["tone"];
export type ProfileRecord = {
  name: string;
  tone: ProfileTone;
  image: Blob | null;
};
export const DEFAULT_PROFILE: ProfileRecord = {
  name: "Minh Anh",
  tone: "sage",
  image: null,
};
export const PROFILE_DB_NAME = "ky-tien-hoi.demo.profile";
const PROFILE_STORE = "profiles";
const PROFILE_KEY = "current";
const LEGACY_AVATAR_KEY = "ky-tien-hoi.demo.avatar.v1";

export const normalizeProfileName = (name: string) => name.trim().normalize("NFC");

export function profileNameError(name: string) {
  const length = normalizeProfileName(name).length;
  if (length < 3) return "Tên kỳ thủ cần có ít nhất 3 ký tự.";
  if (length > 24) return "Tên kỳ thủ không được vượt quá 24 ký tự.";
  return "";
}

function validProfile(value: unknown): value is ProfileRecord {
  if (!value || typeof value !== "object") return false;
  const record = value as Partial<ProfileRecord>;
  return (
    typeof record.name === "string" &&
    !profileNameError(record.name) &&
    PROFILE_AVATARS.some(({ tone }) => tone === record.tone) &&
    (record.image === null ||
      (record.image instanceof Blob &&
        ["image/jpeg", "image/png", "image/webp"].includes(record.image.type) &&
        record.image.size > 0 &&
        record.image.size <= AVATAR_MAX_BYTES))
  );
}

export function profileStorageError(error: unknown) {
  if (error instanceof DOMException && error.name === "QuotaExceededError")
    return "Trình duyệt không còn đủ dung lượng. Hãy giải phóng bộ nhớ hoặc chọn ảnh nhỏ hơn rồi lưu lại.";
  return "Không thể lưu hoặc đọc hồ sơ trên trình duyệt này. Hãy kiểm tra quyền lưu trữ; hồ sơ đang dùng chưa bị thay đổi.";
}

function openProfileDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("IndexedDB không khả dụng."));
      return;
    }
    let blocked = false;
    const request = indexedDB.open(PROFILE_DB_NAME, 1);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(PROFILE_STORE))
        request.result.createObjectStore(PROFILE_STORE);
    };
    request.onerror = () => reject(request.error);
    request.onblocked = () => {
      blocked = true;
      reject(new Error("Đang có một thẻ khác giữ kho hồ sơ."));
    };
    request.onsuccess = () => {
      if (blocked) {
        request.result.close();
        return;
      }
      request.result.onversionchange = () => request.result.close();
      resolve(request.result);
    };
  });
}

async function profileTransaction<T>(
  mode: "readonly" | "readwrite",
  action: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  const database = await openProfileDatabase();
  try {
    return await new Promise<T>((resolve, reject) => {
      const transaction = database.transaction(PROFILE_STORE, mode);
      let request: IDBRequest<T>;
      try {
        request = action(transaction.objectStore(PROFILE_STORE));
      } catch (error) {
        transaction.abort();
        reject(error);
        return;
      }
      transaction.oncomplete = () => resolve(request.result);
      transaction.onabort = () => reject(transaction.error || request.error);
      transaction.onerror = () => reject(transaction.error || request.error);
    });
  } finally {
    database.close();
  }
}

function legacyProfile(): ProfileRecord {
  try {
    const value = localStorage.getItem(LEGACY_AVATAR_KEY);
    if (value && value.length < 600_000) {
      const match = value.match(/^data:(image\/(?:webp|png|jpeg));base64,([A-Za-z0-9+/=]+)$/);
      if (match) {
        const bytes = Uint8Array.from(atob(match[2]), (character) => character.charCodeAt(0));
        return {
          ...DEFAULT_PROFILE,
          image: new Blob([bytes], { type: match[1] }),
        };
      }
    }
  } catch {
    // A blocked or invalid legacy entry must not prevent opening the app.
  }
  return { ...DEFAULT_PROFILE };
}

function clearLegacyAvatar() {
  try {
    localStorage.removeItem(LEGACY_AVATAR_KEY);
  } catch {
    // The committed IndexedDB record remains authoritative if cleanup is blocked.
  }
}

export async function writeProfile(record: ProfileRecord) {
  const value = { ...record, name: normalizeProfileName(record.name) };
  if (!validProfile(value)) throw new Error("Hồ sơ chưa hợp lệ.");
  // A single record/transaction commits name, preset and photo together.
  await profileTransaction("readwrite", (store) => store.put(value, PROFILE_KEY));
  clearLegacyAvatar();
}

export async function readProfile(): Promise<{
  profile: ProfileRecord;
  warning: string;
}> {
  const legacy = legacyProfile();
  try {
    const stored: unknown = await profileTransaction("readonly", (store) => store.get(PROFILE_KEY));
    if (validProfile(stored)) {
      clearLegacyAvatar();
      return { profile: stored, warning: "" };
    }
    if (stored !== undefined)
      return {
        profile: legacy,
        warning: "Hồ sơ lưu cục bộ chưa hợp lệ. Bạn có thể chọn lại ảnh và lưu một hồ sơ mới.",
      };
    if (legacy.image) await writeProfile(legacy);
    return { profile: legacy, warning: "" };
  } catch (error) {
    return { profile: legacy, warning: profileStorageError(error) };
  }
}
