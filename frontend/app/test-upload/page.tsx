import type { Metadata } from "next";
import "react-image-crop/dist/ReactCrop.css";

import { TestUploadFlow } from "@/features/test-upload/components/TestUploadFlow";
import { RequireAuth } from "@/features/auth/components/RequireAuth";

export const metadata: Metadata = {
  title: "テスト画像をアップロード | のびしろくん",
};

export default function TestUploadPage() {
  return (
    <RequireAuth>
      <TestUploadFlow />
    </RequireAuth>
  );
}
