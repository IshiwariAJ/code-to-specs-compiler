"""
mapper.py のユニットテスト

設計方針:
- すべてのテストは「公開インターフェース map_source_to_module_spec() 経由」でIRを検証する
- TypeScript / Python の両言語で同一の IR 型が生成されることを確認する
- 各テストは独立した入力ソースを持ち、外部状態に依存しない
"""
import pytest

from src.ir.mapper import map_source_to_module_spec
from src.ir.profiles import GO_PROFILE, PYTHON_PROFILE, TYPESCRIPT_PROFILE
from src.ir.types import (
    ConditionBlock,
    DataTransformation,
    FunctionSpec,
    GuardClause,
    ImportSpec,
    LoopNode,
    ModuleSpec,
    ModuleVariableSpec,
    SideEffect,
    TypeDefinitionSpec,
)
from src.parser.go_parser import parse_go_source
from src.parser.python_parser import parse_python_source
from src.parser.ts_parser import parse_typescript_source


# ---------------------------------------------------------------------------
# ヘルパー: 小さなコードスニペットからテスト用 ModuleSpec を構築する
# ---------------------------------------------------------------------------


def _ts_module(source: str) -> ModuleSpec:
    """TypeScript スニペットを解析して ModuleSpec を返す純粋ヘルパー。"""
    root = parse_typescript_source(source)
    return map_source_to_module_spec(root, "test", TYPESCRIPT_PROFILE)


def _py_module(source: str) -> ModuleSpec:
    """Python スニペットを解析して ModuleSpec を返す純粋ヘルパー。"""
    root = parse_python_source(source)
    return map_source_to_module_spec(root, "test", PYTHON_PROFILE)


def _go_module(source: str) -> ModuleSpec:
    """Go スニペットを解析して ModuleSpec を返す純粋ヘルパー。"""
    root = parse_go_source(source)
    return map_source_to_module_spec(root, "test", GO_PROFILE)


def _ts_body(source: str) -> tuple:
    """TypeScript スニペットの最初の関数の IR ノード列を返す。"""
    return _ts_module(source).functions[0].body


def _py_body(source: str) -> tuple:
    """Python スニペットの最初の関数の IR ノード列を返す。"""
    return _py_module(source).functions[0].body


# ---------------------------------------------------------------------------
# ModuleSpec の基本構造
# ---------------------------------------------------------------------------


class TestModuleSpec:
    def test_module_name_is_preserved(self):
        root = parse_typescript_source("function f() {}")
        spec = map_source_to_module_spec(root, "my_module", TYPESCRIPT_PROFILE)
        assert spec.name == "my_module"

    def test_empty_typescript_function_has_no_body_nodes(self):
        spec = _ts_module("function f() {}")
        assert len(spec.functions) == 1
        assert spec.functions[0].name == "f"
        assert len(spec.functions[0].body) == 0

    def test_multiple_typescript_functions_are_all_detected(self):
        spec = _ts_module("function a() {} function b() {} function c() {}")
        assert len(spec.functions) == 3
        assert [fn.name for fn in spec.functions] == ["a", "b", "c"]

    def test_python_function_name_is_snake_case(self):
        spec = _py_module("def my_func():\n    pass\n")
        assert spec.functions[0].name == "my_func"

    def test_python_multiple_functions(self):
        src = "def foo():\n    pass\ndef bar():\n    pass\n"
        spec = _py_module(src)
        assert [fn.name for fn in spec.functions] == ["foo", "bar"]


# ---------------------------------------------------------------------------
# ガード句（GuardClause）の検出
# ---------------------------------------------------------------------------


