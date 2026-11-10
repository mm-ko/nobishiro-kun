import {
  ALLOWED_IMAGE_EXTENSIONS,
  ALLOWED_IMAGE_MIME_TYPES,
  MAX_IMAGE_SIZE_BYTES,
  MAX_TOTAL_IMAGE_SIZE_BYTES,
  MAX_UPLOAD_IMAGES,
} from "../constants";

type AllowedImageMimeType = (typeof ALLOWED_IMAGE_MIME_TYPES)[number];

const PNG_SIGNATURE = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];

function formatMegabytes(bytes: number): string {
  return `${Math.round(bytes / 1024 / 1024)}MB`;
}

function getFileExtension(fileName: string): string {
  return fileName.split(".").pop()?.toLowerCase() ?? "";
}

function matchesBytes(bytes: Uint8Array, expected: number[]): boolean {
  return expected.every((value, index) => bytes[index] === value);
}

async function detectImageMimeType(
  file: File,
): Promise<AllowedImageMimeType | null> {
  const bytes = new Uint8Array(await file.slice(0, 8).arrayBuffer());

  if (matchesBytes(bytes, [0xff, 0xd8, 0xff])) {
    return "image/jpeg";
  }

  if (matchesBytes(bytes, PNG_SIGNATURE)) {
    return "image/png";
  }

  return null;
}

export async function validateImageFiles(
  newFiles: File[],
  existingFiles: File[] = [],
): Promise<string | null> {
  if (newFiles.length === 0) {
    return "画像を選択してください。";
  }

  if (existingFiles.length + newFiles.length > MAX_UPLOAD_IMAGES) {
    return `画像は最大${MAX_UPLOAD_IMAGES}枚まで選択できます。`;
  }

  for (const file of newFiles) {
    if (file.size === 0) {
      return "空の画像ファイルは選択できません。";
    }

    const extension = getFileExtension(file.name);
    const detectedMimeType = await detectImageMimeType(file);
    const hasAllowedExtension = ALLOWED_IMAGE_EXTENSIONS.some(
      (allowedExtension) => allowedExtension === extension,
    );
    const hasAllowedMimeType = ALLOWED_IMAGE_MIME_TYPES.some(
      (allowedMimeType) => allowedMimeType === file.type,
    );

    if (
      !hasAllowedExtension ||
      !hasAllowedMimeType ||
      detectedMimeType === null ||
      detectedMimeType !== file.type
    ) {
      return "JPEG、JPG、PNG形式の画像を選択してください。";
    }

    if (file.size > MAX_IMAGE_SIZE_BYTES) {
      return `画像1枚の容量は${formatMegabytes(MAX_IMAGE_SIZE_BYTES)}までです。`;
    }
  }

  const totalSize = [...existingFiles, ...newFiles].reduce(
    (sum, file) => sum + file.size,
    0,
  );

  if (totalSize > MAX_TOTAL_IMAGE_SIZE_BYTES) {
    return `画像の合計容量は${formatMegabytes(MAX_TOTAL_IMAGE_SIZE_BYTES)}までです。`;
  }

  return null;
}
