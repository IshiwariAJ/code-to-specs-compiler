"""
Universal IR (中間表現) のデータ型定義

設計方針（構造化プログラミング原則）:
- すべての型は frozen dataclass（不変オブジェクト）
- シーケンスには tuple を使用（list は不変ではないため使用しない）
- 型の責務は「データを保持すること」のみ。ロジックは一切持たない
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union


# ---------------------------------------------------------------------------
# 関数引数の仕様
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParamSpec:
    """
    関数の1引数（パラメーター）の仕様。

    例:
        function foo(user: User, id: number = 0)
            → ParamSpec(name="user", type_text="User")
            → ParamSpec(name="id",   type_text="number", default_text="0")

        def process(items: list[str], limit: int = 10) -> dict:
            → ParamSpec(name="items", type_text="list[str]")
            → ParamSpec(name="limit", type_text="int", default_text="10")

        func Foo(a int, b string) (string, error)
            → ParamSpec(name="a", type_text="int")
            → ParamSpec(name="b", type_text="string")
    """
    name: str
    type_text: str = ""       # 型アノテーション（なければ空文字）
    default_text: str = ""    # デフォルト値テキスト（なければ空文字）
    is_rest: bool = False     # TypeScript の ...args / Python の *args のような可変長引数


# ---------------------------------------------------------------------------
# モジュールレベルの構造（インポート / 変数定義 / 型定義）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ImportSpec:
    """
    インポート文の仕様（モジュールレベル）。

    例:
        import os                              → source_module="os", names=(), alias=""
        import numpy as np                     → source_module="numpy", alias="np"
        from datetime import datetime          → source_module="datetime", names=("datetime",)
        import { useState } from 'react'       → source_module="react", names=("useState",)
        import * as _ from 'lodash'            → source_module="lodash", alias="*"
    """
    kind: Literal["ImportSpec"]
    source_module: str              # インポート元モジュール名
    imported_names: tuple[str, ...]  # インポートした名前の列（空ならモジュール全体）
    alias: str                      # エイリアス（"np", "*" など。なければ空文字）


@dataclass(frozen=True)
class ModuleVariableSpec:
    """
    モジュールレベルの変数・定数定義。

    例:
        const MAX_VALUE = 1000   → name="MAX_VALUE", value_text="1000", is_constant=True
        let counter = 0          → name="counter", value_text="0", is_constant=False
        DEBUG = False            → name="DEBUG", value_text="False", is_constant=True (ALL_CAPS)
    """
    kind: Literal["ModuleVariableSpec"]
    name: str
    value_text: str   # 右辺の式テキスト（長い場合は先頭部分のみ）
    is_constant: bool  # const (TypeScript) または ALL_CAPS 命名 (Python) の場合 True


@dataclass(frozen=True)
class TypeDefinitionSpec:
    """
    型定義（主に TypeScript の type alias / interface）。

    例:
        type UserId = string                   → name="UserId", def_kind="alias"
        interface AppConfig { host: string; }  → name="AppConfig", def_kind="interface"
    """
    kind: Literal["TypeDefinitionSpec"]
    name: str
    definition_kind: Literal["alias", "interface"]
    type_text: str  # 型本体のテキスト（長い場合は省略）


@dataclass(frozen=True)
class ClassFieldSpec:
    """
    クラスの1フィールド仕様（Python @dataclass 等）。

    例:
        name: str            → name="name", type_text="str"
        value: int = 0       → name="value", type_text="int", default_text="0"
        count: int = 0  # 説明 → comment="説明"
    """
    name: str
    type_text: str        # 型アノテーションのテキスト（例: "str", "frozenset[str]"）
    default_text: str = ""  # デフォルト値テキスト（なければ空文字）
    comment: str = ""     # インラインコメント（# 以降のテキスト）


@dataclass(frozen=True)
class ClassSpec:
    """
    クラス定義の仕様（Python @dataclass 等）。

    TypeScript の TypeDefinitionSpec が type/interface の文字列表現を保持するのに対し、
    ClassSpec はフィールド構造を個別に保持する。

    例:
        @dataclass(frozen=True)
        class LanguageProfile:
            \"\"\"...\"\"\"\
            name: str  # 説明

    注: methods は FunctionSpec のタプルだが、FunctionSpec はこのクラスより後に定義される。
        from __future__ import annotations により文字列アノテーションとして扱われるため問題なし。
    """
    kind: Literal["ClassSpec"]
    name: str
    is_dataclass: bool     # @dataclass デコレータを持つか
    description: str = ""  # クラス docstring
    fields: tuple[ClassFieldSpec, ...] = ()
    methods: tuple[FunctionSpec, ...] = ()  # type: ignore[misc]  # 前方参照（実行時に解決される）


# ---------------------------------------------------------------------------
# 関数本体の IR ノード（制御フロー・データ変換）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GuardClause:
    """
    ガード句パターン: 関数冒頭で前提条件を確認し、満たさない場合に即座に中断する。

    例: if (user === null) { throw new Error("..."); }
    """
    kind: Literal["GuardClause"]
    condition_text: str   # 条件式のテキスト（例: "user === null"）
    action_text: str      # 中断時のアクション説明
    comment: str = ""     # 直前のコメント行（生テキスト）


@dataclass(frozen=True)
class CaseNode:
    """
    条件分岐の1ケース（if / else if / else の1つの分岐）
    """
    condition_text: str          # 条件式のテキスト、またはデフォルトラベル
    body: tuple[IRNode, ...] = () # このケースで実行される処理のIR一覧


@dataclass(frozen=True)
class ConditionBlock:
    """
    条件分岐ブロック: if / else if / else の連鎖全体

    例: if (score >= 90) { ... } else if (score >= 70) { ... } else { ... }
    """
    kind: Literal["ConditionBlock"]
    cases: tuple[CaseNode, ...]
    comment: str = ""  # 直前のコメント行（生テキスト）


@dataclass(frozen=True)
class LoopNode:
    """
    繰り返し処理: for...of（FOR_EACH）または古典的 for ループ（FOR_RANGE）

    例: for (const item of collection) { ... }
    """
    kind: Literal["Loop"]
    loop_type: Literal["FOR_EACH", "FOR_RANGE"]
    collection: str           # イテレート対象の式または範囲の説明
    iterator: str             # イテレータ変数名
    body: tuple[IRNode, ...]  # ループ本体内の入れ子IRノード
    comment: str = ""         # 直前のコメント行（生テキスト）


@dataclass(frozen=True)
class DataTransformation:
    """
    変数への代入・演算更新（例: totalAmount += history.price）

    operation は操作の種類を識別するための記号名。
    日本語への変換はレンダラー層が担当する（マッパーはデータを記録するのみ）。
    """
    kind: Literal["DataTransformation"]
    target: str     # 代入先の変数名        （例: "totalAmount"）
    operation: str  # 操作種別（ADD / ASSIGN / etc.）
    value: str      # 右辺の式テキスト      （例: "history.price"）
    comment: str = ""  # 直前のコメント行（生テキスト）


@dataclass(frozen=True)
class SideEffect:
    """
    外部への副作用を伴う式（関数呼び出し等）

    例: console.log(x), arr.push(v), emitter.emit("done")
    描写内容はコード式の生テキストをそのまま保持する（決定論的）。
    """
    kind: Literal["SideEffect"]
    description: str  # 式全体のテキスト（例: "console.log(x)"）
    comment: str = ""  # 直前のコメント行（生テキスト）


@dataclass(frozen=True)
class ReturnNode:
    """
    return / throw / raise 文（ガード句パターン以外のもの）。

    ガード句（if (cond) { return/throw }）は GuardClause で表現されるため、
    このノードは関数本体またはループ本体に直接現れる return/throw/raise を対象とする。

    例:
        return result                          → action="return", value_text="result"
        return { points: 100, message: "..." } → action="return", value_text="{ points: 100, ... }"
        throw new Error("msg")                 → action="throw",  value_text='new Error("msg")'
        raise ValueError("msg")               → action="raise",  value_text='ValueError("msg")'
        return                                 → action="return", value_text=""
    """
    kind: Literal["ReturnNode"]
    value_text: str                                        # 返却・スローする式テキスト（値なし return は空文字）
    action: Literal["return", "throw", "raise"] = "return"
    comment: str = ""                                      # 直前のコメント行（生テキスト）


# すべての関数本体 IR ノード型のユニオン型エイリアス
IRNode = Union[GuardClause, ConditionBlock, LoopNode, DataTransformation, SideEffect, ReturnNode]


# ---------------------------------------------------------------------------
# スペック集約型（関数 / モジュール）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FunctionSpec:
    """
    1つの関数の仕様: 関数名、引数、戻り値の型、および本体から抽出したIRノードの列
    """
    name: str
    body: tuple[IRNode, ...]
    description: str = ""               # JSDoc コメント（TypeScript）または docstring（Python）
    params: tuple[ParamSpec, ...] = ()  # 引数リスト（順序保持）
    return_type: str = ""               # 戻り値の型テキスト（型アノテーションがなければ空文字）


@dataclass(frozen=True)
class ModuleSpec:
    """
    1つのソースファイル全体の仕様。

    フィールド順: モジュール定義の上から下の流れに対応する。
      imports           → ファイル冒頭のインポート文
      module_variables  → モジュールレベルの定数・変数
      type_definitions  → 型エイリアス・インターフェース（主に TypeScript）
      class_definitions → クラス定義（主に Python @dataclass）
      functions         → 関数定義
    """
    name: str
    functions: tuple[FunctionSpec, ...]
    imports: tuple[ImportSpec, ...] = ()
    module_variables: tuple[ModuleVariableSpec, ...] = ()
    type_definitions: tuple[TypeDefinitionSpec, ...] = ()
    class_definitions: tuple[ClassSpec, ...] = ()
    file_comment: str = ""  # ファイル先頭のコメント / モジュール docstring
    extraction_warnings: tuple[str, ...] = ()  # 未抽出の構文・文ノードの警告