class TestGuardClause:
    def test_typescript_throw_is_guard_clause(self):
        body = _ts_body('function f(x) { if (x === null) { throw new Error("e"); } }')
        assert len(body) == 1
        assert isinstance(body[0], GuardClause)

    def test_typescript_guard_condition_text(self):
        body = _ts_body('function f(x) { if (x === null) { throw new Error("e"); } }')
        assert body[0].condition_text == "x === null"

    def test_typescript_guard_action_contains_throw_keyword(self):
        body = _ts_body('function f(x) { if (x < 0) { throw new RangeError("neg"); } }')
        assert "スロー" in body[0].action_text

    def test_typescript_return_is_guard_clause(self):
        body = _ts_body("function f(x) { if (x < 0) { return -1; } }")
        assert isinstance(body[0], GuardClause)
        assert "終了" in body[0].action_text

    def test_typescript_guard_with_else_becomes_condition_block(self):
        # else があればガード句ではなく ConditionBlock に変換される
        body = _ts_body("function f(x) { if (x > 0) { return 1; } else { return 0; } }")
        assert isinstance(body[0], ConditionBlock)

    def test_typescript_guard_with_else_if_becomes_condition_block(self):
        src = "function f(x) { if (x > 10) { return 2; } else if (x > 0) { return 1; } }"
        body = _ts_body(src)
        assert isinstance(body[0], ConditionBlock)

    def test_python_raise_is_guard_clause(self):
        body = _py_body("def f(x):\n    if x is None:\n        raise ValueError('null')\n")
        assert isinstance(body[0], GuardClause)
        assert "raise" in body[0].action_text

    def test_python_guard_condition_text_has_no_outer_parens(self):
        # Python の条件式には外側の括弧がないことを確認
        body = _py_body("def f(x):\n    if x is None:\n        raise ValueError('null')\n")
        assert not body[0].condition_text.startswith("(")

    def test_python_guard_with_elif_becomes_condition_block(self):
        src = (
            "def f(x):\n"
            "    if x < 0:\n"
            "        raise ValueError('neg')\n"
            "    elif x > 100:\n"
            "        return 0\n"
        )
        body = _py_body(src)
        assert isinstance(body[0], ConditionBlock)


# ---------------------------------------------------------------------------
# 条件分岐（ConditionBlock）の検出
# ---------------------------------------------------------------------------


class TestConditionBlock:
    def test_typescript_if_else_has_two_cases(self):
        body = _ts_body("function f(x) { if (x > 0) { return 1; } else { return 0; } }")
        assert isinstance(body[0], ConditionBlock)
        assert len(body[0].cases) == 2

    def test_typescript_if_else_condition_texts(self):
        body = _ts_body("function f(x) { if (x > 0) { return 1; } else { return 0; } }")
        assert body[0].cases[0].condition_text == "x > 0"
        assert "デフォルト" in body[0].cases[1].condition_text

    def test_typescript_if_elif_else_has_three_cases(self):
        src = (
            "function f(x) {"
            " if (x >= 90) { return 'A'; }"
            " else if (x >= 70) { return 'B'; }"
            " else { return 'C'; }"
            " }"
        )
        body = _ts_body(src)
        assert isinstance(body[0], ConditionBlock)
        assert len(body[0].cases) == 3

    def test_typescript_if_elif_else_condition_texts(self):
        src = (
            "function f(x) {"
            " if (x >= 90) { return 'A'; }"
            " else if (x >= 70) { return 'B'; }"
            " else { return 'C'; }"
            " }"
        )
        cases = _ts_body(src)[0].cases
        assert cases[0].condition_text == "x >= 90"
        assert cases[1].condition_text == "x >= 70"
        assert "デフォルト" in cases[2].condition_text

    def test_python_if_elif_else_has_three_cases(self):
        src = (
            "def f(x):\n"
            "    if x >= 90:\n"
            "        return 'A'\n"
            "    elif x >= 70:\n"
            "        return 'B'\n"
            "    else:\n"
            "        return 'C'\n"
        )
        body = _py_body(src)
        assert isinstance(body[0], ConditionBlock)
        assert len(body[0].cases) == 3

    def test_python_condition_texts_are_correct(self):
        src = (
            "def f(x):\n"
            "    if x >= 90:\n"
            "        return 'A'\n"
            "    elif x >= 70:\n"
            "        return 'B'\n"
            "    else:\n"
            "        return 'C'\n"
        )
        cases = _py_body(src)[0].cases
        assert cases[0].condition_text == "x >= 90"
        assert cases[1].condition_text == "x >= 70"
        assert "デフォルト" in cases[2].condition_text

    def test_python_multiple_elif(self):
        src = (
            "def f(x):\n"
            "    if x >= 90:\n"
            "        return 'S'\n"
            "    elif x >= 80:\n"
            "        return 'A'\n"
            "    elif x >= 70:\n"
            "        return 'B'\n"
            "    else:\n"
            "        return 'C'\n"
        )
        cases = _py_body(src)[0].cases
        assert len(cases) == 4


# ---------------------------------------------------------------------------
# 繰り返し処理（LoopNode）の検出
# ---------------------------------------------------------------------------


