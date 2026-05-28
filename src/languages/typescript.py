"""
TypeScript 言語プラグイン

このファイルを src/languages/ に置くだけで、パイプラインが
.ts / .tsx ファイルを自動的に処理できるようになる。
"""
from __future__ import annotations

from typing import Optional

from tree_sitter import Node

from ..ir.node_utils import extract_node_text, normalize_whitespace
from ..ir.profiles import LanguageProfile
from ..ir.types import CaseNode, ImportSpec, IRNode, ModuleVariableSpec, ParamSpec, SwitchNode, TypeDefinitionSpec
from ..parser.ts_parser import parse_typescript_source
from . import LanguagePlugin

# ---------------------------------------------------------------------------
# LanguageProfile 定数
# ---------------------------------------------------------------------------

TYPESCRIPT_PROFILE = LanguageProfile(
    name="typescript",
    function_node_type="function_declaration",
    for_each_node_type="for_in_statement",
    for_range_node_type="for_statement",
    guard_action_types=frozenset({"return_statement", "throw_statement"}),
    condition_has_outer_parens=True,
    augmented_assignment_type="augmented_assignment_expression",
    assignment_type="assignment_expression",
    call_type="call_expression",
    elif_structure="nested",
    lexical_declaration_types=frozenset({"lexical_declaration", "variable_declaration"}),
    import_node_types=frozenset({"import_statement"}),
    module_var_node_types=frozenset({"lexical_declaration"}),
    type_alias_node_type="type_alias_declaration",
    interface_node_type="interface_declaration",
    block_inner_node_type="",
    has_module_docstring=False,
    for_loop_flavor="of_keyword",
    direct_statement_types=frozenset(),
    class_node_types=frozenset(),  # TypeScript クラスは将来対応
    while_node_type="while_statement",
    do_while_node_type="do_statement",
    switch_node_type="switch_statement",
    await_expression_type="await_expression",
)


# ---------------------------------------------------------------------------
# インポート抽出
# ---------------------------------------------------------------------------

def _extract_ts_import(import_node: Node) -> Optional[ImportSpec]:
    """
    TypeScript の import_statement ノードから ImportSpec を生成する。

    対応パターン:
    - import React from 'react'            → default import
    - import { A, B } from 'react'         → named imports
    - import * as _ from 'lodash'          → namespace import
    - import 'side-effect'                 → side-effect import（names=()）
    """
    source_module = ""
    for child in import_node.children:
        if child.type == "string":
            raw = extract_node_text(child)
            source_module = raw.strip("'\"` ")

    imported_names: list[str] = []
    alias = ""

    for child in import_node.children:
        if child.type == "import_clause":
            for clause_child in child.children:
                if clause_child.type == "identifier":
                    imported_names.append(extract_node_text(clause_child))
                elif clause_child.type == "namespace_import":
                    alias = "*"
                    for ns_child in clause_child.children:
                        if ns_child.type == "identifier":
                            alias = extract_node_text(ns_child)
                elif clause_child.type == "named_imports":
                    for spec in clause_child.children:
                        if spec.type == "import_specifier":
                            name_node = spec.child_by_field_name("name")
                            if name_node is not None:
                                imported_names.append(extract_node_text(name_node))

    return ImportSpec(
        kind="ImportSpec",
        source_module=source_module,
        imported_names=tuple(imported_names),
        alias=alias,
    )


def extract_ts_import_list(node: Node) -> list[ImportSpec]:
    """TypeScript の import_statement 1ノードから ImportSpec リストを返す。"""
    spec = _extract_ts_import(node)
    return [spec] if spec is not None else []


# ---------------------------------------------------------------------------
# モジュール変数抽出
# ---------------------------------------------------------------------------

def _get_ts_declarator(node: Node):
    """lexical_declaration から variable_declarator を返す。"""
    return next(
        (c for c in node.named_children if c.type == "variable_declarator"),
        None,
    )


