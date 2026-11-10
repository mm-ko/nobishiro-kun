import type { Metadata } from "next";
import { RequireAuth } from "@/features/auth/components/RequireAuth";
import { PlanGuide } from "@/features/plan/components/PlanGuide";

export const metadata: Metadata = {
  title: "有料案内・プラン確認 | のびしろくん",
};

// UI-008 有料案内・プラン確認
export default function PlanPage() {
  return (
    <RequireAuth>
      <PlanGuide />
    </RequireAuth>
  );
}
