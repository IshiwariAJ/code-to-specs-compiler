"""
PowerShell 言語プラグイン (.ps1 / .psm1)

このファイルを src/languages/ に置くだけで、パイプラインが
.ps1 / .psm1 ファイルを自動的に処理できるようになる。

対応する PowerShell 構文:
  - function Get-Name { param(...) ... }  → FunctionSpec
  - if (-not $x) { throw "..." }          → GuardClause
  - if ($x) { ... } elseif { ... } else  → ConditionBlock
  - foreach ($item in $items) { ... }     → LoopNode (FOR_EACH)
  - $result = $value                      → DataTransformation (ASSIGN)
  - $count += 1                           → DataTransformation (ADD)
  - Write-Output $x                       → SideEffect
  - return $result / throw "err"          → ReturnNode
"""
from __future__ import annotations

from typing import Callable, Optional

from tree_sitter import Node

from ..ir.node_utils import extract_node_text, normalize_whitespace
from ..ir.profiles import LanguageProfile
from ..ir.types import (
    DataTransformation,
    ImportSpec,
    IRNode,
    LoopNode,
    ModuleVariableSpec,
    ParamSpec,
    SideEffect,
)
from ..parser.powershell_parser import parse_powershell_source
from . import LanguagePlugin

# ---------------------------------------------------------------------------
# LanguageProfile 定数
# ---------------------------------------------------------------------------

POWERSHELL_PROFILE = LanguageProfile(
    name="powershell",
    function_node_type="function_statement",
    for_each_node_type="foreach_statement",
    for_range_node_type="",              # PowerShell の for は将来対応
    guard_action_types=frozenset({"flow_control_statement"}),
    condition_has_outer_parens=False,    # condition フィールドが pipeline（括弧なし）を返す
    augmented_assignment_type="",        # PowerShell は pipeline 内の assignment_expression
    assignment_type="",
    call_type="",                        # command は pipeline 経由（direct_statement_types で処理）
    elif_structure="elseif_clauses",     # elseif_clauses コンテナ + else_clause
    lexical_declaration_types=frozenset(),
    import_node_types=frozenset(),       # using module 等は将来対応
    module_var_node_types=frozenset(),   # スクリプトスコープ変数は将来対応
    type_alias_node_type="",
    interface_node_type="",
    block_inner_node_type="statement_list",  # statement_block → statement_list → 文ノード
    has_module_docstring=False,
    for_loop_flavor="always_foreach",    # mapper では参照されない（ps_for_loop_mapper フックを使用）
    direct_statement_types=frozenset({"pipeline"}),  # 代入・コマンド呼び出しはすべて pipeline
    class_node_types=frozenset(),        # PowerShell class は将来対応
    # 言語固有アクセス方法
    if_then_block_access="statement_block_child",
    function_name_access="function_name_child",
    function_body_access="script_block_body",
    top_level_wrapper_type="statement_list",  # program → statement_list → function_statement
)

# PowerShell 代入演算子マッピング
_PS_AUGMENTED_OPS: dict[str, str] = {
    "+=": "ADD",
    "-=": "SUBTRACT",
    "*=": "MULTIPLY",
    "/=": "DIVIDE",
    "%=": "MODULO",
}


# ---------------------------------------------------------------------------
# 関数説明文抽出（<# .SYNOPSIS ... #> コメント）
# ---------------------------------------------------------------------------

def _extract_ps_synopsis(comment_text: str) -> str:
    """
    PowerShell コメントベースヘルプ（<# .SYNOPSIS ... #>）から .SYNOPSIS の内容を抽出する。

    .SYNOPSIS セクションが存在しない場合はコメント全体（クリーンアップ後）を返す。
    """
    lines = comment_text.strip().lstrip("<#").rstrip("#>").strip().splitlines()
    in_synopsis = False
    synopsis_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith(".SYNOPSIS"):
            in_synopsis = True
            rest = stripped[len(".SYNOPSIS"):].strip()
            if rest:
                synopsis_lines.append(rest)
            continue
        if in_synopsis:
            if stripped.startswith("."):
                break  # 次のセクションが始まった
            synopsis_lines.append(stripped)

    if synopsis_lines:
        return " ".join(s for s in synopsis_lines if s)
    # .SYNOPSIS がなければ先頭の非空行（または空文字）
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("."):
            return stripped
    return ""


