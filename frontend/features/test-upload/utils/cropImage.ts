import type { PixelCrop } from "react-image-crop";

export function cropImageToFile(
  image: HTMLImageElement,
  crop: PixelCrop,
  sourceFile: File,
): Promise<File> {
  const scaleX = image.naturalWidth / image.width;
  const scaleY = image.naturalHeight / image.height;
  const canvas = document.createElement("canvas");

  canvas.width = Math.max(1, Math.floor(crop.width * scaleX));
  canvas.height = Math.max(1, Math.floor(crop.height * scaleY));

  const context = canvas.getContext("2d");
  if (context === null) {
    return Promise.reject(new Error("画像の切り抜きを開始できませんでした。"));
  }

  context.imageSmoothingEnabled = true;
  context.imageSmoothingQuality = "high";
  context.drawImage(
    image,
    crop.x * scaleX,
    crop.y * scaleY,
    crop.width * scaleX,
    crop.height * scaleY,
    0,
    0,
    canvas.width,
    canvas.height,
  );

  const outputType =
    sourceFile.type === "image/png" ? "image/png" : "image/jpeg";
  const outputQuality = outputType === "image/jpeg" ? 0.92 : undefined;

  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (blob === null) {
          reject(new Error("画像の切り抜きに失敗しました。"));
          return;
        }

        resolve(
          new File([blob], sourceFile.name, {
            type: outputType,
            lastModified: Date.now(),
          }),
        );
      },
      outputType,
      outputQuality,
    );
  });
}
