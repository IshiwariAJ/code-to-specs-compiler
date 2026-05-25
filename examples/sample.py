# ユーザー特典計算モジュール（TypeScript 版の sample.ts と意図的に同一ロジック）
# 同じロジックが TypeScript と Python で同一フォーマットの仕様書に変換されることを実証する


def calculate_user_benefit(user):
    # ガード句: 無効なユーザーは即座に弾く
    if user["status"] != "ACTIVE":
        raise ValueError("エラー: 無効なユーザーです")

    # 購入履歴を合計する
    total_amount = 0
    for history in user["purchase_history"]:
        total_amount += history["price"]

    # 合計金額とランクに応じて特典を決定する
    if total_amount >= 100000 and user["rank"] == "Gold":
        return {"points": 1000, "message": "プレミアム特典付与"}
    elif total_amount >= 50000:
        return {"points": 500, "message": "シルバー特典付与"}
    else:
        return {"points": 100, "message": "通常特典付与"}


def validate_score(score):
    # ガード句: スコアが範囲外なら即時エラー
    if score < 0 or score > 100:
        raise ValueError("スコアは0〜100の範囲で指定してください")

    if score >= 90:
        return "S"
    elif score >= 80:
        return "A"
    elif score >= 70:
        return "B"
    else:
        return "C以下"


def sum_array(numbers):
    # ガード句: 空リストは0を返す
    if len(numbers) == 0:
        return 0

    total = 0
    for n in numbers:
        total += n
    return total
