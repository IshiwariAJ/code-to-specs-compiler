"""
フロントエンド（Parser Layer）: Go ソースコード → tree-sitter AST

責務: Go ソースコード文字列を受け取り、tree-sitter でパースして
      ルートノードを返す。構文解析のみを担当し、意味解析は行わない。

公開インターフェース:
    parse_go_source(source_code: str) -> Node
"""
from __future__ import annotations

import tree_sitter_go
from tree_sitter import Language, Node, Parser

_GO_LANGUAGE = Language(tree_sitter_go.language())
_GO_PARSER = Parser(_GO_LANGUAGE)


def parse_go_source(source_code: str) -> Node:
    """
    Go ソースコード文字列を tree-sitter でパースし、AST のルートノードを返す。

    Args:
        source_code: Go ソースコード（UTF-8 文字列）

    Returns:
        tree-sitter の source_file ルートノード
    """
    tree = _GO_PARSER.parse(source_code.encode("utf-8"))
    return tree.root_node
