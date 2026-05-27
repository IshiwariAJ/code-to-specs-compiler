"""
フロントエンド（Parser Layer）: TypeScript ソースコード → AST

責務: tree-sitter を用いて TypeScript ソースコードを解析し、
      ルートのASTノードを返すことのみ。

設計方針（構造化プログラミング原則）:
- 副作用なし（ファイルI/Oや状態保持はしない）
- 入力: ソースコード文字列 / 出力: ASTのルートノード
- tree-sitter-typescript は lazy import（未インストール環境でのインポートエラーを防ぐ）
"""
from tree_sitter import Node


def parse_typescript_source(source_code: str) -> Node:
    """
    TypeScript ソースコード文字列を解析し、ASTのルートノードを返す。

    tree-sitter-typescript パッケージは呼び出し時に初めてインポートする。
    インストールされていない場合は ImportError が発生する。

    Args:
        source_code: TypeScript のソースコード文字列

    Returns:
        tree-sitter の AST ルートノード（program ノード）
    """
    import tree_sitter_typescript as ts_typescript
    from tree_sitter import Language, Parser

    language = Language(ts_typescript.language_typescript())
    parser = Parser(language)
    tree = parser.parse(source_code.encode("utf-8"))
    return tree.root_node
