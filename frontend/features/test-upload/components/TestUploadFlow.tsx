"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { AnalysisWaiting } from "@/components/AnalysisWaiting";
import { useAnalysisResult } from "@/features/test-analysis/context/AnalysisResultContext";
import { withAnalysisTimeout } from "@/lib/analysisWaiting";
import {
  getStageAErrorMessage,
  getStageBErrorMessage,
  shouldGoToPlanAfterAnalysisError,
  shouldReturnHomeAfterStageAError,
  shouldReturnHomeAfterStageBError,
  startStageA,
  submitStageB,
} from "@/lib/api/analysis";
import type { StageAResponse, StageBRequest } from "@/types/api";

import {
  STAGE_A_WAITING_MESSAGES,
  STAGE_B_WAITING_MESSAGES,
} from "../constants";
import type { SelectedTestImage } from "../types";
import { validateImageFiles } from "../utils/imageValidation";
import { CropStep } from "./CropStep";
import { ReviewStep } from "./ReviewStep";
import styles from "./TestUploadFlow.module.css";
import { UploadStep } from "./UploadStep";

type FlowStep =
  | "upload"
  | "crop"
  | "loading"
  | "review"
  | "error"
  | "stage-b-loading"
  | "stage-b-error";

function createSelectedImage(file: File, isCropped = false): SelectedTestImage {
  return {
    id: crypto.randomUUID(),
    file,
    previewUrl: URL.createObjectURL(file),
    isCropped,
  };
}

function revokePreviews(images: SelectedTestImage[]) {
  images.forEach((image) => URL.revokeObjectURL(image.previewUrl));
}

