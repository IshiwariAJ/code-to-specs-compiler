"""
Java 言語プラグイン (.java)

このファイルを src/languages/ に置くだけで、パイプラインが
.java ファイルを自動的に処理できるようになる。

Java の特徴:
  - すべてのメソッドはクラス内に存在する（トップレベル関数なし）
    → ClassSpec.methods を通じて仕様書に出力される
  - for-each は enhanced_for_statement（name / value / body フィールド）
  - if/else は Go と同じ nested 構造（alternative フィールド）
  - JavaDoc コメント（/** ... */）を関数・クラスの説明として抽出

対応する Java 構文:
  - public class Foo { ... }                → ClassSpec
  - public static String bar(int x) { ... } → FunctionSpec（ClassSpec.methods）
  - if (!cond) { throw new ... }            → GuardClause
  - if (x) { ... } else if { ... } else    → ConditionBlock
  - for (Type item : collection) { ... }   → LoopNode (FOR_EACH)
  - int x = 0 / x += y                    → DataTransformation
  - System.out.println(x)                  → SideEffect
  - return / throw                         → ReturnNode
  - import java.util.List;                 → ImportSpec
"""
from __future__ import annotations

from typing import Callable, Optional

from tree_sitter import Node

from ..ir.node_utils import extract_node_text, normalize_whitespace
from ..ir.profiles import LanguageProfile
from ..ir.types import ClassSpec, ImportSpec, IRNode, LoopNode, ModuleVariableSpec, ParamSpec
from ..parser.java_parser import parse_java_source
from . import LanguagePlugin

# ---------------------------------------------------------------------------
# LanguageProfile 定数
# ---------------------------------------------------------------------------

JAVA_PROFILE = LanguageProfile(
    name="java",
    function_node_type="method_declaration",
    # Java の for-each は enhanced_for_statement（name/value/body フィールド）
    # java_for_loop_mapper フックで処理するため for_loop_flavor は参照されない
    for_each_node_type="enhanced_for_statement",
    for_range_node_type="",   # 従来型 for_statement は将来対応
    guard_action_types=frozenset({"throw_statement", "return_statement"}),
    condition_has_outer_parens=True,   # if (cond) — condition フィールドが parenthesized_expression
    # Java では assignment_expression が += と = の両方を兼ねる
    # operator フィールドの値で区別する（= → ASSIGN、+= → ADD など）
    augmented_assignment_type="assignment_expression",
    assignment_type="",          # augmented_assignment_type で統一
    call_type="method_invocation",
    elif_structure="nested",     # else if → alternative = if_statement（Go と同じ構造）
    lexical_declaration_types=frozenset({"local_variable_declaration"}),
    import_node_types=frozenset({"import_declaration"}),
    module_var_node_types=frozenset(),   # クラスフィールドは ClassSpec で処理
    type_alias_node_type="",
    interface_node_type="",
    block_inner_node_type="",
    has_module_docstring=False,
    for_loop_flavor="always_foreach",  # mapper では参照されない（java_for_loop_mapper を使用）
    direct_statement_types=frozenset(),
    class_node_types=frozenset({"class_declaration"}),
)


# ---------------------------------------------------------------------------
# JavaDoc コメント整形ユーティリティ
# ---------------------------------------------------------------------------

def _extract_javadoc(comment_text: str) -> str:
    """
    JavaDoc コメント（/** ... */）から説明文を抽出する。

    処理内容:
      - /** と */ を除去
      - 各行先頭の * プレフィックスを除去
      - @param / @return / @throws 等のタグ行以降は除外
    """
    text = comment_text.strip()
    if text.startswith("/**"):
        text = text[3:]
    if text.endswith("*/"):
        text = text[:-2]

    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip().lstrip("*").strip()
        if stripped.startswith("@"):
            break  # @param, @return 等のタグで説明文終了
        if stripped:
            lines.append(stripped)

    return " ".join(lines)


# ---------------------------------------------------------------------------
# 関数説明文抽出（JavaDoc コメント）
# ---------------------------------------------------------------------------

def extract_java_function_description(fn_node: Node) -> str:
    """
    メソッド直前の JavaDoc コメント（/** ... */）から説明文を返す
    （LanguagePlugin.function_description_extractor フック）。

    クラスボディ内でメソッドの prev_named_sibling が block_comment の場合に取得する。
    コメントがない場合は空文字を返す。
    """
    prev = fn_node.prev_named_sibling
    if prev is None or prev.type != "block_comment":
        return ""
    return _extract_javadoc(extract_node_text(prev).strip())


# ---------------------------------------------------------------------------
# for-each ループ変換（enhanced_for_statement の name/value フィールド）
# ---------------------------------------------------------------------------

def java_for_loop_mapper(
    for_node: Node,
    extract_body: Callable[[Node], list[IRNode]],
) -> Optional[LoopNode]:
    """
    Java の enhanced_for_statement を LoopNode IR（FOR_EACH）に変換する
    （LanguagePlugin.for_loop_mapper フック）。

    for (Type item : collection) { ... } の AST フィールド:
      name:  identifier（ループ変数）
      value: 式（コレクション）
      body:  block（ボディ）

    ※ TypeScript/Python の left/right と異なりフィールド名が違うため、
       汎用 _map_for_each_to_loop の代わりにこのフックを使用する。
    """
    left_node = for_node.child_by_field_name("name")
    right_node = for_node.child_by_field_name("value")
    body_node = for_node.child_by_field_name("body")

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
# インポート抽出
# ---------------------------------------------------------------------------

