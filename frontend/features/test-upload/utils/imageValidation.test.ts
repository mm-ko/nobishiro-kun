import { describe, expect, test } from "vitest";

import { MAX_IMAGE_SIZE_BYTES, MAX_UPLOAD_IMAGES } from "../constants";
import { validateImageFiles } from "./imageValidation";

function createImageFile(
  name: string,
  type: string,
  signature: number[],
  size = signature.length,
): File {
  const bytes = new Uint8Array(size);
  bytes.set(signature);

  return new File([bytes.buffer], name, { type });
}

const jpegSignature = [0xff, 0xd8, 0xff];
const pngSignature = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];

describe("validateImageFiles", () => {
  test.each([
    ["JPEG", createImageFile("answer.jpeg", "image/jpeg", jpegSignature)],
    ["JPG", createImageFile("answer.JPG", "image/jpeg", jpegSignature)],
    ["PNG", createImageFile("answer.png", "image/png", pngSignature)],
  ])("%s形式の画像を受け付ける", async (_format, file) => {
    await expect(validateImageFiles([file])).resolves.toBeNull();
  });

  test("画像を選択していない場合はエラーを返す", async () => {
    await expect(validateImageFiles([])).resolves.toBe(
      "画像を選択してください。",
    );
  });

  test("空の画像ファイルは拒否する", async () => {
    const file = new File([], "empty.jpg", { type: "image/jpeg" });

    await expect(validateImageFiles([file])).resolves.toBe(
      "空の画像ファイルは選択できません。",
    );
  });

  test("HEICなどの非対応形式は拒否する", async () => {
    const file = new File(
      [new Uint8Array([0x00, 0x00, 0x00, 0x18]).buffer],
      "answer.heic",
      { type: "image/heic" },
    );

    await expect(validateImageFiles([file])).resolves.toBe(
      "JPEG、JPG、PNG形式の画像を選択してください。",
    );
  });

  test("拡張子がJPEGでも実データがPNGなら拒否する", async () => {
    const file = createImageFile("answer.jpg", "image/jpeg", pngSignature);

    await expect(validateImageFiles([file])).resolves.toBe(
      "JPEG、JPG、PNG形式の画像を選択してください。",
    );
  });

  test("最大枚数までは受け付ける", async () => {
    const files = [
      createImageFile("first.jpg", "image/jpeg", jpegSignature),
      createImageFile("second.png", "image/png", pngSignature),
    ];

    await expect(validateImageFiles(files)).resolves.toBeNull();
  });

  test("既存画像と追加画像の合計が最大枚数を超えたら拒否する", async () => {
    const existing = [
      createImageFile("first.jpg", "image/jpeg", jpegSignature),
    ];
    const newFiles = [
      createImageFile("second.jpg", "image/jpeg", jpegSignature),
      createImageFile("third.png", "image/png", pngSignature),
    ];

    await expect(validateImageFiles(newFiles, existing)).resolves.toBe(
      `画像は最大${MAX_UPLOAD_IMAGES}枚まで選択できます。`,
    );
  });

  test("1枚の容量が上限ちょうどなら受け付ける", async () => {
    const file = createImageFile(
      "large.jpg",
      "image/jpeg",
      jpegSignature,
      MAX_IMAGE_SIZE_BYTES,
    );

    await expect(validateImageFiles([file])).resolves.toBeNull();
  });

  test("1枚の容量が上限を超えたら拒否する", async () => {
    const file = createImageFile(
      "too-large.jpg",
      "image/jpeg",
      jpegSignature,
      MAX_IMAGE_SIZE_BYTES + 1,
    );

    await expect(validateImageFiles([file])).resolves.toBe(
      `画像1枚の容量は${MAX_IMAGE_SIZE_BYTES / 1024 / 1024}MBまでです。`,
    );
  });
});