def extract_ts_module_variable(node: Node) -> Optional[ModuleVariableSpec]:
    """
    TypeScript トップレベルの lexical_declaration（const/let）から
    ModuleVariableSpec を生成する。

    value が arrow_function の場合は None を返す（警告は module_var_warning_extractor が担う）。
    """
    declarator = _get_ts_declarator(node)
    if declarator is None:
        return None

    name_node = declarator.child_by_field_name("name")
    value_node = declarator.child_by_field_name("value")

    if name_node is None or value_node is None:
        return None

    if value_node.type == "arrow_function":
        return None

    is_constant = any(
        child.type == "const" or extract_node_text(child) == "const"
        for child in node.children
        if not child.is_named
    )

    name = extract_node_text(name_node).strip()
    value_text = normalize_whitespace(extract_node_text(value_node))

    return ModuleVariableSpec(
        kind="ModuleVariableSpec",
        name=name,
        value_text=value_text,
        is_constant=is_constant,
    )


def ts_module_var_warning(node: Node) -> Optional[str]:
    """
    value が arrow_function の lexical_declaration に対して警告文字列を返す。

    extract_ts_module_variable が None を返したノードに対して mapper が呼び出す。
    アロー関数以外の理由で None になった場合（構文エラー等）は None を返す。
    """
    declarator = _get_ts_declarator(node)
    if declarator is None:
        return None
    value_node = declarator.child_by_field_name("value")
    if value_node is None or value_node.type != "arrow_function":
        return None
    name_node = declarator.child_by_field_name("name")
    name = extract_node_text(name_node).strip() if name_node is not None else "?"
    return f"アロー関数 `{name}` は仕様化対象外です（関数として仕様化するには function 宣言への変換が必要）"


# ---------------------------------------------------------------------------
# 型定義抽出
# ---------------------------------------------------------------------------

def extract_ts_type_definition(node: Node) -> Optional[TypeDefinitionSpec]:
    """
    TypeScript の type_alias_declaration / interface_declaration から
    TypeDefinitionSpec を生成する。
    """
    name_node = next(
        (c for c in node.named_children if c.type == "type_identifier"),
        None,
    )
    if name_node is None:
        return None

    name = extract_node_text(name_node).strip()

    if node.type == "type_alias_declaration":
        type_body_node = next(
            (c for c in node.named_children if c.type != "type_identifier"),
            None,
        )
        type_text = normalize_whitespace(extract_node_text(type_body_node)) if type_body_node else ""
        return TypeDefinitionSpec(
            kind="TypeDefinitionSpec",
            name=name,
            definition_kind="alias",
            type_text=type_text,
        )

    if node.type == "interface_declaration":
        body_node = next(
            (c for c in node.named_children if c.type == "interface_body"),
            None,
        )
        type_text = normalize_whitespace(extract_node_text(body_node)) if body_node else ""
        return TypeDefinitionSpec(
            kind="TypeDefinitionSpec",
            name=name,
            definition_kind="interface",
            type_text=type_text,
        )

    return None


# ---------------------------------------------------------------------------
# 引数・戻り値の型抽出
# ---------------------------------------------------------------------------

def _extract_ts_param_type(type_annotation_node: Node) -> str:
    """
    TypeScript の type_annotation ノードから型テキストを返す。

    type_annotation は ":" を含む（例: ": string", ": User"）。
    最初の named child が実際の型ノードであるため、それを取り出す。
    named child がない場合はテキストから ": " を除去してフォールバック。
    """
    inner = next((c for c in type_annotation_node.named_children), None)
    if inner is not None:
        return normalize_whitespace(extract_node_text(inner))
    return normalize_whitespace(extract_node_text(type_annotation_node)).lstrip(":").strip()


