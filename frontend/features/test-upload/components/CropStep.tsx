"use client";

import { useRef, useState } from "react";
import ReactCrop, {
  convertToPixelCrop,
  type Crop,
  type PixelCrop,
} from "react-image-crop";

import type { SelectedTestImage } from "../types";
import { cropImageToFile } from "../utils/cropImage";
import styles from "./CropStep.module.css";

type CropStepProps = {
  image: SelectedTestImage;
  imageIndex: number;
  totalImages: number;
  onApplyCrop: (file: File) => Promise<string | null>;
  onUseOriginal: () => void;
  onBack: () => void;
};

const INITIAL_CROP: Crop = {
  unit: "%",
  x: 5,
  y: 5,
  width: 90,
  height: 90,
};

export function CropStep({
  image,
  imageIndex,
  totalImages,
  onApplyCrop,
  onUseOriginal,
  onBack,
}: CropStepProps) {
  const imageRef = useRef<HTMLImageElement>(null);
  const [crop, setCrop] = useState<Crop>(INITIAL_CROP);
  const [completedCrop, setCompletedCrop] = useState<PixelCrop | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);

  const handleImageLoad = () => {
    const element = imageRef.current;
    if (!element) {
      return;
    }

    setCompletedCrop(
      convertToPixelCrop(INITIAL_CROP, element.width, element.height),
    );
  };

  const handleApplyCrop = async () => {
    if (!imageRef.current || !completedCrop) {
      setErrorMessage("切り抜く範囲を選択してください。");
      return;
    }

    setIsProcessing(true);
    setErrorMessage(null);

    try {
      const croppedFile = await cropImageToFile(
        imageRef.current,
        completedCrop,
        image.file,
      );
      const validationError = await onApplyCrop(croppedFile);
      setErrorMessage(validationError);
    } catch {
      setErrorMessage(
        "画像を切り抜けませんでした。範囲を選び直してもう一度お試しください。",
      );
    } finally {
      setIsProcessing(false);
    }
  };

  const isLastImage = imageIndex === totalImages - 1;

  return (
    <section className={styles.card} aria-labelledby="crop-heading">
      <p className={styles.step}>STEP 2/2</p>
      <h1 id="crop-heading">必要な部分を囲んでください</h1>
      <p className={styles.description}>
        画像 {imageIndex + 1} / {totalImages}
        ：四隅や辺を動かして、問題番号・問題文・解答・採点結果を残します。
      </p>

      <div className={styles.cropArea}>
        <ReactCrop
          crop={crop}
          onChange={(pixelCrop, percentCrop) => {
            setCrop(percentCrop);
            setCompletedCrop(pixelCrop);
          }}
          onComplete={(pixelCrop) => setCompletedCrop(pixelCrop)}
          minWidth={24}
          minHeight={24}
        >
          {/* Blob URLをReactCrop内で直接扱うため、最適化対象外のimgを使用する。 */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            ref={imageRef}
            src={image.previewUrl}
            alt={`トリミングするテスト画像${imageIndex + 1}`}
            onLoad={handleImageLoad}
          />
        </ReactCrop>
      </div>

      {errorMessage && (
        <p className={styles.error} role="alert">
          {errorMessage}
        </p>
      )}

      <div className={styles.decisionActions}>
        <button
          className={styles.secondaryButton}
          type="button"
          onClick={onUseOriginal}
          disabled={isProcessing}
        >
          そのまま{isLastImage ? "分析する" : "次へ"}
        </button>
        <button
          className={styles.primaryButton}
          type="button"
          onClick={handleApplyCrop}
          disabled={isProcessing}
        >
          {isProcessing
            ? "切り抜き中…"
            : `切り抜いて${isLastImage ? "分析する" : "次へ"}`}
        </button>
      </div>

      <button
        className={styles.backButton}
        type="button"
        onClick={onBack}
        disabled={isProcessing}
      >
        画像選択へ戻る
      </button>
    </section>
  );
}
