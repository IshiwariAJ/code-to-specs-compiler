"""
ミドルウェア（IR Layer）: AST ノード → Universal IR

責務: tree-sitter の AST ノードを巡回し、言語固有の構文を
      言語に依存しない Universal IR オブジェクトにマッピングする。

設計方針（構造化プログラミング原則）:
- すべての関数は純粋関数（副作用なし）
- 1関数1責務: 各関数はひとつのマッピング処理のみを担う
- 言語差異は LanguageProfile に集約し、ロジックは言語非依存に保つ
"""
from __future__ import annotations

import dataclasses
from typing import Optional

from tree_sitter import Node

from .profiles import LanguageProfile
from .types import (
    CaseNode,
    ConditionBlock,
    DataTransformation,
    FunctionSpec,
    GuardClause,
    ImportSpec,
    IRNode,
    LoopNode,
    ModuleSpec,
    ModuleVariableSpec,
    SideEffect,
    TypeDefinitionSpec,
)


# ---------------------------------------------------------------------------
# プリミティブ操作: ASTノードのテキスト抽出
# ---------------------------------------------------------------------------


def _extract_node_text(node: Node) -> str:
    """ASTノードのソーステキストを UTF-8 文字列として返す。"""
    if node.text is None:
        return ""
    return node.text.decode("utf-8")


def _strip_outer_parens(text: str) -> str:
    """条件式の外側の丸括弧を除去して返す。例: '(x > 0)' → 'x > 0'"""
    stripped = text.strip()
    if stripped.startswith("(") and stripped.endswith(")"):
        return stripped[1:-1].strip()
    return stripped


def _extract_condition_text(if_node: Node) -> str:
    """if 文の条件式テキストを返す。外側の括弧は言語にかかわらず除去する。"""
    condition_node = if_node.child_by_field_name("condition")
    if condition_node is None:
        return ""
    return _strip_outer_parens(_extract_node_text(condition_node))


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


def _truncate_text(text: str, max_len: int = 60) -> str:
    """テキストが長い場合は省略記号を付けて切り詰める。"""
    cleaned = text.replace("\n", " ").strip()
    if len(cleaned) > max_len:
        return cleaned[:max_len] + "..."
    return cleaned


# ---------------------------------------------------------------------------
# コメント抽出: 直前コメント / 関数説明 / ファイルヘッダー
# ---------------------------------------------------------------------------


def _get_preceding_comment(node: Node) -> str:
    """
    ノードの直前にある連続した comment ノードのテキストを結合して返す。

    複数行コメント（連続した // 行）を1つの文字列にまとめる。
    JSDoc ブロックコメント（/** */）は1ノードとして取得される。
    """
    comments: list[str] = []
    prev = node.prev_named_sibling
    while prev is not None and prev.type == "comment":
        comments.insert(0, _extract_node_text(prev))
        prev = prev.prev_named_sibling
    return "\n".join(comments) if comments else ""


def _get_py_function_docstring(fn_node: Node) -> str:
    """
    Python 関数本体の先頭にある docstring を返す。

    docstring は関数 block の最初の expression_statement 内の string リテラル。
    """
    body_node = fn_node.child_by_field_name("body")
    if body_node is None:
        return ""
    first_stmt = next(iter(body_node.named_children), None)
    if first_stmt is None or first_stmt.type != "expression_statement":
        return ""
    string_node = next(
        (c for c in first_stmt.named_children if c.type == "string"),
        None,
    )
    if string_node is None:
        return ""
    return _extract_node_text(string_node)


def _get_function_description(fn_node: Node, profile: LanguageProfile) -> str:
    """
    関数の説明文を返す。

    TypeScript / Go: 関数直前の JSDoc または行コメント
    Python:          関数本体先頭の docstring
    """
    if profile.name == "python":
        return _get_py_function_docstring(fn_node)
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
            comments.append(_extract_node_text(child))
        elif profile.name == "python" and child.type == "expression_statement":
            # Python モジュール docstring（最初の文が文字列リテラルの場合）
            string_node = next(
                (c for c in child.named_children if c.type == "string"),
                None,
            )
            if string_node is not None:
                comments.append(_extract_node_text(string_node))
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


