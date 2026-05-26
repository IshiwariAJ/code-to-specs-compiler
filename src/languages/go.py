"""
Go 言語プラグイン

このファイルを src/languages/ に置くだけで、パイプラインが
.go ファイルを自動的に処理できるようになる。
"""
from __future__ import annotations

from typing import Optional

from tree_sitter import Node

from ..ir.node_utils import extract_node_text, normalize_whitespace
from ..ir.profiles import LanguageProfile
from ..ir.types import DataTransformation, ImportSpec, ModuleVariableSpec, ParamSpec
from ..parser.go_parser import parse_go_source
from . import LanguagePlugin

# ---------------------------------------------------------------------------
# LanguageProfile 定数
# ---------------------------------------------------------------------------

GO_PROFILE = LanguageProfile(
    name="go",
    function_node_type="function_declaration",
    # Go の for は range / C スタイル / 無限ループがすべて for_statement
    # 内部で range_clause / for_clause の有無を判定して振り分ける
    for_each_node_type="for_statement",
    for_range_node_type="",  # for_each_node_type と同じノード。空文字で第2パスを無効化
    guard_action_types=frozenset({"return_statement"}),  # Go に throw はない（panic は call）
    condition_has_outer_parens=False,   # Go は if x > 0 { の形（括弧不要）
    augmented_assignment_type="",       # Go の代入は expression_statement に包まれない直接文
    assignment_type="",                 # 同上
    call_type="call_expression",
    elif_structure="nested",            # else if → alternative = if_statement（TypeScript と同じ構造）
    lexical_declaration_types=frozenset(),  # Go の代入は直接処理（assignment_statement / short_var_declaration）
    import_node_types=frozenset({"import_declaration"}),
    module_var_node_types=frozenset({"var_declaration", "const_declaration"}),
    type_alias_node_type="",    # Go の type 宣言は将来対応
    interface_node_type="",
    block_inner_node_type="statement_list",  # Go: block → statement_list → 文ノード
    function_description_style="comment",
    has_module_docstring=False,
    for_loop_flavor="range_clause",
    direct_statement_types=frozenset({
        "assignment_statement",   # x = y  /  x += y 等
        "short_var_declaration",  # x := y
        "var_declaration",        # var x = y（関数内）
    }),
    class_node_types=frozenset(),  # Go にクラスは存在しない
)

# Go の複合代入演算子マッピング
_GO_AUGMENTED_OPS: dict[str, str] = {
    "+=": "ADD",
    "-=": "SUBTRACT",
    "*=": "MULTIPLY",
    "/=": "DIVIDE",
    "%=": "MODULO",
}


# ---------------------------------------------------------------------------
# インポート抽出
# ---------------------------------------------------------------------------

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

    content_node = next(
        (c for c in path_node.named_children if "content" in c.type),
        None,
    )
    if content_node is not None:
        module_name = extract_node_text(content_node)
    else:
        module_name = extract_node_text(path_node).strip('"')

    alias = extract_node_text(name_node).strip() if name_node is not None else ""

    return ImportSpec(
        kind="ImportSpec",
        source_module=module_name,
        imported_names=(),
        alias=alias,
    )


def extract_go_imports(import_node: Node) -> list[ImportSpec]:
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


# ---------------------------------------------------------------------------
# モジュール変数抽出
# ---------------------------------------------------------------------------

def extract_go_module_variable(node: Node) -> Optional[ModuleVariableSpec]:
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

    name = extract_node_text(name_node).strip()
    value_text = normalize_whitespace(extract_node_text(value_node))

    return ModuleVariableSpec(
        kind="ModuleVariableSpec",
        name=name,
        value_text=value_text,
        is_constant=is_constant,
    )


# ---------------------------------------------------------------------------
# 直接代入文の抽出（expression_statement を介さない Go 固有の文）
# ---------------------------------------------------------------------------

