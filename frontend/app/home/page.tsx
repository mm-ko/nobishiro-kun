import type { Metadata } from "next";
import { AnalyzeButton } from "@/features/home/components/AnalyzeButton";
import { LogoutButton } from "@/features/home/components/LogoutButton";
import { LearningHistory } from "@/features/learning-history/components/LearningHistory";
import { UnitRanking } from "@/features/ranking/components/UnitRanking";
import { RequireAuth } from "@/features/auth/components/RequireAuth";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "ホーム | のびしろくん",
};

// UI-002 ホーム。並び順は「分析ボタン → 学習履歴（#36）→ 苦手単元ランキング（#35）」
export default function HomePage() {
  return (
    <RequireAuth>
      <main className={styles.page}>
        <header className={styles.header}>
          <h1 className={styles.title}>のびしろくん</h1>
          <div className={styles.logout}>
            <LogoutButton />
          </div>
        </header>
        <section>
          <p className={styles.lead}>今日も一緒に見てみましょう</p>
          <AnalyzeButton />
        </section>
        <LearningHistory />
        <UnitRanking />
      </main>
    </RequireAuth>
  );
}
