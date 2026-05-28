"""
mapper.py のユニットテスト

設計方針:
- すべてのテストは「公開インターフェース map_source_to_module_spec() 経由」でIRを検証する
- TypeScript / Python の両言語で同一の IR 型が生成されることを確認する
- 各テストは独立した入力ソースを持ち、外部状態に依存しない
"""
import pytest

from src.ir.mapper import map_source_to_module_spec
from src.ir.types import (
    ClassSpec,
    ConditionBlock,
    DataTransformation,
    FunctionSpec,
    GuardClause,
    ImportSpec,
    LoopNode,
    ModuleSpec,
    ModuleVariableSpec,
    ReturnNode,
    SideEffect,
    TryCatchNode,
    TypeDefinitionSpec,
)
from src.languages.go import PLUGIN as GO_PLUGIN
from src.languages.java import PLUGIN as JAVA_PLUGIN
from src.languages.powershell import PLUGIN as POWERSHELL_PLUGIN
from src.languages.python import PLUGIN as PYTHON_PLUGIN
from src.languages.typescript import PLUGIN as TYPESCRIPT_PLUGIN


# ---------------------------------------------------------------------------
# ヘルパー: 小さなコードスニペットからテスト用 ModuleSpec を構築する
# ---------------------------------------------------------------------------


def _ts_module(source: str) -> ModuleSpec:
    """TypeScript スニペットを解析して ModuleSpec を返す純粋ヘルパー。"""
    root = TYPESCRIPT_PLUGIN.parse_source(source)
    return map_source_to_module_spec(root, "test", TYPESCRIPT_PLUGIN)


def _py_module(source: str) -> ModuleSpec:
    """Python スニペットを解析して ModuleSpec を返す純粋ヘルパー。"""
    root = PYTHON_PLUGIN.parse_source(source)
    return map_source_to_module_spec(root, "test", PYTHON_PLUGIN)


def _go_module(source: str) -> ModuleSpec:
    """Go スニペットを解析して ModuleSpec を返す純粋ヘルパー。"""
    root = GO_PLUGIN.parse_source(source)
    return map_source_to_module_spec(root, "test", GO_PLUGIN)


def _ps_module(source: str) -> ModuleSpec:
    """PowerShell スニペットを解析して ModuleSpec を返す純粋ヘルパー。"""
    root = POWERSHELL_PLUGIN.parse_source(source)
    return map_source_to_module_spec(root, "test", POWERSHELL_PLUGIN)


def _ts_body(source: str) -> tuple:
    """TypeScript スニペットの最初の関数の IR ノード列を返す。"""
    return _ts_module(source).functions[0].body


def _py_body(source: str) -> tuple:
    """Python スニペットの最初の関数の IR ノード列を返す。"""
    return _py_module(source).functions[0].body


def _ps_body(source: str) -> tuple:
    """PowerShell スニペットの最初の関数の IR ノード列を返す。"""
    return _ps_module(source).functions[0].body


# ---------------------------------------------------------------------------
# ModuleSpec の基本構造
# ---------------------------------------------------------------------------


class TestModuleSpec:
    def test_module_name_is_preserved(self):
        root = TYPESCRIPT_PLUGIN.parse_source("function f() {}")
        spec = map_source_to_module_spec(root, "my_module", TYPESCRIPT_PLUGIN)
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

    def test_typescript_case_body_contains_return_node(self):
        body = _ts_body("function f(x) { if (x > 0) { return 1; } else { return 0; } }")
        case_body = body[0].cases[0].body
        assert len(case_body) == 1
        assert isinstance(case_body[0], ReturnNode)
        assert case_body[0].value_text == "1"

    def test_typescript_case_body_contains_data_transformation(self):
        src = (
            "function f(user) {"
            " let points = 0;"
            " if (user.rank === 'Gold') {"
            "   points += 1000;"
            " } else {"
            "   points += 100;"
            " }"
            "}"
        )
        condition = _ts_body(src)[1]
        assert isinstance(condition, ConditionBlock)
        assert isinstance(condition.cases[0].body[0], DataTransformation)
        assert condition.cases[0].body[0].operation == "ADD"

    def test_typescript_case_body_contains_side_effect(self):
        src = (
            "function f(user) {"
            " if (user.active) {"
            "   notify(user);"
            " } else {"
            "   log(user);"
            " }"
            "}"
        )
        condition = _ts_body(src)[0]
        assert isinstance(condition.cases[0].body[0], SideEffect)
        assert condition.cases[0].body[0].description == "notify(user)"


# ---------------------------------------------------------------------------
# 例外処理（TryCatchNode）の検出
# ---------------------------------------------------------------------------


class TestTryCatchNode:
    def test_typescript_try_catch_finally_is_try_catch_node(self):
        src = (
            "function f() {"
            " try { const x = work(); }"
            " catch (error) { log(error); throw error; }"
            " finally { cleanup(); }"
            "}"
        )
        body = _ts_body(src)
        assert isinstance(body[0], TryCatchNode)

    def test_typescript_try_body_contains_nested_ir(self):
        src = (
            "function f() {"
            " try { const x = work(); }"
            " catch (error) { log(error); }"
            "}"
        )
        node = _ts_body(src)[0]
        assert isinstance(node.try_body[0], DataTransformation)
        assert node.try_body[0].target == "x"

    def test_typescript_catch_var_and_body_are_extracted(self):
        src = (
            "function f() {"
            " try { work(); }"
            " catch (error) { log(error); throw error; }"
            "}"
        )
        node = _ts_body(src)[0]
        assert node.catch_var == "error"
        assert isinstance(node.catch_body[0], SideEffect)
        assert isinstance(node.catch_body[1], ReturnNode)
        assert node.catch_body[1].action == "throw"

    def test_typescript_finally_body_is_extracted(self):
        src = (
            "function f() {"
            " try { work(); }"
            " catch (error) { log(error); }"
            " finally { cleanup(); }"
            "}"
        )
        node = _ts_body(src)[0]
        assert isinstance(node.finally_body[0], SideEffect)
        assert node.finally_body[0].description == "cleanup()"

    def test_python_except_alias_is_catch_var(self):
        src = (
            "def f():\n"
            "    try:\n"
            "        x = work()\n"
            "    except ValueError as error:\n"
            "        log(error)\n"
            "        raise error\n"
        )
        node = _py_body(src)[0]
        assert isinstance(node, TryCatchNode)
        assert node.catch_var == "error"
        assert isinstance(node.catch_body[1], ReturnNode)
        assert node.catch_body[1].action == "raise"

    def test_powershell_try_catch_finally_is_extracted(self):
        src = (
            "function f {"
            " try { $x = work }"
            " catch { Write-Error $_; throw $_ }"
            " finally { cleanup }"
            "}"
        )
        node = _ps_body(src)[0]
        assert isinstance(node, TryCatchNode)
        assert isinstance(node.try_body[0], DataTransformation)
        assert isinstance(node.catch_body[0], SideEffect)
        assert isinstance(node.finally_body[0], SideEffect)