def extract_ts_params(fn_node: Node) -> tuple[ParamSpec, ...]:
    """
    TypeScript の function_declaration ノードから引数リストを抽出する。

    対応パターン:
      required_parameter:  (user: User)
      optional_parameter:  (limit?: number)
      optional_parameter with default: (id: number = 0)
      rest_parameter:      (...args: string[])
    """
    params_node = fn_node.child_by_field_name("parameters")
    if params_node is None:
        return ()

    result: list[ParamSpec] = []
    for child in params_node.named_children:
        if child.type in ("required_parameter", "optional_parameter"):
            pattern_node = child.child_by_field_name("pattern")
            type_node    = child.child_by_field_name("type")
            value_node   = child.child_by_field_name("value")

            name         = extract_node_text(pattern_node).strip() if pattern_node is not None else ""
            type_text    = _extract_ts_param_type(type_node) if type_node is not None else ""
            default_text = normalize_whitespace(extract_node_text(value_node)) if value_node is not None else ""

            result.append(ParamSpec(name=name, type_text=type_text, default_text=default_text))

        elif child.type == "rest_parameter":
            pattern_node = child.child_by_field_name("pattern")
            type_node    = child.child_by_field_name("type")

            name      = extract_node_text(pattern_node).strip() if pattern_node is not None else ""
            type_text = _extract_ts_param_type(type_node) if type_node is not None else ""

            result.append(ParamSpec(name=name, type_text=type_text, is_rest=True))

    return tuple(result)


def extract_ts_return_type(fn_node: Node) -> str:
    """
    TypeScript の function_declaration ノードから戻り値の型テキストを返す。

    return_type フィールドは type_annotation ノード（": ReturnType" の形）。
    最初の named child が実際の型。
    """
    rt_node = fn_node.child_by_field_name("return_type")
    if rt_node is None:
        return ""
    return _extract_ts_param_type(rt_node)


# ---------------------------------------------------------------------------
# switch 文抽出
# ---------------------------------------------------------------------------

def extract_ts_switch(
    switch_node: Node,
    extract_stmts: "Callable[[list[Node]], list[IRNode]]",
) -> Optional[SwitchNode]:
    """
    TypeScript の switch_statement から SwitchNode を生成する。

    switch (subject) {
      case X: stmts...
      default: stmts...
    }
    """
    from typing import Callable  # noqa: PLC0415 — ローカルインポートで循環回避

    subject_node = next(
        (c for c in switch_node.named_children if c.type == "parenthesized_expression"),
        None,
    )
    subject = normalize_whitespace(extract_node_text(subject_node)).strip("()") if subject_node else ""

    body_node = next(
        (c for c in switch_node.named_children if c.type == "switch_body"),
        None,
    )
    if body_node is None:
        return None

    cases: list[CaseNode] = []
    for case_node in body_node.named_children:
        if case_node.type == "switch_case":
            value_node = case_node.child_by_field_name("value")
            condition = extract_node_text(value_node).strip() if value_node else ""
            # body = value 以外の named_children（value_node の後のすべての文）
            body_stmts = [c for c in case_node.named_children if c is not value_node]
            cases.append(CaseNode(condition_text=condition, body=tuple(extract_stmts(body_stmts))))
        elif case_node.type == "switch_default":
            body_stmts = list(case_node.named_children)
            cases.append(CaseNode(condition_text="default", body=tuple(extract_stmts(body_stmts))))

    return SwitchNode(kind="SwitchNode", subject=subject, cases=tuple(cases))


# ---------------------------------------------------------------------------
# プラグイン定数（discover_plugins() が検出する）
# ---------------------------------------------------------------------------

PLUGIN = LanguagePlugin(
    extensions=(".ts", ".tsx"),
    profile=TYPESCRIPT_PROFILE,
    parse_source=parse_typescript_source,
    import_extractor=extract_ts_import_list,
    module_var_extractor=extract_ts_module_variable,
    type_def_extractor=extract_ts_type_definition,
    direct_statement_extractors=(),
    class_extractor=lambda _: None,  # TypeScript クラスは将来対応
    param_extractor=extract_ts_params,
    return_type_extractor=extract_ts_return_type,
    module_var_warning_extractor=ts_module_var_warning,
    switch_extractor=extract_ts_switch,
)
