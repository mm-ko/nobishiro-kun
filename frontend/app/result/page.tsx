import { AnalysisResult } from "@/features/test-analysis/components/AnalysisResult";
import { RequireAuth } from "@/features/auth/components/RequireAuth";

export default function ResultPage() {
  return (
    <RequireAuth>
      <AnalysisResult homeHref="/home" />
    </RequireAuth>
  );
}
