"""
パイプライン結合: フロントエンド → ミドルウェア → バックエンドを接続する

責務: 言語に応じて適切な LanguagePlugin を選択し、
     3層を順に呼び出してソースコードから仕様書Markdownを生成する。

設計方針（構造化プログラミング原則）:
- この関数はデータを変換するだけ（副作用なし）
- 各層の実装詳細を隠蔽し、呼び出し順序だけを定義する
- 新言語追加: src/languages/<言語名>.py を置くだけ。このファイルは変更不要
"""
from tree_sitter import Node

from src.ir.mapper import map_source_to_module_spec
from src.languages import LanguagePlugin, discover_plugins
from src.renderer.markdown import render_module_spec

# ---------------------------------------------------------------------------
# 言語プラグインの自動探索
# src/languages/ 内の *.py を自動的に検索し、PLUGIN 定数を持つものを登録する
# ---------------------------------------------------------------------------

_PLUGINS: dict[str, LanguagePlugin] = discover_plugins()

_DEFAULT_EXTENSION = ".ts"


def get_supported_extensions() -> frozenset[str]:
    """現在サポートしている拡張子の集合を返す。"""
    return frozenset(_PLUGINS.keys())


def select_plugin(extension: str) -> LanguagePlugin:
    """
    ファイル拡張子に対応する LanguagePlugin を返す。

    Args:
        extension: ファイル拡張子（例: ".ts", ".py"）

    Returns:
        対応する LanguagePlugin。
        未知の拡張子はデフォルト（TypeScript）を返す。
    """
    return _PLUGINS.get(extension, _PLUGINS[_DEFAULT_EXTENSION])


# ---------------------------------------------------------------------------
# メインパイプライン
# ---------------------------------------------------------------------------


def compile_to_spec(source_code: str, module_name: str, extension: str = ".ts") -> str:
    """
    ソースコードを構造化Markdown仕様書に変換する。

    パイプライン:
        source_code (str)
            ↓ plugin.parse_source（拡張子で自動選択）  【フロントエンド】
        AST root Node
            ↓ map_source_to_module_spec                【ミドルウェア】
        ModuleSpec IR
            ↓ render_module_spec                       【バックエンド】
        Markdown str

    Args:
        source_code: ソースコード文字列
        module_name: モジュール名（通常はファイル名のステム）
        extension:   ファイル拡張子（例: ".ts", ".py"）

    Returns:
        Markdown 形式の仕様書文字列
    """
    plugin = select_plugin(extension)
    root_node: Node = plugin.parse_source(source_code)
    module_spec = map_source_to_module_spec(root_node, module_name, plugin)
    return render_module_spec(module_spec)
