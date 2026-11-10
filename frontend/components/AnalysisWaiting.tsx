"use client";

import Image from "next/image";
import { Fragment, useEffect, useState } from "react";

import { ANALYSIS_WAITING_STEP_DELAYS_MS } from "@/lib/analysisWaiting";

import styles from "./AnalysisWaiting.module.css";

type AnalysisWaitingProps = {
  title: string;
  // 時間で切り替える3つの文言。内容は、使う画面で決めて渡す
  messages: readonly [string, string, string];
};

// 分析中の待ち表示（UI-005・UI-006B）。実際の処理の進み具合とは連動せず、時間で進める。
// 3つ目は「進行中」のまま止める。結果が返ったら、使う側ですぐ次の画面へ進む
export function AnalysisWaiting({ title, messages }: AnalysisWaitingProps) {
  const [stepIndex, setStepIndex] = useState(0);

  useEffect(() => {
    const timeoutIds = ANALYSIS_WAITING_STEP_DELAYS_MS.map((delayMs, index) =>
      window.setTimeout(() => setStepIndex(index + 1), delayMs),
    );

    return () => {
      timeoutIds.forEach((timeoutId) => window.clearTimeout(timeoutId));
    };
  }, []);

  function getDotClassName(index: number) {
    if (index < stepIndex) {
      return `${styles.dot} ${styles.dotDone}`;
    }
    if (index === stepIndex) {
      return `${styles.dot} ${styles.dotActive}`;
    }
    return styles.dot;
  }

  return (
    <section className={styles.card} aria-busy="true">
      <h1 className={styles.title}>{title}</h1>
      <Image
        className={styles.character}
        src="/nobishiro_think.png"
        alt=""
        width={512}
        height={512}
        loading="eager"
      />
      <p className={styles.message} aria-live="polite">
        {messages[stepIndex]}
      </p>
      {/* 文言で進み具合を伝えるため、ゲージは読み上げない */}
      <div className={styles.gauge} aria-hidden="true">
        {messages.map((message, index) => (
          <Fragment key={message}>
            {index > 0 && <span className={styles.line} />}
            <span className={getDotClassName(index)} />
          </Fragment>
        ))}
      </div>
      <p className={styles.note}>画面を閉じずに、そのままお待ちください。</p>
    </section>
  );
}
