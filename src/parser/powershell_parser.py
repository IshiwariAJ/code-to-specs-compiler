"""
フロントエンド（Parser Layer）: PowerShell ソースコード → AST

責務: tree-sitter を用いて PowerShell ソースコードを解析し、
      ルートのASTノードを返すことのみ。

設計方針（構造化プログラミング原則）:
- 副作用なし（ファイルI/Oや状態保持はしない）
- 入力: ソースコード文字列 / 出力: ASTのルートノード
- tree-sitter-powershell は lazy import（未インストール環境でのインポートエラーを防ぐ）
"""
from tree_sitter import Node


def parse_powershell_source(source_code: str) -> Node:
    """
    PowerShell ソースコード文字列を解析し、ASTのルートノードを返す。

    tree-sitter-powershell パッケージは呼び出し時に初めてインポートする。
    インストールされていない場合は ImportError が発生する。

    Args:
        source_code: PowerShell のソースコード文字列（.ps1 / .psm1）

    Returns:
        tree-sitter の AST ルートノード（program ノード）
    """
    import tree_sitter_powershell as tspwsh
    from tree_sitter import Language, Parser

    language = Language(tspwsh.language())
    parser = Parser(language)
    tree = parser.parse(source_code.encode("utf-8"))
    return tree.root_node