def extract_java_imports(import_node: Node) -> list[ImportSpec]:
    """
    Java の import_declaration から ImportSpec を生成する。

    import java.util.List;   → source_module="java.util", imported_names=("List",)
    import java.util.*;      → source_module="java.util", imported_names=()
    import static com.Foo.X; → source_module="com.Foo",   imported_names=("X",)

    tree-sitter-java の AST 構造:
      import java.util.*;
        → named_children: [scoped_identifier("java.util"), asterisk("*")]
      import java.util.List;
        → named_children: [scoped_identifier("java.util.List")]

    ワイルドカードかどうかは named child に "asterisk" ノードがあるかで判定する。
    """
    # static import かどうかを判定（non-named child に "static" キーワード）
    is_static = any(
        not c.is_named and c.text and c.text.decode("utf-8") == "static"
        for c in import_node.children
    )

    # ワイルドカード判定: import_declaration の named child に "asterisk" ノードが存在するか
    has_wildcard = any(
        c.is_named and c.type == "asterisk"
        for c in import_node.named_children
    )

    # パスノード: asterisk 以外の最初の named child（scoped_identifier または identifier）
    path_node = next(
        (c for c in import_node.named_children if c.type != "asterisk"),
        None,
    )
    if path_node is None:
        return []

    full_path = extract_node_text(path_node).strip()

    # java.util.* → source_module="java.util", 名前なし
    # （asterisk は別の named child として存在するため full_path は "java.util" になる）
    if has_wildcard:
        return [ImportSpec(
            kind="ImportSpec",
            source_module=full_path,
            imported_names=(),
            alias="",
        )]

    # java.util.List → source_module="java.util", imported_names=("List",)
    parts = full_path.rsplit(".", 1)
    if len(parts) == 2:
        source_module, class_name = parts
        return [ImportSpec(
            kind="ImportSpec",
            source_module=source_module,
            imported_names=(class_name,),
            alias="",
        )]

    # パッケージ名のみ（まれなケース）
    return [ImportSpec(
        kind="ImportSpec",
        source_module=full_path,
        imported_names=(),
        alias="",
    )]


# ---------------------------------------------------------------------------
# クラス定義抽出
# ---------------------------------------------------------------------------

def extract_java_class(node: Node) -> Optional[ClassSpec]:
    """
    Java の class_declaration から ClassSpec を生成する。

    class_declaration の構造:
      modifiers: public / abstract 等
      name:      identifier（クラス名）
      body:      class_body

    クラス説明は直前の block_comment（JavaDoc）から取得する。
    フィールドの抽出は将来対応（クラスの型・アノテーションは複雑なため）。
    """
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    name = extract_node_text(name_node).strip()

    # 直前の JavaDoc コメントをクラス説明として取得
    description = ""
    prev = node.prev_named_sibling
    if prev is not None and prev.type == "block_comment":
        description = _extract_javadoc(extract_node_text(prev).strip())

    return ClassSpec(
        kind="ClassSpec",
        name=name,
        is_dataclass=False,
        description=description,
    )


# ---------------------------------------------------------------------------
# 引数・戻り値の型抽出
# ---------------------------------------------------------------------------

def extract_java_params(fn_node: Node) -> tuple[ParamSpec, ...]:
    """
    Java の method_declaration から引数リストを抽出する。

    formal_parameter 構造:
      type: 型ノード（integral_type / type_identifier / generic_type 等）
      name: identifier（引数名）

    可変長引数（varargs）は将来対応。
    """
    params_node = fn_node.child_by_field_name("parameters")
    if params_node is None:
        return ()

    result: list[ParamSpec] = []
    for child in params_node.named_children:
        if child.type == "formal_parameter":
            name_node = child.child_by_field_name("name")
            type_node = child.child_by_field_name("type")
            name = extract_node_text(name_node).strip() if name_node is not None else ""
            type_text = normalize_whitespace(extract_node_text(type_node)) if type_node is not None else ""
            if name:
                result.append(ParamSpec(name=name, type_text=type_text))

        elif child.type == "spread_parameter":
            # 可変長引数: Type... args
            name_node = child.child_by_field_name("name")
            type_node = next(
                (c for c in child.named_children if c != name_node),
                None,
            )
            name = extract_node_text(name_node).strip() if name_node is not None else "args"
            type_text = normalize_whitespace(extract_node_text(type_node)) + "..." if type_node else "..."
            result.append(ParamSpec(name=name, type_text=type_text, is_rest=True))

    return tuple(result)


def extract_java_return_type(fn_node: Node) -> str:
    """
    Java の method_declaration ノードから戻り値の型テキストを返す。

    type フィールド: integral_type / type_identifier / void_type / generic_type 等
    """
    type_node = fn_node.child_by_field_name("type")
    if type_node is None:
        return ""
    return normalize_whitespace(extract_node_text(type_node))


# ---------------------------------------------------------------------------
# プラグイン定数（discover_plugins() が検出する）
# ---------------------------------------------------------------------------

PLUGIN = LanguagePlugin(
    extensions=(".java",),
    profile=JAVA_PROFILE,
    parse_source=parse_java_source,
    import_extractor=extract_java_imports,
    module_var_extractor=lambda _: None,  # Java はモジュールレベル変数なし
    type_def_extractor=lambda _: None,    # interface / enum は将来対応
    class_extractor=extract_java_class,
    direct_statement_extractors=(),
    param_extractor=extract_java_params,
    return_type_extractor=extract_java_return_type,
    for_loop_mapper=java_for_loop_mapper,                          # name/value フィールドアクセス
    function_description_extractor=extract_java_function_description,  # JavaDoc を整形して使用
)
