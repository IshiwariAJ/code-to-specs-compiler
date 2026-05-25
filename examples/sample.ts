// ユーザー特典計算モジュール（設計書のサンプルコードを TypeScript で実装したもの）

// モジュール定数（ModuleVariableSpec のサンプル）
const MAX_POINTS = 1000;
const PREMIUM_THRESHOLD = 100000;

// 型定義（TypeDefinitionSpec のサンプル）
type UserStatus = "ACTIVE" | "INACTIVE" | "BANNED";

interface User {
  status: UserStatus;
  rank: string;
  purchaseHistory: { price: number }[];
}

interface BenefitResult {
  points: number;
  message: string;
}

/**
 * ユーザーの購入履歴からポイント特典を計算して返す
 */
function calculateUserBenefit(user: User): BenefitResult {
  // ガード句: 無効なユーザーは即座に弾く
  if (user.status !== "ACTIVE") {
    throw new Error("エラー: 無効なユーザーです");
  }

  // 購入履歴を合計する
  let totalAmount = 0;
  for (const history of user.purchaseHistory) {
    totalAmount += history.price;
  }

  // 合計金額とランクに応じて特典を決定する
  if (totalAmount >= PREMIUM_THRESHOLD && user.rank === "Gold") {
    return { points: MAX_POINTS, message: "プレミアム特典付与" };
  } else if (totalAmount >= 50000) {
    return { points: 500, message: "シルバー特典付与" };
  } else {
    return { points: 100, message: "通常特典付与" };
  }
}

function validateScore(score: number): string {
  // ガード句: スコアが範囲外なら即時エラー
  if (score < 0 || score > 100) {
    throw new RangeError("スコアは0〜100の範囲で指定してください");
  }

  if (score >= 90) {
    return "S";
  } else if (score >= 80) {
    return "A";
  } else if (score >= 70) {
    return "B";
  } else {
    return "C以下";
  }
}

function sumArray(numbers: number[]): number {
  // ガード句: 空配列は0を返す
  if (numbers.length === 0) {
    return 0;
  }

  let total = 0;
  for (let i = 0; i < numbers.length; i++) {
    total += numbers[i];
  }
  return total;
}
