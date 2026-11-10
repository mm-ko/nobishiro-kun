"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/Button";
import { createCheckoutSession, PaymentRequestError } from "@/lib/api/payment";
import styles from "./PlanGuide.module.css";

// UI-008 有料案内・プラン確認。金額と月額プランであることを、決済の前に明示する
export function PlanGuide() {
  const router = useRouter();
  const isSubmittingRef = useRef(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function handleSubscribe() {
    if (isSubmittingRef.current) {
      return;
    }

    isSubmittingRef.current = true;
    setErrorMessage(null);

    // クリックと同時に空タブを開き、API応答後のwindow.openがブロックされるのを防ぐ。
    const checkoutTab = window.open("about:blank", "_blank");
    if (!checkoutTab) {
      isSubmittingRef.current = false;
      setErrorMessage(
        "決済画面を開けませんでした。ブラウザのポップアップを許可して、もう一度お試しください。",
      );
      return;
    }

    checkoutTab.opener = null;
    setIsSubmitting(true);

    try {
      const response = await createCheckoutSession();
      checkoutTab.location.replace(response.checkout_url);
    } catch (error) {
      checkoutTab.close();
      if (
        error instanceof PaymentRequestError &&
        error.code === "ALREADY_SUBSCRIBED"
      ) {
        router.push("/plan/result?status=success");
      } else {
        setErrorMessage(
          "決済画面を開けませんでした。時間をおいてもう一度お試しください。",
        );
      }
    } finally {
      isSubmittingRef.current = false;
      setIsSubmitting(false);
    }
  }

  function handleCancel() {
    router.push("/home");
  }

  return (
    <main className={styles.page}>
      <h1 className={styles.title}>ご利用プラン</h1>
      <div className={styles.plan}>
        <p className={styles.text}>月2回まで無料</p>
        <p className={styles.text}>3回目以降は月額300円</p>
        <p className={styles.text}>月10回まで（無料分を含む）</p>
      </div>
      {errorMessage && (
        <p className={styles.error} role="alert">
          {errorMessage}
        </p>
      )}
      <div className={styles.actions}>
        <Button onClick={handleSubscribe} disabled={isSubmitting}>
          {isSubmitting ? "決済画面を開いています" : "月額300円で利用する"}
        </Button>
        <Button
          variant="secondary"
          onClick={handleCancel}
          disabled={isSubmitting}
        >
          今回はやめる
        </Button>
      </div>
    </main>
  );
}
