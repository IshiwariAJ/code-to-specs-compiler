"""
ミドルウェア（IR Layer）: AST ノード → Universal IR

責務: tree-sitter の AST ノードを巡回し、言語固有の構文を
      言語に依存しない Universal IR オブジェクトにマッピングする。

設計方針（構造化プログラミング原則）:
- すべての関数は純粋関数（副作用なし）
- 1関数1責務: 各関数はひとつのマッピング処理のみを担う
- 言語差異は LanguageProfile（設定値）と LanguagePlugin（抽出関数）に委譲する
- このモジュール自体は言語名を一切参照しない
"""
from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Callable, Optional

from tree_sitter import Node

from .node_utils import extract_node_text, normalize_whitespace, strip_outer_parens
from .profiles import LanguageProfile
from .types import (
    CaseNode,
    ClassSpec,
    ConditionBlock,
    DataTransformation,
    FunctionSpec,
    GuardClause,
    ImportSpec,
    IRNode,
    LoopNode,
    ModuleSpec,
    ModuleVariableSpec,
    ParamSpec,
    ReturnNode,
    SideEffect,
    TryCatchNode,
    TypeDefinitionSpec,
)

if TYPE_CHECKING:
    from ..languages import LanguagePlugin

# DirectStmtMap: ノードタイプ → 変換関数（LanguagePlugin から構築）
# DataTransformation のほか SideEffect 等の IRNode を返せるよう Optional[IRNode] に拡張
_DirectStmtMap = dict[str, Callable[[Node], Optional[IRNode]]]


# ---------------------------------------------------------------------------
# ブロック操作
# ---------------------------------------------------------------------------


def _get_block_statements(block_node: Node, profile: LanguageProfile) -> list[Node]:
    """
    ブロックノードから文ノードのリストを返す。

    言語差異を吸収する:
    - TypeScript / Python: block の named_children が直接文ノードを含む
    - Go: block → statement_list → 文ノード の2段構造

    profile.block_inner_node_type が設定されている場合は1段深く潜る。
    コメントノードは除外する。
    """
    if profile.block_inner_node_type:
        inner = next(
            (c for c in block_node.named_children if c.type == profile.block_inner_node_type),
            None,
        )
        children = inner.named_children if inner is not None else []
    else:
        children = block_node.named_children
    return [c for c in children if c.type != "comment"]


# ---------------------------------------------------------------------------
# コメント抽出: 直前コメント / 関数説明 / ファイルヘッダー
# ---------------------------------------------------------------------------


def _get_preceding_comment(node: Node) -> str:
    """
    ノードの直前にある連続した comment ノードのテキストを結合して返す。

    複数行コメント（連続した // 行）を1つの文字列にまとめる。
    JSDoc ブロックコメント（/** */）は1ノードとして取得される。

    Python 特有の注意:
    tree-sitter-python は、関数ブロックの最初のコメントを block の内側ではなく
    function_definition の子（: と block の間）として配置する。
    そのため、ブロック先頭のノード（prev_named_sibling が None）については、
    親ノード（block）の直前の named sibling も確認するフォールバックを行う。
    """
    comments: list[str] = []
    prev = node.prev_named_sibling
    while prev is not None and prev.type == "comment":
        comments.insert(0, extract_node_text(prev))
        prev = prev.prev_named_sibling

    if comments:
        return "\n".join(comments)

    # フォールバック: ブロック先頭のノードで、親ノードの直前に comment がある場合
    # （Python の関数ブロック先頭コメントが function_definition 直下に置かれるケース）
    if node.prev_named_sibling is None and node.parent is not None:
        parent_prev = node.parent.prev_named_sibling
        if parent_prev is not None and parent_prev.type == "comment":
            return extract_node_text(parent_prev)

    return ""


def _get_function_description(fn_node: Node, plugin: "LanguagePlugin") -> str:
    """
    関数の説明文を返す。

    plugin.function_description_extractor が設定されている場合はそれを使う。
    なければ関数直前のコメントを返す（TypeScript / Go のデフォルト）。

    言語固有の抽出ロジック（Python docstring / PowerShell .SYNOPSIS）は
    各言語のプラグインファイル（python.py / powershell.py）に定義されている。
    """
    if plugin.function_description_extractor is not None:
        return plugin.function_description_extractor(fn_node)
    return _get_preceding_comment(fn_node)


def _get_file_header_comment(root_node: Node, profile: LanguageProfile) -> str:
    """
    ファイル先頭の連続したコメントノード（またはモジュール docstring）を返す。

    TypeScript / Go: 先頭に連続する comment ノードを結合する
    Python:          先頭の comment ノード群、または最初の expression_statement の string
    """
    comments: list[str] = []
    for child in root_node.named_children:
        if child.type == "comment":
            comments.append(extract_node_text(child))
        elif profile.has_module_docstring and child.type == "expression_statement":
            # モジュール docstring（最初の文が文字列リテラルの場合。Python など）
            string_node = next(
                (c for c in child.named_children if c.type == "string"),
                None,
            )
            if string_node is not None:
                comments.append(extract_node_text(string_node))
            break  # docstring の後は終了
        else:
            break  # コメント以外が出たら終了
    return "\n".join(comments) if comments else ""


# ---------------------------------------------------------------------------
# 判定: if 文がガード句パターンかどうかを判定する
# ---------------------------------------------------------------------------


def _has_child_of_type(node: Node, target_type: str) -> bool:
    """ノードの直接の子の中に、指定タイプのノードが存在するか判定する。"""
    return any(child.type == target_type for child in node.children)


def _get_if_then_block(if_node: Node, profile: LanguageProfile) -> Optional[Node]:
    """
    if 文の then ブロック（consequence）ノードを返す。

    言語差異を吸収する:
    - consequence_field:    child_by_field_name("consequence")（TypeScript / Python / Go）
    - statement_block_child: named_children[1] の statement_block（PowerShell）
    """
    if profile.if_then_block_access == "statement_block_child":
        named = if_node.named_children
        return named[1] if len(named) > 1 else None
    return if_node.child_by_field_name("consequence")