class TestLoopNode:
    def test_typescript_for_of_is_for_each(self):
        body = _ts_body("function f(arr) { for (const item of arr) { total += item; } }")
        loops = [n for n in body if isinstance(n, LoopNode)]
        assert len(loops) == 1
        assert loops[0].loop_type == "FOR_EACH"

    def test_typescript_for_of_collection_and_iterator(self):
        body = _ts_body("function f(arr) { for (const item of arr) { total += item; } }")
        loop = next(n for n in body if isinstance(n, LoopNode))
        assert loop.collection == "arr"
        assert loop.iterator == "item"

    def test_typescript_for_of_body_contains_nested_ir(self):
        body = _ts_body("function f(arr) { for (const item of arr) { total += item; } }")
        loop = next(n for n in body if isinstance(n, LoopNode))
        assert len(loop.body) == 1
        assert isinstance(loop.body[0], DataTransformation)

    def test_typescript_for_range_is_for_range(self):
        body = _ts_body("function f(n) { for (let i = 0; i < n; i++) { s += i; } }")
        loops = [n for n in body if isinstance(n, LoopNode)]
        assert loops[0].loop_type == "FOR_RANGE"

    def test_typescript_for_range_iterator_name(self):
        body = _ts_body("function f(n) { for (let i = 0; i < n; i++) { s += i; } }")
        loop = next(n for n in body if isinstance(n, LoopNode))
        assert loop.iterator == "i"

    def test_python_for_in_is_for_each(self):
        body = _py_body("def f(arr):\n    for item in arr:\n        total += item\n")
        loops = [n for n in body if isinstance(n, LoopNode)]
        assert len(loops) == 1
        assert loops[0].loop_type == "FOR_EACH"

    def test_python_for_in_collection_and_iterator(self):
        body = _py_body("def f(arr):\n    for item in arr:\n        total += item\n")
        loop = next(n for n in body if isinstance(n, LoopNode))
        assert loop.collection == "arr"
        assert loop.iterator == "item"

    def test_python_for_in_body_contains_nested_ir(self):
        body = _py_body("def f(arr):\n    for item in arr:\n        total += item\n")
        loop = next(n for n in body if isinstance(n, LoopNode))
        assert len(loop.body) == 1
        assert isinstance(loop.body[0], DataTransformation)


# ---------------------------------------------------------------------------
# データ変換（DataTransformation）の検出
# ---------------------------------------------------------------------------


class TestDataTransformation:
    def test_typescript_add_assign_operation(self):
        body = _ts_body("function f() { total += 1; }")
        dt = [n for n in body if isinstance(n, DataTransformation)]
        assert dt[0].operation == "ADD"
        assert dt[0].target == "total"
        assert dt[0].value == "1"

    def test_typescript_subtract_assign_operation(self):
        body = _ts_body("function f() { count -= 1; }")
        dt = [n for n in body if isinstance(n, DataTransformation)]
        assert dt[0].operation == "SUBTRACT"

    def test_typescript_multiply_assign_operation(self):
        body = _ts_body("function f() { x *= 2; }")
        dt = [n for n in body if isinstance(n, DataTransformation)]
        assert dt[0].operation == "MULTIPLY"

    def test_typescript_simple_assign_operation(self):
        body = _ts_body("function f() { x = 42; }")
        dt = [n for n in body if isinstance(n, DataTransformation)]
        assert dt[0].operation == "ASSIGN"
        assert dt[0].target == "x"
        assert dt[0].value == "42"

    def test_typescript_let_initialization_is_data_transformation(self):
        body = _ts_body("function f() { let total = 0; }")
        dt = [n for n in body if isinstance(n, DataTransformation)]
        assert len(dt) == 1
        assert dt[0].target == "total"
        assert dt[0].operation == "ASSIGN"
        assert dt[0].value == "0"

    def test_typescript_let_without_init_is_not_captured(self):
        # 初期化値のない let は IR に含めない
        body = _ts_body("function f() { let x; }")
        dt = [n for n in body if isinstance(n, DataTransformation)]
        assert len(dt) == 0

    def test_python_add_assign_operation(self):
        body = _py_body("def f():\n    total += 1\n")
        dt = [n for n in body if isinstance(n, DataTransformation)]
        assert dt[0].operation == "ADD"
        assert dt[0].target == "total"
        assert dt[0].value == "1"

    def test_python_simple_assign_operation(self):
        body = _py_body("def f():\n    x = 42\n")
        dt = [n for n in body if isinstance(n, DataTransformation)]
        assert dt[0].operation == "ASSIGN"
        assert dt[0].target == "x"
        assert dt[0].value == "42"


# ---------------------------------------------------------------------------
# 副作用（SideEffect）の検出
# ---------------------------------------------------------------------------


class TestSideEffect:
    def test_typescript_call_expression_is_side_effect(self):
        body = _ts_body("function f(x) { console.log(x); }")
        se = [n for n in body if isinstance(n, SideEffect)]
        assert len(se) == 1
        assert "console.log" in se[0].description

    def test_typescript_method_call_is_side_effect(self):
        body = _ts_body("function f(arr, v) { arr.push(v); }")
        se = [n for n in body if isinstance(n, SideEffect)]
        assert len(se) == 1
        assert "push" in se[0].description

    def test_python_print_is_side_effect(self):
        body = _py_body("def f(x):\n    print(x)\n")
        se = [n for n in body if isinstance(n, SideEffect)]
        assert len(se) == 1
        assert "print" in se[0].description