def map_go_assignment_to_ir(stmt_node: Node) -> Optional[DataTransformation]:
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

    op_text = "="
    for c in stmt_node.children:
        if not c.is_named and c.text:
            txt = c.text.decode()
            if txt in _GO_AUGMENTED_OPS or txt == "=":
                op_text = txt
                break

    target = extract_node_text(left_node).strip()
    value = extract_node_text(right_node).strip()
    operation = _GO_AUGMENTED_OPS.get(op_text, "ASSIGN")

    return DataTransformation(
        kind="DataTransformation",
        target=target,
        operation=operation,
        value=value,
    )


def map_go_short_var_decl_to_ir(stmt_node: Node) -> Optional[DataTransformation]:
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

    target = extract_node_text(left_node).strip()
    value = extract_node_text(right_node).strip()

    return DataTransformation(
        kind="DataTransformation",
        target=target,
        operation="ASSIGN",
        value=value,
    )


def map_go_var_decl_to_ir(stmt_node: Node) -> Optional[DataTransformation]:
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

    target = extract_node_text(name_node).strip()
    value = extract_node_text(value_node).strip()

    return DataTransformation(
        kind="DataTransformation",
        target=target,
        operation="ASSIGN",
        value=value,
    )


# ---------------------------------------------------------------------------
# 引数・戻り値の型抽出
# ---------------------------------------------------------------------------

def extract_go_params(fn_node: Node) -> tuple[ParamSpec, ...]:
    """
    Go の function_declaration ノードから引数リストを抽出する。

    Go の parameter_list 構造:
      parameter_declaration: name=identifier_list / identifier, type=<型>
      variadic_parameter_declaration: name=identifier, type=<型>（...T 形式）

    複数変数が同じ型を共有するケース（a, b int）は個別の ParamSpec に展開する。
    名前なしパラメーター（型のみ: func foo(int, string)）は名前を "_" とする。
    """
    params_node = fn_node.child_by_field_name("parameters")
    if params_node is None:
        return ()

    result: list[ParamSpec] = []
    for child in params_node.named_children:
        if child.type == "parameter_declaration":
            name_node = child.child_by_field_name("name")
            type_node = child.child_by_field_name("type")
            type_text = normalize_whitespace(extract_node_text(type_node)) if type_node is not None else ""

            if name_node is not None:
                # identifier_list（a, b int）または単一 identifier
                raw_names = extract_node_text(name_node).strip()
                for name in (n.strip() for n in raw_names.split(",") if n.strip()):
                    result.append(ParamSpec(name=name, type_text=type_text))
            else:
                # 名前なしパラメーター（型のみ）
                result.append(ParamSpec(name="_", type_text=type_text))

        elif child.type == "variadic_parameter_declaration":
            # ...T 形式
            name_node = child.child_by_field_name("name")
            type_node = child.child_by_field_name("type")
            name      = extract_node_text(name_node).strip() if name_node is not None else "args"
            type_text = normalize_whitespace(extract_node_text(type_node)) if type_node is not None else ""
            result.append(ParamSpec(name=name, type_text=f"...{type_text}", is_rest=True))

    return tuple(result)


def extract_go_return_type(fn_node: Node) -> str:
    """
    Go の function_declaration ノードから戻り値の型テキストを返す。

    result フィールド:
      単一型:          string, int, error
      複数型（括弧付き）: (string, error), (result string, err error)
    戻り値なしの場合は空文字を返す。
    """
    result_node = fn_node.child_by_field_name("result")
    if result_node is None:
        return ""
    return normalize_whitespace(extract_node_text(result_node))


# ---------------------------------------------------------------------------
# プラグイン定数（discover_plugins() が検出する）
# ---------------------------------------------------------------------------

PLUGIN = LanguagePlugin(
    extensions=(".go",),
    profile=GO_PROFILE,
    parse_source=parse_go_source,
    import_extractor=extract_go_imports,
    module_var_extractor=extract_go_module_variable,
    type_def_extractor=lambda _: None,   # Go の type 宣言は将来対応
    class_extractor=lambda _: None,      # Go にクラスは存在しない
    direct_statement_extractors=(
        ("assignment_statement",  map_go_assignment_to_ir),
        ("short_var_declaration", map_go_short_var_decl_to_ir),
        ("var_declaration",       map_go_var_decl_to_ir),
    ),
    param_extractor=extract_go_params,
    return_type_extractor=extract_go_return_type,
)
