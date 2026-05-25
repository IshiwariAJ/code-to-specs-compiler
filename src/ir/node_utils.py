"""
ASTノードのテキスト抽出・正規化ユーティリティ（言語非依存）

mapper.py と各言語モジュール（src/languages/*.py）の両方から使用される。
循環インポートを防ぐため、このモジュールは tree_sitter と標準ライブラリのみに依存する。
"""
from __future__ import annotations

from tree_sitter import Node


def extract_node_text(node: Node) -> str:
    """ASTノードのソーステキストを UTF-8 文字列として返す。"""
    if node.text is None:
        return ""
    return node.text.decode("utf-8")


def strip_outer_parens(text: str) -> str:
    """条件式の外側の丸括弧を除去して返す。例: '(x > 0)' → 'x > 0'"""
    stripped = text.strip()
    if stripped.startswith("(") and stripped.endswith(")"):
        return stripped[1:-1].strip()
    return stripped


def truncate_text(text: str, max_len: int = 60) -> str:
    """テキストが長い場合は省略記号を付けて切り詰める。

    モジュール変数の値など長くなりうる部分に使用する。
    型定義テキストには使用しないこと（normalize_whitespace を使う）。
    """
    cleaned = text.replace("\n", " ").strip()
    if len(cleaned) > max_len:
        return cleaned[:max_len] + "..."
    return cleaned


def normalize_whitespace(text: str) -> str:
    """改行・連続スペースを単一スペースに正規化する（省略なし）。

    型定義（interface / type alias）のように全文表示が必要な箇所で使用する。
    """
    return " ".join(text.split())
