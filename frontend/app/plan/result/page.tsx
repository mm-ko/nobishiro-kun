import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { RequireAuth } from "@/features/auth/components/RequireAuth";
import { PaymentResult } from "@/features/plan/components/PaymentResult";
import { isPaymentStatus } from "@/features/plan/paymentStatus";

export const metadata: Metadata = {
  title: "決済結果 | のびしろくん",
};

// UI-009 決済結果。状態は URL の ?status=success|failure|cancel で受け取る
export default async function PlanResultPage(props: PageProps<"/plan/result">) {
  const { status } = await props.searchParams;

  // 想定外の値は UI-008 へ戻す。履歴を置き換えて移動するので、「戻る」でこの画面に戻らない
  if (!isPaymentStatus(status)) {
    redirect("/plan");
  }

  return (
    <RequireAuth>
      <PaymentResult status={status} />
    </RequireAuth>
  );
}