# ---------------------------------------------------------------------------
# switch / match 文（SwitchNode）の検出
# ---------------------------------------------------------------------------


class TestSwitchNode:
    # --- TypeScript switch ---

    def test_ts_switch_is_switch_node(self):
        body = _ts_body("function f(s) { switch (s) { case 'A': return 1; } }")
        from src.ir.types import SwitchNode
        assert any(isinstance(n, SwitchNode) for n in body)

    def test_ts_switch_subject_extracted(self):
        from src.ir.types import SwitchNode
        body = _ts_body("function f(status) { switch (status) { case 'A': return 1; } }")
        sw = next(n for n in body if isinstance(n, SwitchNode))
        assert sw.subject == "status"

    def test_ts_switch_case_condition_extracted(self):
        from src.ir.types import SwitchNode
        body = _ts_body("function f(s) { switch (s) { case 'ACTIVE': return 1; case 'INACTIVE': return 2; } }")
        sw = next(n for n in body if isinstance(n, SwitchNode))
        assert sw.cases[0].condition_text == "'ACTIVE'"
        assert sw.cases[1].condition_text == "'INACTIVE'"

    def test_ts_switch_default_condition_is_default(self):
        from src.ir.types import SwitchNode
        body = _ts_body("function f(s) { switch (s) { default: return 0; } }")
        sw = next(n for n in body if isinstance(n, SwitchNode))
        assert sw.cases[0].condition_text == "default"

    def test_ts_switch_case_body_extracted(self):
        from src.ir.types import SwitchNode
        body = _ts_body("function f(s) { switch (s) { case 'A': count += 1; return 1; } }")
        sw = next(n for n in body if isinstance(n, SwitchNode))
        assert len(sw.cases[0].body) == 2
        assert isinstance(sw.cases[0].body[0], DataTransformation)
        assert isinstance(sw.cases[0].body[1], ReturnNode)

    def test_ts_switch_multiple_cases(self):
        from src.ir.types import SwitchNode
        src = "function f(s) { switch (s) { case 'A': return 1; case 'B': return 2; default: return 0; } }"
        body = _ts_body(src)
        sw = next(n for n in body if isinstance(n, SwitchNode))
        assert len(sw.cases) == 3

    # --- Python match ---

    def test_py_match_is_switch_node(self):
        from src.ir.types import SwitchNode
        body = _py_body("def f(cmd):\n    match cmd:\n        case 'start':\n            start()\n")
        assert any(isinstance(n, SwitchNode) for n in body)

    def test_py_match_subject_extracted(self):
        from src.ir.types import SwitchNode
        body = _py_body("def f(command):\n    match command:\n        case 'start':\n            start()\n")
        sw = next(n for n in body if isinstance(n, SwitchNode))
        assert sw.subject == "command"

    def test_py_match_case_condition_extracted(self):
        from src.ir.types import SwitchNode
        src = "def f(cmd):\n    match cmd:\n        case 'start':\n            a()\n        case 'stop':\n            b()\n"
        body = _py_body(src)
        sw = next(n for n in body if isinstance(n, SwitchNode))
        assert sw.cases[0].condition_text == "'start'"
        assert sw.cases[1].condition_text == "'stop'"

    def test_py_match_wildcard_is_default(self):
        from src.ir.types import SwitchNode
        src = "def f(cmd):\n    match cmd:\n        case _:\n            raise ValueError()\n"
        body = _py_body(src)
        sw = next(n for n in body if isinstance(n, SwitchNode))
        assert sw.cases[0].condition_text == "default"


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

    # --- while ループ ---

    def test_typescript_while_is_while_type(self):
        body = _ts_body("function f() { while (!ready) { poll(); } }")
        loops = [n for n in body if isinstance(n, LoopNode)]
        assert len(loops) == 1
        assert loops[0].loop_type == "WHILE"

    def test_typescript_while_condition_extracted(self):
        body = _ts_body("function f() { while (queue.length > 0) { process(); } }")
        loop = next(n for n in body if isinstance(n, LoopNode))
        assert loop.collection == "queue.length > 0"

    def test_typescript_while_outer_parens_stripped(self):
        """condition フィールドが parenthesized_expression でも外側の括弧を除去する。"""
        body = _ts_body("function f() { while (x > 0) { x--; } }")
        loop = next(n for n in body if isinstance(n, LoopNode))
        assert not loop.collection.startswith("(")

    def test_typescript_while_body_extracted(self):
        body = _ts_body("function f() { while (n > 0) { total += n; } }")
        loop = next(n for n in body if isinstance(n, LoopNode))
        assert len(loop.body) == 1
        assert isinstance(loop.body[0], DataTransformation)

    def test_python_while_is_while_type(self):
        body = _py_body("def f():\n    while retries < MAX:\n        attempt()\n")
        loops = [n for n in body if isinstance(n, LoopNode)]
        assert len(loops) == 1
        assert loops[0].loop_type == "WHILE"

    def test_python_while_condition_extracted(self):
        body = _py_body("def f():\n    while retries < MAX:\n        attempt()\n")
        loop = next(n for n in body if isinstance(n, LoopNode))
        assert loop.collection == "retries < MAX"

    # --- do-while ループ（TypeScript）---

    def test_typescript_do_while_is_do_while_type(self):
        body = _ts_body("function f() { do { step(); } while (running); }")
        loops = [n for n in body if isinstance(n, LoopNode)]
        assert len(loops) == 1
        assert loops[0].loop_type == "DO_WHILE"

    def test_typescript_do_while_condition_extracted(self):
        body = _ts_body("function f() { do { step(); } while (n > 0); }")
        loop = next(n for n in body if isinstance(n, LoopNode))
        assert loop.collection == "n > 0"

    def test_typescript_do_while_body_extracted(self):
        body = _ts_body("function f() { do { total += 1; } while (running); }")
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

    # --- TypeScript アロー関数の誤分類防止 ---

    def test_ts_arrow_function_not_in_module_variables(self):
        """アロー関数は module_variables に含まれない。"""
        spec = _ts_module("const greet = (name: string): string => name;\nfunction f() {}")
        assert all(v.name != "greet" for v in spec.module_variables)

    def test_ts_arrow_function_generates_warning(self):
        """アロー関数は extraction_warnings に追加される。"""
        spec = _ts_module("const greet = (name: string): string => name;\nfunction f() {}")
        assert any("greet" in w for w in spec.extraction_warnings)

    def test_ts_arrow_function_warning_mentions_function(self):
        """警告メッセージに function 宣言への変換について言及する。"""
        spec = _ts_module("const fn = (x: number) => x + 1;\nfunction f() {}")
        warning = next(w for w in spec.extraction_warnings if "fn" in w)
        assert "function" in warning

    def test_ts_non_arrow_const_still_captured(self):
        """通常の const はアロー関数修正後も module_variables に残る。"""
        spec = _ts_module("const MAX = 100;\nconst greet = (x: string) => x;\nfunction f() {}")
        assert any(v.name == "MAX" for v in spec.module_variables)
        assert not any(v.name == "greet" for v in spec.module_variables)

    def test_ts_multiline_arrow_function_not_captured(self):
        """複数行のアロー関数も module_variables に含まれない。"""
        src = "const process = (items: string[]): void => {\n  items.forEach(i => console.log(i));\n};\nfunction f() {}"
        spec = _ts_module(src)
        assert all(v.name != "process" for v in spec.module_variables)
        assert any("process" in w for w in spec.extraction_warnings)


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

    def test_py_docstring_not_listed_in_extraction_warnings(self):
        """関数 docstring は description として抽出済みなので警告に含めない。"""
        src = (
            'def calc(x: int) -> int:\n'
            '    """これは関数の説明 docstring。"""\n'
            '    return x + 1\n'
        )
        spec = _py_module(src)
        for warning in spec.extraction_warnings:
            assert "docstring" not in warning
            assert "これは関数の説明" not in warning

    def test_py_triple_quoted_docstring_only_function_has_no_warnings(self):
        """docstring 単独の関数（pass すらない）でも警告に出ない。"""
        src = 'def f():\n    """説明のみ。"""\n'
        spec = _py_module(src)
        assert spec.extraction_warnings == ()

    def test_py_single_quoted_docstring_excluded_from_warnings(self):
        """単行 docstring も警告から除外される。"""
        src = "def f():\n    '単行docstring'\n    pass\n"
        spec = _py_module(src)
        for warning in spec.extraction_warnings:
            assert "単行docstring" not in warning

    def test_py_string_only_statement_in_middle_still_warned(self):
        """body 途中の string-only expression_statement は docstring ではないので警告対象のまま。"""
        src = (
            'def f():\n'
            '    """先頭の docstring。"""\n'
            '    x = 1\n'
            '    "中間の浮いた文字列"\n'
            '    return x\n'
        )
        spec = _py_module(src)
        warnings_text = "\n".join(spec.extraction_warnings)
        assert "中間の浮いた文字列" in warnings_text
        assert "先頭の docstring" not in warnings_text

    # --- Python no-op 文（pass / ...）は警告に出ない ---

    def test_py_pass_statement_does_not_warn(self):
        """`pass` は syntactic placeholder であって未対応構文ではないため警告に出ない。"""
        src = "def f():\n    pass\n"
        spec = _py_module(src)
        assert spec.extraction_warnings == ()

    def test_py_ellipsis_stub_does_not_warn(self):
        """`...` を body とするスタブ関数も警告に出ない。"""
        src = "def f():\n    ...\n"
        spec = _py_module(src)
        assert spec.extraction_warnings == ()

    def test_py_pass_mixed_with_real_statements_does_not_warn_pass(self):
        """body 内に意味のある文と pass が混在しても、pass 自体は警告に出ない。"""
        src = (
            "def f(x):\n"
            "    if x < 0:\n"
            "        pass\n"
            "    return x\n"
        )
        spec = _py_module(src)
        warnings_text = "\n".join(spec.extraction_warnings)
        assert "pass_statement" not in warnings_text

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

    def test_py_guard_clause_leading_comment_extracted(self):
        """
        Python の関数ブロック先頭コメントは tree-sitter が
        function_definition の直下（: と block の間）に配置するが、
        フォールバック処理により GuardClause の comment フィールドに正しく取り込まれる。
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
        assert "前提条件チェック" in guard.comment


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

    def test_go_while_style_for_is_while_type(self):
        """Go の `for condition { }` は WHILE として検出される。"""
        src = (
            "package main\n"
            "func f() {\n"
            "  for queue.Len() > 0 {\n"
            "    process()\n"
            "  }\n"
            "}\n"
        )
        body = _go_body(src)
        loops = [n for n in body if isinstance(n, LoopNode)]
        assert len(loops) == 1
        assert loops[0].loop_type == "WHILE"

    def test_go_while_style_for_condition_extracted(self):
        src = (
            "package main\n"
            "func f() {\n"
            "  for n > 0 {\n"
            "    n--\n"
            "  }\n"
            "}\n"
        )
        body = _go_body(src)
        loop = next(n for n in body if isinstance(n, LoopNode))
        assert loop.collection == "n > 0"


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


# ---------------------------------------------------------------------------
# Python クラス定義（@dataclass / class）の抽出テスト
# ---------------------------------------------------------------------------


class TestPyClassDefinition:
    """Python の @dataclass / class 定義が ClassSpec に正しく変換されることを検証する。"""

    def test_dataclass_detected_as_is_dataclass_true(self):
        src = (
            "from dataclasses import dataclass\n"
            "@dataclass(frozen=True)\n"
            "class Config:\n"
            "    host: str\n"
        )
        spec = _py_module(src)
        assert len(spec.class_definitions) == 1
        assert spec.class_definitions[0].is_dataclass is True

    def test_plain_class_detected_as_is_dataclass_false(self):
        src = (
            "class MyClass:\n"
            "    x: int\n"
        )
        spec = _py_module(src)
        assert len(spec.class_definitions) == 1
        assert spec.class_definitions[0].is_dataclass is False

    def test_class_name_extracted(self):
        src = (
            "@dataclass(frozen=True)\n"
            "class LanguageProfile:\n"
            "    name: str\n"
        )
        spec = _py_module(src)
        assert spec.class_definitions[0].name == "LanguageProfile"

    def test_field_name_and_type_extracted(self):
        src = (
            "@dataclass\n"
            "class Point:\n"
            "    x: int\n"
            "    y: float\n"
        )
        spec = _py_module(src)
        cls = spec.class_definitions[0]
        assert len(cls.fields) == 2
        assert cls.fields[0].name == "x"
        assert cls.fields[0].type_text == "int"
        assert cls.fields[1].name == "y"
        assert cls.fields[1].type_text == "float"

    def test_field_with_default_value_extracted(self):
        src = (
            "@dataclass\n"
            "class Config:\n"
            "    host: str\n"
            "    port: int = 8080\n"
        )
        spec = _py_module(src)
        fields = spec.class_definitions[0].fields
        assert fields[0].default_text == ""     # host: デフォルトなし
        assert fields[1].default_text == "8080"  # port: デフォルト 8080

    def test_field_inline_comment_extracted(self):
        src = (
            "@dataclass\n"
            "class Config:\n"
            "    host: str  # サーバーホスト名\n"
        )
        spec = _py_module(src)
        assert "サーバーホスト名" in spec.class_definitions[0].fields[0].comment

    def test_field_preceding_block_comment_ignored(self):
        """フィールドの前の行コメントはインラインコメントとして拾わない。"""
        src = (
            "@dataclass\n"
            "class Config:\n"
            "    # これは次のフィールドの説明\n"
            "    host: str\n"
        )
        spec = _py_module(src)
        # フィールドは抽出される（コメントは空）
        assert spec.class_definitions[0].fields[0].name == "host"
        assert spec.class_definitions[0].fields[0].comment == ""

    def test_class_docstring_extracted(self):
        src = (
            "@dataclass\n"
            "class Config:\n"
            '    """設定値を保持する。"""\n'
            "    host: str\n"
        )
        spec = _py_module(src)
        assert "設定値を保持する" in spec.class_definitions[0].description

    def test_multiple_classes_all_extracted(self):
        src = (
            "@dataclass\n"
            "class A:\n"
            "    x: int\n"
            "@dataclass\n"
            "class B:\n"
            "    y: str\n"
        )
        spec = _py_module(src)
        assert len(spec.class_definitions) == 2
        names = [c.name for c in spec.class_definitions]
        assert "A" in names
        assert "B" in names

    def test_decorated_function_not_treated_as_class(self):
        """デコレータ付き関数は class_definitions に含まれない。"""
        src = (
            "def my_decorator(f): return f\n"
            "@my_decorator\n"
            "def my_func(): pass\n"
        )
        spec = _py_module(src)
        assert len(spec.class_definitions) == 0

    def test_class_and_function_coexist(self):
        """クラス定義と関数定義が共存する場合も正しく分離される。"""
        src = (
            "@dataclass\n"
            "class Config:\n"
            "    host: str\n"
            "def do_work(): pass\n"
        )
        spec = _py_module(src)
        assert len(spec.class_definitions) == 1
        assert len(spec.functions) == 1
        assert spec.class_definitions[0].name == "Config"
        assert spec.functions[0].name == "do_work"

    def test_typescript_has_no_class_definitions(self):
        """TypeScript ソースでは class_definitions が空になる。"""
        src = "function f(): void {}\n"
        spec = _ts_module(src)
        assert spec.class_definitions == ()

    def test_go_has_no_class_definitions(self):
        """Go ソースでは class_definitions が空になる（Go にクラスは存在しない）。"""
        src = "package main\nfunc f() {}\n"
        spec = _go_module(src)
        assert spec.class_definitions == ()

    def test_generic_type_annotation_extracted(self):
        """frozenset[str] のようなジェネリック型も正しく抽出される。"""
        src = (
            "@dataclass\n"
            "class Profile:\n"
            "    tags: frozenset[str]\n"
        )
        spec = _py_module(src)
        assert "frozenset[str]" in spec.class_definitions[0].fields[0].type_text

    def test_method_only_class_extracted_with_no_fields(self):
        """メソッドのみのクラス（型アノテーション付きフィールドなし・非 dataclass）も
        class_definitions に含まれる。フィールドが空なだけでクラスとして抽出する。
        レンダラー側でフィールドなしの場合はプレースホルダーを出さずに正しく表示する。"""
        src = (
            "class TestConfig:\n"
            "    def test_something(self): pass\n"
            "    def test_other(self): pass\n"
        )
        spec = _py_module(src)
        assert len(spec.class_definitions) == 1
        assert spec.class_definitions[0].name == "TestConfig"
        assert spec.class_definitions[0].is_dataclass is False
        assert len(spec.class_definitions[0].fields) == 0

    def test_dataclass_with_no_fields_extracted(self):
        """@dataclass が付いているクラスは、フィールドがなくても class_definitions に含まれる。
        フィールドなし dataclass は有効なパターン（frozen=True の空コンテナ等）。"""
        src = (
            "@dataclass(frozen=True)\n"
            "class Empty:\n"
            "    pass\n"
        )
        spec = _py_module(src)
        assert len(spec.class_definitions) == 1
        assert spec.class_definitions[0].name == "Empty"
        assert spec.class_definitions[0].is_dataclass is True
        assert len(spec.class_definitions[0].fields) == 0

    def test_class_methods_extracted(self):
        """クラス内のメソッドが ClassSpec.methods に含まれる。"""
        src = (
            "class TestFoo:\n"
            "    def test_one(self): pass\n"
            "    def test_two(self): pass\n"
            "    def test_three(self): pass\n"
        )
        spec = _py_module(src)
        cls = spec.class_definitions[0]
        assert len(cls.methods) == 3
        method_names = [m.name for m in cls.methods]
        assert method_names == ["test_one", "test_two", "test_three"]

    def test_class_method_with_docstring(self):
        """docstring 付きメソッドの description が FunctionSpec に抽出される。"""
        src = (
            "class MyClass:\n"
            '    def do_something(self):\n'
            '        """何かを実行する。"""\n'
            "        pass\n"
        )
        spec = _py_module(src)
        method = spec.class_definitions[0].methods[0]
        assert method.name == "do_something"
        assert "何かを実行する" in method.description

    def test_dataclass_with_fields_and_methods(self):
        """フィールドとメソッドが共存するクラスで両方が抽出される。"""
        src = (
            "@dataclass\n"
            "class Config:\n"
            "    host: str\n"
            "    port: int = 8080\n"
            "    def validate(self): pass\n"
            "    def reset(self): pass\n"
        )
        spec = _py_module(src)
        cls = spec.class_definitions[0]
        assert len(cls.fields) == 2
        assert len(cls.methods) == 2
        assert [m.name for m in cls.methods] == ["validate", "reset"]


# ---------------------------------------------------------------------------
# Java 言語サポートのテスト
# ---------------------------------------------------------------------------


def _java_module(source: str) -> ModuleSpec:
    """Java スニペットを解析して ModuleSpec を返す純粋ヘルパー。"""
    root = JAVA_PLUGIN.parse_source(source)
    return map_source_to_module_spec(root, "test", JAVA_PLUGIN)


def _java_class_body(source: str) -> tuple:
    """Java スニペットの最初のクラスの最初のメソッドの IR ノード列を返す。"""
    spec = _java_module(source)
    return spec.class_definitions[0].methods[0].body


class TestJavaClassDefinition:
    """Java の class_declaration が ClassSpec に正しく変換されることを検証する。"""

    def test_java_class_detected(self):
        src = "public class MyService {}\n"
        spec = _java_module(src)
        assert len(spec.class_definitions) == 1

    def test_java_class_name_extracted(self):
        src = "public class UserService {}\n"
        spec = _java_module(src)
        assert spec.class_definitions[0].name == "UserService"

    def test_java_class_is_not_dataclass(self):
        src = "public class Foo {}\n"
        spec = _java_module(src)
        assert spec.class_definitions[0].is_dataclass is False

    def test_java_class_javadoc_as_description(self):
        src = (
            "/** ユーザーサービスクラス */\n"
            "public class UserService {}\n"
        )
        spec = _java_module(src)
        assert "ユーザーサービスクラス" in spec.class_definitions[0].description

    def test_java_class_without_javadoc_has_empty_description(self):
        src = "public class Foo {}\n"
        spec = _java_module(src)
        assert spec.class_definitions[0].description == ""

    def test_java_has_no_top_level_functions(self):
        """Java はトップレベル関数がない — functions は空になる。"""
        src = (
            "public class Foo {\n"
            "    public static void bar() {}\n"
            "}\n"
        )
        spec = _java_module(src)
        assert spec.functions == ()

    def test_java_method_extracted_into_class(self):
        src = (
            "public class Foo {\n"
            "    public static void bar() {}\n"
            "}\n"
        )
        spec = _java_module(src)
        cls = spec.class_definitions[0]
        assert len(cls.methods) == 1
        assert cls.methods[0].name == "bar"

    def test_java_multiple_methods_all_extracted(self):
        src = (
            "public class Svc {\n"
            "    public void a() {}\n"
            "    public void b() {}\n"
            "    public void c() {}\n"
            "}\n"
        )
        spec = _java_module(src)
        cls = spec.class_definitions[0]
        assert len(cls.methods) == 3
        names = [m.name for m in cls.methods]
        assert names == ["a", "b", "c"]

    def test_java_method_javadoc_as_description(self):
        src = (
            "public class Svc {\n"
            "    /** 合計を計算する */\n"
            "    public int sum(int a, int b) { return a + b; }\n"
            "}\n"
        )
        spec = _java_module(src)
        method = spec.class_definitions[0].methods[0]
        assert "合計を計算する" in method.description

    def test_java_method_return_type_extracted(self):
        src = (
            "public class Svc {\n"
            "    public String getName() { return name; }\n"
            "}\n"
        )
        spec = _java_module(src)
        method = spec.class_definitions[0].methods[0]
        assert method.return_type == "String"

    def test_java_void_return_type_extracted(self):
        src = (
            "public class Svc {\n"
            "    public void doWork() {}\n"
            "}\n"
        )
        spec = _java_module(src)
        method = spec.class_definitions[0].methods[0]
        assert method.return_type == "void"

    def test_java_method_params_extracted(self):
        src = (
            "public class Svc {\n"
            "    public void process(String name, int count) {}\n"
            "}\n"
        )
        spec = _java_module(src)
        method = spec.class_definitions[0].methods[0]
        assert len(method.params) == 2
        assert method.params[0].name == "name"
        assert method.params[0].type_text == "String"
        assert method.params[1].name == "count"
        assert method.params[1].type_text == "int"

    def test_java_generic_type_param_extracted(self):
        src = (
            "import java.util.List;\n"
            "public class Svc {\n"
            "    public int sum(List<Integer> nums) { return 0; }\n"
            "}\n"
        )
        spec = _java_module(src)
        method = spec.class_definitions[0].methods[0]
        assert "List" in method.params[0].type_text


class TestJavaImports:
    """Java の import_declaration が ImportSpec に正しく変換されることを検証する。"""

    def test_java_single_import_detected(self):
        src = (
            "import java.util.List;\n"
            "public class Foo {}\n"
        )
        spec = _java_module(src)
        assert len(spec.imports) == 1

    def test_java_import_module_name(self):
        src = (
            "import java.util.List;\n"
            "public class Foo {}\n"
        )
        spec = _java_module(src)
        assert spec.imports[0].source_module == "java.util"

    def test_java_import_class_name(self):
        src = (
            "import java.util.List;\n"
            "public class Foo {}\n"
        )
        spec = _java_module(src)
        assert "List" in spec.imports[0].imported_names

    def test_java_wildcard_import_no_class_name(self):
        src = (
            "import java.util.*;\n"
            "public class Foo {}\n"
        )
        spec = _java_module(src)
        assert spec.imports[0].source_module == "java.util"
        assert spec.imports[0].imported_names == ()

    def test_java_multiple_imports_detected(self):
        src = (
            "import java.util.List;\n"
            "import java.io.IOException;\n"
            "public class Foo {}\n"
        )
        spec = _java_module(src)
        assert len(spec.imports) == 2

    def test_java_multiple_imports_modules(self):
        src = (
            "import java.util.List;\n"
            "import java.io.IOException;\n"
            "public class Foo {}\n"
        )
        spec = _java_module(src)
        modules = {s.source_module for s in spec.imports}
        assert "java.util" in modules
        assert "java.io" in modules


class TestJavaGuardClause:
    """Java のガード句（throw で早期中断）が GuardClause に変換されることを検証する。"""

    def test_java_throw_guard_clause_detected(self):
        src = (
            "public class Svc {\n"
            "    public void check(String s) {\n"
            "        if (s == null) {\n"
            '            throw new IllegalArgumentException("null");\n'
            "        }\n"
            "    }\n"
            "}\n"
        )
        body = _java_class_body(src)
        assert isinstance(body[0], GuardClause)

    def test_java_guard_clause_condition_text(self):
        src = (
            "public class Svc {\n"
            "    public void check(String s) {\n"
            "        if (s == null) {\n"
            '            throw new IllegalArgumentException("null");\n'
            "        }\n"
            "    }\n"
            "}\n"
        )
        body = _java_class_body(src)
        assert "s == null" in body[0].condition_text

    def test_java_guard_clause_throw_action(self):
        src = (
            "public class Svc {\n"
            "    public void check(String s) {\n"
            "        if (s == null) {\n"
            '            throw new RuntimeException("err");\n'
            "        }\n"
            "    }\n"
            "}\n"
        )
        body = _java_class_body(src)
        assert "スローして処理を中断する" in body[0].action_text

    def test_java_return_guard_clause_detected(self):
        src = (
            "public class Svc {\n"
            "    public int safe(int x) {\n"
            "        if (x < 0) { return 0; }\n"
            "        return x;\n"
            "    }\n"
            "}\n"
        )
        body = _java_class_body(src)
        assert isinstance(body[0], GuardClause)
        assert "処理を終了する" in body[0].action_text

    def test_java_if_else_not_guard_clause(self):
        src = (
            "public class Svc {\n"
            "    public int abs(int x) {\n"
            "        if (x >= 0) { return x; } else { return -x; }\n"
            "    }\n"
            "}\n"
        )
        body = _java_class_body(src)
        assert isinstance(body[0], ConditionBlock)


class TestJavaForEachLoop:
    """Java の enhanced_for_statement が LoopNode (FOR_EACH) に変換されることを検証する。"""

    def test_java_foreach_detected_as_loop_node(self):
        src = (
            "import java.util.List;\n"
            "public class Svc {\n"
            "    public void process(List<String> items) {\n"
            "        for (String item : items) {}\n"
            "    }\n"
            "}\n"
        )
        body = _java_class_body(src)
        assert isinstance(body[0], LoopNode)
        assert body[0].loop_type == "FOR_EACH"

    def test_java_foreach_collection(self):
        src = (
            "import java.util.List;\n"
            "public class Svc {\n"
            "    public void process(List<String> items) {\n"
            "        for (String item : items) {}\n"
            "    }\n"
            "}\n"
        )
        body = _java_class_body(src)
        assert body[0].collection == "items"

    def test_java_foreach_iterator(self):
        src = (
            "import java.util.List;\n"
            "public class Svc {\n"
            "    public void process(List<String> items) {\n"
            "        for (String item : items) {}\n"
            "    }\n"
            "}\n"
        )
        body = _java_class_body(src)
        assert body[0].iterator == "item"

    def test_java_foreach_body_extracted(self):
        src = (
            "import java.util.List;\n"
            "public class Svc {\n"
            "    public void sum(List<Integer> nums) {\n"
            "        int total = 0;\n"
            "        for (int n : nums) {\n"
            "            total += n;\n"
            "        }\n"
            "    }\n"
            "}\n"
        )
        body = _java_class_body(src)
        loop = body[1]
        assert isinstance(loop, LoopNode)
        assert len(loop.body) == 1
        assert isinstance(loop.body[0], DataTransformation)
        assert loop.body[0].operation == "ADD"


class TestJavaDataTransformation:
    """Java の変数宣言・代入が DataTransformation に変換されることを検証する。"""

    def test_java_local_var_decl_is_data_transformation(self):
        src = (
            "public class Svc {\n"
            "    public void f() {\n"
            "        int total = 0;\n"
            "    }\n"
            "}\n"
        )
        body = _java_class_body(src)
        assert isinstance(body[0], DataTransformation)
        assert body[0].operation == "ASSIGN"

    def test_java_local_var_decl_target(self):
        src = (
            "public class Svc {\n"
            "    public void f() {\n"
            "        int total = 0;\n"
            "    }\n"
            "}\n"
        )
        body = _java_class_body(src)
        assert body[0].target == "total"

    def test_java_local_var_decl_value(self):
        src = (
            "public class Svc {\n"
            "    public void f() {\n"
            "        int total = 0;\n"
            "    }\n"
            "}\n"
        )
        body = _java_class_body(src)
        assert body[0].value == "0"

    def test_java_augmented_assignment_add(self):
        src = (
            "public class Svc {\n"
            "    public void f() {\n"
            "        int x = 0;\n"
            "        x += 5;\n"
            "    }\n"
            "}\n"
        )
        body = _java_class_body(src)
        assert isinstance(body[1], DataTransformation)
        assert body[1].operation == "ADD"

    def test_java_simple_assignment(self):
        src = (
            "public class Svc {\n"
            "    public void f() {\n"
            "        int x = 0;\n"
            "        x = 10;\n"
            "    }\n"
            "}\n"
        )
        body = _java_class_body(src)
        assert isinstance(body[1], DataTransformation)
        assert body[1].operation == "ASSIGN"


class TestJavaConditionBlock:
    """Java の if/else-if/else が ConditionBlock に変換されることを検証する。"""

    def test_java_if_else_is_condition_block(self):
        src = (
            "public class Svc {\n"
            "    public int abs(int x) {\n"
            "        if (x >= 0) { return x; } else { return -x; }\n"
            "    }\n"
            "}\n"
        )
        body = _java_class_body(src)
        assert isinstance(body[0], ConditionBlock)

    def test_java_if_else_has_two_cases(self):
        src = (
            "public class Svc {\n"
            "    public int abs(int x) {\n"
            "        if (x >= 0) { return x; } else { return -x; }\n"
            "    }\n"
            "}\n"
        )
        body = _java_class_body(src)
        assert len(body[0].cases) == 2

    def test_java_else_if_chain_has_three_cases(self):
        src = (
            "public class Svc {\n"
            "    public String grade(int s) {\n"
            '        if (s >= 90) { return "S"; }\n'
            '        else if (s >= 70) { return "B"; }\n'
            '        else { return "C"; }\n'
            "    }\n"
            "}\n"
        )
        body = _java_class_body(src)
        assert isinstance(body[0], ConditionBlock)
        assert len(body[0].cases) == 3

    def test_java_condition_text_strips_outer_parens(self):
        """Java の条件式は parenthesized_expression — 外側の括弧は除去される。"""
        src = (
            "public class Svc {\n"
            "    public int sign(int x) {\n"
            "        if (x > 0) { return 1; } else { return -1; }\n"
            "    }\n"
            "}\n"
        )
        body = _java_class_body(src)
        assert body[0].cases[0].condition_text == "x > 0"

    def test_java_else_case_default_condition(self):
        src = (
            "public class Svc {\n"
            "    public int f(int x) {\n"
            "        if (x > 0) { return 1; } else { return -1; }\n"
            "    }\n"
            "}\n"
        )
        body = _java_class_body(src)
        assert "デフォルト" in body[0].cases[1].condition_text


class TestJavaTryCatchNode:
    """Java の try/catch/finally が TryCatchNode に変換されることを検証する。"""

    def test_java_try_catch_finally_is_extracted(self):
        src = (
            "public class Svc {\n"
            "    public void f() {\n"
            "        try { int x = work(); }\n"
            "        catch (Exception error) { log(error); throw error; }\n"
            "        finally { cleanup(); }\n"
            "    }\n"
            "}\n"
        )
        node = _java_class_body(src)[0]
        assert isinstance(node, TryCatchNode)
        assert node.catch_var == "error"
        assert isinstance(node.try_body[0], DataTransformation)
        assert isinstance(node.catch_body[0], SideEffect)
        assert isinstance(node.catch_body[1], ReturnNode)
        assert isinstance(node.finally_body[0], SideEffect)


# ---------------------------------------------------------------------------
# トップレベル未対応宣言の警告化
# ---------------------------------------------------------------------------


class TestTopLevelExtractionWarnings:
    """トップレベルで認識されなかった宣言が extraction_warnings に追加されるか検証。"""

    # --- TypeScript: class_declaration は未対応 → 警告 ---

    def test_ts_class_declaration_appears_in_warnings(self):
        src = "class AuditLog { add(message: string): void {} }\n"
        spec = _ts_module(src)
        warnings_text = "\n".join(spec.extraction_warnings)
        assert "class_declaration" in warnings_text
        assert "AuditLog" in warnings_text

    def test_ts_class_warning_has_top_level_scope(self):
        src = "class Foo {}\n"
        spec = _ts_module(src)
        warnings_text = "\n".join(spec.extraction_warnings)
        assert "トップレベル" in warnings_text

    def test_ts_recognized_top_level_does_not_warn(self):
        """interface / type / function / import / const は警告に出ない。"""
        src = (
            "import { x } from 'm';\n"
            "const y = 1;\n"
            "type T = string;\n"
            "interface I { a: number }\n"
            "function f() {}\n"
        )
        spec = _ts_module(src)
        assert spec.extraction_warnings == ()

    def test_ts_top_level_console_log_appears_in_warnings(self):
        """モジュール直下の expression_statement は recognized 集合に含まれず警告される。"""
        src = 'console.log("at module top");\n'
        spec = _ts_module(src)
        warnings_text = "\n".join(spec.extraction_warnings)
        assert "expression_statement" in warnings_text

    # --- Go: type_declaration は未対応 → 警告 / package_clause は無視 ---

    def test_go_type_declaration_appears_in_warnings(self):
        src = (
            "package main\n\n"
            "type Purchase struct {\n"
            "    Price int\n"
            "}\n"
        )
        spec = _go_module(src)
        warnings_text = "\n".join(spec.extraction_warnings)
        assert "type_declaration" in warnings_text
        assert "Purchase" in warnings_text

    def test_go_package_clause_does_not_warn(self):
        src = "package main\n\nfunc f() {}\n"
        spec = _go_module(src)
        warnings_text = "\n".join(spec.extraction_warnings)
        assert "package_clause" not in warnings_text

    def test_go_recognized_top_level_does_not_warn(self):
        """import / const / var / func は警告に出ない。"""
        src = (
            "package main\n\n"
            'import "fmt"\n\n'
            "const Max = 10\n"
            "var counter = 0\n"
            "func f() {}\n"
        )
        spec = _go_module(src)
        assert spec.extraction_warnings == ()

    # --- Python: モジュール docstring とコメントは無視 ---

    def test_py_module_docstring_does_not_warn(self):
        src = '"""モジュールの説明。"""\n\ndef f():\n    pass\n'
        spec = _py_module(src)
        warnings_text = "\n".join(spec.extraction_warnings)
        assert "モジュールの説明" not in warnings_text

    def test_py_top_level_comment_does_not_warn(self):
        src = "# ファイル冒頭コメント\ndef f():\n    pass\n"
        spec = _py_module(src)
        assert spec.extraction_warnings == ()

    def test_py_class_definition_is_recognized(self):
        """Python の class は class_extractor が処理するので警告しない。"""
        src = "class Foo:\n    x: int = 0\n"
        spec = _py_module(src)
        assert spec.extraction_warnings == ()

    # --- PowerShell: class は未対応 → 警告 ---

    def test_ps_class_definition_appears_in_warnings(self):
        src = (
            "class Purchase {\n"
            "    [int]$Price\n"
            "}\n"
            "function Get-Foo {}\n"
        )
        spec = _ps_module(src)
        warnings_text = "\n".join(spec.extraction_warnings)
        # PowerShell の class 文ノードは class_statement / class_definition のいずれか
        # tree-sitter-powershell の実装に依存するため、'class' という単語が警告に
        # 含まれていることを確認する（ノードタイプ・スニペット双方を含む）。
        assert "Purchase" in warnings_text


# ---------------------------------------------------------------------------
# async / await マーカー
# ---------------------------------------------------------------------------


class TestAsyncFunction:
    """FunctionSpec.is_async: async 宣言の検出テスト"""

    def test_ts_async_function_is_marked(self):
        src = "async function fetchUser(id: number): Promise<string> { return ''; }"
        spec = _ts_module(src)
        assert spec.functions[0].is_async is True

    def test_ts_regular_function_is_not_async(self):
        src = "function fetchUser(id: number): string { return ''; }"
        spec = _ts_module(src)
        assert spec.functions[0].is_async is False

    def test_py_async_function_is_marked(self):
        src = "async def fetch_data(url: str) -> str:\n    return url\n"
        spec = _py_module(src)
        assert spec.functions[0].is_async is True

    def test_py_regular_function_is_not_async(self):
        src = "def fetch_data(url: str) -> str:\n    return url\n"
        spec = _py_module(src)
        assert spec.functions[0].is_async is False


class TestAwaitedExpressions:
    """SideEffect.is_awaited / DataTransformation.is_awaited の検出テスト"""

    # --- TypeScript: スタンドアロン await（SideEffect） ---

    def test_ts_standalone_await_is_side_effect(self):
        src = "async function f() { await doSomething(); }"
        body = _ts_body(src)
        assert isinstance(body[0], SideEffect)

    def test_ts_standalone_await_is_awaited(self):
        src = "async function f() { await doSomething(); }"
        body = _ts_body(src)
        assert body[0].is_awaited is True

    def test_ts_standalone_await_description_includes_await(self):
        src = "async function f() { await doSomething(); }"
        body = _ts_body(src)
        assert "await" in body[0].description

    def test_ts_regular_call_is_not_awaited(self):
        src = "function f() { console.log('hi'); }"
        body = _ts_body(src)
        assert body[0].is_awaited is False

    # --- TypeScript: await を含む変数宣言（DataTransformation） ---

    def test_ts_lexical_await_is_data_transformation(self):
        src = "async function f() { const data = await fetchData(1); }"
        body = _ts_body(src)
        assert isinstance(body[0], DataTransformation)

    def test_ts_lexical_await_is_awaited(self):
        src = "async function f() { const data = await fetchData(1); }"
        body = _ts_body(src)
        assert body[0].is_awaited is True

    def test_ts_lexical_await_value_text(self):
        src = "async function f() { const data = await fetchData(1); }"
        body = _ts_body(src)
        assert "await" in body[0].value

    def test_ts_lexical_no_await_is_not_awaited(self):
        src = "function f() { const x = getValue(); }"
        body = _ts_body(src)
        assert body[0].is_awaited is False

    # --- TypeScript: await を含む代入式（DataTransformation） ---

    def test_ts_assignment_await_is_awaited(self):
        src = "async function f() { result = await processData(); }"
        body = _ts_body(src)
        assert isinstance(body[0], DataTransformation)
        assert body[0].is_awaited is True

    # --- Python: スタンドアロン await（SideEffect） ---

    def test_py_standalone_await_is_awaited(self):
        src = "async def f():\n    await do_something()\n"
        body = _py_body(src)
        assert isinstance(body[0], SideEffect)
        assert body[0].is_awaited is True

    # --- Python: await を含む代入（DataTransformation） ---

    def test_py_assignment_await_is_awaited(self):
        src = "async def f():\n    data = await fetch_data(1)\n"
        body = _py_body(src)
        assert isinstance(body[0], DataTransformation)
        assert body[0].is_awaited is True
