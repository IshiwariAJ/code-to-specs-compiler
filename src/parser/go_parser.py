"""
フロントエンド（Parser Layer）: Go ソースコード → tree-sitter AST

責務: Go ソースコード文字列を受け取り、tree-sitter でパースして
      ルートノードを返す。構文解析のみを担当し、意味解析は行わない。

公開インターフェース:
    parse_go_source(source_code: str) -> Node

設計方針:
- tree-sitter-go は lazy import（未インストール環境でのインポートエラーを防ぐ）
"""
from __future__ import annotations

from tree_sitter import Node


def parse_go_source(source_code: str) -> Node:
    """
    Go ソースコード文字列を tree-sitter でパースし、AST のルートノードを返す。

    tree-sitter-go パッケージは呼び出し時に初めてインポートする。
    インストールされていない場合は ImportError が発生する。

    Args:
        source_code: Go ソースコード（UTF-8 文字列）

    Returns:
        tree-sitter の source_file ルートノード
    """
    import tree_sitter_go
    from tree_sitter import Language, Parser

    language = Language(tree_sitter_go.language())
    parser = Parser(language)
    tree = parser.parse(source_code.encode("utf-8"))
    return tree.root_node
