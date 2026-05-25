"""
フロントエンド（Parser Layer）: TypeScript ソースコード → AST

責務: tree-sitter を用いて TypeScript ソースコードを解析し、
      ルートのASTノードを返すことのみ。

設計方針（構造化プログラミング原則）:
- 副作用なし（ファイルI/Oや状態保持はしない）
- 入力: ソースコード文字列 / 出力: ASTのルートノード
"""
from tree_sitter import Language, Node, Parser
import tree_sitter_typescript as ts_typescript


def _create_typescript_language() -> Language:
    """TypeScript 言語オブジェクトを生成して返す。"""
    return Language(ts_typescript.language_typescript())


def parse_typescript_source(source_code: str) -> Node:
    """
    TypeScript ソースコード文字列を解析し、ASTのルートノードを返す。

    Args:
        source_code: TypeScript のソースコード文字列

    Returns:
        tree-sitter の AST ルートノード（program ノード）
    """
    language = _create_typescript_language()
    parser = Parser(language)
    tree = parser.parse(source_code.encode("utf-8"))
    return tree.root_node
