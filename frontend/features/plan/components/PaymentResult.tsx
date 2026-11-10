"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/Button";
import { Loading } from "@/components/Loading";
import type { PaymentStatus } from "@/features/plan/paymentStatus";
import { getCurrentSubscription } from "@/lib/api/payment";
import styles from "./PaymentResult.module.css";

const SUBSCRIPTION_CHECK_INTERVAL_MS = 1000;
const SUBSCRIPTION_CHECK_MAX_ATTEMPTS = 10;

type SubscriptionCheckState = "checking" | "confirmed" | "unconfirmed";

// UI-009 決済結果。成功・失敗・キャンセルは、同じ画面内の表示状態として扱う。
// カード情報や失敗理由の詳細は表示しない（画面設計書）
export function PaymentResult({ status }: { status: PaymentStatus }) {
  const router = useRouter();
  const [checkState, setCheckState] =
    useState<SubscriptionCheckState>("checking");
  const [retryCount, setRetryCount] = useState(0);

  useEffect(() => {
    if (status !== "success") {
      return;
    }

    let isActive = true;
    let timeoutId: ReturnType<typeof setTimeout> | undefined;

    async function checkSubscription(attempt: number) {
      let isSubscribed = false;
      try {
        const subscription = await getCurrentSubscription();
        isSubscribed =
          subscription.is_subscribed && subscription.status === "active";
      } catch {
        // 通信失敗もWebhook未反映と同様に、上限回数までは再試行する。
      }

      if (!isActive) {
        return;
      }

      if (isSubscribed) {
        setCheckState("confirmed");
        return;
      }

      if (attempt >= SUBSCRIPTION_CHECK_MAX_ATTEMPTS) {
        setCheckState("unconfirmed");
        return;
      }

      timeoutId = setTimeout(() => {
        void checkSubscription(attempt + 1);
      }, SUBSCRIPTION_CHECK_INTERVAL_MS);
    }

    void checkSubscription(1);

    return () => {
      isActive = false;
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, [retryCount, status]);

  function handleHome() {
    router.push("/home");
  }

  function handleBackToPlan() {
    router.push("/plan");
  }

  function handleRetry() {
    setCheckState("checking");
    setRetryCount((count) => count + 1);
  }

  if (status === "success") {
    if (checkState === "checking") {
      return (
        <main className={styles.page}>
          <h1 className={styles.title}>決済状況を確認しています</h1>
          <Loading message="反映まで少し時間がかかることがあります" />
        </main>
      );
    }

    if (checkState === "unconfirmed") {
      return (
        <main className={styles.page}>
          <h1 className={styles.title}>決済状況を確認できませんでした</h1>
          <p className={styles.description}>
            決済が完了している場合があります。しばらくしてから、もう一度確認してください。
          </p>
          <div className={styles.actions}>
            <Button onClick={handleRetry}>もう一度確認する</Button>
            <Button variant="secondary" onClick={handleHome}>
              ホームへ戻る
            </Button>
          </div>
        </main>
      );
    }

    return (
      <main className={styles.page}>
        <h1 className={styles.title}>決済が完了しました</h1>
        <div className={styles.actions}>
          <Button onClick={handleHome}>ホームへ戻る</Button>
        </div>
      </main>
    );
  }

  if (status === "failure") {
    return (
      <main className={styles.page}>
        <h1 className={styles.title}>決済を完了できませんでした</h1>
        <div className={styles.actions}>
          <Button onClick={handleBackToPlan}>再試行する</Button>
          <Button variant="secondary" onClick={handleHome}>
            ホームへ戻る
          </Button>
        </div>
      </main>
    );
  }

  return (
    <main className={styles.page}>
      <h1 className={styles.title}>決済をキャンセルしました</h1>
      <div className={styles.actions}>
        <Button onClick={handleBackToPlan}>決済へ戻る</Button>
        <Button variant="secondary" onClick={handleHome}>
          ホームへ戻る
        </Button>
      </div>
    </main>
  );
}
