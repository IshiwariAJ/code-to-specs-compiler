"""
フロントエンド（Parser Layer）: Python ソースコード → AST

責務: tree-sitter を用いて Python ソースコードを解析し、
      ルートのASTノードを返すことのみ。

設計方針（構造化プログラミング原則）:
- 副作用なし（ファイルI/Oや状態保持はしない）
- 入力: ソースコード文字列 / 出力: ASTのルートノード
- ts_parser.py と同一のインターフェース設計（フロントエンドの交換可能性を実証）
- tree-sitter-python は lazy import（未インストール環境でのインポートエラーを防ぐ）
"""
from tree_sitter import Node


def parse_python_source(source_code: str) -> Node:
    """
    Python ソースコード文字列を解析し、ASTのルートノードを返す。

    tree-sitter-python パッケージは呼び出し時に初めてインポートする。
    インストールされていない場合は ImportError が発生する。

    Args:
        source_code: Python のソースコード文字列

    Returns:
        tree-sitter の AST ルートノード（module ノード）
    """
    import tree_sitter_python
    from tree_sitter import Language, Parser

    language = Language(tree_sitter_python.language())
    parser = Parser(language)
    tree = parser.parse(source_code.encode("utf-8"))
    return tree.root_node