def _is_guard_clause(if_node: Node, profile: LanguageProfile) -> bool:
    """
    if 文がガード句パターンか判定する。

    ガード句の定義:
    - else / elif 節がない
    - then ブロックにちょうど1つの文がある
    - その1文が profile.guard_action_types に含まれるタイプである
    """
    if profile.elif_structure == "nested":
        if if_node.child_by_field_name("alternative") is not None:
            return False
    elif profile.elif_structure == "elseif_clauses":
        # PowerShell: elseif_clauses コンテナ または else_clause が named_child にあれば除外
        has_elif_or_else = any(
            c.type in ("elseif_clauses", "else_clause")
            for c in if_node.named_children
        )
        if has_elif_or_else:
            return False
    else:
        # flat (Python): elif_clause or else_clause が兄弟にあれば除外
        has_elif_or_else = any(
            c.type in ("elif_clause", "else_clause")
            for c in if_node.named_children
        )
        if has_elif_or_else:
            return False

    consequence = _get_if_then_block(if_node, profile)
    if consequence is None:
        return False

    statements = _get_block_statements(consequence, profile)
    if len(statements) != 1:
        return False

    return statements[0].type in profile.guard_action_types


# ---------------------------------------------------------------------------
# 抽出: ガード句のアクション説明文を生成する
# ---------------------------------------------------------------------------


def _extract_guard_action_text(statement_node: Node) -> str:
    """
    return / throw / raise 文から、人間が読めるアクション説明文を返す。

    TypeScript: return_statement, throw_statement
    Python:     return_statement, raise_statement
    Go:         return_statement
    PowerShell: flow_control_statement（キーワード子ノードで throw / return を判別）
    """
    value_node = next(
        (child for child in statement_node.named_children),
        None,
    )
    value_text = extract_node_text(value_node).strip() if value_node else ""

    if statement_node.type == "return_statement":
        if value_text:
            return f"値 `{value_text}` を返して処理を終了する"
        return "処理を終了する（値なし）"

    if statement_node.type == "throw_statement":
        if value_text:
            return f"例外 `{value_text}` をスローして処理を中断する"
        return "例外をスローして処理を中断する"

    if statement_node.type == "raise_statement":
        if value_text:
            return f"例外 `{value_text}` を raise して処理を中断する"
        return "例外を raise して処理を中断する"

    # PowerShell: flow_control_statement（throw / return の両方を含む）
    if statement_node.type == "flow_control_statement":
        keyword = next(
            (c for c in statement_node.children if not c.is_named and c.text),
            None,
        )
        keyword_text = keyword.text.decode("utf-8") if keyword and keyword.text else ""
        if keyword_text == "throw":
            if value_text:
                return f"例外 `{value_text}` をスローして処理を中断する"
            return "例外をスローして処理を中断する"
        # return（値ありまたは値なし）
        if value_text:
            return f"値 `{value_text}` を返して処理を終了する"
        return "処理を終了する（値なし）"

    return extract_node_text(statement_node)


# ---------------------------------------------------------------------------
# マッピング: if 文 → GuardClause IR
# ---------------------------------------------------------------------------


def _map_if_to_guard_clause(if_node: Node, profile: LanguageProfile) -> GuardClause:
    """ガード句パターンの if 文を GuardClause IR ノードに変換する。"""
    condition_text = _extract_condition_text(if_node)

    consequence = _get_if_then_block(if_node, profile)
    statements = _get_block_statements(consequence, profile) if consequence is not None else []
    action_text = _extract_guard_action_text(statements[0]) if statements else ""

    return GuardClause(
        kind="GuardClause",
        condition_text=condition_text,
        action_text=action_text,
    )


def _extract_condition_text(if_node: Node) -> str:
    """if 文の条件式テキストを返す。外側の括弧は言語にかかわらず除去する。"""
    condition_node = if_node.child_by_field_name("condition")
    if condition_node is None:
        return ""
    return strip_outer_parens(extract_node_text(condition_node))


# ---------------------------------------------------------------------------
# マッピング: if/else-if/else チェーン → ConditionBlock IR
# ---------------------------------------------------------------------------


def _extract_case_body_ir_nodes(
    block_node: Node | None,
    profile: LanguageProfile,
    direct_stmt_map: _DirectStmtMap,
    plugin: "LanguagePlugin",
    warnings: list[str] | None,
    scope: str,
) -> tuple[IRNode, ...]:
    """条件分岐ケースの本体ブロックをIRノード列に変換する。"""
    if block_node is None:
        return ()
    return tuple(_extract_body_ir_nodes(
        block_node,
        profile,
        direct_stmt_map,
        plugin,
        warnings,
        scope,
    ))


def _build_case_from_if(
    if_node: Node,
    profile: LanguageProfile,
    direct_stmt_map: _DirectStmtMap,
    plugin: "LanguagePlugin",
    warnings: list[str] | None,
    scope: str,
) -> CaseNode:
    """if 文の単一ケース（条件と本体IR）を CaseNode に変換する。"""
    condition_text = _extract_condition_text(if_node)

    consequence = _get_if_then_block(if_node, profile)
    body = _extract_case_body_ir_nodes(
        consequence,
        profile,
        direct_stmt_map,
        plugin,
        warnings,
        scope,
    )

    return CaseNode(condition_text=condition_text, body=body)


def _collect_all_cases_nested(
    if_node: Node,
    profile: LanguageProfile,
    direct_stmt_map: _DirectStmtMap,
    plugin: "LanguagePlugin",
    warnings: list[str] | None,
    scope: str,
) -> list[CaseNode]:
    """
    nested スタイル（TypeScript / Go）の else if チェーンを再帰的に辿る。

    TypeScript: alternative → else_clause → [if_statement | statement_block]
    Go:         alternative → [if_statement | block]（else_clause ラッパーなし）
    """
    cases: list[CaseNode] = [
        _build_case_from_if(if_node, profile, direct_stmt_map, plugin, warnings, scope)
    ]

    alternative = if_node.child_by_field_name("alternative")
    if alternative is None:
        return cases

    # Go: alternative が直接 if_statement または block
    # TypeScript: alternative は else_clause（ラッパー）→ 中の子を取り出す
    if alternative.type in ("if_statement", "block"):
        else_body = alternative  # Go スタイル
    else:
        else_body = next(
            (child for child in alternative.named_children),
            None,
        )  # TypeScript スタイル（else_clause を unwrap）

    if else_body is None:
        return cases

    if else_body.type == "if_statement":
        cases.extend(_collect_all_cases_nested(
            else_body,
            profile,
            direct_stmt_map,
            plugin,
            warnings,
            scope,
        ))
    else:
        body = _extract_case_body_ir_nodes(
            else_body,
            profile,
            direct_stmt_map,
            plugin,
            warnings,
            scope,
        )
        cases.append(CaseNode(
            condition_text="上記のいずれにも該当しない場合（デフォルト）",
            body=body,
        ))

    return cases


