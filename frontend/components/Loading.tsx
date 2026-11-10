import styles from "./Loading.module.css";

type LoadingProps = {
  // 説明文の内容は、使う画面で決めて渡す
  message: string;
};

// 共通の処理中の表示（くるくる回るマーク＋説明文）
export function Loading({ message }: LoadingProps) {
  return (
    <div className={styles.loading} role="status">
      <span className={styles.spinner} aria-hidden="true" />
      <p className={styles.message}>{message}</p>
    </div>
  );
}
