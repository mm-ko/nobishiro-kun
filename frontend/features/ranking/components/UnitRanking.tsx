"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/Card";
import { Loading } from "@/components/Loading";
import { getUnitRankings } from "@/lib/api/records";
import type { UnitRankingItem } from "@/types/api";
import styles from "./UnitRanking.module.css";

// 苦手単元ランキング（UI-002）。順位と並び順は API の結果をそのまま使い、画面では計算しない
export function UnitRanking() {
  const [rankings, setRankings] = useState<UnitRankingItem[] | null>(null);
  const [hasError, setHasError] = useState(false);

  useEffect(() => {
    let isActive = true;

    async function loadRankings() {
      try {
        const response = await getUnitRankings();
        if (isActive) {
          setRankings(response.items);
        }
      } catch {
        if (isActive) {
          setHasError(true);
        }
      }
    }

    void loadRankings();

    return () => {
      isActive = false;
    };
  }, []);

  function renderContent() {
    if (hasError) {
      return (
        <p className={styles.error} role="alert">
          ランキングを読み込めませんでした。時間をおいてもう一度お試しください。
        </p>
      );
    }

    if (rankings === null) {
      return <Loading message="ランキングを読み込んでいます" />;
    }

    if (rankings.length === 0) {
      return (
        <p className={styles.empty}>
          まだ記録がありません。テストを分析すると、ここに苦手な単元が表示されます
        </p>
      );
    }

    return (
      <>
        <p className={styles.lead}>ここから復習すると伸びやすい単元です</p>
        <ol className={styles.list}>
          {rankings.map((ranking) => (
            <li key={ranking.unit.code} className={styles.item}>
              <span className={styles.rank}>{ranking.rank}</span>
              <span className={styles.unitName}>{ranking.unit.name}</span>
              <span className={styles.rate}>
                {ranking.average_score_rate.toFixed(1)}%
              </span>
            </li>
          ))}
        </ol>
      </>
    );
  }

  return <Card title="苦手単元ランキング">{renderContent()}</Card>;
}