# ---------------------------------------------------------------------------
# インポート（ImportSpec）の検出
# ---------------------------------------------------------------------------


class TestImportSpec:
    def test_ts_default_import_source_module(self):
        spec = _ts_module("import React from 'react'; function f() {}")
        assert len(spec.imports) == 1
        assert spec.imports[0].source_module == "react"

    def test_ts_default_import_has_name(self):
        spec = _ts_module("import React from 'react'; function f() {}")
        assert "React" in spec.imports[0].imported_names

    def test_ts_named_import_extracts_names(self):
        spec = _ts_module("import { useState, useEffect } from 'react'; function f() {}")
        assert spec.imports[0].source_module == "react"
        assert "useState" in spec.imports[0].imported_names
        assert "useEffect" in spec.imports[0].imported_names

    def test_ts_namespace_import_alias(self):
        spec = _ts_module("import * as _ from 'lodash'; function f() {}")
        assert spec.imports[0].source_module == "lodash"
        assert spec.imports[0].alias == "_"

    def test_ts_multiple_imports_count(self):
        src = (
            "import React from 'react';\n"
            "import { useState } from 'react';\n"
            "function f() {}\n"
        )
        spec = _ts_module(src)
        assert len(spec.imports) == 2

    def test_ts_type_import_extracts_names(self):
        spec = _ts_module("import type { User } from './types'; function f() {}")
        assert spec.imports[0].source_module == "./types"
        assert "User" in spec.imports[0].imported_names

    def test_ts_import_is_import_spec_instance(self):
        spec = _ts_module("import os from 'os'; function f() {}")
        assert isinstance(spec.imports[0], ImportSpec)

    def test_py_module_import(self):
        spec = _py_module("import os\ndef f():\n    pass\n")
        assert len(spec.imports) == 1
        assert spec.imports[0].source_module == "os"
        assert spec.imports[0].imported_names == ()

    def test_py_aliased_import(self):
        spec = _py_module("import numpy as np\ndef f():\n    pass\n")
        assert spec.imports[0].source_module == "numpy"
        assert spec.imports[0].alias == "np"

    def test_py_from_import_source_module(self):
        spec = _py_module("from datetime import datetime\ndef f():\n    pass\n")
        assert spec.imports[0].source_module == "datetime"

    def test_py_from_import_names(self):
        spec = _py_module("from typing import Optional, List\ndef f():\n    pass\n")
        assert "Optional" in spec.imports[0].imported_names
        assert "List" in spec.imports[0].imported_names

    def test_py_multiple_imports(self):
        src = "import os\nimport sys\ndef f():\n    pass\n"
        spec = _py_module(src)
        assert len(spec.imports) == 2

    def test_py_import_is_import_spec_instance(self):
        spec = _py_module("import os\ndef f():\n    pass\n")
        assert isinstance(spec.imports[0], ImportSpec)

    def test_no_imports_returns_empty_tuple(self):
        spec = _ts_module("function f() {}")
        assert spec.imports == ()

    def test_py_future_import_detected(self):
        src = "from __future__ import annotations\ndef f():\n    pass\n"
        spec = _py_module(src)
        assert len(spec.imports) == 1

    def test_py_future_import_source_module(self):
        src = "from __future__ import annotations\ndef f():\n    pass\n"
        spec = _py_module(src)
        assert spec.imports[0].source_module == "__future__"

    def test_py_future_import_imported_names(self):
        src = "from __future__ import annotations\ndef f():\n    pass\n"
        spec = _py_module(src)
        assert "annotations" in spec.imports[0].imported_names

    def test_py_future_import_with_regular_import(self):
        src = "from __future__ import annotations\nimport os\ndef f():\n    pass\n"
        spec = _py_module(src)
        assert len(spec.imports) == 2
        assert spec.imports[0].source_module == "__future__"


# ---------------------------------------------------------------------------
# モジュール変数・定数（ModuleVariableSpec）の検出
# ---------------------------------------------------------------------------