def _collect_all_cases_flat(
    if_node: Node,
    profile: LanguageProfile,
    direct_stmt_map: _DirectStmtMap,
    plugin: "LanguagePlugin",
    warnings: list[str] | None,
    scope: str,
) -> list[CaseNode]:
    """
    Python スタイル: elif_clause / else_clause が if_statement の兄弟として並ぶ。
    """
    named = if_node.named_children

    condition_text = strip_outer_parens(extract_node_text(named[0]))
    block_node = named[1]
    body = _extract_case_body_ir_nodes(
        block_node,
        profile,
        direct_stmt_map,
        plugin,
        warnings,
        scope,
    )
    cases: list[CaseNode] = [CaseNode(condition_text=condition_text, body=body)]

    for node in named[2:]:
        if node.type == "elif_clause":
            cond_node = node.child_by_field_name("condition")
            conseq_node = node.child_by_field_name("consequence")
            cond_text = (
                strip_outer_parens(extract_node_text(cond_node))
                if cond_node is not None
                else ""
            )
            elif_body = _extract_case_body_ir_nodes(
                conseq_node,
                profile,
                direct_stmt_map,
                plugin,
                warnings,
                scope,
            )
            cases.append(CaseNode(condition_text=cond_text, body=elif_body))

        elif node.type == "else_clause":
            body = node.child_by_field_name("body")
            else_body = _extract_case_body_ir_nodes(
                body,
                profile,
                direct_stmt_map,
                plugin,
                warnings,
                scope,
            )
            cases.append(CaseNode(
                condition_text="上記のいずれにも該当しない場合（デフォルト）",
                body=else_body,
            ))

    return cases


def _collect_all_cases_elseif_clauses(
    if_node: Node,
    profile: LanguageProfile,
    direct_stmt_map: _DirectStmtMap,
    plugin: "LanguagePlugin",
    warnings: list[str] | None,
    scope: str,
) -> list[CaseNode]:
    """
    PowerShell スタイル: elseif_clauses コンテナ + else_clause。

    if_statement の named_children:
      [0] pipeline       (条件式)
      [1] statement_block (then ブロック)
      [2] elseif_clauses  (elseif 節のコンテナ、オプション)
      [3] else_clause     (else 節、オプション)
    """
    named = if_node.named_children

    # then ブロック: named[0] = 条件 pipeline、named[1] = statement_block
    condition_text = strip_outer_parens(extract_node_text(named[0])) if named else ""
    then_block = named[1] if len(named) > 1 else None
    then_body = _extract_case_body_ir_nodes(
        then_block,
        profile,
        direct_stmt_map,
        plugin,
        warnings,
        scope,
    )
    cases: list[CaseNode] = [CaseNode(condition_text=condition_text, body=then_body)]

    for node in named[2:]:
        if node.type == "elseif_clauses":
            for clause in node.named_children:
                if clause.type != "elseif_clause":
                    continue
                # elseif_clause.child_by_field_name("condition") → pipeline（条件）
                cond_node = clause.child_by_field_name("condition")
                body_node = clause.named_children[1] if len(clause.named_children) > 1 else None
                cond_text = (
                    strip_outer_parens(extract_node_text(cond_node))
                    if cond_node is not None else ""
                )
                elif_body = _extract_case_body_ir_nodes(
                    body_node,
                    profile,
                    direct_stmt_map,
                    plugin,
                    warnings,
                    scope,
                )
                cases.append(CaseNode(condition_text=cond_text, body=elif_body))

        elif node.type == "else_clause":
            # else_clause.named_children[0] = statement_block
            body = node.named_children[0] if node.named_children else None
            else_body = _extract_case_body_ir_nodes(
                body,
                profile,
                direct_stmt_map,
                plugin,
                warnings,
                scope,
            )
            cases.append(CaseNode(
                condition_text="上記のいずれにも該当しない場合（デフォルト）",
                body=else_body,
            ))

    return cases


def _map_if_to_condition_block(
    if_node: Node,
    profile: LanguageProfile,
    direct_stmt_map: _DirectStmtMap,
    plugin: "LanguagePlugin",
    warnings: list[str] | None,
    scope: str,
) -> ConditionBlock:
    """if/else チェーン全体を ConditionBlock IR ノードに変換する。"""
    if profile.elif_structure == "nested":
        cases = _collect_all_cases_nested(if_node, profile, direct_stmt_map, plugin, warnings, scope)
    elif profile.elif_structure == "elseif_clauses":
        cases = _collect_all_cases_elseif_clauses(
            if_node,
            profile,
            direct_stmt_map,
            plugin,
            warnings,
            scope,
        )
    else:
        cases = _collect_all_cases_flat(if_node, profile, direct_stmt_map, plugin, warnings, scope)

    return ConditionBlock(
        kind="ConditionBlock",
        cases=tuple(cases),
    )


# ---------------------------------------------------------------------------
# マッピング: try / catch / finally → TryCatchNode IR
# ---------------------------------------------------------------------------


_TRY_BODY_NODE_TYPES = {"block", "statement_block", "script_block_body"}


def _first_named_descendant_of_type(node: Node, node_type: str) -> Optional[Node]:
    """Return the first named descendant with the requested tree-sitter type."""
    for child in node.named_children:
        if child.type == node_type:
            return child
        found = _first_named_descendant_of_type(child, node_type)
        if found is not None:
            return found
    return None


def _last_identifier_text(node: Node) -> str:
    """Return the last identifier-like token below a node."""
    result = ""
    for child in node.named_children:
        if child.type in {"identifier", "variable"}:
            result = extract_node_text(child).strip()
        nested = _last_identifier_text(child)
        if nested:
            result = nested
    return result


def _first_try_body_node(node: Node) -> Optional[Node]:
    """Return the direct body block for try/catch/finally-like nodes."""
    body = node.child_by_field_name("body")
    if body is not None and body.type in _TRY_BODY_NODE_TYPES:
        return body

    return next(
        (child for child in node.named_children if child.type in _TRY_BODY_NODE_TYPES),
        None,
    )


def _iter_catch_clauses(try_node: Node) -> list[Node]:
    """Return catch/except clauses directly attached to a try_statement."""
    clauses: list[Node] = []
    for child in try_node.named_children:
        if child.type in {"catch_clause", "except_clause"}:
            clauses.append(child)
        elif child.type == "catch_clauses":
            clauses.extend(c for c in child.named_children if c.type == "catch_clause")
    return clauses


