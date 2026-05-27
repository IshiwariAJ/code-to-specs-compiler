// ユーザー特典計算モジュール（Java 版）
// TypeScript / Python / Go / PowerShell 版と意図的に同一ロジックを実装し、
// Universal IR の多言語対応を実証するサンプルクラスです。

import java.util.List;

/**
 * ユーザーの購入履歴からポイント特典を計算するサービスクラス
 */
public class UserBenefitService {

    /**
     * ユーザーの購入履歴からポイント特典を計算して返す
     */
    public static BenefitResult getUserBenefit(String status, String rank, List<Purchase> purchaseHistory) {
        // ガード句: 無効なユーザーは即座に弾く
        if (!status.equals("ACTIVE")) {
            throw new IllegalArgumentException("エラー: 無効なユーザーです");
        }

        // 購入履歴を合計する
        int totalAmount = 0;
        for (Purchase history : purchaseHistory) {
            totalAmount += history.getPrice();
        }

        // ランクと合計金額に応じて特典を決定する
        if (totalAmount >= 100000 && rank.equals("Gold")) {
            return new BenefitResult(1000, "プレミアム特典付与");
        } else if (totalAmount >= 50000) {
            return new BenefitResult(500, "シルバー特典付与");
        } else {
            return new BenefitResult(100, "通常特典付与");
        }
    }

    /**
     * スコアを評価してグレード文字列を返す
     */
    public static String evaluateScore(int score) {
        // ガード句: スコアが範囲外なら即時エラー
        if (score < 0 || score > 100) {
            throw new IllegalArgumentException("スコアは0〜100の範囲で指定してください");
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

    /**
     * 数値リストの合計を計算して返す
     */
    public static int getArraySum(List<Integer> numbers) {
        // ガード句: 空リストは 0 を返す
        if (numbers.isEmpty()) {
            return 0;
        }

        int total = 0;
        for (int n : numbers) {
            total += n;
        }
        return total;
    }

    /**
     * 特典計算結果を標準出力に表示する
     */
    public static void printResult(BenefitResult result) {
        System.out.println("ポイント: " + result.getPoints());
        System.out.println("メッセージ: " + result.getMessage());
    }
}
