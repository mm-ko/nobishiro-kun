import type { Metadata } from "next";
import { Noto_Sans_JP, Zen_Maru_Gothic } from "next/font/google";
import "./globals.css";
import styles from "./layout.module.css";
import { AuthProvider } from "@/features/auth/context/AuthContext";
import { AnalysisResultProvider } from "@/features/test-analysis/context/AnalysisResultContext";

// 見出し用（丸ゴシック）
const zenMaruGothic = Zen_Maru_Gothic({
  variable: "--font-zen-maru-gothic",
  weight: "700",
  subsets: ["latin"],
});

// 本文用
const notoSansJp = Noto_Sans_JP({
  variable: "--font-noto-sans-jp",
  weight: ["400", "700"],
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "のびしろくん",
  description: "保護者向け学習サポートアプリ",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="ja"
      className={`${zenMaruGothic.variable} ${notoSansJp.variable}`}
    >
      <body>
        <AuthProvider>
          <AnalysisResultProvider>
            <div className={styles.container}>{children}</div>
          </AnalysisResultProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
