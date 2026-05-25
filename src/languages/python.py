"""
Python 言語プラグイン

このファイルを src/languages/ に置くだけで、パイプラインが
.py ファイルを自動的に処理できるようになる。
"""
from __future__ import annotations

from typing import Optional

from tree_sitter import Node

from ..ir.node_utils import extract_node_text, normalize_whitespace
from ..ir.profiles import LanguageProfile
from ..ir.types import ClassFieldSpec, ClassSpec, ImportSpec, ModuleVariableSpec
from ..parser.python_parser import parse_python_source
from . import LanguagePlugin

# ---------------------------------------------------------------------------
# LanguageProfile 定数
# ---------------------------------------------------------------------------

PYTHON_PROFILE = LanguageProfile(
    name="python",
    function_node_type="function_definition",
    for_each_node_type="for_statement",
    for_range_node_type="",  # Python に古典的な for ループは存在しない
    guard_action_types=frozenset({"return_statement", "raise_statement"}),
    condition_has_outer_parens=False,
    augmented_assignment_type="augmented_assignment",
    assignment_type="assignment",
    call_type="call",
    elif_structure="flat",
    lexical_declaration_types=frozenset(),  # Python は assignment で処理
    import_node_types=frozenset({"import_statement", "import_from_statement", "future_import_statement"}),
    module_var_node_types=frozenset({"expression_statement"}),
    type_alias_node_type="",   # Python は型エイリアス未対応（3.12+ の type 文は将来対応）
    interface_node_type="",    # Python はインターフェース未対応
    block_inner_node_type="",
    function_description_style="docstring",
    has_module_docstring=True,
    for_loop_flavor="always_foreach",
    direct_statement_types=frozenset(),
    class_node_types=frozenset({"decorated_definition", "class_definition"}),
)


# ---------------------------------------------------------------------------
# インポート抽出
# ---------------------------------------------------------------------------