def _extract_catch_var(catch_node: Node) -> str:
    """Extract catch variable text across TypeScript, Python, Java and PowerShell."""
    parameter = catch_node.child_by_field_name("parameter")
    if parameter is not None:
        return extract_node_text(parameter).strip()

    alias = _first_named_descendant_of_type(catch_node, "as_pattern_target")
    if alias is not None:
        return extract_node_text(alias).strip()

    for param_type in ("catch_formal_parameter", "formal_parameter"):
        param = next((c for c in catch_node.named_children if c.type == param_type), None)
        if param is not None:
            name = param.child_by_field_name("name")
            if name is not None:
                return extract_node_text(name).strip()
            return _last_identifier_text(param)

    value = catch_node.child_by_field_name("value")
    if value is not None:
        return extract_node_text(value).strip()

    return ""


def _map_try_to_ir(
    try_node: Node,
    profile: LanguageProfile,
    direct_stmt_map: _DirectStmtMap,
    plugin: "LanguagePlugin",
    warnings: list[str] | None,
    scope: str,
) -> TryCatchNode:
    """Convert a try_statement into a TryCatchNode with nested IR bodies."""
    try_body_node = _first_try_body_node(try_node)
    try_body = _extract_case_body_ir_nodes(
        try_body_node,
        profile,
        direct_stmt_map,
        plugin,
        warnings,
        scope,
    )

    catch_clauses = _iter_catch_clauses(try_node)
    catch_node = catch_clauses[0] if catch_clauses else None
    catch_body_node = _first_try_body_node(catch_node) if catch_node is not None else None
    catch_body = _extract_case_body_ir_nodes(
        catch_body_node,
        profile,
        direct_stmt_map,
        plugin,
        warnings,
        scope,
    )

    finalizer = try_node.child_by_field_name("finalizer")
    if finalizer is None:
        finalizer = next(
            (child for child in try_node.named_children if child.type == "finally_clause"),
            None,
        )
    finally_body_node = _first_try_body_node(finalizer) if finalizer is not None else None
    finally_body = _extract_case_body_ir_nodes(
        finally_body_node,
        profile,
        direct_stmt_map,
        plugin,
        warnings,
        scope,
    )

    if warnings is not None and len(catch_clauses) > 1:
        warnings.append(f"{scope}: try_statement は最初の catch / except 節のみ仕様化しました")

    return TryCatchNode(
        kind="TryCatchNode",
        try_body=try_body,
        catch_var=_extract_catch_var(catch_node) if catch_node is not None else "",
        catch_body=catch_body,
        finally_body=finally_body,
    )


# ---------------------------------------------------------------------------
# マッピング: for ループ → LoopNode IR（TypeScript / Python 共通）
# ---------------------------------------------------------------------------


def _is_for_of(for_node: Node) -> bool:
    """TypeScript: for_in_statement が for...of 構文かどうかを判定する。"""
    return _has_child_of_type(for_node, "of")


def _map_for_each_to_loop(
    for_node: Node,
    profile: LanguageProfile,
    direct_stmt_map: _DirectStmtMap,
    plugin: "LanguagePlugin",
    warnings: list[str] | None = None,
    scope: str = "",
) -> LoopNode:
    """
    for...of（TypeScript）または for...in（Python）を LoopNode IR（FOR_EACH）に変換する。

    tree-sitter フィールド名 left / right / body を使用する（TypeScript / Python 共通）。
    PowerShell の foreach は powershell.py の for_loop_mapper フックで処理される。
    """
    left_node = for_node.child_by_field_name("left")
    right_node = for_node.child_by_field_name("right")
    body_node = for_node.child_by_field_name("body")

    iterator = extract_node_text(left_node).strip() if left_node is not None else "item"
    collection = extract_node_text(right_node).strip() if right_node is not None else ""
    nested_body = (
        _extract_body_ir_nodes(body_node, profile, direct_stmt_map, plugin, warnings, scope)
        if body_node is not None
        else []
    )

    return LoopNode(
        kind="Loop",
        loop_type="FOR_EACH",
        collection=collection,
        iterator=iterator,
        body=tuple(nested_body),
    )


def _extract_for_range_summary(for_node: Node) -> str:
    """古典的 for 文（TypeScript のみ）の範囲サマリーを返す。"""
    initializer = for_node.child_by_field_name("initializer")
    condition = for_node.child_by_field_name("condition")
    increment = for_node.child_by_field_name("increment")

    init_text = extract_node_text(initializer).rstrip(";").strip() if initializer is not None else ""
    cond_text = extract_node_text(condition).strip() if condition is not None else ""
    incr_text = extract_node_text(increment).strip() if increment is not None else ""

    return f"{init_text}; {cond_text}; {incr_text}"


def _extract_for_range_iterator(for_node: Node) -> str:
    """古典的 for 文（TypeScript のみ）のカウンタ変数名を返す。"""
    initializer = for_node.child_by_field_name("initializer")
    if initializer is None:
        return "i"

    for child in initializer.named_children:
        if child.type == "variable_declarator":
            name_node = child.child_by_field_name("name")
            if name_node is not None:
                return extract_node_text(name_node).strip()

    return "i"


def _map_for_range_to_loop(
    for_node: Node,
    profile: LanguageProfile,
    direct_stmt_map: _DirectStmtMap,
    plugin: "LanguagePlugin",
    warnings: list[str] | None = None,
    scope: str = "",
) -> LoopNode:
    """古典的 for 文（TypeScript のみ）を LoopNode IR（FOR_RANGE）に変換する。"""
    body_node = for_node.child_by_field_name("body")
    nested_body = (
        _extract_body_ir_nodes(body_node, profile, direct_stmt_map, plugin, warnings, scope)
        if body_node is not None
        else []
    )

    return LoopNode(
        kind="Loop",
        loop_type="FOR_RANGE",
        collection=_extract_for_range_summary(for_node),
        iterator=_extract_for_range_iterator(for_node),
        body=tuple(nested_body),
    )


# ---------------------------------------------------------------------------
# マッピング: while / do-while → LoopNode IR
# ---------------------------------------------------------------------------


