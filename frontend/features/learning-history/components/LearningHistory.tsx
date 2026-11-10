"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/Card";
import { Loading } from "@/components/Loading";
import { getAnalysisRecords } from "@/lib/api/records";
import type { AnalysisRecordItem } from "@/types/api";
import styles from "./LearningHistory.module.css";

type LoadState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "loaded"; records: AnalysisRecordItem[] };

// recorded_at はUTCで返るため、日本時間の「月/日」に変換して表示する（例：10/1）
const dateFormatter = new Intl.DateTimeFormat("ja-JP", {
  timeZone: "Asia/Tokyo",
  month: "numeric",
  day: "numeric",
});

// 学習履歴の一覧（UI-002 ホーム）。並び順はAPIが返した順（新しい順）のまま表示する
export function LearningHistory() {
  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let isActive = true;

    async function loadRecords() {
      try {
        const response = await getAnalysisRecords();

        if (isActive) {
          setLoadState({ status: "loaded", records: response.items });
        }
      } catch {
        if (isActive) {
          setLoadState({ status: "error" });
        }
      }
    }

    void loadRecords();

    return () => {
      isActive = false;
    };
  }, []);

  return (
    <Card title="学習履歴">
      {loadState.status === "loading" && (
        <Loading message="学習履歴を読み込んでいます。" />
      )}

      {loadState.status === "error" && (
        <p className={styles.message} role="alert">
          学習履歴を読み込めませんでした。時間をおいてもう一度お試しください。
        </p>
      )}

      {loadState.status === "loaded" && loadState.records.length === 0 && (
        <p className={styles.message}>
          まだ記録がありません。テストを分析すると、ここに表示されます。
        </p>
      )}

      {loadState.status === "loaded" && loadState.records.length > 0 && (
        <ul className={styles.list}>
          {loadState.records.map((record) => (
            <li key={record.id} className={styles.item}>
              <time className={styles.date} dateTime={record.recorded_at}>
                {dateFormatter.format(new Date(record.recorded_at))}
              </time>
              <span className={styles.unit}>{record.unit.name}</span>
              <span className={styles.score}>
                {record.score}/{record.max_score}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