class TestModuleVariableSpec:
    def test_ts_const_is_constant(self):
        spec = _ts_module("const MAX = 100; function f() {}")
        assert len(spec.module_variables) == 1
        assert spec.module_variables[0].is_constant is True

    def test_ts_let_is_not_constant(self):
        spec = _ts_module("let counter = 0; function f() {}")
        assert spec.module_variables[0].is_constant is False

    def test_ts_const_name_and_value(self):
        spec = _ts_module("const MAX_RETRY = 3; function f() {}")
        v = spec.module_variables[0]
        assert v.name == "MAX_RETRY"
        assert v.value_text == "3"

    def test_ts_multiple_vars(self):
        src = "const A = 1; const B = 2; function f() {}"
        spec = _ts_module(src)
        assert len(spec.module_variables) == 2

    def test_ts_var_without_init_is_not_captured(self):
        spec = _ts_module("let x; function f() {}")
        assert spec.module_variables == ()

    def test_ts_module_variable_is_correct_type(self):
        spec = _ts_module("const X = 1; function f() {}")
        assert isinstance(spec.module_variables[0], ModuleVariableSpec)

    def test_py_all_caps_is_constant(self):
        spec = _py_module("MAX_VALUE = 1000\ndef f():\n    pass\n")
        assert spec.module_variables[0].is_constant is True

    def test_py_lowercase_is_not_constant(self):
        spec = _py_module("debug_mode = False\ndef f():\n    pass\n")
        assert spec.module_variables[0].is_constant is False

    def test_py_variable_name_and_value(self):
        spec = _py_module("MAX_RETRY = 3\ndef f():\n    pass\n")
        v = spec.module_variables[0]
        assert v.name == "MAX_RETRY"
        assert v.value_text == "3"

    def test_no_module_vars_returns_empty_tuple(self):
        spec = _ts_module("function f() {}")
        assert spec.module_variables == ()


# ---------------------------------------------------------------------------
# 型定義（TypeDefinitionSpec）の検出 ── TypeScript のみ
# ---------------------------------------------------------------------------


class TestTypeDefinitionSpec:
    def test_ts_type_alias_detected(self):
        spec = _ts_module("type UserId = string; function f() {}")
        assert len(spec.type_definitions) == 1
        assert spec.type_definitions[0].definition_kind == "alias"

    def test_ts_type_alias_name(self):
        spec = _ts_module("type UserId = string; function f() {}")
        assert spec.type_definitions[0].name == "UserId"

    def test_ts_type_alias_type_text(self):
        spec = _ts_module("type UserId = string; function f() {}")
        assert "string" in spec.type_definitions[0].type_text

    def test_ts_interface_detected(self):
        spec = _ts_module("interface User { name: string; } function f() {}")
        assert len(spec.type_definitions) == 1
        assert spec.type_definitions[0].definition_kind == "interface"

    def test_ts_interface_name(self):
        spec = _ts_module("interface User { name: string; } function f() {}")
        assert spec.type_definitions[0].name == "User"

    def test_ts_multiple_type_definitions(self):
        src = "type A = string; interface B { x: number; } function f() {}"
        spec = _ts_module(src)
        assert len(spec.type_definitions) == 2

    def test_ts_type_definition_is_correct_type(self):
        spec = _ts_module("type X = string; function f() {}")
        assert isinstance(spec.type_definitions[0], TypeDefinitionSpec)

    def test_py_has_no_type_definitions(self):
        # Python は型定義未対応
        spec = _py_module("def f():\n    pass\n")
        assert spec.type_definitions == ()


# ---------------------------------------------------------------------------
# コメント抽出（JSDoc / docstring / インライン / ファイルヘッダー）
# ---------------------------------------------------------------------------