def _map_while_to_loop(
    while_node: Node,
    profile: LanguageProfile,
    direct_stmt_map: _DirectStmtMap,
    plugin: "LanguagePlugin",
    warnings: list[str] | None = None,
    scope: str = "",
) -> LoopNode:
    """while 文を LoopNode IR（WHILE）に変換する。"""
    condition_node = while_node.child_by_field_name("condition")
    condition_text = strip_outer_parens(extract_node_text(condition_node)) if condition_node is not None else ""

    body_node = while_node.child_by_field_name("body")
    nested_body = (
        _extract_body_ir_nodes(body_node, profile, direct_stmt_map, plugin, warnings, scope)
        if body_node is not None
        else []
    )

    return LoopNode(
        kind="Loop",
        loop_type="WHILE",
        collection=condition_text,
        iterator="",
        body=tuple(nested_body),
    )


def _map_do_while_to_loop(
    do_node: Node,
    profile: LanguageProfile,
    direct_stmt_map: _DirectStmtMap,
    plugin: "LanguagePlugin",
    warnings: list[str] | None = None,
    scope: str = "",
) -> LoopNode:
    """do-while 文を LoopNode IR（DO_WHILE）に変換する。"""
    condition_node = do_node.child_by_field_name("condition")
    condition_text = strip_outer_parens(extract_node_text(condition_node)) if condition_node is not None else ""

    body_node = do_node.child_by_field_name("body")
    nested_body = (
        _extract_body_ir_nodes(body_node, profile, direct_stmt_map, plugin, warnings, scope)
        if body_node is not None
        else []
    )

    return LoopNode(
        kind="Loop",
        loop_type="DO_WHILE",
        collection=condition_text,
        iterator="",
        body=tuple(nested_body),
    )


# ---------------------------------------------------------------------------
# マッピング: expression_statement → DataTransformation / SideEffect IR
# （TypeScript / Python 共通）
# ---------------------------------------------------------------------------

_AUGMENTED_ASSIGNMENT_OPERATIONS: dict[str, str] = {
    "+=":  "ADD",
    "-=":  "SUBTRACT",
    "*=":  "MULTIPLY",
    "/=":  "DIVIDE",
    "%=":  "MODULO",
    "||=": "LOGICAL_OR_ASSIGN",
    "&&=": "LOGICAL_AND_ASSIGN",
    "??=": "NULLISH_ASSIGN",
}


def _map_augmented_assignment_to_ir(expr_node: Node) -> DataTransformation:
    """
    複合代入式（+=, -= 等）を DataTransformation IR ノードに変換する。
    TypeScript: augmented_assignment_expression
    Python:     augmented_assignment
    （フィールド名 left / operator / right は両言語で共通）
    """
    left_node = expr_node.child_by_field_name("left")
    right_node = expr_node.child_by_field_name("right")
    op_node = expr_node.child_by_field_name("operator")

    target = extract_node_text(left_node).strip() if left_node is not None else ""
    value = extract_node_text(right_node).strip() if right_node is not None else ""
    op_text = extract_node_text(op_node).strip() if op_node is not None else "+="
    operation = _AUGMENTED_ASSIGNMENT_OPERATIONS.get(op_text, "ASSIGN")

    return DataTransformation(
        kind="DataTransformation",
        target=target,
        operation=operation,
        value=value,
    )


def _map_assignment_to_ir(expr_node: Node) -> DataTransformation:
    """
    単純代入式（=）を DataTransformation IR ノードに変換する。
    TypeScript: assignment_expression
    Python:     assignment
    （フィールド名 left / right は両言語で共通）
    """
    left_node = expr_node.child_by_field_name("left")
    right_node = expr_node.child_by_field_name("right")

    target = extract_node_text(left_node).strip() if left_node is not None else ""
    value = extract_node_text(right_node).strip() if right_node is not None else ""

    return DataTransformation(
        kind="DataTransformation",
        target=target,
        operation="ASSIGN",
        value=value,
    )


def _map_call_to_ir(expr_node: Node) -> SideEffect:
    """
    関数呼び出し式を SideEffect IR ノードに変換する。
    TypeScript: call_expression
    Python:     call
    Go:         call_expression（expression_statement 内）
    """
    return SideEffect(
        kind="SideEffect",
        description=extract_node_text(expr_node).strip(),
    )


def _map_expression_statement_to_ir(
    stmt_node: Node, profile: LanguageProfile
) -> Optional[IRNode]:
    """
    expression_statement ノードの式の種類を profile を参照して判定し、
    対応する IR ノードに変換する。
    """
    expr_node = next((c for c in stmt_node.named_children), None)
    if expr_node is None:
        return None

    if expr_node.type == profile.augmented_assignment_type:
        return _map_augmented_assignment_to_ir(expr_node)

    if expr_node.type == profile.assignment_type:
        return _map_assignment_to_ir(expr_node)

    if expr_node.type == profile.call_type:
        return _map_call_to_ir(expr_node)

    return None


def _map_lexical_declaration_to_ir(stmt_node: Node) -> Optional[IRNode]:
    """
    変数宣言文（TypeScript の let / const）を DataTransformation IR ノードに変換する。
    Python はこのノードタイプを持たず、expression_statement → assignment で処理される。
    """
    declarator = next(
        (c for c in stmt_node.named_children if c.type == "variable_declarator"),
        None,
    )
    if declarator is None:
        return None

    name_node = declarator.child_by_field_name("name")
    value_node = declarator.child_by_field_name("value")

    if value_node is None:
        return None

    target = extract_node_text(name_node).strip() if name_node is not None else ""
    value = extract_node_text(value_node).strip()

    return DataTransformation(
        kind="DataTransformation",
        target=target,
        operation="ASSIGN",
        value=value,
    )


# ---------------------------------------------------------------------------
# ディスパッチ: 1つの文ノード → Optional[IRNode]
# ---------------------------------------------------------------------------


