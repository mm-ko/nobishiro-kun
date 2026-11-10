export const MAX_UPLOAD_IMAGES = 2;
export const MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024;
export const MAX_TOTAL_IMAGE_SIZE_BYTES = 20 * 1024 * 1024;

export const ALLOWED_IMAGE_MIME_TYPES = ["image/jpeg", "image/png"] as const;
export const ALLOWED_IMAGE_EXTENSIONS = ["jpg", "jpeg", "png"] as const;

export const IMAGE_INPUT_ACCEPT = ".jpg,.jpeg,.png,image/jpeg,image/png";

// UI-005（分析中）で、時間で切り替える文言（画面設計書 Ver.1.06）
export const STAGE_A_WAITING_MESSAGES = [
  "画像を読み取っています",
  "採点を確認しています",
  "分析しています",
] as const;

// UI-006B（分析中）で、時間で切り替える文言（画面設計書 Ver.1.06）
export const STAGE_B_WAITING_MESSAGES = [
  "単元を確認しています",
  "間違え方を分析しています",
  "コメントをまとめています",
] as const;
