# ユーザー特典計算モジュール（PowerShell 版）
# TypeScript / Python / Go 版と意図的に同一ロジックを実装し、
# Universal IR の多言語対応を実証するサンプルスクリプトです。

function Get-UserBenefit {
    <#
    .SYNOPSIS
    ユーザーの購入履歴からポイント特典を計算して返す
    .DESCRIPTION
    アクティブなユーザーの購入合計金額とランクに応じて
    付与ポイント数とメッセージを返します。
    #>
    param(
        [string]$Status,
        [string]$Rank,
        [object[]]$PurchaseHistory
    )

    # ガード句: 無効なユーザーは即座に弾く
    if ($Status -ne "ACTIVE") {
        throw "エラー: 無効なユーザーです"
    }

    # 購入履歴を合計する
    $totalAmount = 0
    foreach ($history in $PurchaseHistory) {
        $totalAmount += $history.Price
    }

    # ランクと合計金額に応じて特典を決定する
    if ($totalAmount -ge 100000 -and $Rank -eq "Gold") {
        return @{ Points = 1000; Message = "プレミアム特典付与" }
    } elseif ($totalAmount -ge 50000) {
        return @{ Points = 500; Message = "シルバー特典付与" }
    } else {
        return @{ Points = 100; Message = "通常特典付与" }
    }
}


function Test-Score {
    <#
    .SYNOPSIS
    スコアを評価してグレード文字列を返す
    #>
    param(
        [int]$Score
    )

    # ガード句: スコアが範囲外なら即時エラー
    if ($Score -lt 0 -or $Score -gt 100) {
        throw "スコアは0〜100の範囲で指定してください"
    }

    if ($Score -ge 90) {
        return "S"
    } elseif ($Score -ge 80) {
        return "A"
    } elseif ($Score -ge 70) {
        return "B"
    } else {
        return "C以下"
    }
}


function Get-ArraySum {
    <#
    .SYNOPSIS
    数値配列の合計を計算して返す
    #>
    param(
        [int[]]$Numbers
    )

    # ガード句: 空配列は 0 を返す
    if ($Numbers.Count -eq 0) {
        return 0
    }

    $total = 0
    foreach ($n in $Numbers) {
        $total += $n
    }
    return $total
}


function Write-Result {
    <#
    .SYNOPSIS
    特典計算結果を標準出力に表示する
    #>
    param(
        [hashtable]$Result
    )

    Write-Output "ポイント: $($Result.Points)"
    Write-Output "メッセージ: $($Result.Message)"
}
