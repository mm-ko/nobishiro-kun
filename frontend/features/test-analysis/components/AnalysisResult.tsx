"use client";

import { useRouter } from "next/navigation";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { useAuth } from "@/features/auth/context/AuthContext";
import { useAnalysisResult } from "@/features/test-analysis/context/AnalysisResultContext";
import {
  isActionSentence,
  splitCommentBody,
  splitFormula,
} from "@/features/test-analysis/utils/commentBody";
import styles from "./AnalysisResult.module.css";

type AnalysisResultProps = {
  homeHref?: string;
};

type CommentCardsProps = {
  title: string;
  body: string;
};

// AIコメントを「タイトル＋労いの1文」と「残りの文」の2つのカードに分けて表示する（Issue #134）
// AIの文章はHTMLとして差し込まず、分けた文をReactの部品で包む
function CommentCards({ title, body }: CommentCardsProps) {
  const { greeting, sentences } = splitCommentBody(body);

  return (
    <div className={styles.commentCards}>
      <Card>
        <h2 className={styles.commentTitle}>
          <span className={styles.titleMarker}>{title}</span>
        </h2>
        {greeting && <p className={styles.greeting}>{greeting}</p>}
      </Card>

      {sentences.length > 0 && (
        <Card>
          <div className={styles.commentBody}>
            {sentences.map((sentence, index) => {
              const parts = splitFormula(sentence).map((part, partIndex) =>
                part.isFormula ? (
                  <strong key={partIndex} className={styles.formula}>
                    {part.text}
                  </strong>
                ) : (
                  part.text
                ),
              );

              return (
                <p key={index} className={styles.sentence}>
                  {isActionSentence(sentence) ? (
                    <strong className={styles.actionMarker}>{parts}</strong>
                  ) : (
                    parts
                  )}
                </p>
              );
            })}
          </div>
        </Card>
      )}
    </div>
  );
}

export function AnalysisResult({ homeHref }: AnalysisResultProps) {
  const router = useRouter();
  const { logout } = useAuth();
  const { analysisResult, clearAnalysisResult } = useAnalysisResult();

  function handleHome() {
    if (homeHref) {
      clearAnalysisResult();
      router.push(homeHref);
    }
  }

  async function handleLogout() {
    try {
      await logout();
      clearAnalysisResult();
      router.replace("/login");
    } catch {
      // Firebase上でログアウトできなかった場合は、認証済み画面に留める。
    }
  }

  return (
    <main className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>
          <span className={styles.pageMarker}>分析結果</span>
        </h1>
        <div className={styles.logout}>
          <Button variant="secondary" onClick={handleLogout}>
            ログアウト
          </Button>
        </div>
      </header>

      {analysisResult === null ? (
        <Card title="分析結果を表示できません">
          <p>
            分析結果がありません。ホームへ戻り、テスト画像の
            アップロードからやり直してください。
          </p>
        </Card>
      ) : analysisResult.status === "unsupported" ? (
        <Card title="分析対象外">
          <p>
            このテストの単元は
            <br />
            分析対象外のため、
            <br />
            分析を終了します。
          </p>
          <p>利用回数は消費されません。</p>
        </Card>
      ) : analysisResult.status === "unit_undetermined" ? (
        <Card title="単元を特定できませんでした">
          <p>
            このテストの単元を
            <br />
            特定できなかったため、
            <br />
            分析を終了します。
          </p>
          <p>利用回数は消費されません。</p>
        </Card>
      ) : (
        <>
          <div className={styles.character}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              className={styles.characterImage}
              src="/nobishiro_think.png"
              alt="のびしろくん"
              width={180}
              height={180}
            />
          </div>

          <CommentCards
            title={analysisResult.comment_title}
            body={analysisResult.comment_body}
          />
        </>
      )}

      <Button disabled={!homeHref} onClick={handleHome}>
        ホームへ戻る
      </Button>
    </main>
  );
}
