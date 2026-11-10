"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/Button";
import { Loading } from "@/components/Loading";
import { getUsage } from "@/lib/api/usage";
import type { UsageBlockedReason } from "@/types/api";
import styles from "./AnalyzeButton.module.css";

// 分析を始めるボタン。利用状況（blocked_reason）で、分析ボタン・有料案内ボタン・
// 月の上限のお知らせのどれか1つだけを出す（#37）
export function AnalyzeButton() {
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(true);
  const [blockedReason, setBlockedReason] = useState<UsageBlockedReason | null>(
    null,
  );

  useEffect(() => {
    let isActive = true;

    async function loadUsage() {
      try {
        const response = await getUsage();
        if (isActive) {
          setBlockedReason(response.blocked_reason);
        }
      } catch {
        // 取得できなくても分析ボタンを出す。使えない場合は、分析を始めるときに BE が止める
      } finally {
        if (isActive) {
          setIsLoading(false);
        }
      }
    }

    void loadUsage();

    return () => {
      isActive = false;
    };
  }, []);

  // モックの「分析済み」の状態を消さないよう、<a href> ではなく router.push で移動する
  function handleAnalyze() {
    router.push("/test-upload");
  }

  function handleShowPlan() {
    router.push("/plan");
  }

  if (isLoading) {
    return <Loading message="読み込んでいます" />;
  }

  // 契約しても今月は分析できないので、押せないお知らせにして UI-008 へは進ませない
  if (blockedReason === "monthly_limit_reached") {
    return (
      <p className={styles.limitNotice} role="status">
        今月の分析回数の上限に達しました。来月1日から、また分析できます。
      </p>
    );
  }

  if (blockedReason === "plan_required") {
    return <Button onClick={handleShowPlan}>3回目以降は有料です</Button>;
  }

  return <Button onClick={handleAnalyze}>テストを分析する</Button>;
}