class TestCommentExtraction:
    # --- TypeScript 関数 JSDoc / 行コメント ---

    def test_ts_jsdoc_before_function_extracted_as_description(self):
        src = "/** ユーザーの特典を計算する */\nfunction f() {}"
        spec = _ts_module(src)
        assert "ユーザーの特典を計算する" in spec.functions[0].description

    def test_ts_line_comment_before_function_extracted_as_description(self):
        src = "// 合計を計算する\nfunction f() {}"
        spec = _ts_module(src)
        assert "合計を計算する" in spec.functions[0].description

    def test_ts_multiple_line_comments_before_function_joined(self):
        src = "// 行1\n// 行2\nfunction f() {}"
        spec = _ts_module(src)
        assert "行1" in spec.functions[0].description
        assert "行2" in spec.functions[0].description

    def test_ts_function_without_comment_has_empty_description(self):
        src = "function f() {}"
        spec = _ts_module(src)
        assert spec.functions[0].description == ""

    # --- Python 関数 docstring ---

    def test_py_docstring_extracted_as_description(self):
        src = 'def f():\n    """これは docstring です。"""\n    pass\n'
        spec = _py_module(src)
        assert "docstring" in spec.functions[0].description

    def test_py_function_without_docstring_has_empty_description(self):
        src = "def f():\n    pass\n"
        spec = _py_module(src)
        assert spec.functions[0].description == ""

    def test_py_single_line_docstring_extracted(self):
        src = "def f():\n    '単行docstring'\n    pass\n"
        spec = _py_module(src)
        assert "単行docstring" in spec.functions[0].description

    # --- TypeScript ファイルヘッダーコメント ---

    def test_ts_file_header_comment_extracted(self):
        src = "// このファイルは認証モジュールです\nfunction f() {}"
        spec = _ts_module(src)
        assert "このファイルは認証モジュールです" in spec.file_comment

    def test_ts_multiple_header_comments_joined(self):
        src = "// 行A\n// 行B\nfunction f() {}"
        spec = _ts_module(src)
        assert "行A" in spec.file_comment
        assert "行B" in spec.file_comment

    def test_ts_no_header_comment_returns_empty(self):
        src = "function f() {}"
        spec = _ts_module(src)
        assert spec.file_comment == ""

    # --- Python ファイルヘッダー（モジュール docstring）---

    def test_py_module_docstring_extracted_as_file_comment(self):
        src = '"""モジュールの説明。"""\n\ndef f():\n    pass\n'
        spec = _py_module(src)
        assert "モジュールの説明" in spec.file_comment

    def test_py_no_module_docstring_returns_empty(self):
        src = "def f():\n    pass\n"
        spec = _py_module(src)
        assert spec.file_comment == ""

    # --- インラインコメント（直前のコメントが IR ノードに付与される）---

    def test_ts_comment_before_guard_clause_attached(self):
        src = (
            "function f(x: number): void {\n"
            "  // 前提条件チェック\n"
            '  if (x < 0) { throw new Error("invalid"); }\n'
            "}"
        )
        body = _ts_body(src)
        guard = body[0]
        assert isinstance(guard, GuardClause)
        assert "前提条件チェック" in guard.comment

    def test_ts_comment_before_data_transformation_attached(self):
        src = (
            "function f(): void {\n"
            "  // カウンター初期化\n"
            "  let count = 0;\n"
            "}"
        )
        body = _ts_body(src)
        dt = body[0]
        assert isinstance(dt, DataTransformation)
        assert "カウンター初期化" in dt.comment

    def test_ts_node_without_preceding_comment_has_empty_comment(self):
        src = "function f(): void { let x = 0; }"
        body = _ts_body(src)
        assert body[0].comment == ""

    def test_py_inline_comment_not_extracted(self):
        """
        Python の tree-sitter では関数本体 block の comment ノードが
        extra として扱われ named_children に含まれないため、
        インラインコメントは抽出されない（仕様）。
        """
        src = (
            "def f(x):\n"
            "    # 前提条件チェック\n"
            "    if x < 0:\n"
            "        raise ValueError('invalid')\n"
        )
        body = _py_body(src)
        guard = body[0]
        assert isinstance(guard, GuardClause)
        # Python の関数内インラインコメントは非対応（tree-sitter 制約）
        assert guard.comment == ""


# ---------------------------------------------------------------------------
# Go 言語対応テスト
# ---------------------------------------------------------------------------


def _go_body(source: str) -> tuple:
    """Go スニペットの最初の関数の IR ノード列を返す。"""
    return _go_module(source).functions[0].body


class TestGoGuardClause:
    """Go のガード句検出テスト"""

    def test_go_guard_clause_detected(self):
        src = (
            "package main\n"
            "func f(x int) int {\n"
            "  if x < 0 {\n"
            "    return 0\n"
            "  }\n"
            "  return x\n"
            "}\n"
        )
        body = _go_body(src)
        assert isinstance(body[0], GuardClause)

    def test_go_guard_clause_condition(self):
        src = (
            "package main\n"
            "func f(x int) int {\n"
            '  if x != 0 {\n'
            "    return -1\n"
            "  }\n"
            "  return 0\n"
            "}\n"
        )
        body = _go_body(src)
        assert body[0].condition_text == "x != 0"

    def test_go_guard_clause_action_text(self):
        src = (
            "package main\n"
            "func f(x int) int {\n"
            "  if x < 0 {\n"
            "    return 0\n"
            "  }\n"
            "  return x\n"
            "}\n"
        )
        body = _go_body(src)
        assert "処理を終了する" in body[0].action_text

    def test_go_if_with_else_is_not_guard_clause(self):
        src = (
            "package main\n"
            "func f(x int) int {\n"
            "  if x > 0 {\n"
            "    return 1\n"
            "  } else {\n"
            "    return -1\n"
            "  }\n"
            "}\n"
        )
        body = _go_body(src)
        assert isinstance(body[0], ConditionBlock)