def _map_statement_to_ir(
    statement_node: Node,
    profile: LanguageProfile,
    direct_stmt_map: _DirectStmtMap,
    plugin: "LanguagePlugin",
    warnings: list[str] | None = None,
    scope: str = "",
) -> Optional[IRNode]:
    """
    1つの文ASTノードを profile / plugin を参照して適切な IR ノードに変換する。

    対応する文タイプ（profile によって異なる）:
    - if_statement                               → GuardClause または ConditionBlock
    - for_each_node_type                         → LoopNode（plugin.for_loop_mapper または汎用）
    - for_range_node_type (TS のみ)              → LoopNode (FOR_RANGE)
    - expression_statement                       → DataTransformation または SideEffect
    - lexical_declaration_types (TS のみ)        → DataTransformation
    - direct_stmt_map（Go 等の直接代入文）        → DataTransformation

    変換後、直前の comment ノードがあれば IR ノードの comment フィールドに付与する。
    """
    node_type = statement_node.type
    ir_node: Optional[IRNode] = None

    if node_type == "if_statement":
        if _is_guard_clause(statement_node, profile):
            ir_node = _map_if_to_guard_clause(statement_node, profile)
        else:
            ir_node = _map_if_to_condition_block(
                statement_node,
                profile,
                direct_stmt_map,
                plugin,
                warnings,
                scope,
            )

    elif node_type == "try_statement":
        ir_node = _map_try_to_ir(
            statement_node,
            profile,
            direct_stmt_map,
            plugin,
            warnings,
            scope,
        )

    elif node_type == profile.for_each_node_type:
        if plugin.for_loop_mapper is not None:
            # 言語固有フック（Go / PowerShell 等）: range_clause 判定など複雑なロジックはプラグイン側で実装
            body_extractor = lambda body_node: _extract_body_ir_nodes(
                body_node,
                profile,
                direct_stmt_map,
                plugin,
                warnings,
                scope,
            )
            ir_node = plugin.for_loop_mapper(statement_node, body_extractor)
        elif profile.for_loop_flavor == "of_keyword":
            # TypeScript: for_in_statement が for...of かどうかで振り分け
            if not _is_for_of(statement_node):
                return None  # for...in はスコープ外（Phase 1 定義）
            ir_node = _map_for_each_to_loop(
                statement_node,
                profile,
                direct_stmt_map,
                plugin,
                warnings,
                scope,
            )
        else:
            # "always_foreach": Python など、常に FOR_EACH
            ir_node = _map_for_each_to_loop(
                statement_node,
                profile,
                direct_stmt_map,
                plugin,
                warnings,
                scope,
            )

    elif profile.for_range_node_type and node_type == profile.for_range_node_type:
        ir_node = _map_for_range_to_loop(
            statement_node,
            profile,
            direct_stmt_map,
            plugin,
            warnings,
            scope,
        )

    elif profile.while_node_type and node_type == profile.while_node_type:
        ir_node = _map_while_to_loop(
            statement_node,
            profile,
            direct_stmt_map,
            plugin,
            warnings,
            scope,
        )

    elif profile.do_while_node_type and node_type == profile.do_while_node_type:
        ir_node = _map_do_while_to_loop(
            statement_node,
            profile,
            direct_stmt_map,
            plugin,
            warnings,
            scope,
        )

    elif node_type == "expression_statement":
        ir_node = _map_expression_statement_to_ir(statement_node, profile)

    elif node_type in profile.lexical_declaration_types:
        ir_node = _map_lexical_declaration_to_ir(statement_node)

    # --- expression_statement を介さない直接代入文（Go / PowerShell 等）---
    elif node_type in profile.direct_statement_types:
        mapper_fn = direct_stmt_map.get(node_type)
        if mapper_fn is not None:
            ir_node = mapper_fn(statement_node)

    # --- return / throw / raise 文（ガード句以外）---
    # ガード句（if (cond) { return/throw }）は上の if_statement ブランチで処理済み。
    # ここでは関数本体またはループ本体に直接現れる return/throw/raise を扱う。
    elif node_type in {"return_statement", "throw_statement", "raise_statement"}:
        value_node = next((c for c in statement_node.named_children), None)
        value_text = extract_node_text(value_node).strip() if value_node is not None else ""
        if node_type == "throw_statement":
            action = "throw"
        elif node_type == "raise_statement":
            action = "raise"
        else:
            action = "return"
        ir_node = ReturnNode(kind="ReturnNode", value_text=value_text, action=action)

    # --- PowerShell: flow_control_statement（return / throw を兼ねる）---
    elif node_type == "flow_control_statement":
        keyword = next(
            (c for c in statement_node.children if not c.is_named and c.text),
            None,
        )
        keyword_text = keyword.text.decode("utf-8") if keyword and keyword.text else ""
        value_node = next((c for c in statement_node.named_children), None)
        value_text = extract_node_text(value_node).strip() if value_node is not None else ""
        action = "throw" if keyword_text == "throw" else "return"
        ir_node = ReturnNode(kind="ReturnNode", value_text=value_text, action=action)

    if ir_node is None:
        return None

    # 直前の comment ノードを IR ノードの comment フィールドに付与する
    comment = _get_preceding_comment(statement_node)
    if comment:
        return dataclasses.replace(ir_node, comment=comment)
    return ir_node


# ---------------------------------------------------------------------------
# 本体ブロックの抽出: block / statement_block → IRNode リスト
# ---------------------------------------------------------------------------


def _format_unmapped_statement_warning(statement: Node, scope: str) -> str:
    """未抽出の文ノードを、監査しやすい短い警告文に整形する。"""
    snippet = normalize_whitespace(extract_node_text(statement))
    if len(snippet) > 120:
        snippet = snippet[:117].rstrip() + "..."
    scope_prefix = f"{scope}: " if scope else ""
    return f"{scope_prefix}{statement.type} は未対応のため仕様化されませんでした: `{snippet}`"


def _is_docstring_statement(statement: Node) -> bool:
    """
    `expression_statement` の唯一の named child が `string` であるか判定する。

    Python の関数 / クラス body 先頭に置かれる docstring は
    `expression_statement → string` の構造で出現する。function_description_extractor が
    description として既に取り込んでいるため、body 反復時には警告対象から除外する。
    """
    if statement.type != "expression_statement":
        return False
    named = statement.named_children
    return len(named) == 1 and named[0].type == "string"


# 「意味のある処理を行わない」ことが構文上明らかなノードタイプ
# 警告に出すと「未対応構文」と誤読されるため body 反復時に silent skip する
# （未対応ではなく、定義上 no-op であるため）
_NO_OP_STATEMENT_NODE_TYPES: frozenset[str] = frozenset({
    "pass_statement",   # Python: `pass`（空 body の syntactic placeholder）
})


def _is_no_op_statement(statement: Node) -> bool:
    """
    構文上 no-op であることが明らかな文か判定する。

    対象:
    - `pass_statement`: Python の `pass`
    - `expression_statement` 配下が `ellipsis` のみ: Python の `...`（スタブ慣用句）
    """
    if statement.type in _NO_OP_STATEMENT_NODE_TYPES:
        return True
    if statement.type == "expression_statement":
        named = statement.named_children
        if len(named) == 1 and named[0].type == "ellipsis":
            return True
    return False