def extract_ps_function_description(fn_node: Node) -> str:
    """
    PowerShell 関数の <# .SYNOPSIS ... #> コメントから説明文を返す
    （LanguagePlugin.function_description_extractor フック）。

    <# ... #> コメントは function_statement の named_child として現れる。
    コメントが存在しない場合は空文字を返す。
    """
    comment_node = next((c for c in fn_node.named_children if c.type == "comment"), None)
    if comment_node is None:
        return ""
    return _extract_ps_synopsis(extract_node_text(comment_node))


# ---------------------------------------------------------------------------
# foreach ループ変換（named_children アクセス）
# ---------------------------------------------------------------------------

def ps_for_loop_mapper(
    for_node: Node,
    extract_body: Callable[[Node], list[IRNode]],
) -> Optional[LoopNode]:
    """
    PowerShell の foreach_statement を LoopNode IR（FOR_EACH）に変換する
    （LanguagePlugin.for_loop_mapper フック）。

    foreach ($item in $collection) { ... } の AST 構造:
      named_children[0]: variable  （$item）
      named_children[1]: pipeline  （$collection）
      named_children[2]: statement_block（ボディ）
    """
    fe_named = for_node.named_children
    left_node = fe_named[0] if len(fe_named) > 0 else None   # variable ($item)
    right_node = fe_named[1] if len(fe_named) > 1 else None  # pipeline ($collection)
    body_node = fe_named[2] if len(fe_named) > 2 else None   # statement_block

    iterator = extract_node_text(left_node).strip() if left_node is not None else "item"
    collection = extract_node_text(right_node).strip() if right_node is not None else ""
    nested_body = extract_body(body_node) if body_node is not None else []

    return LoopNode(
        kind="Loop",
        loop_type="FOR_EACH",
        collection=collection,
        iterator=iterator,
        body=tuple(nested_body),
    )


# ---------------------------------------------------------------------------
# インポート抽出（MVP では未対応）
# ---------------------------------------------------------------------------

def extract_ps_imports(import_node: Node) -> list[ImportSpec]:
    """PowerShell の using 文は将来対応。現在は空リストを返す。"""
    return []


# ---------------------------------------------------------------------------
# モジュール変数抽出（MVP では未対応）
# ---------------------------------------------------------------------------

def extract_ps_module_variable(node: Node) -> Optional[ModuleVariableSpec]:
    """PowerShell のスクリプトスコープ変数は将来対応。"""
    return None


# ---------------------------------------------------------------------------
# pipeline 文の変換: 代入または SideEffect（コマンド呼び出し）
# ---------------------------------------------------------------------------

def _extract_ps_assignment(assign_node: Node) -> Optional[DataTransformation]:
    """
    PowerShell の assignment_expression を DataTransformation に変換する。

    構造:
        left_assignment_expression | assignement_operator | pipeline
    ※ 文法の typo: "assignment" → "assignement"（tree-sitter-powershell の仕様）
    """
    left_node = next(
        (c for c in assign_node.named_children if c.type == "left_assignment_expression"),
        None,
    )
    op_node = next(
        (c for c in assign_node.named_children if c.type == "assignement_operator"),
        None,
    )
    right_node = next(
        (c for c in assign_node.named_children if c.type == "pipeline"),
        None,
    )

    if left_node is None or right_node is None:
        return None

    target = extract_node_text(left_node).strip()
    value = extract_node_text(right_node).strip()
    op_text = extract_node_text(op_node).strip() if op_node is not None else "="
    operation = _PS_AUGMENTED_OPS.get(op_text, "ASSIGN")

    return DataTransformation(
        kind="DataTransformation",
        target=target,
        operation=operation,
        value=value,
    )


