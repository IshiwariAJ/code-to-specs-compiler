"""
Java ソースコード → tree-sitter AST ルートノード

依存: tree-sitter-java（オプション）
インストール: pip install tree-sitter-java
"""
from tree_sitter import Node


def parse_java_source(source_code: str) -> Node:
    """
    Java ソースコード文字列を受け取り、tree-sitter の AST ルートノードを返す。

    tree-sitter-java は遅延インポートするため、.java ファイルを処理するときのみ
    パッケージが必要になる。
    """
    import tree_sitter_java  # lazy import: .java 処理時のみロード
    from tree_sitter import Language, Parser

    language = Language(tree_sitter_java.language())
    parser = Parser(language)
    tree = parser.parse(source_code.encode("utf-8"))
    return tree.root_node