def _extract_body_ir_nodes(
    body_node: Node,
    profile: LanguageProfile,
    direct_stmt_map: _DirectStmtMap,
    plugin: "LanguagePlugin",
    warnings: list[str] | None = None,
    scope: str = "",
) -> list[IRNode]:
    """
    ブロックノード（statement_block / block）から、
    マッピング可能な IRNode の一覧を返す。
    """
    results: list[IRNode] = []
    statements = _get_block_statements(body_node, profile)

    # body 先頭の docstring は function_description_extractor が description として
    # 既に取り込んでいるため、warnings に重複計上しないようスキップする（Python のみ）。
    if (
        profile.function_docstring_in_body
        and statements
        and _is_docstring_statement(statements[0])
    ):
        statements = statements[1:]

    for statement in statements:
        # 構文上 no-op の文（pass / ...）は「未対応構文」ではないので
        # IR にも警告にも乗せず silent skip する。
        if _is_no_op_statement(statement):
            continue

        ir_node = _map_statement_to_ir(
            statement,
            profile,
            direct_stmt_map,
            plugin,
            warnings,
            scope,
        )
        if ir_node is not None:
            results.append(ir_node)
        elif warnings is not None:
            warnings.append(_format_unmapped_statement_warning(statement, scope))
    return results


# ---------------------------------------------------------------------------
# 関数レベルのマッピング
# ---------------------------------------------------------------------------


def _get_top_level_nodes(root_node: Node, profile: LanguageProfile) -> list[Node]:
    """
    トップレベルの AST ノードリストを返す。

    多くの言語はルートノードの直接の子にトップレベル宣言を持つ。
    PowerShell のように program → statement_list → 各宣言 の2段構造の言語は
    profile.top_level_wrapper_type でラッパーのタイプを指定する。
    """
    if profile.top_level_wrapper_type:
        wrapper = next(
            (c for c in root_node.named_children if c.type == profile.top_level_wrapper_type),
            None,
        )
        return list(wrapper.named_children) if wrapper is not None else []
    return list(root_node.named_children)


def _find_top_level_functions(root_node: Node, profile: LanguageProfile) -> list[Node]:
    """プログラムのトップレベルから、profile.function_node_type のノードを返す。"""
    return [
        child for child in _get_top_level_nodes(root_node, profile)
        if child.type == profile.function_node_type
    ]


def _map_function_to_spec(
    fn_node: Node,
    profile: LanguageProfile,
    direct_stmt_map: _DirectStmtMap,
    plugin: "LanguagePlugin",
    warnings: list[str] | None = None,
) -> FunctionSpec:
    """関数定義 AST ノードを FunctionSpec IR に変換する。"""
    # 関数名ノードを取得（言語差異を吸収）
    if profile.function_name_access == "function_name_child":
        # PowerShell: named_child の type == "function_name"
        name_node = next(
            (c for c in fn_node.named_children if c.type == "function_name"),
            None,
        )
    else:
        name_node = fn_node.child_by_field_name("name")
    name = extract_node_text(name_node).strip() if name_node is not None else "anonymous"

    # 本体ノードを取得（言語差異を吸収）
    if profile.function_body_access == "script_block_body":
        # PowerShell: function_statement → script_block → script_block_body
        script_block = next(
            (c for c in fn_node.named_children if c.type == "script_block"),
            None,
        )
        body_node = next(
            (c for c in script_block.named_children if c.type == "script_block_body"),
            None,
        ) if script_block is not None else None
    else:
        body_node = fn_node.child_by_field_name("body")
    scope = f"関数 `{name}`"
    ir_nodes = (
        _extract_body_ir_nodes(body_node, profile, direct_stmt_map, plugin, warnings, scope)
        if body_node is not None
        else []
    )

    return FunctionSpec(
        name=name,
        body=tuple(ir_nodes),
        description=_get_function_description(fn_node, plugin),
        params=plugin.param_extractor(fn_node),
        return_type=plugin.return_type_extractor(fn_node),
    )


# ---------------------------------------------------------------------------
# モジュールレベルの抽出（LanguagePlugin のエクストラクタに委譲）
# ---------------------------------------------------------------------------


def _extract_all_imports(
    root_node: Node, plugin: "LanguagePlugin"
) -> tuple[ImportSpec, ...]:
    """プログラムのトップレベルからインポート文を収集して返す。"""
    results: list[ImportSpec] = []
    for child in _get_top_level_nodes(root_node, plugin.profile):
        if child.type in plugin.profile.import_node_types:
            results.extend(plugin.import_extractor(child))
    return tuple(results)


def _extract_all_module_variables(
    root_node: Node, plugin: "LanguagePlugin", warnings: list[str]
) -> tuple[ModuleVariableSpec, ...]:
    """プログラムのトップレベルから変数・定数定義を収集して返す。"""
    results: list[ModuleVariableSpec] = []
    for child in _get_top_level_nodes(root_node, plugin.profile):
        if child.type in plugin.profile.module_var_node_types:
            spec = plugin.module_var_extractor(child)
            if spec is not None:
                results.append(spec)
            elif plugin.module_var_warning_extractor is not None:
                warning = plugin.module_var_warning_extractor(child)
                if warning is not None:
                    warnings.append(warning)
    return tuple(results)


def _extract_all_type_definitions(
    root_node: Node, plugin: "LanguagePlugin"
) -> tuple[TypeDefinitionSpec, ...]:
    """プログラムのトップレベルから型定義を収集して返す。"""
    target_types = {
        t for t in (plugin.profile.type_alias_node_type, plugin.profile.interface_node_type) if t
    }
    if not target_types:
        return ()

    results: list[TypeDefinitionSpec] = []
    for child in _get_top_level_nodes(root_node, plugin.profile):
        if child.type in target_types:
            spec = plugin.type_def_extractor(child)
            if spec is not None:
                results.append(spec)
    return tuple(results)


def _get_class_body_node(class_ast_node: Node) -> Optional[Node]:
    """
    クラス定義 AST ノードから body ブロックを返す。

    Python の decorated_definition（@dataclass 等）と class_definition の両方に対応する:
      - decorated_definition → definition (class_definition) → body
      - class_definition     → body
    """
    if class_ast_node.type == "decorated_definition":
        definition = class_ast_node.child_by_field_name("definition")
        if definition is None:
            return None
        return definition.child_by_field_name("body")
    return class_ast_node.child_by_field_name("body")


