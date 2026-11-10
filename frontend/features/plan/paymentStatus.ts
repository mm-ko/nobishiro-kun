// UI-009 決済結果の状態。URL の ?status= で受け取る
export type PaymentStatus = "success" | "failure" | "cancel";

export function isPaymentStatus(value: unknown): value is PaymentStatus {
  return value === "success" || value === "failure" || value === "cancel";
}