export function TestUploadFlow() {
  const router = useRouter();
  const { clearAnalysisResult, setAnalysisResult } = useAnalysisResult();
  const [step, setStep] = useState<FlowStep>("upload");
  const [images, setImages] = useState<SelectedTestImage[]>([]);
  const [cropIndex, setCropIndex] = useState(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSubmittingStageB, setIsSubmittingStageB] = useState(false);
  // 対象外・判定困難（結果画面 #34 が対応するまで）と、分析を続けられないエラー（Stage A・Stage B）のとき true
  const [shouldReturnHome, setShouldReturnHome] = useState(false);
  const [result, setResult] = useState<StageAResponse | null>(null);
  const [pendingStageBRequest, setPendingStageBRequest] =
    useState<StageBRequest | null>(null);
  const imagesRef = useRef<SelectedTestImage[]>([]);
  const allowNavigationRef = useRef(false);
  const isSubmittingStageBRef = useRef(false);
  const stageAIdempotencyKeyRef = useRef<string | null>(null);
  const stageBIdempotencyKeyRef = useRef<string | null>(null);

  useEffect(() => {
    imagesRef.current = images;
  }, [images]);

  useEffect(() => {
    clearAnalysisResult();
  }, [clearAnalysisResult]);

  useEffect(() => {
    return () => {
      revokePreviews(imagesRef.current);
    };
  }, []);

  useEffect(() => {
    if (images.length === 0 && result === null) {
      return;
    }

    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      if (allowNavigationRef.current) {
        return;
      }

      event.preventDefault();
      event.returnValue = "";
    };

    window.addEventListener("beforeunload", handleBeforeUnload);

    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
    };
  }, [images.length, result]);

  const handleAdd = async (files: File[]) => {
    const validationError = await validateImageFiles(
      files,
      images.map((image) => image.file),
    );

    if (validationError) {
      setErrorMessage(validationError);
      return;
    }

    setImages((currentImages) => [
      ...currentImages,
      ...files.map((file) => createSelectedImage(file)),
    ]);
    setErrorMessage(null);
  };

  const handleRemove = (id: string) => {
    const imageToRemove = images.find((image) => image.id === id);
    if (imageToRemove) {
      URL.revokeObjectURL(imageToRemove.previewUrl);
    }

    setImages((currentImages) =>
      currentImages.filter((image) => image.id !== id),
    );
    setErrorMessage(null);
  };

  const handleReplace = async (id: string, file: File) => {
    const otherFiles = images
      .filter((image) => image.id !== id)
      .map((image) => image.file);
    const validationError = await validateImageFiles([file], otherFiles);

    if (validationError) {
      setErrorMessage(validationError);
      return;
    }

    const imageToReplace = images.find((image) => image.id === id);
    if (!imageToReplace) {
      return;
    }

    URL.revokeObjectURL(imageToReplace.previewUrl);
    setImages((currentImages) =>
      currentImages.map((image) =>
        image.id === id ? createSelectedImage(file) : image,
      ),
    );
    setErrorMessage(null);
  };

  const startAnalysis = async (targetImages: SelectedTestImage[]) => {
    setStep("loading");
    setErrorMessage(null);
    setShouldReturnHome(false);

    try {
      const idempotencyKey =
        stageAIdempotencyKeyRef.current ?? crypto.randomUUID();
      stageAIdempotencyKeyRef.current = idempotencyKey;
      const controller = new AbortController();

      const response = await withAnalysisTimeout(
        startStageA(
          targetImages.map((image) => image.file),
          { idempotencyKey, signal: controller.signal },
        ),
        { onTimeout: () => controller.abort() },
      );

      stageAIdempotencyKeyRef.current = null;
      revokePreviews(targetImages);
      setImages([]);
      setResult(response);
      setStep("review");
    } catch (error) {
      // 確認中のデータは消えるが、まれなケースなので MVP ではそのまま移動する
      if (shouldGoToPlanAfterAnalysisError(error)) {
        allowNavigationRef.current = true;
        router.replace("/plan");
        return;
      }

      setErrorMessage(getStageAErrorMessage(error));
      setShouldReturnHome(shouldReturnHomeAfterStageAError(error));
      setStep("error");
    }
  };

  const advanceFromCrop = async (
    croppedFile: File | null,
  ): Promise<string | null> => {
    const currentImage = images[cropIndex];
    if (!currentImage) {
      return "画像が見つかりません。画像選択へ戻ってやり直してください。";
    }

    let nextImages = images;

    if (croppedFile) {
      const otherFiles = images
        .filter((_, index) => index !== cropIndex)
        .map((image) => image.file);
      const validationError = await validateImageFiles(
        [croppedFile],
        otherFiles,
      );

      if (validationError) {
        return validationError;
      }

      const replacement = createSelectedImage(croppedFile, true);
      nextImages = images.map((image, index) =>
        index === cropIndex ? replacement : image,
      );
      URL.revokeObjectURL(currentImage.previewUrl);
      setImages(nextImages);
    }

    if (cropIndex < nextImages.length - 1) {
      setCropIndex((currentIndex) => currentIndex + 1);
      return null;
    }

    await startAnalysis(nextImages);
    return null;
  };

  const currentCropImage = images[cropIndex];

  const submitConfirmedResult = async (request: StageBRequest) => {
    if (!result || isSubmittingStageBRef.current) return;

    isSubmittingStageBRef.current = true;
    setIsSubmittingStageB(true);
    setErrorMessage(null);
    setShouldReturnHome(false);
    setStep("stage-b-loading");

    try {
      const idempotencyKey =
        stageBIdempotencyKeyRef.current ?? crypto.randomUUID();
      stageBIdempotencyKeyRef.current = idempotencyKey;
      const controller = new AbortController();

      const analysisResult = await withAnalysisTimeout(
        submitStageB(result.analysis_request_id, request, {
          idempotencyKey,
          signal: controller.signal,
        }),
        { onTimeout: () => controller.abort() },
      );

      stageBIdempotencyKeyRef.current = null;
      setAnalysisResult(analysisResult);
      allowNavigationRef.current = true;
      router.push("/result");
    } catch (error) {
      // 確認中のデータは消えるが、まれなケースなので MVP ではそのまま移動する
      if (shouldGoToPlanAfterAnalysisError(error)) {
        allowNavigationRef.current = true;
        router.replace("/plan");
        return;
      }

      setErrorMessage(getStageBErrorMessage(error));
      setShouldReturnHome(shouldReturnHomeAfterStageBError(error));
      isSubmittingStageBRef.current = false;
      setIsSubmittingStageB(false);
      setStep("stage-b-error");
    }
  };

  return (
    <main className={styles.page}>
      {step === "upload" && (
        <UploadStep
          images={images}
          errorMessage={errorMessage}
          onAdd={handleAdd}
          onRemove={handleRemove}
          onReplace={handleReplace}
          onContinue={() => {
            setCropIndex(0);
            setErrorMessage(null);
            setStep("crop");
          }}
        />
      )}

      {step === "crop" && currentCropImage && (
        <CropStep
          key={currentCropImage.id}
          image={currentCropImage}
          imageIndex={cropIndex}
          totalImages={images.length}
          onApplyCrop={(file) => advanceFromCrop(file)}
          onUseOriginal={() => void advanceFromCrop(null)}
          onBack={() => {
            setCropIndex(0);
            setErrorMessage(null);
            setStep("upload");
          }}
        />
      )}

      {step === "loading" && (
        <AnalysisWaiting
          title="内容を確認しています"
          messages={STAGE_A_WAITING_MESSAGES}
        />
      )}

      {result &&
        (step === "review" ||
          step === "stage-b-loading" ||
          step === "stage-b-error") && (
          <div hidden={step !== "review"}>
            <ReviewStep
              key={result.analysis_request_id}
              result={result}
              isSubmitting={isSubmittingStageB}
              onComplete={async (request) => {
                setPendingStageBRequest(request);
                await submitConfirmedResult(request);
              }}
            />
          </div>
        )}

      {step === "stage-b-loading" && (
        <AnalysisWaiting
          title="伸びしろを分析しています"
          messages={STAGE_B_WAITING_MESSAGES}
        />
      )}

      {step === "stage-b-error" && (
        <section className={styles.statusCard} role="alert">
          <span className={styles.errorIcon} aria-hidden="true">
            !
          </span>
          <h1>分析を完了できませんでした</h1>
          <p>{errorMessage}</p>
          {shouldReturnHome ? (
            <div className={styles.statusActions}>
              <button
                type="button"
                onClick={() => {
                  allowNavigationRef.current = true;
                  router.push("/home");
                }}
              >
                ホームへ戻る
              </button>
            </div>
          ) : (
            <div className={styles.statusActions}>
              <button
                type="button"
                disabled={!pendingStageBRequest}
                onClick={() => {
                  if (pendingStageBRequest) {
                    void submitConfirmedResult(pendingStageBRequest);
                  }
                }}
              >
                もう一度試す
              </button>
              <button
                className={styles.secondaryButton}
                type="button"
                onClick={() => {
                  stageBIdempotencyKeyRef.current = null;
                  setPendingStageBRequest(null);
                  setErrorMessage(null);
                  setStep("review");
                }}
              >
                確認画面へ戻る
              </button>
            </div>
          )}
        </section>
      )}

      {step === "error" && (
        <section className={styles.statusCard} role="alert">
          <span className={styles.errorIcon} aria-hidden="true">
            !
          </span>
          <h1>分析を完了できませんでした</h1>
          <p>{errorMessage}</p>
          {shouldReturnHome ? (
            <div className={styles.statusActions}>
              <button
                type="button"
                onClick={() => {
                  allowNavigationRef.current = true;
                  router.push("/home");
                }}
              >
                ホームへ戻る
              </button>
            </div>
          ) : (
            <div className={styles.statusActions}>
              <button type="button" onClick={() => void startAnalysis(images)}>
                もう一度試す
              </button>
              <button
                className={styles.secondaryButton}
                type="button"
                onClick={() => {
                  stageAIdempotencyKeyRef.current = null;
                  setErrorMessage(null);
                  setStep("crop");
                }}
              >
                トリミングへ戻る
              </button>
            </div>
          )}
        </section>
      )}
    </main>
  );
}