def _extract_class_methods(
    class_ast_node: Node,
    plugin: "LanguagePlugin",
    direct_stmt_map: _DirectStmtMap,
    warnings: list[str] | None = None,
) -> tuple[FunctionSpec, ...]:
    """
    クラスボディ内の function_definition ノードを FunctionSpec タプルとして返す。

    メソッド本体の IR は top-level 関数と同じロジックで変換する。
    """
    body_node = _get_class_body_node(class_ast_node)
    if body_node is None:
        return ()

    methods: list[FunctionSpec] = []
    for child in body_node.named_children:
        if child.type == plugin.profile.function_node_type:
            methods.append(_map_function_to_spec(child, plugin.profile, direct_stmt_map, plugin, warnings))
    return tuple(methods)


def _extract_all_class_definitions(
    root_node: Node,
    plugin: "LanguagePlugin",
    direct_stmt_map: _DirectStmtMap,
    warnings: list[str] | None = None,
) -> tuple[ClassSpec, ...]:
    """
    プログラムのトップレベルからクラス定義を収集して返す。

    profile.class_node_types が空の言語（TypeScript / Go 等）は即座に空タプルを返す。
    各クラスのメソッドは _extract_class_methods() で抽出し、ClassSpec に付与する。
    """
    if not plugin.profile.class_node_types:
        return ()

    results: list[ClassSpec] = []
    for child in _get_top_level_nodes(root_node, plugin.profile):
        if child.type in plugin.profile.class_node_types:
            spec = plugin.class_extractor(child)
            if spec is not None:
                methods = _extract_class_methods(child, plugin, direct_stmt_map, warnings)
                if methods:
                    spec = dataclasses.replace(spec, methods=methods)
                results.append(spec)
    return tuple(results)


# ---------------------------------------------------------------------------
# トップレベル未対応宣言の警告化
# ---------------------------------------------------------------------------


# どの抽出器にもマッチしないが、警告に出すと監査ノイズになるノードタイプ
# - comment / line_comment / block_comment: ファイル冒頭は file_comment、関数前は preceding_comment で取り込み済み
#   （言語によって名前が異なる: TypeScript/Python/Go/PowerShell は `comment`、Java は `line_comment` / `block_comment`）
# - package_clause:      Go の `package main`（ファイルメタデータ）
# - package_declaration: Java の `package com.foo`（ファイルメタデータ）
_TOP_LEVEL_IGNORED_NODE_TYPES: frozenset[str] = frozenset({
    "comment",
    "line_comment",
    "block_comment",
    "package_clause",
    "package_declaration",
})


def _collect_recognized_top_level_types(plugin: "LanguagePlugin") -> frozenset[str]:
    """LanguagePlugin が認識するトップレベルノードタイプの集合を返す。"""
    profile = plugin.profile
    types: set[str] = set()
    types.update(profile.import_node_types)
    types.update(profile.module_var_node_types)
    if profile.type_alias_node_type:
        types.add(profile.type_alias_node_type)
    if profile.interface_node_type:
        types.add(profile.interface_node_type)
    types.update(profile.class_node_types)
    if profile.function_node_type:
        types.add(profile.function_node_type)
    return frozenset(types)


def _collect_top_level_extraction_warnings(
    root_node: Node, plugin: "LanguagePlugin"
) -> list[str]:
    """
    トップレベルで認識されなかった宣言を警告化する。

    profile に登録された抽出対象（imports / module_vars / type defs / classes / functions）の
    いずれにもマッチしなかった named child は、監査用途で重要なので警告に追加する。
    例: TypeScript の class_declaration、Go の type_declaration、PowerShell の class_definition。

    file_comment として既に取り込んだファイル先頭の string-only expression_statement
    （Python のモジュール docstring）は警告対象から除外する。
    """
    recognized = _collect_recognized_top_level_types(plugin)
    profile = plugin.profile
    warnings: list[str] = []
    module_docstring_skipped = not profile.has_module_docstring

    for node in _get_top_level_nodes(root_node, profile):
        if node.type in recognized or node.type in _TOP_LEVEL_IGNORED_NODE_TYPES:
            module_docstring_skipped = True
            continue

        # Python のモジュール docstring（ファイル先頭の string-only expression_statement）は
        # file_comment として取り込み済みのため警告対象から除外する。
        # 「先頭のみ」の判定: profile.has_module_docstring が True で、まだ最初の named child を
        # 通過していない場合に限定する。
        if not module_docstring_skipped and _is_docstring_statement(node):
            module_docstring_skipped = True
            continue

        warnings.append(_format_unmapped_statement_warning(node, scope="トップレベル"))
        module_docstring_skipped = True

    return warnings


# ---------------------------------------------------------------------------
# 公開インターフェース
# ---------------------------------------------------------------------------


def map_source_to_module_spec(
    root_node: Node, module_name: str, plugin: "LanguagePlugin"
) -> ModuleSpec:
    """
    ソースファイルの AST ルートノードを ModuleSpec IR に変換する。

    これがミドルウェア層の唯一の公開インターフェース。

    Args:
        root_node:   tree-sitter の program/module ルートノード
        module_name: モジュール名（通常はファイル名のステム）
        plugin:      使用言語の LanguagePlugin

    Returns:
        ModuleSpec IR オブジェクト（imports / module_variables / type_definitions / functions を含む）
    """
    profile = plugin.profile
    direct_stmt_map: _DirectStmtMap = dict(plugin.direct_statement_extractors)
    warnings: list[str] = _collect_top_level_extraction_warnings(root_node, plugin)

    return ModuleSpec(
        name=module_name,
        file_comment=_get_file_header_comment(root_node, profile),
        imports=_extract_all_imports(root_node, plugin),
        module_variables=_extract_all_module_variables(root_node, plugin, warnings),
        type_definitions=_extract_all_type_definitions(root_node, plugin),
        class_definitions=_extract_all_class_definitions(root_node, plugin, direct_stmt_map, warnings),
        functions=tuple(
            _map_function_to_spec(fn_node, profile, direct_stmt_map, plugin, warnings)
            for fn_node in _find_top_level_functions(root_node, profile)
        ),
        extraction_warnings=tuple(dict.fromkeys(warnings)),
    )