def _is_guard_clause(if_node: Node, profile: LanguageProfile) -> bool:
    """
    if 文がガード句パターンか判定する。

    ガード句の定義:
    - else / elif 節がない
    - then ブロックにちょうど1つの文がある
    - その1文が profile.guard_action_types に含まれるタイプである
    """
    # TypeScript / Go: alternative フィールドで else/elif を検出
    # Python: named_children に elif_clause / else_clause があれば除外
    if profile.elif_structure == "nested":
        if if_node.child_by_field_name("alternative") is not None:
            return False
    else:
        # flat (Python): elif_clause or else_clause が兄弟にあれば除外
        has_elif_or_else = any(
            c.type in ("elif_clause", "else_clause")
            for c in if_node.named_children
        )
        if has_elif_or_else:
            return False

    consequence = if_node.child_by_field_name("consequence")
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
    """
    value_node = next(
        (child for child in statement_node.named_children),
        None,
    )
    value_text = _extract_node_text(value_node).strip() if value_node else ""

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

    return _extract_node_text(statement_node)


# ---------------------------------------------------------------------------
# マッピング: if 文 → GuardClause IR
# ---------------------------------------------------------------------------


def _map_if_to_guard_clause(if_node: Node, profile: LanguageProfile) -> GuardClause:
    """ガード句パターンの if 文を GuardClause IR ノードに変換する。"""
    condition_text = _extract_condition_text(if_node)

    consequence = if_node.child_by_field_name("consequence")
    statements = _get_block_statements(consequence, profile) if consequence is not None else []
    action_text = _extract_guard_action_text(statements[0]) if statements else ""

    return GuardClause(
        kind="GuardClause",
        condition_text=condition_text,
        action_text=action_text,
    )


# ---------------------------------------------------------------------------
# マッピング: if/else-if/else チェーン → ConditionBlock IR
# ---------------------------------------------------------------------------


def _extract_case_action_texts(
    block_node: Node, profile: LanguageProfile
) -> tuple[str, ...]:
    """ブロックノードの各文のテキストをアクション一覧として返す。"""
    statements = _get_block_statements(block_node, profile)
    return tuple(_extract_node_text(stmt) for stmt in statements)


def _build_case_from_if(if_node: Node, profile: LanguageProfile) -> CaseNode:
    """if 文の単一ケース（条件と本体アクション）を CaseNode に変換する。"""
    condition_text = _extract_condition_text(if_node)

    consequence = if_node.child_by_field_name("consequence")
    action_texts = (
        _extract_case_action_texts(consequence, profile)
        if consequence is not None
        else ()
    )

    return CaseNode(condition_text=condition_text, action_texts=action_texts)


def _collect_all_cases_nested(if_node: Node, profile: LanguageProfile) -> list[CaseNode]:
    """
    nested スタイル（TypeScript / Go）の else if チェーンを再帰的に辿る。

    TypeScript: alternative → else_clause → [if_statement | statement_block]
    Go:         alternative → [if_statement | block]（else_clause ラッパーなし）

    再帰の終了条件:
    - alternative がない（else なし）
    - alternative の本体が statement_block / block（else ブロック）
    """
    cases: list[CaseNode] = [_build_case_from_if(if_node, profile)]

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
        # else if: 再帰
        cases.extend(_collect_all_cases_nested(else_body, profile))
    else:
        # else ブロック（statement_block / block）
        action_texts = _extract_case_action_texts(else_body, profile)
        cases.append(CaseNode(
            condition_text="上記のいずれにも該当しない場合（デフォルト）",
            action_texts=action_texts,
        ))

    return cases


def _collect_all_cases_flat(if_node: Node, profile: LanguageProfile) -> list[CaseNode]:
    """
    Python スタイル: elif_clause / else_clause が if_statement の兄弟として並ぶ。

    named_children の構造:
    [0] condition   (比較式等)
    [1] block       (then ブロック)
    [2..] elif_clause* (0個以上)
    [last] else_clause  (省略可)
    """
    named = if_node.named_children

    # if 本体のケース
    condition_text = _strip_outer_parens(_extract_node_text(named[0]))
    block_node = named[1]
    action_texts = _extract_case_action_texts(block_node, profile)
    cases: list[CaseNode] = [CaseNode(condition_text=condition_text, action_texts=action_texts)]

    # elif / else ケース（インデックス 2 以降）
    for node in named[2:]:
        if node.type == "elif_clause":
            cond_node = node.child_by_field_name("condition")
            conseq_node = node.child_by_field_name("consequence")
            cond_text = (
                _strip_outer_parens(_extract_node_text(cond_node))
                if cond_node is not None
                else ""
            )
            elif_actions = (
                _extract_case_action_texts(conseq_node, profile)
                if conseq_node is not None
                else ()
            )
            cases.append(CaseNode(condition_text=cond_text, action_texts=elif_actions))

        elif node.type == "else_clause":
            body = node.child_by_field_name("body")
            else_actions = _extract_case_action_texts(body, profile) if body is not None else ()
            cases.append(CaseNode(
                condition_text="上記のいずれにも該当しない場合（デフォルト）",
                action_texts=else_actions,
            ))

    return cases


def _map_if_to_condition_block(if_node: Node, profile: LanguageProfile) -> ConditionBlock:
    """if/else チェーン全体を ConditionBlock IR ノードに変換する。"""
    if profile.elif_structure == "nested":
        cases = _collect_all_cases_nested(if_node, profile)
    else:
        cases = _collect_all_cases_flat(if_node, profile)

    return ConditionBlock(
        kind="ConditionBlock",
        cases=tuple(cases),
    )


# ---------------------------------------------------------------------------
# マッピング: for ループ → LoopNode IR（TypeScript / Python 共通）
# ---------------------------------------------------------------------------


def _is_for_of(for_node: Node) -> bool:
    """TypeScript: for_in_statement が for...of 構文かどうかを判定する。"""
    return _has_child_of_type(for_node, "of")


def _map_for_each_to_loop(for_node: Node, profile: LanguageProfile) -> LoopNode:
    """
    for...of（TypeScript）または for...in（Python）を LoopNode IR（FOR_EACH）に変換する。

    tree-sitter のフィールド名は両言語とも left / right / body で統一されている。
    """
    left_node = for_node.child_by_field_name("left")
    right_node = for_node.child_by_field_name("right")
    body_node = for_node.child_by_field_name("body")

    iterator = _extract_node_text(left_node).strip() if left_node is not None else "item"
    collection = _extract_node_text(right_node).strip() if right_node is not None else ""
    nested_body = _extract_body_ir_nodes(body_node, profile) if body_node is not None else []

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

    init_text = _extract_node_text(initializer).rstrip(";").strip() if initializer is not None else ""
    cond_text = _extract_node_text(condition).strip() if condition is not None else ""
    incr_text = _extract_node_text(increment).strip() if increment is not None else ""

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
                return _extract_node_text(name_node).strip()

    return "i"


def _map_for_range_to_loop(for_node: Node, profile: LanguageProfile) -> LoopNode:
    """古典的 for 文（TypeScript のみ）を LoopNode IR（FOR_RANGE）に変換する。"""
    body_node = for_node.child_by_field_name("body")
    nested_body = _extract_body_ir_nodes(body_node, profile) if body_node is not None else []

    return LoopNode(
        kind="Loop",
        loop_type="FOR_RANGE",
        collection=_extract_for_range_summary(for_node),
        iterator=_extract_for_range_iterator(for_node),
        body=tuple(nested_body),
    )


# ---------------------------------------------------------------------------
# マッピング: for ループ → LoopNode IR（Go 専用）
# ---------------------------------------------------------------------------


def _has_range_clause(for_node: Node) -> bool:
    """Go: for_statement が range_clause を持つか（for...range ループ）。"""
    return _has_child_of_type(for_node, "range_clause")


def _has_for_clause(for_node: Node) -> bool:
    """Go: for_statement が for_clause を持つか（C スタイルループ）。"""
    return _has_child_of_type(for_node, "for_clause")


def _extract_go_range_iterator(range_clause: Node) -> str:
    """
    Go の range_clause から iterator 変数テキストを返す。

    range_clause の構造:
        expression_list (variables) := range collection
    named_children[0] = expression_list（左辺の変数群: "_, item" 等）
    """
    left_node = range_clause.named_children[0] if range_clause.named_children else None
    if left_node is None:
        return "item"
    return _extract_node_text(left_node).strip()


def _extract_go_range_collection(range_clause: Node) -> str:
    """
    Go の range_clause からコレクション式テキストを返す。

    named_children の最後が range 対象（right 側）になる。
    """
    children = range_clause.named_children
    if len(children) < 2:
        return ""
    return _extract_node_text(children[-1]).strip()


def _map_go_for_each_to_loop(for_node: Node, profile: LanguageProfile) -> LoopNode:
    """Go の for...range 文を LoopNode IR（FOR_EACH）に変換する。"""
    range_clause = next(
        (c for c in for_node.named_children if c.type == "range_clause"),
        None,
    )
    iterator = _extract_go_range_iterator(range_clause) if range_clause is not None else "item"
    collection = _extract_go_range_collection(range_clause) if range_clause is not None else ""

    body_node = for_node.child_by_field_name("body")
    nested_body = _extract_body_ir_nodes(body_node, profile) if body_node is not None else []

    return LoopNode(
        kind="Loop",
        loop_type="FOR_EACH",
        collection=collection,
        iterator=iterator,
        body=tuple(nested_body),
    )


def _extract_go_for_clause_summary(for_clause: Node) -> str:
    """Go の for_clause サマリーを 'init; condition; update' 形式で返す。"""
    parts = [_extract_node_text(c).strip() for c in for_clause.named_children]
    return "; ".join(parts)


def _extract_go_for_clause_iterator(for_clause: Node) -> str:
    """Go の for_clause の初期化文からカウンタ変数名を返す。"""
    if not for_clause.named_children:
        return "i"
    init_node = for_clause.named_children[0]
    if init_node.type == "short_var_declaration":
        left_node = init_node.named_children[0] if init_node.named_children else None
        if left_node is not None:
            first_id = next(
                (c for c in left_node.named_children if c.type == "identifier"),
                None,
            )
            if first_id is not None:
                return _extract_node_text(first_id)
    return "i"


def _map_go_for_range_to_loop(for_node: Node, profile: LanguageProfile) -> LoopNode:
    """Go の C スタイル for 文を LoopNode IR（FOR_RANGE）に変換する。"""
    for_clause = next(
        (c for c in for_node.named_children if c.type == "for_clause"),
        None,
    )
    body_node = for_node.child_by_field_name("body")
    nested_body = _extract_body_ir_nodes(body_node, profile) if body_node is not None else []

    collection = _extract_go_for_clause_summary(for_clause) if for_clause is not None else ""
    iterator = _extract_go_for_clause_iterator(for_clause) if for_clause is not None else "i"

    return LoopNode(
        kind="Loop",
        loop_type="FOR_RANGE",
        collection=collection,
        iterator=iterator,
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

    target = _extract_node_text(left_node).strip() if left_node is not None else ""
    value = _extract_node_text(right_node).strip() if right_node is not None else ""
    op_text = _extract_node_text(op_node).strip() if op_node is not None else "+="
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

    target = _extract_node_text(left_node).strip() if left_node is not None else ""
    value = _extract_node_text(right_node).strip() if right_node is not None else ""

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
        description=_extract_node_text(expr_node).strip(),
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

    target = _extract_node_text(name_node).strip() if name_node is not None else ""
    value = _extract_node_text(value_node).strip()

    return DataTransformation(
        kind="DataTransformation",
        target=target,
        operation="ASSIGN",
        value=value,
    )


# ---------------------------------------------------------------------------
# マッピング: Go 専用の代入文 → DataTransformation IR
# ---------------------------------------------------------------------------


def _map_go_assignment_to_ir(stmt_node: Node) -> Optional[DataTransformation]:
    """
    Go の assignment_statement（x = y, x += y, x -= y 等）を
    DataTransformation IR ノードに変換する。

    構造:
        expression_list  +=|-=|=  expression_list
    named_children[0] = 左辺 expression_list
    named_children[-1] = 右辺 expression_list
    演算子は non-named child として埋め込まれている。
    """
    named = stmt_node.named_children
    if len(named) < 2:
        return None

    left_node = named[0]
    right_node = named[-1]

    # 演算子は非名前付き子ノードから取得
    op_text = "="
    for c in stmt_node.children:
        if not c.is_named and c.text:
            txt = c.text.decode()
            if txt in _AUGMENTED_ASSIGNMENT_OPERATIONS or txt == "=":
                op_text = txt
                break

    target = _extract_node_text(left_node).strip()
    value = _extract_node_text(right_node).strip()
    operation = _AUGMENTED_ASSIGNMENT_OPERATIONS.get(op_text, "ASSIGN")

    return DataTransformation(
        kind="DataTransformation",
        target=target,
        operation=operation,
        value=value,
    )


def _map_go_short_var_decl_to_ir(stmt_node: Node) -> Optional[DataTransformation]:
    """
    Go の short_var_declaration（x := y）を DataTransformation（ASSIGN）IR に変換する。

    構造:
        expression_list  :=  expression_list
    named_children[0] = 左辺 expression_list（変数名）
    named_children[-1] = 右辺 expression_list（初期値）
    """
    named = stmt_node.named_children
    if len(named) < 2:
        return None

    left_node = named[0]
    right_node = named[-1]

    target = _extract_node_text(left_node).strip()
    value = _extract_node_text(right_node).strip()

    return DataTransformation(
        kind="DataTransformation",
        target=target,
        operation="ASSIGN",
        value=value,
    )


def _map_go_var_decl_to_ir(stmt_node: Node) -> Optional[DataTransformation]:
    """
    Go の var_declaration（関数内の var x = y）を DataTransformation（ASSIGN）IR に変換する。

    var_declaration → var_spec → name / value フィールド
    """
    spec_node = next(
        (c for c in stmt_node.named_children if c.type == "var_spec"),
        None,
    )
    if spec_node is None:
        return None

    name_node = spec_node.child_by_field_name("name")
    value_node = spec_node.child_by_field_name("value")

    if name_node is None or value_node is None:
        return None

    target = _extract_node_text(name_node).strip()
    value = _extract_node_text(value_node).strip()

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
    statement_node: Node, profile: LanguageProfile
) -> Optional[IRNode]:
    """
    1つの文ASTノードを profile を参照して適切な IR ノードに変換する。

    対応する文タイプ（profile によって異なる）:
    - if_statement                               → GuardClause または ConditionBlock
    - for_each_node_type (TS: of / Py: in / Go: range_clause) → LoopNode (FOR_EACH)
    - for_range_node_type (TS のみ / Go は for_each と共用)    → LoopNode (FOR_RANGE)
    - expression_statement                       → DataTransformation または SideEffect
    - lexical_declaration_types (TS のみ)        → DataTransformation
    - assignment_statement (Go のみ)             → DataTransformation
    - short_var_declaration (Go のみ)            → DataTransformation
    - var_declaration (Go のみ)                  → DataTransformation

    変換後、直前の comment ノードがあれば IR ノードの comment フィールドに付与する。
    """
    node_type = statement_node.type
    ir_node: Optional[IRNode] = None

    if node_type == "if_statement":
        if _is_guard_clause(statement_node, profile):
            ir_node = _map_if_to_guard_clause(statement_node, profile)
        else:
            ir_node = _map_if_to_condition_block(statement_node, profile)

    elif node_type == profile.for_each_node_type:
        if profile.name == "typescript" and not _is_for_of(statement_node):
            return None  # for...in はスコープ外（Phase 1 定義）
        elif profile.name == "go":
            # Go は for_statement が range / C スタイル / 無限ループを兼ねる
            if _has_range_clause(statement_node):
                ir_node = _map_go_for_each_to_loop(statement_node, profile)
            elif _has_for_clause(statement_node):
                ir_node = _map_go_for_range_to_loop(statement_node, profile)
            else:
                return None  # 無限ループ・while スタイルは対象外
        else:
            ir_node = _map_for_each_to_loop(statement_node, profile)

    elif profile.for_range_node_type and node_type == profile.for_range_node_type:
        ir_node = _map_for_range_to_loop(statement_node, profile)

    elif node_type == "expression_statement":
        ir_node = _map_expression_statement_to_ir(statement_node, profile)

    elif node_type in profile.lexical_declaration_types:
        ir_node = _map_lexical_declaration_to_ir(statement_node)

    # --- Go 専用の直接代入文 ---
    elif profile.name == "go" and node_type == "assignment_statement":
        ir_node = _map_go_assignment_to_ir(statement_node)

    elif profile.name == "go" and node_type == "short_var_declaration":
        ir_node = _map_go_short_var_decl_to_ir(statement_node)

    elif profile.name == "go" and node_type == "var_declaration":
        ir_node = _map_go_var_decl_to_ir(statement_node)

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


def _extract_body_ir_nodes(body_node: Node, profile: LanguageProfile) -> list[IRNode]:
    """
    ブロックノード（statement_block / block）から、
    マッピング可能な IRNode の一覧を返す。

    _get_block_statements を使うことで Go の statement_list 二段構造を吸収する。
    """
    results: list[IRNode] = []
    for statement in _get_block_statements(body_node, profile):
        ir_node = _map_statement_to_ir(statement, profile)
        if ir_node is not None:
            results.append(ir_node)
    return results


# ---------------------------------------------------------------------------
# 関数レベルのマッピング
# ---------------------------------------------------------------------------


def _find_top_level_functions(root_node: Node, profile: LanguageProfile) -> list[Node]:
    """プログラムの直接の子から、profile.function_node_type のノードを返す。"""
    return [
        child for child in root_node.named_children
        if child.type == profile.function_node_type
    ]


def _map_function_to_spec(fn_node: Node, profile: LanguageProfile) -> FunctionSpec:
    """関数定義 AST ノードを FunctionSpec IR に変換する。"""
    name_node = fn_node.child_by_field_name("name")
    name = _extract_node_text(name_node).strip() if name_node is not None else "anonymous"

    body_node = fn_node.child_by_field_name("body")
    ir_nodes = _extract_body_ir_nodes(body_node, profile) if body_node is not None else []

    return FunctionSpec(
        name=name,
        body=tuple(ir_nodes),
        description=_get_function_description(fn_node, profile),
    )


# ---------------------------------------------------------------------------
# モジュールレベルの抽出: インポート
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
    # ソースモジュール名（最後の string ノード）
    source_module = ""
    for child in import_node.children:
        if child.type == "string":
            raw = _extract_node_text(child)
            source_module = raw.strip("'\"` ")

    imported_names: list[str] = []
    alias = ""

    # import_clause の中を調べる
    for child in import_node.children:
        if child.type == "import_clause":
            for clause_child in child.children:
                if clause_child.type == "identifier":
                    # default import: import React from 'react'
                    imported_names.append(_extract_node_text(clause_child))
                elif clause_child.type == "namespace_import":
                    # import * as x from 'y'
                    alias = "*"
                    for ns_child in clause_child.children:
                        if ns_child.type == "identifier":
                            alias = _extract_node_text(ns_child)
                elif clause_child.type == "named_imports":
                    # import { A, B } from 'x'
                    for spec in clause_child.children:
                        if spec.type == "import_specifier":
                            name_node = spec.child_by_field_name("name")
                            if name_node is not None:
                                imported_names.append(_extract_node_text(name_node))

    return ImportSpec(
        kind="ImportSpec",
        source_module=source_module,
        imported_names=tuple(imported_names),
        alias=alias,
    )


def _extract_py_import(import_node: Node) -> Optional[ImportSpec]:
    """
    Python の import_statement / import_from_statement / future_import_statement
    ノードから ImportSpec を生成する。
    """
    if import_node.type == "future_import_statement":
        imported_names = tuple(
            _extract_node_text(child)
            for child in import_node.named_children
            if child.type == "dotted_name"
        )
        return ImportSpec(
            kind="ImportSpec",
            source_module="__future__",
            imported_names=imported_names,
            alias="",
        )
    if import_node.type == "import_statement":
        for child in import_node.named_children:
            if child.type == "dotted_name":
                return ImportSpec(
                    kind="ImportSpec",
                    source_module=_extract_node_text(child),
                    imported_names=(),
                    alias="",
                )
            if child.type == "aliased_import":
                name_node = child.named_children[0] if child.named_children else None
                alias_node = child.named_children[1] if len(child.named_children) > 1 else None
                source = _extract_node_text(name_node) if name_node else ""
                alias = _extract_node_text(alias_node) if alias_node else ""
                return ImportSpec(
                    kind="ImportSpec",
                    source_module=source,
                    imported_names=(),
                    alias=alias,
                )
        return None

    if import_node.type == "import_from_statement":
        named = import_node.named_children
        if not named:
            return None
        first = named[0]
        if first.type == "relative_import":
            source_module = _extract_node_text(first)
        else:
            source_module = _extract_node_text(first)
        imported_names = tuple(
            _extract_node_text(child)
            for child in named[1:]
            if child.type == "dotted_name"
        )
        return ImportSpec(
            kind="ImportSpec",
            source_module=source_module,
            imported_names=imported_names,
            alias="",
        )

    return None


def _extract_go_import_spec(spec_node: Node) -> Optional[ImportSpec]:
    """
    Go の import_spec ノードから ImportSpec を生成する。

    import_spec の構造:
        [name: package_identifier]  path: interpreted_string_literal
    path フィールドの内部コンテンツノードからモジュール名を取得する。
    """
    path_node = spec_node.child_by_field_name("path")
    name_node = spec_node.child_by_field_name("name")

    if path_node is None:
        return None

    # interpreted_string_literal の内部コンテンツノードを探す
    content_node = next(
        (c for c in path_node.named_children if "content" in c.type),
        None,
    )
    if content_node is not None:
        module_name = _extract_node_text(content_node)
    else:
        # フォールバック: リテラル全体から引用符を除去
        module_name = _extract_node_text(path_node).strip('"')

    alias = _extract_node_text(name_node).strip() if name_node is not None else ""

    return ImportSpec(
        kind="ImportSpec",
        source_module=module_name,
        imported_names=(),
        alias=alias,
    )


def _extract_go_imports(import_node: Node) -> list[ImportSpec]:
    """
    Go の import_declaration（単一 / グループ）から ImportSpec リストを生成する。

    単一: import_declaration → import_spec
    グループ: import_declaration → import_spec_list → import_spec*
    """
    results: list[ImportSpec] = []
    for child in import_node.named_children:
        if child.type == "import_spec":
            spec = _extract_go_import_spec(child)
            if spec is not None:
                results.append(spec)
        elif child.type == "import_spec_list":
            for spec_node in child.named_children:
                if spec_node.type == "import_spec":
                    spec = _extract_go_import_spec(spec_node)
                    if spec is not None:
                        results.append(spec)
    return results


def _extract_all_imports(
    root_node: Node, profile: LanguageProfile
) -> tuple[ImportSpec, ...]:
    """プログラムのトップレベルからインポート文を収集して返す。"""
    results: list[ImportSpec] = []
    for child in root_node.named_children:
        if child.type not in profile.import_node_types:
            continue
        if profile.name == "typescript":
            spec = _extract_ts_import(child)
            if spec is not None:
                results.append(spec)
        elif profile.name == "go":
            # Go は1 import_declaration に複数 spec が含まれる場合がある
            results.extend(_extract_go_imports(child))
        else:
            spec = _extract_py_import(child)
            if spec is not None:
                results.append(spec)
    return tuple(results)


# ---------------------------------------------------------------------------
# モジュールレベルの抽出: 変数・定数定義
# ---------------------------------------------------------------------------


def _extract_ts_module_variable(node: Node) -> Optional[ModuleVariableSpec]:
    """
    TypeScript トップレベルの lexical_declaration（const/let）から
    ModuleVariableSpec を生成する。
    """
    is_constant = any(
        child.type == "const" or _extract_node_text(child) == "const"
        for child in node.children
        if not child.is_named
    )

    declarator = next(
        (c for c in node.named_children if c.type == "variable_declarator"),
        None,
    )
    if declarator is None:
        return None

    name_node = declarator.child_by_field_name("name")
    value_node = declarator.child_by_field_name("value")

    if name_node is None or value_node is None:
        return None

    name = _extract_node_text(name_node).strip()
    value_text = _truncate_text(_extract_node_text(value_node))

    return ModuleVariableSpec(
        kind="ModuleVariableSpec",
        name=name,
        value_text=value_text,
        is_constant=is_constant,
    )


def _extract_py_module_variable(node: Node) -> Optional[ModuleVariableSpec]:
    """
    Python トップレベルの expression_statement 内の assignment から
    ModuleVariableSpec を生成する。
    """
    assignment = next(
        (c for c in node.named_children if c.type == "assignment"),
        None,
    )
    if assignment is None:
        return None

    left_node = assignment.child_by_field_name("left")
    right_node = assignment.child_by_field_name("right")

    if left_node is None or right_node is None:
        return None

    name = _extract_node_text(left_node).strip()
    if "," in name:
        return None

    value_text = _truncate_text(_extract_node_text(right_node))
    is_constant = name.isupper() or (name.replace("_", "").isupper() and "_" in name)

    return ModuleVariableSpec(
        kind="ModuleVariableSpec",
        name=name,
        value_text=value_text,
        is_constant=is_constant,
    )


def _extract_go_module_variable(node: Node) -> Optional[ModuleVariableSpec]:
    """
    Go トップレベルの var_declaration / const_declaration から ModuleVariableSpec を生成する。

    var_declaration   → var_spec   → name / value フィールド
    const_declaration → const_spec → name / value フィールド
    """
    is_constant = node.type == "const_declaration"
    spec_type = "const_spec" if is_constant else "var_spec"

    spec_node = next(
        (c for c in node.named_children if c.type == spec_type),
        None,
    )
    if spec_node is None:
        return None

    name_node = spec_node.child_by_field_name("name")
    value_node = spec_node.child_by_field_name("value")

    if name_node is None or value_node is None:
        return None

    name = _extract_node_text(name_node).strip()
    value_text = _truncate_text(_extract_node_text(value_node))

    return ModuleVariableSpec(
        kind="ModuleVariableSpec",
        name=name,
        value_text=value_text,
        is_constant=is_constant,
    )


def _extract_all_module_variables(
    root_node: Node, profile: LanguageProfile
) -> tuple[ModuleVariableSpec, ...]:
    """プログラムのトップレベルから変数・定数定義を収集して返す。"""
    results: list[ModuleVariableSpec] = []
    for child in root_node.named_children:
        if child.type not in profile.module_var_node_types:
            continue
        if profile.name == "typescript":
            spec = _extract_ts_module_variable(child)
        elif profile.name == "go":
            spec = _extract_go_module_variable(child)
        else:
            spec = _extract_py_module_variable(child)
        if spec is not None:
            results.append(spec)
    return tuple(results)


# ---------------------------------------------------------------------------
# モジュールレベルの抽出: 型定義（TypeScript のみ）
# ---------------------------------------------------------------------------


def _extract_ts_type_definition(node: Node) -> Optional[TypeDefinitionSpec]:
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

    name = _extract_node_text(name_node).strip()

    if node.type == "type_alias_declaration":
        type_body_node = next(
            (c for c in node.named_children if c.type != "type_identifier"),
            None,
        )
        type_text = _truncate_text(_extract_node_text(type_body_node)) if type_body_node else ""
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
        type_text = _truncate_text(_extract_node_text(body_node)) if body_node else ""
        return TypeDefinitionSpec(
            kind="TypeDefinitionSpec",
            name=name,
            definition_kind="interface",
            type_text=type_text,
        )

    return None


def _extract_all_type_definitions(
    root_node: Node, profile: LanguageProfile
) -> tuple[TypeDefinitionSpec, ...]:
    """プログラムのトップレベルから型定義を収集して返す（TypeScript のみ）。"""
    if not profile.type_alias_node_type and not profile.interface_node_type:
        return ()

    target_types = {
        t for t in (profile.type_alias_node_type, profile.interface_node_type) if t
    }

    results: list[TypeDefinitionSpec] = []
    for child in root_node.named_children:
        if child.type not in target_types:
            continue
        spec = _extract_ts_type_definition(child)
        if spec is not None:
            results.append(spec)
    return tuple(results)


# ---------------------------------------------------------------------------
# 公開インターフェース
# ---------------------------------------------------------------------------


def map_source_to_module_spec(
    root_node: Node, module_name: str, profile: LanguageProfile
) -> ModuleSpec:
    """
    ソースファイルの AST ルートノードを ModuleSpec IR に変換する。

    これがミドルウェア層の唯一の公開インターフェース。

    Args:
        root_node:   tree-sitter の program/module ルートノード
        module_name: モジュール名（通常はファイル名のステム）
        profile:     使用言語の LanguageProfile

    Returns:
        ModuleSpec IR オブジェクト（imports / module_variables / type_definitions / functions を含む）
    """
    return ModuleSpec(
        name=module_name,
        file_comment=_get_file_header_comment(root_node, profile),
        imports=_extract_all_imports(root_node, profile),
        module_variables=_extract_all_module_variables(root_node, profile),
        type_definitions=_extract_all_type_definitions(root_node, profile),
        functions=tuple(
            _map_function_to_spec(fn_node, profile)
            for fn_node in _find_top_level_functions(root_node, profile)
        ),
    )