def _extract_py_import(import_node: Node) -> Optional[ImportSpec]:
    """
    Python の import_statement / import_from_statement / future_import_statement
    ノードから ImportSpec を生成する。
    """
    if import_node.type == "future_import_statement":
        imported_names = tuple(
            extract_node_text(child)
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
                    source_module=extract_node_text(child),
                    imported_names=(),
                    alias="",
                )
            if child.type == "aliased_import":
                name_node = child.named_children[0] if child.named_children else None
                alias_node = child.named_children[1] if len(child.named_children) > 1 else None
                source = extract_node_text(name_node) if name_node else ""
                alias = extract_node_text(alias_node) if alias_node else ""
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
        source_module = extract_node_text(first)
        imported_names = tuple(
            extract_node_text(child)
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


def extract_py_import_list(node: Node) -> list[ImportSpec]:
    """Python の import ノード1つから ImportSpec リストを返す。"""
    spec = _extract_py_import(node)
    return [spec] if spec is not None else []


# ---------------------------------------------------------------------------
# モジュール変数抽出
# ---------------------------------------------------------------------------

def extract_py_module_variable(node: Node) -> Optional[ModuleVariableSpec]:
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

    name = extract_node_text(left_node).strip()
    if "," in name:
        return None  # タプルアンパック（a, b = ...）は対象外

    value_text = normalize_whitespace(extract_node_text(right_node))
    is_constant = name.isupper() or (name.replace("_", "").isupper() and "_" in name)

    return ModuleVariableSpec(
        kind="ModuleVariableSpec",
        name=name,
        value_text=value_text,
        is_constant=is_constant,
    )


# ---------------------------------------------------------------------------
# クラス定義抽出（@dataclass / class）
# ---------------------------------------------------------------------------


def _is_dataclass_decorator(decorator_node: Node) -> bool:
    """
    デコレータノードが @dataclass（または @dataclass(...)）かどうかを判定する。

    tree-sitter では:
      @dataclass     → decorator の子に identifier "dataclass"
      @dataclass(...)→ decorator の子に call (function=identifier "dataclass")
    """
    for child in decorator_node.children:
        if child.type == "identifier":
            if child.text and child.text.decode("utf-8") == "dataclass":
                return True
        if child.type == "call":
            fn = child.child_by_field_name("function")
            if fn is not None and fn.text and fn.text.decode("utf-8") == "dataclass":
                return True
    return False


def _extract_class_docstring(block_node: Node) -> str:
    """
    クラスブロックの先頭 expression_statement から docstring 文字列を返す。
    docstring がなければ空文字を返す。
    """
    first = next(
        (c for c in block_node.named_children if c.type == "expression_statement"),
        None,
    )
    if first is None:
        return ""
    string_node = next(
        (c for c in first.named_children if c.type == "string"),
        None,
    )
    return extract_node_text(string_node) if string_node is not None else ""


def _extract_class_fields(block_node: Node) -> tuple[ClassFieldSpec, ...]:
    """
    クラスブロックから型アノテーション付きフィールド定義の一覧を返す。

    tree-sitter-python では各フィールドが次の構造になる:
      expression_statement
        assignment
          left: identifier (フィールド名)
          type: <型アノテーション>
          right: <デフォルト値>（省略可）

    インラインコメント（# ...）は expression_statement の次の兄弟 comment ノードとして
    現れるため、直後の named sibling を確認して付与する。
    """
    children = list(block_node.named_children)
    fields: list[ClassFieldSpec] = []

    for i, child in enumerate(children):
        if child.type != "expression_statement":
            continue

        assignment = next(
            (c for c in child.named_children if c.type == "assignment"),
            None,
        )
        if assignment is None:
            continue  # docstring の expression_statement 等はスキップ

        left_node = assignment.child_by_field_name("left")
        if left_node is None:
            continue  # 左辺なし（型アノテーションのみで識別子なし）はスキップ

        type_node = assignment.child_by_field_name("type")
        right_node = assignment.child_by_field_name("right")

        field_name = extract_node_text(left_node).strip()
        type_text = normalize_whitespace(extract_node_text(type_node)) if type_node else ""
        default_text = normalize_whitespace(extract_node_text(right_node)) if right_node else ""

        # 次の兄弟が comment で、かつ同一行にある場合のみインラインコメントとして使用する。
        # 別行の comment は次フィールドの前置コメントであるため、ここでは無視する。
        comment_text = ""
        if i + 1 < len(children) and children[i + 1].type == "comment":
            next_comment = children[i + 1]
            # start_point[0] は 0 始まりの行番号。フィールドと同じ行なら inline コメント
            if next_comment.start_point[0] == child.start_point[0]:
                raw = extract_node_text(next_comment)
                comment_text = raw.lstrip("#").strip()

        fields.append(ClassFieldSpec(
            name=field_name,
            type_text=type_text,
            default_text=default_text,
            comment=comment_text,
        ))

    return tuple(fields)


def extract_py_class(node: Node) -> Optional[ClassSpec]:
    """
    Python の decorated_definition または class_definition から ClassSpec を生成する。

    decorated_definition で中身が class_definition でない場合（デコレータ付き関数等）は
    None を返してスキップする。
    """
    is_dataclass = False

    if node.type == "decorated_definition":
        definition = node.child_by_field_name("definition")
        if definition is None or definition.type != "class_definition":
            return None  # @staticmethod / @property 等の装飾された関数はスキップ
        for child in node.named_children:
            if child.type == "decorator" and _is_dataclass_decorator(child):
                is_dataclass = True
                break
        class_node = definition

    elif node.type == "class_definition":
        class_node = node

    else:
        return None

    name_node = class_node.child_by_field_name("name")
    if name_node is None:
        return None
    name = extract_node_text(name_node).strip()

    body_node = class_node.child_by_field_name("body")
    if body_node is None:
        return ClassSpec(kind="ClassSpec", name=name, is_dataclass=is_dataclass)

    description = _extract_class_docstring(body_node)
    fields = _extract_class_fields(body_node)

    return ClassSpec(
        kind="ClassSpec",
        name=name,
        is_dataclass=is_dataclass,
        description=description,
        fields=fields,
    )


# ---------------------------------------------------------------------------
# プラグイン定数（discover_plugins() が検出する）
# ---------------------------------------------------------------------------

PLUGIN = LanguagePlugin(
    extensions=(".py",),
    profile=PYTHON_PROFILE,
    parse_source=parse_python_source,
    import_extractor=extract_py_import_list,
    module_var_extractor=extract_py_module_variable,
    type_def_extractor=lambda _: None,  # Python は型定義抽出未対応
    direct_statement_extractors=(),
    class_extractor=extract_py_class,
)
