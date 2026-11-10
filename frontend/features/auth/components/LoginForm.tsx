"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/features/auth/context/AuthContext";
import { Button } from "@/components/Button";
import { TextField } from "@/components/TextField";
import { Card } from "@/components/Card";
import styles from "./LoginForm.module.css";

type AuthMode = "login" | "register";

export function LoginForm() {
  const router = useRouter();
  const { login, register, isLoading } = useAuth();

  const [mode, setMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const isRegister = mode === "register";

  function changeMode(nextMode: AuthMode) {
    setMode(nextMode);
    setFormError(null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);

    if (!email.trim() || !password) {
      setFormError("メールアドレスとパスワードを入力してください");
      return;
    }

    if (mode === "register" && password.length < 6) {
      setFormError("パスワードは6文字以上で入力してください");
      return;
    }

    try {
      if (isRegister) {
        await register(email.trim(), password);
      } else {
        await login(email.trim(), password);
      }

      router.push("/home");
    } catch {
      setFormError(
        isRegister
          ? "新規登録に失敗しました。もう一度お試しください"
          : "ログインに失敗しました。もう一度お試しください",
      );
    }
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>のびしろくん</h1>
        <p className={styles.lead}>テストを撮ると苦手が見える</p>
      </header>

      <Card title={isRegister ? "新規登録" : "ログイン"}>
        <form onSubmit={handleSubmit} noValidate className={styles.form}>
          <TextField
            id="login-email"
            label="メールアドレス"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />

          <TextField
            id="login-password"
            label="パスワード"
            type="password"
            autoComplete={isRegister ? "new-password" : "current-password"}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            error={formError ?? undefined}
            required
          />

          <Button type="submit" disabled={isLoading}>
            {isLoading ? "処理中..." : isRegister ? "新規登録" : "ログイン"}
          </Button>

          <button
            type="button"
            className={styles.link}
            onClick={() => changeMode(isRegister ? "login" : "register")}
            disabled={isLoading}
          >
            {isRegister ? "ログインはこちら" : "新規登録はこちら"}
          </button>
        </form>
      </Card>
    </div>
  );
}
