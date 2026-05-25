"""
パイプライン結合: フロントエンド → ミドルウェア → バックエンドを接続する

責務: 言語に応じて適切なパーサーと LanguageProfile を選択し、
     3層を順に呼び出してソースコードから仕様書Markdownを生成する。

設計方針（構造化プログラミング原則）:
- この関数はデータを変換するだけ（副作用なし）
- 各層の実装詳細を隠蔽し、呼び出し順序だけを定義する
- 新言語追加は select_language_config() への1行追加のみで済む
"""
from tree_sitter import Node

from src.ir.mapper import map_source_to_module_spec
from src.ir.profiles import GO_PROFILE, PYTHON_PROFILE, TYPESCRIPT_PROFILE, LanguageProfile
from src.parser.go_parser import parse_go_source
from src.parser.python_parser import parse_python_source
from src.parser.ts_parser import parse_typescript_source
from src.renderer.markdown import render_module_spec


# ---------------------------------------------------------------------------
# 言語設定の選択: 拡張子 → (パーサー関数, LanguageProfile) のペアを返す
# ---------------------------------------------------------------------------

# サポートする言語の拡張子と設定のマッピング
# 新言語を追加する際はここに1エントリを追加するだけでよい
_LANGUAGE_CONFIGS: dict[str, tuple] = {
    ".ts":  (parse_typescript_source, TYPESCRIPT_PROFILE),
    ".tsx": (parse_typescript_source, TYPESCRIPT_PROFILE),
    ".py":  (parse_python_source,     PYTHON_PROFILE),
    ".go":  (parse_go_source,         GO_PROFILE),
}

_DEFAULT_EXTENSION = ".ts"


def get_supported_extensions() -> frozenset[str]:
    """現在サポートしている拡張子の集合を返す。"""
    return frozenset(_LANGUAGE_CONFIGS.keys())


def select_language_config(extension: str) -> tuple:
    """
    ファイル拡張子に対応する (パーサー関数, LanguageProfile) ペアを返す。

    Args:
        extension: ファイル拡張子（例: ".ts", ".py"）

    Returns:
        (parse_func, profile) のタプル。
        未知の拡張子はデフォルト（TypeScript）を返す。
    """
    return _LANGUAGE_CONFIGS.get(extension, _LANGUAGE_CONFIGS[_DEFAULT_EXTENSION])


# ---------------------------------------------------------------------------
# メインパイプライン
# ---------------------------------------------------------------------------


def compile_to_spec(source_code: str, module_name: str, extension: str = ".ts") -> str:
    """
    ソースコードを構造化Markdown仕様書に変換する。

    パイプライン:
        source_code (str)
            ↓ parse_func（拡張子で自動選択）  【フロントエンド】
        AST root Node
            ↓ map_source_to_module_spec        【ミドルウェア】
        ModuleSpec IR
            ↓ render_module_spec               【バックエンド】
        Markdown str

    Args:
        source_code: ソースコード文字列
        module_name: モジュール名（通常はファイル名のステム）
        extension:   ファイル拡張子（例: ".ts", ".py"）

    Returns:
        Markdown 形式の仕様書文字列
    """
    parse_func, profile = select_language_config(extension)
    root_node: Node = parse_func(source_code)
    module_spec = map_source_to_module_spec(root_node, module_name, profile)
    return render_module_spec(module_spec)