class TestGoLoopNode:
    """Go の for ループ検出テスト"""

    def test_go_for_range_is_for_each(self):
        src = (
            "package main\n"
            "func f(items []int) {\n"
            "  for _, item := range items {\n"
            "    _ = item\n"
            "  }\n"
            "}\n"
        )
        body = _go_body(src)
        assert isinstance(body[0], LoopNode)
        assert body[0].loop_type == "FOR_EACH"

    def test_go_for_range_collection(self):
        src = (
            "package main\n"
            "func f(items []int) {\n"
            "  for _, v := range items {\n"
            "    _ = v\n"
            "  }\n"
            "}\n"
        )
        body = _go_body(src)
        assert body[0].collection == "items"

    def test_go_for_range_iterator_includes_variables(self):
        src = (
            "package main\n"
            "func f(items []int) {\n"
            "  for _, v := range items {\n"
            "    _ = v\n"
            "  }\n"
            "}\n"
        )
        body = _go_body(src)
        # iterator は "_, v" のような expression_list テキスト
        assert "v" in body[0].iterator

    def test_go_c_style_for_is_for_range(self):
        src = (
            "package main\n"
            "func f() {\n"
            "  for i := 0; i < 10; i++ {\n"
            "  }\n"
            "}\n"
        )
        body = _go_body(src)
        assert isinstance(body[0], LoopNode)
        assert body[0].loop_type == "FOR_RANGE"

    def test_go_c_style_for_iterator_name(self):
        src = (
            "package main\n"
            "func f() {\n"
            "  for i := 0; i < 10; i++ {\n"
            "  }\n"
            "}\n"
        )
        body = _go_body(src)
        assert body[0].iterator == "i"

    def test_go_for_range_body_extracted(self):
        src = (
            "package main\n"
            "func f(items []int) {\n"
            "  total := 0\n"
            "  for _, v := range items {\n"
            "    total += v\n"
            "  }\n"
            "}\n"
        )
        body = _go_body(src)
        loop = body[1]
        assert isinstance(loop, LoopNode)
        assert len(loop.body) == 1
        assert isinstance(loop.body[0], DataTransformation)
        assert loop.body[0].operation == "ADD"


class TestGoDataTransformation:
    """Go の代入・変数宣言の DataTransformation テスト"""

    def test_go_short_var_decl_is_data_transformation(self):
        src = (
            "package main\n"
            "func f() {\n"
            "  x := 42\n"
            "}\n"
        )
        body = _go_body(src)
        assert isinstance(body[0], DataTransformation)
        assert body[0].operation == "ASSIGN"

    def test_go_short_var_decl_target(self):
        src = (
            "package main\n"
            "func f() {\n"
            "  total := 0\n"
            "}\n"
        )
        body = _go_body(src)
        assert body[0].target == "total"

    def test_go_short_var_decl_value(self):
        src = (
            "package main\n"
            "func f() {\n"
            "  total := 0\n"
            "}\n"
        )
        body = _go_body(src)
        assert body[0].value == "0"

    def test_go_augmented_assignment_add(self):
        src = (
            "package main\n"
            "func f() {\n"
            "  total := 0\n"
            "  total += 5\n"
            "}\n"
        )
        body = _go_body(src)
        assert isinstance(body[1], DataTransformation)
        assert body[1].operation == "ADD"

    def test_go_augmented_assignment_subtract(self):
        src = (
            "package main\n"
            "func f() {\n"
            "  x := 10\n"
            "  x -= 3\n"
            "}\n"
        )
        body = _go_body(src)
        assert body[1].operation == "SUBTRACT"

    def test_go_simple_assignment(self):
        src = (
            "package main\n"
            "func f() {\n"
            "  x := 0\n"
            "  x = 5\n"
            "}\n"
        )
        body = _go_body(src)
        assert isinstance(body[1], DataTransformation)
        assert body[1].operation == "ASSIGN"


