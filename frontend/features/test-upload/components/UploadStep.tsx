import type { ChangeEvent } from "react";
import Image from "next/image";

import {
  IMAGE_INPUT_ACCEPT,
  MAX_IMAGE_SIZE_BYTES,
  MAX_TOTAL_IMAGE_SIZE_BYTES,
  MAX_UPLOAD_IMAGES,
} from "../constants";
import type { SelectedTestImage } from "../types";
import styles from "./UploadStep.module.css";

type UploadStepProps = {
  images: SelectedTestImage[];
  errorMessage: string | null;
  onAdd: (files: File[]) => Promise<void>;
  onRemove: (id: string) => void;
  onReplace: (id: string, file: File) => Promise<void>;
  onContinue: () => void;
};

function toMegabytes(bytes: number): number {
  return bytes / 1024 / 1024;
}

export function UploadStep({
  images,
  errorMessage,
  onAdd,
  onRemove,
  onReplace,
  onContinue,
}: UploadStepProps) {
  const handleAdd = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    event.target.value = "";

    if (files.length > 0) {
      await onAdd(files);
    }
  };

  const handleReplace =
    (id: string) => async (event: ChangeEvent<HTMLInputElement>) => {
      const [file] = Array.from(event.target.files ?? []);
      event.target.value = "";

      if (file) {
        await onReplace(id, file);
      }
    };

  return (
    <section className={styles.card} aria-labelledby="upload-heading">
      <div className={styles.headingGroup}>
        <p className={styles.step}>STEP 1/2</p>
        <h1 id="upload-heading">テスト画像をアップロード</h1>
      </div>

      <div className={styles.guidance}>
        <Image
          className={styles.mascot}
          src="/nobishiro_smile.png"
          alt=""
          width={56}
          height={56}
          aria-hidden="true"
        />
        <p>問題番号・問題文・解答・採点結果が読めるように撮影してください。</p>
      </div>

      <div className={styles.previewSection}>
        <h2 aria-live="polite">
          選んだ画像 {images.length}/{MAX_UPLOAD_IMAGES}
        </h2>

        {images.length === 0 ? (
          <p className={styles.emptyPreview}>ここに並びます</p>
        ) : (
          <ul className={styles.previewList}>
            {images.map((image, index) => (
              <li key={image.id} className={styles.previewItem}>
                {/* Blob URLのプレビューのため、最適化対象外のimgを使用する。 */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={image.previewUrl} alt={`テスト画像${index + 1}`} />
                <p className={styles.previewLabel}>画像 {index + 1}</p>
                {image.isCropped && (
                  <span className={styles.croppedLabel}>トリミング済み</span>
                )}
                <div className={styles.previewActions}>
                  <label>
                    差し替え
                    <input
                      className={styles.visuallyHidden}
                      type="file"
                      accept={IMAGE_INPUT_ACCEPT}
                      onChange={handleReplace(image.id)}
                    />
                  </label>
                  <button type="button" onClick={() => onRemove(image.id)}>
                    削除
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className={styles.actions}>
        <label className={styles.primaryAction}>
          カメラで撮影
          <input
            className={styles.visuallyHidden}
            type="file"
            accept={IMAGE_INPUT_ACCEPT}
            capture="environment"
            onChange={handleAdd}
          />
        </label>
        <label className={styles.secondaryAction}>
          画像を選ぶ
          <input
            className={styles.visuallyHidden}
            type="file"
            accept={IMAGE_INPUT_ACCEPT}
            multiple
            onChange={handleAdd}
          />
        </label>
      </div>

      <p className={styles.limitText}>
        JPEG・JPG・PNG／最大{MAX_UPLOAD_IMAGES}枚／1枚
        {toMegabytes(MAX_IMAGE_SIZE_BYTES)}MB、合計
        {toMegabytes(MAX_TOTAL_IMAGE_SIZE_BYTES)}MB
      </p>

      {errorMessage && (
        <p className={styles.error} role="alert">
          {errorMessage}
        </p>
      )}

      <div className={styles.continueBar}>
        <button
          className={styles.continueButton}
          type="button"
          onClick={onContinue}
          disabled={images.length === 0}
        >
          トリミングへ進む
        </button>
      </div>
    </section>
  );
}
