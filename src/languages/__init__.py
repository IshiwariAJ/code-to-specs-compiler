"""
言語プラグインシステム

LanguagePlugin: 1言語分のすべての情報をまとめた不変オブジェクト。
discover_plugins(): src/languages/ 内を自動探索して登録済み言語を返す。

新言語を追加するには:
  src/languages/<言語名>.py を作成し、PLUGIN 定数（LanguagePlugin インスタンス）を定義する。
  既存ファイルへの変更は一切不要。discover_plugins() が自動的に検出する。
"""
from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from tree_sitter import Node

from ..ir.profiles import LanguageProfile
from ..ir.types import ClassSpec, DataTransformation, ImportSpec, ModuleVariableSpec, ParamSpec, TypeDefinitionSpec


@dataclass(frozen=True)
class LanguagePlugin:
    """
    1言語分のすべての情報をまとめた不変オブジェクト。

    このオブジェクトを PLUGIN という名前でモジュールに定義すると、
    discover_plugins() によって自動検出される。

    新言語対応時は src/languages/<言語名>.py を作成してこの型のインスタンスを
    PLUGIN という名前で定義するだけでよい。
    """

    # 対応ファイル拡張子（例: (".ts", ".tsx")）
    extensions: tuple[str, ...]

    # 言語の AST 構造仕様（mapper.py の共通ロジックが参照する）
    profile: LanguageProfile

    # ソースコード文字列 → tree-sitter AST ルートノード
    parse_source: Callable[[str], Node]

    # import ノード1つ → ImportSpec リスト
    import_extractor: Callable[[Node], list[ImportSpec]]

    # モジュールレベル変数ノード1つ → ModuleVariableSpec | None
    module_var_extractor: Callable[[Node], Optional[ModuleVariableSpec]]

    # 型定義ノード1つ → TypeDefinitionSpec | None（未対応言語は lambda _: None）
    type_def_extractor: Callable[[Node], Optional[TypeDefinitionSpec]]

    # expression_statement を介さない直接代入文のノードタイプ → 変換関数
    # 例: Go の ("assignment_statement", map_go_assignment)
    # TypeScript / Python は空タプルでよい
    direct_statement_extractors: tuple[
        tuple[str, Callable[[Node], Optional[DataTransformation]]], ...
    ]

    # クラス定義ノード1つ → ClassSpec | None
    # Python: @dataclass / class を抽出する関数
    # TypeScript / Go: lambda _: None（クラスは別途 TypeDefinitionSpec / 将来対応）
    class_extractor: Callable[[Node], Optional[ClassSpec]]

    # 関数定義ノード → 引数リスト（ParamSpec のタプル）
    # 未対応の場合は lambda _: () を渡す
    param_extractor: Callable[[Node], tuple[ParamSpec, ...]]

    # 関数定義ノード → 戻り値の型テキスト（型アノテーションがなければ空文字）
    # 未対応の場合は lambda _: "" を渡す
    return_type_extractor: Callable[[Node], str]


def discover_plugins() -> dict[str, LanguagePlugin]:
    """
    src/languages/ 内の全 *.py モジュールを探索し、
    PLUGIN 定数を持つものを「拡張子 → LanguagePlugin」の辞書にまとめて返す。

    新言語対応モジュールは自動的に検出される。
    アンダースコアで始まるモジュール（__init__.py 等）はスキップする。
    """
    plugins: dict[str, LanguagePlugin] = {}
    package_dir = Path(__file__).parent
    for mod_info in pkgutil.iter_modules([str(package_dir)]):
        if mod_info.name.startswith("_"):
            continue
        module = importlib.import_module(f".{mod_info.name}", package=__package__)
        if hasattr(module, "PLUGIN"):
            plugin: LanguagePlugin = module.PLUGIN
            for ext in plugin.extensions:
                plugins[ext] = plugin
    return plugins