class TestGoConditionBlock:
    """Go の if/else-if/else 条件分岐テスト"""

    def test_go_if_else_is_condition_block(self):
        src = (
            "package main\n"
            "func f(x int) int {\n"
            "  if x > 0 {\n"
            "    return 1\n"
            "  } else {\n"
            "    return -1\n"
            "  }\n"
            "}\n"
        )
        body = _go_body(src)
        assert isinstance(body[0], ConditionBlock)

    def test_go_if_else_has_two_cases(self):
        src = (
            "package main\n"
            "func f(x int) int {\n"
            "  if x > 0 {\n"
            "    return 1\n"
            "  } else {\n"
            "    return -1\n"
            "  }\n"
            "}\n"
        )
        body = _go_body(src)
        assert len(body[0].cases) == 2

    def test_go_else_if_chain_has_three_cases(self):
        src = (
            "package main\n"
            "func f(x int) string {\n"
            '  if x > 100 {\n'
            '    return "big"\n'
            "  } else if x > 50 {\n"
            '    return "medium"\n'
            "  } else {\n"
            '    return "small"\n'
            "  }\n"
            "}\n"
        )
        body = _go_body(src)
        assert isinstance(body[0], ConditionBlock)
        assert len(body[0].cases) == 3

    def test_go_condition_text_no_outer_parens(self):
        src = (
            "package main\n"
            "func f(x int) int {\n"
            "  if x > 0 {\n"
            "    return 1\n"
            "  } else {\n"
            "    return -1\n"
            "  }\n"
            "}\n"
        )
        body = _go_body(src)
        # Go の条件式には外側の括弧がない
        assert body[0].cases[0].condition_text == "x > 0"

    def test_go_else_case_has_default_condition(self):
        src = (
            "package main\n"
            "func f(x int) int {\n"
            "  if x > 0 {\n"
            "    return 1\n"
            "  } else {\n"
            "    return -1\n"
            "  }\n"
            "}\n"
        )
        body = _go_body(src)
        assert "デフォルト" in body[0].cases[1].condition_text


class TestGoImports:
    """Go のインポート抽出テスト"""

    def test_go_single_import_detected(self):
        src = (
            'package main\nimport "fmt"\nfunc f() {}\n'
        )
        spec = _go_module(src)
        assert len(spec.imports) == 1

    def test_go_single_import_module_name(self):
        src = (
            'package main\nimport "fmt"\nfunc f() {}\n'
        )
        spec = _go_module(src)
        assert spec.imports[0].source_module == "fmt"

    def test_go_group_import_two_packages(self):
        src = (
            "package main\n"
            "import (\n"
            '    "fmt"\n'
            '    "os"\n'
            ")\n"
            "func f() {}\n"
        )
        spec = _go_module(src)
        assert len(spec.imports) == 2

    def test_go_group_import_module_names(self):
        src = (
            "package main\n"
            "import (\n"
            '    "fmt"\n'
            '    "os"\n'
            ")\n"
            "func f() {}\n"
        )
        spec = _go_module(src)
        modules = {s.source_module for s in spec.imports}
        assert "fmt" in modules
        assert "os" in modules

    def test_go_aliased_import(self):
        src = (
            "package main\n"
            'import os "os"\n'
            "func f() {}\n"
        )
        spec = _go_module(src)
        assert spec.imports[0].alias == "os"


class TestGoModuleVariables:
    """Go のモジュールレベル定数・変数テスト"""

    def test_go_const_is_constant(self):
        src = (
            "package main\n"
            'const VERSION = "1.0"\n'
            "func f() {}\n"
        )
        spec = _go_module(src)
        assert len(spec.module_variables) == 1
        assert spec.module_variables[0].is_constant is True

    def test_go_const_name(self):
        src = (
            "package main\n"
            "const MAX_SIZE = 100\n"
            "func f() {}\n"
        )
        spec = _go_module(src)
        assert spec.module_variables[0].name == "MAX_SIZE"

    def test_go_var_is_not_constant(self):
        src = (
            "package main\n"
            "var counter = 0\n"
            "func f() {}\n"
        )
        spec = _go_module(src)
        assert spec.module_variables[0].is_constant is False

    def test_go_var_name_and_value(self):
        src = (
            "package main\n"
            "var maxRetry = 3\n"
            "func f() {}\n"
        )
        spec = _go_module(src)
        assert spec.module_variables[0].name == "maxRetry"
        assert spec.module_variables[0].value_text == "3"


class TestGoFunctionSpec:
    """Go の関数仕様全般テスト"""

    def test_go_function_name_extracted(self):
        src = "package main\nfunc myFunc() {}\n"
        spec = _go_module(src)
        assert spec.functions[0].name == "myFunc"

    def test_go_function_comment_as_description(self):
        src = (
            "package main\n"
            "// myFunc は何かをする\n"
            "func myFunc() {}\n"
        )
        spec = _go_module(src)
        assert "myFunc は何かをする" in spec.functions[0].description

    def test_go_multiple_functions_detected(self):
        src = (
            "package main\n"
            "func f1() {}\n"
            "func f2() {}\n"
        )
        spec = _go_module(src)
        assert len(spec.functions) == 2

    def test_go_file_header_comment_extracted(self):
        src = (
            "// Package main はサンプルです\n"
            "package main\n"
            "func f() {}\n"
        )
        spec = _go_module(src)
        assert "サンプルです" in spec.file_comment