def map_ps_pipeline_to_ir(pipeline_node: Node) -> Optional[IRNode]:
    """
    PowerShell のトップレベル pipeline 文を DataTransformation または SideEffect に変換する。

    - assignment_expression を含む → DataTransformation（代入）
    - pipeline_chain を含む        → SideEffect（コマンド呼び出し）
    """
    named = pipeline_node.named_children
    if not named:
        return None

    first = named[0]

    if first.type == "assignment_expression":
        return _extract_ps_assignment(first)

    if first.type == "pipeline_chain":
        return SideEffect(
            kind="SideEffect",
            description=extract_node_text(pipeline_node).strip(),
        )

    return None


# ---------------------------------------------------------------------------
# 引数抽出
# ---------------------------------------------------------------------------

def _get_type_text_from_attribute_list(attr_list: Node) -> str:
    """
    attribute_list → attribute → type_literal → type_spec → type_name → type_identifier
    のパスで型テキストを取得する。
    """
    attr = next((c for c in attr_list.named_children if c.type == "attribute"), None)
    if attr is None:
        return ""
    type_lit = next((c for c in attr.named_children if c.type == "type_literal"), None)
    if type_lit is None:
        return ""
    type_spec = next((c for c in type_lit.named_children if c.type == "type_spec"), None)
    if type_spec is None:
        return ""
    type_name = next((c for c in type_spec.named_children if c.type == "type_name"), None)
    if type_name is None:
        return ""
    type_id = next((c for c in type_name.named_children if c.type == "type_identifier"), None)
    return extract_node_text(type_id).strip() if type_id is not None else ""


def extract_ps_params(fn_node: Node) -> tuple[ParamSpec, ...]:
    """
    PowerShell の function_statement から param_block を辿って引数リストを抽出する。

    function_statement → script_block → param_block → parameter_list → script_parameter*
    script_parameter 構造:
      attribute_list (型情報: [string], [int] 等)
      variable       ($Name 等)
      script_parameter_default（デフォルト値、オプション）
    """
    script_block = next(
        (c for c in fn_node.named_children if c.type == "script_block"),
        None,
    )
    if script_block is None:
        return ()

    param_block = next(
        (c for c in script_block.named_children if c.type == "param_block"),
        None,
    )
    if param_block is None:
        return ()

    param_list = next(
        (c for c in param_block.named_children if c.type == "parameter_list"),
        None,
    )
    if param_list is None:
        return ()

    results: list[ParamSpec] = []
    for sp in param_list.named_children:
        if sp.type != "script_parameter":
            continue

        var_node = next((c for c in sp.named_children if c.type == "variable"), None)
        if var_node is None:
            continue
        name = extract_node_text(var_node).strip()  # $Name のまま保持

        attr_list = next((c for c in sp.named_children if c.type == "attribute_list"), None)
        type_text = _get_type_text_from_attribute_list(attr_list) if attr_list is not None else ""

        results.append(ParamSpec(name=name, type_text=type_text))

    return tuple(results)


# ---------------------------------------------------------------------------
# 戻り値型抽出（PowerShell は静的型なし）
# ---------------------------------------------------------------------------

def extract_ps_return_type(_fn_node: Node) -> str:
    """PowerShell は戻り値型アノテーションを持たないため空文字を返す。"""
    return ""


# ---------------------------------------------------------------------------
# プラグイン定数（discover_plugins() が検出する）
# ---------------------------------------------------------------------------

PLUGIN = LanguagePlugin(
    extensions=(".ps1", ".psm1"),
    profile=POWERSHELL_PROFILE,
    parse_source=parse_powershell_source,
    import_extractor=extract_ps_imports,
    module_var_extractor=extract_ps_module_variable,
    type_def_extractor=lambda _: None,
    class_extractor=lambda _: None,
    direct_statement_extractors=(
        ("pipeline", map_ps_pipeline_to_ir),
    ),
    param_extractor=extract_ps_params,
    return_type_extractor=extract_ps_return_type,
    for_loop_mapper=ps_for_loop_mapper,                              # foreach 構文差異を吸収
    function_description_extractor=extract_ps_function_description,  # <# .SYNOPSIS #> を使用
)
