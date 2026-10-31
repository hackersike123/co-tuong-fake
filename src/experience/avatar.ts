export const AVATAR_MAX_BYTES = 5 * 1024 * 1024;
export type DecodedAvatar = {
  image: ImageBitmap | HTMLImageElement;
  width: number;
  height: number;
  dispose: () => void;
};
export type AvatarCrop = {
  zoom: number;
  rotation: number;
  x: number;
  y: number;
};
export const INITIAL_CROP: AvatarCrop = { zoom: 1, rotation: 0, x: 0, y: 0 };

export async function decodeAvatar(file: File): Promise<DecodedAvatar> {
  if (
    !["image/jpeg", "image/png", "image/webp"].includes(file.type) ||
    !/\.(jpe?g|png|webp)$/i.test(file.name)
  ) {
    throw new Error("Vui lòng chọn ảnh JPG, PNG hoặc WebP. Không hỗ trợ SVG, GIF hay tệp khác.");
  }
  if (file.size === 0 || file.size > AVATAR_MAX_BYTES)
    throw new Error("Ảnh phải có dung lượng lớn hơn 0 và không quá 5 MB.");
  const header = new Uint8Array(await file.slice(0, 12).arrayBuffer());
  const actualType =
    header[0] === 0xff && header[1] === 0xd8 && header[2] === 0xff
      ? "image/jpeg"
      : [137, 80, 78, 71, 13, 10, 26, 10].every((byte, index) => header[index] === byte)
        ? "image/png"
        : String.fromCharCode(...header.slice(0, 4)) === "RIFF" &&
            String.fromCharCode(...header.slice(8, 12)) === "WEBP"
          ? "image/webp"
          : null;
  if (actualType !== file.type)
    throw new Error(
      "Nội dung tệp không phải ảnh JPG, PNG hoặc WebP hợp lệ, hoặc không khớp với loại tệp.",
    );
  let result: DecodedAvatar;
  try {
    if (typeof createImageBitmap === "function") {
      const image = await createImageBitmap(file);
      result = {
        image,
        width: image.width,
        height: image.height,
        dispose: () => image.close(),
      };
    } else {
      const url = URL.createObjectURL(file);
      const image = new Image();
      image.src = url;
      try {
        await image.decode();
      } catch (error) {
        URL.revokeObjectURL(url);
        throw error;
      }
      result = {
        image,
        width: image.naturalWidth,
        height: image.naturalHeight,
        dispose: () => URL.revokeObjectURL(url),
      };
    }
  } catch {
    throw new Error(
      "Không thể đọc ảnh này. Tệp có thể bị hỏng; hãy thử một ảnh JPG, PNG hoặc WebP khác.",
    );
  }
  if (!result.width || !result.height || result.width * result.height > 24_000_000) {
    result.dispose();
    throw new Error(
      "Ảnh có kích thước quá lớn hoặc không hợp lệ. Hãy chọn ảnh dưới 24 triệu điểm ảnh.",
    );
  }
  return result;
}

export function cropGeometry(image: DecodedAvatar, crop: AvatarCrop, size: number) {
  const quarterTurn = Math.abs(crop.rotation % 180) === 90;
  const width = quarterTurn ? image.height : image.width;
  const height = quarterTurn ? image.width : image.height;
  const scale = Math.max(size / width, size / height) * crop.zoom;
  return {
    scale,
    maxX: Math.max(0, (width * scale - size) / 2),
    maxY: Math.max(0, (height * scale - size) / 2),
  };
}

export function drawAvatar(canvas: HTMLCanvasElement, image: DecodedAvatar, crop: AvatarCrop) {
  const context = canvas.getContext("2d");
  if (!context) throw new Error("Trình duyệt chưa hỗ trợ cắt ảnh bằng canvas.");
  const size = canvas.width;
  const geometry = cropGeometry(image, crop, size);
  context.setTransform(1, 0, 0, 1, 0, 0);
  context.clearRect(0, 0, size, size);
  context.translate(size / 2 + crop.x * geometry.maxX, size / 2 + crop.y * geometry.maxY);
  context.rotate((crop.rotation * Math.PI) / 180);
  context.drawImage(
    image.image,
    (-image.width * geometry.scale) / 2,
    (-image.height * geometry.scale) / 2,
    image.width * geometry.scale,
    image.height * geometry.scale,
  );
  context.setTransform(1, 0, 0, 1, 0, 0);
}

export async function encodeAvatar(image: DecodedAvatar, crop: AvatarCrop): Promise<Blob> {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 256;
  drawAvatar(canvas, image, crop);
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (blob && blob.size > 0 && blob.size <= AVATAR_MAX_BYTES) resolve(blob);
        else reject(new Error("Không thể xử lý ảnh đại diện. Vui lòng chọn ảnh khác."));
      },
      "image/webp",
      0.88,
    );
  });
}
