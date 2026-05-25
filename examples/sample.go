// Package main は自然言語コンパイラのサンプルです（Go 版）。
// TypeScript 版・Python 版と同一ロジックを実装し、Universal IR の多言語対応を実証します。
package main

import (
	"errors"
	"fmt"
)

// MAX_POINTS は最大付与ポイント数
const MAX_POINTS = 1000

// calculateUserBenefit はユーザーの特典ポイントを計算する
func calculateUserBenefit(user User) (BenefitResult, error) {
	// アクティブユーザーのみ処理する
	if user.Status != "ACTIVE" {
		return BenefitResult{}, errors.New("エラー: 無効なユーザーです")
	}
	totalAmount := 0
	for _, history := range user.PurchaseHistory {
		totalAmount += history.Price
	}
	// ランクに応じてポイントを付与
	if totalAmount >= 100000 && user.Rank == "Gold" {
		return BenefitResult{Points: 1000, Message: "プレミアム特典付与"}, nil
	} else if totalAmount >= 50000 {
		return BenefitResult{Points: 500, Message: "シルバー特典付与"}, nil
	} else {
		return BenefitResult{Points: 100, Message: "通常特典付与"}, nil
	}
}

// printResult は計算結果を標準出力に表示する
func printResult(result BenefitResult) {
	fmt.Printf("ポイント: %d\n", result.Points)
	fmt.Printf("メッセージ: %s\n", result.Message)
}

// countInRange は指定範囲内の件数をカウントする（C スタイル for のサンプル）
func countInRange(values []int, threshold int) int {
	count := 0
	for i := 0; i < len(values); i++ {
		if values[i] > threshold {
			count += 1
		}
	}
	return count
}
