"""
バックエンド（Renderer Layer）: Universal IR → Markdown テキスト

責務: Universal IR オブジェクトツリーを走査し、
      人間が読めるMarkdown形式の日本語仕様書文字列を生成する。

設計方針（構造化プログラミング原則）:
- すべての関数は純粋関数（入力IR → 出力文字列、副作用なし）
- 1関数1責務: 各関数は1種類のIRノードのレンダリングのみを担う
- ディスパッチ関数でノード型を振り分ける
"""
from __future__ import annotations

from dataclasses import replace as _dataclass_replace

from src.ir.types import (
    CaseNode,
    ClassFieldSpec,
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
    TypeDefinitionSpec,
)


# ---------------------------------------------------------------------------
# プリミティブ: テキスト整形ユーティリティ
# ---------------------------------------------------------------------------


def _indent_lines(text: str, indent: str = "  ") -> str:
    """複数行テキストの各行の先頭にインデント文字列を付与して返す。"""
    return "\n".join(indent + line for line in text.splitlines())


def _truncate_to_first_line(text: str) -> str:
    """複数行テキストの最初の行のみを返す（コードブロック等の折り畳み用）。"""
    return text.splitlines()[0].strip() if text else ""


def _normalize_comment(text: str) -> str:
    """
    コメント記号を除去して、Markdown 表示用プレーンテキストに変換する。

    対応形式:
    - TypeScript JSDoc:  /** ... */
    - TypeScript ブロック: /* ... */
    - TypeScript 行コメント: // ...
    - Python 行コメント: # ...
    - Python docstring: \"\"\"...\"\"\" / '''...'''
    """
    text = text.strip()

    # JSDoc / ブロックコメント: /** ... */ または /* ... */
    if text.startswith("/*") and text.endswith("*/"):
        inner = text[3:-2] if text.startswith("/**") else text[2:-2]
        lines = []
        for line in inner.splitlines():
            stripped = line.strip().lstrip("*").strip()
            if stripped:
                lines.append(stripped)
        return "\n".join(lines)

    # TypeScript 行コメント: // ...（複数行の連結にも対応）
    if text.startswith("//"):
        lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("//"):
                lines.append(stripped[2:].strip())
            elif stripped:
                lines.append(stripped)
        return "\n".join(lines)

    # Python 行コメント: # ...（複数行の連結にも対応）
    if text.startswith("#"):
        lines = []
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                lines.append(stripped[1:].strip())
            elif stripped:
                lines.append(stripped)
        return "\n".join(lines)

    # Python triple-double-quote docstring
    if text.startswith('"""') and text.endswith('"""'):
        return text[3:-3].strip()

    # Python triple-single-quote docstring
    if text.startswith("'''") and text.endswith("'''"):
        return text[3:-3].strip()

    # Python 単行 string リテラル（モジュール docstring として現れる場合）
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
        return text[1:-1]

    return text


def _render_comment_blockquote(comment: str) -> str:
    """
    コメントテキストを Markdown ブロッククォート形式に変換する。

    例: "// 合計を計算する" → "> 合計を計算する"
    """
    if not comment:
        return ""
    normalized = _normalize_comment(comment)
    if not normalized:
        return ""
    lines = normalized.splitlines()
    return "\n".join(f"> {line}" for line in lines if line.strip())


# ---------------------------------------------------------------------------
# 定数: operation 識別子 → 日本語アクション表現
# （マッパーが記録した構造情報を、レンダラーが自然言語に変換する）
# ---------------------------------------------------------------------------

_OPERATION_LABELS: dict[str, str] = {
    "ADD":               "に加算して更新する",
    "SUBTRACT":          "から減算して更新する",
    "MULTIPLY":          "に乗算して更新する",
    "DIVIDE":            "で除算して更新する",
    "MODULO":            "で剰余を取って更新する",
    "ASSIGN":            "に代入する",
    "LOGICAL_OR_ASSIGN": "が falsy の場合に代入する",
    "LOGICAL_AND_ASSIGN": "が truthy の場合に代入する",
    "NULLISH_ASSIGN":    "が null/undefined の場合に代入する",
}


# ---------------------------------------------------------------------------
# レンダリング: モジュールレベルのインポート
# ---------------------------------------------------------------------------


def _render_import_row(spec: ImportSpec) -> str:
    """ImportSpec をテーブル行（Markdown）に変換する。"""
    module = f"`{spec.source_module}`"

    if spec.alias == "*":
        names_col = f"全エクスポート (`*`)"
    elif spec.alias:
        names_col = f"モジュール全体 → `{spec.alias}` としてバインド"
    elif spec.imported_names:
        names_col = ", ".join(f"`{n}`" for n in spec.imported_names)
    else:
        names_col = "モジュール全体"

    return f"| {module} | {names_col} |"


def _render_imports_section(imports: tuple[ImportSpec, ...]) -> str:
    """インポート一覧を Markdown テーブルセクションに変換する。"""
    lines = [
        "## 📦 依存関係（インポート）",
        "",
        "| モジュール | インポートした名前 |",
        "|---|---|",
    ]
    for spec in imports:
        lines.append(_render_import_row(spec))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# レンダリング: モジュールレベルの変数・定数
# ---------------------------------------------------------------------------


def _render_module_variable_row(spec: ModuleVariableSpec) -> str:
    """ModuleVariableSpec をテーブル行に変換する。"""
    kind = "定数" if spec.is_constant else "変数"
    return f"| `{spec.name}` | `{spec.value_text}` | {kind} |"


def _render_module_variables_section(vars_: tuple[ModuleVariableSpec, ...]) -> str:
    """モジュール変数・定数一覧を Markdown テーブルセクションに変換する。"""
    lines = [
        "## 📌 モジュール定数・変数",
        "",
        "| 名前 | 値 | 種別 |",
        "|---|---|---|",
    ]
    for spec in vars_:
        lines.append(_render_module_variable_row(spec))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# レンダリング: 型定義（TypeScript）
# ---------------------------------------------------------------------------


def _render_type_definition_row(spec: TypeDefinitionSpec) -> str:
    """TypeDefinitionSpec をテーブル行に変換する。

    Markdown テーブルのセル内で | はカラム区切りと誤解されるため \\| にエスケープする。
    TypeScript のユニオン型（"A" | "B" | "C"）で必須の処理。
    """
    kind_label = "type エイリアス" if spec.definition_kind == "alias" else "interface"
    safe_type_text = spec.type_text.replace("|", r"\|")
    return f"| `{spec.name}` | {kind_label} | `{safe_type_text}` |"


def _render_type_definitions_section(defs: tuple[TypeDefinitionSpec, ...]) -> str:
    """型定義一覧を Markdown テーブルセクションに変換する。"""
    lines = [
        "## 🏷️ 型定義",
        "",
        "| 名前 | 種別 | 定義 |",
        "|---|---|---|",
    ]
    for spec in defs:
        lines.append(_render_type_definition_row(spec))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# レンダリング: クラス定義（Python @dataclass 等）
# ---------------------------------------------------------------------------


def _render_class_field_row(field: ClassFieldSpec) -> str:
    """ClassFieldSpec をテーブル行（Markdown）に変換する。"""
    type_col = f"`{field.type_text}`" if field.type_text else "—"
    default_col = f"`{field.default_text}`" if field.default_text else "—"
    comment_col = field.comment if field.comment else "—"
    return f"| `{field.name}` | {type_col} | {default_col} | {comment_col} |"


def _render_class_spec(spec: ClassSpec) -> str:
    """ClassSpec を Markdown サブセクションに変換する。"""
    kind_label = "dataclass" if spec.is_dataclass else "class"
    lines = [f"### 🏛️ `{spec.name}` ({kind_label})", ""]

    if spec.description:
        comment_block = _render_comment_blockquote(spec.description)
        if comment_block:
            lines.append(comment_block)
            lines.append("")

    if spec.fields:
        lines.extend([
            "| フィールド名 | 型 | デフォルト値 | 説明 |",
            "|---|---|---|---|",
        ])
        for field in spec.fields:
            lines.append(_render_class_field_row(field))
    # フィールドがない場合は何も追加しない（メソッドのみのクラスも正常なパターン）

    if spec.methods:
        if spec.fields:
            lines.append("")  # フィールドテーブルとの間にスペース
        lines.append("**メソッド:**")
        lines.append("")
        for method in spec.methods:
            if method.description:
                lines.append(f"* `{method.name}` — {method.description}")
            else:
                lines.append(f"* `{method.name}`")

    return "\n".join(lines)


def _render_class_definitions_section(classes: tuple[ClassSpec, ...]) -> str:
    """クラス定義一覧を Markdown セクションに変換する。"""
    lines = ["## 🏛️ クラス定義", ""]
    for spec in classes:
        lines.append(_render_class_spec(spec))
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# レンダリング: 引数テーブル（FunctionSpec.params）
# ---------------------------------------------------------------------------


def _render_params_section(params: tuple[ParamSpec, ...]) -> str:
    """引数リストをMarkdownテーブルに変換する。"""
    lines = [
        "**引数:**",
        "",
        "| 引数名 | 型 | デフォルト値 |",
        "|---|---|---|",
    ]
    for p in params:
        name_display = f"`...{p.name}`" if p.is_rest else f"`{p.name}`"
        type_col     = f"`{p.type_text}`"    if p.type_text    else "—"
        default_col  = f"`{p.default_text}`" if p.default_text else "—"
        lines.append(f"| {name_display} | {type_col} | {default_col} |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# レンダリング: ReturnNode
# ---------------------------------------------------------------------------


def _render_return_node(node: ReturnNode, index: int) -> str:
    """
    ReturnNode IR ノードを Markdown テキストに変換する。

    - return: ↩️ 返却する / 処理を終了する（値なし）
    - throw:  💥 例外をスローする
    - raise:  💥 例外を raise する
    - index > 0（関数本体の直下）: 番号付きセクションヘッダーを付ける
    - index == 0（ループ本体等の入れ子）: 箇条書きのみ
    """
    comment_line = _render_comment_blockquote(node.comment)

    if node.action == "return":
        section_label = "↩️ 返却"
        bullet = (
            f"* ↩️ 返却する: `{node.value_text}`"
            if node.value_text
            else "* ↩️ 処理を終了する（値なし）"
        )
    elif node.action == "throw":
        section_label = "💥 例外スロー"
        bullet = f"* 💥 例外をスローする: `{node.value_text}`"
    else:  # raise
        section_label = "💥 例外 raise"
        bullet = f"* 💥 例外を raise する: `{node.value_text}`"

    if index > 0:
        if comment_line:
            return f"### {index}. {section_label}\n{comment_line}\n{bullet}"
        return f"### {index}. {section_label}\n{bullet}"
    if comment_line:
        return f"{comment_line}\n{bullet}"
    return bullet


# ---------------------------------------------------------------------------
# レンダリング: DataTransformation
# ---------------------------------------------------------------------------


def _render_data_transformation(node: DataTransformation, index: int) -> str:
    """
    DataTransformation IR ノードを Markdown テキストに変換する。

    - index > 0（関数本体の直下）: 番号付きセクションヘッダーを付ける
    - index == 0（ループ本体等の入れ子）: 箇条書きのみ
    """
    label = _OPERATION_LABELS.get(node.operation, "を更新する")
    comment_line = _render_comment_blockquote(node.comment)
    bullet = f"* `{node.target}` {label}: `{node.value}`"

    if index > 0:
        if comment_line:
            return f"### {index}. 🔁 データ変換\n{comment_line}\n{bullet}"
        return f"### {index}. 🔁 データ変換\n{bullet}"
    if comment_line:
        return f"{comment_line}\n{bullet}"
    return bullet


# ---------------------------------------------------------------------------
# レンダリング: SideEffect
# ---------------------------------------------------------------------------


def _render_side_effect(node: SideEffect, index: int) -> str:
    """
    SideEffect IR ノードを Markdown テキストに変換する。

    - index > 0（関数本体の直下）: 番号付きセクションヘッダーを付ける
    - index == 0（ループ本体等の入れ子）: 箇条書きのみ
    """
    comment_line = _render_comment_blockquote(node.comment)
    bullet = f"* 🔔 副作用: `{node.description}`"

    if index > 0:
        if comment_line:
            return f"### {index}. 🔔 外部への副作用\n{comment_line}\n{bullet}"
        return f"### {index}. 🔔 外部への副作用\n{bullet}"
    if comment_line:
        return f"{comment_line}\n{bullet}"
    return bullet


# ---------------------------------------------------------------------------
# レンダリング: GuardClause
# ---------------------------------------------------------------------------


def _render_guard_clause(node: GuardClause, index: int) -> str:
    """GuardClause IR ノードを Markdown テキストに変換する。"""
    lines = [f"### {index}. 📢 前提条件（ガード句）"]
    if node.comment:
        comment_line = _render_comment_blockquote(node.comment)
        if comment_line:
            lines.append(comment_line)
    lines.extend([
        f"* **条件:** `{node.condition_text}` の場合",
        f"  * ➔ {node.action_text}",
    ])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# レンダリング: CaseNode（条件分岐の1ケース）
# ---------------------------------------------------------------------------


def _render_case_node(case: CaseNode, case_number: int) -> list[str]:
    """
    CaseNode を Markdown 行リストに変換する。

    Returns:
        各要素が1行の文字列リスト
    """
    lines = [f"* **ケース {case_number}: {case.condition_text}**"]

    for action_text in case.action_texts:
        first_line = _truncate_to_first_line(action_text)
        lines.append(f"  * ➔ `{first_line}`")

    return lines


# ---------------------------------------------------------------------------
# レンダリング: ConditionBlock
# ---------------------------------------------------------------------------


def _render_condition_block(node: ConditionBlock, index: int) -> str:
    """ConditionBlock IR ノードを Markdown テキストに変換する。"""
    lines = [f"### {index}. 🔀 条件分岐"]
    if node.comment:
        comment_line = _render_comment_blockquote(node.comment)
        if comment_line:
            lines.append(comment_line)

    for i, case in enumerate(node.cases, 1):
        lines.extend(_render_case_node(case, i))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# レンダリング: LoopNode
# ---------------------------------------------------------------------------


def _render_loop_header(node: LoopNode, index: int) -> str:
    """LoopNode のヘッダー行（繰り返し処理の説明）を返す。"""
    if node.loop_type == "FOR_EACH":
        return (
            f"### {index}. 🔄 繰り返し処理\n"
            f"* `{node.collection}` の各要素（`{node.iterator}`）に対して以下をループ実行:"
        )

    # FOR_RANGE
    return (
        f"### {index}. 🔄 繰り返し処理\n"
        f"* `{node.collection}` の条件で `{node.iterator}` をカウントしながらループ実行:"
    )


def _render_loop_node(node: LoopNode, index: int) -> str:
    """LoopNode IR ノードを Markdown テキストに変換する。"""
    lines = [_render_loop_header(node, index)]
    if node.comment:
        comment_line = _render_comment_blockquote(node.comment)
        if comment_line:
            lines.append(comment_line)

    for nested_node in node.body:
        nested_text = _render_ir_node(nested_node, index=0)
        lines.append(_indent_lines(nested_text))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# ディスパッチ: IRNode の型に応じてレンダリング関数を呼び分ける
# ---------------------------------------------------------------------------


def _render_ir_node(node: IRNode, index: int) -> str:
    """
    IRNode の型を判定し、対応するレンダリング関数に委譲する。

    Args:
        node:  レンダリング対象の IR ノード
        index: セクション番号（0 の場合は入れ子表示）

    Returns:
        Markdown テキスト文字列
    """
    if isinstance(node, GuardClause):
        return _render_guard_clause(node, index)

    if isinstance(node, ConditionBlock):
        return _render_condition_block(node, index)

    if isinstance(node, LoopNode):
        return _render_loop_node(node, index)

    if isinstance(node, DataTransformation):
        return _render_data_transformation(node, index)

    if isinstance(node, SideEffect):
        return _render_side_effect(node, index)

    if isinstance(node, ReturnNode):
        return _render_return_node(node, index)

    return ""


# ---------------------------------------------------------------------------
# レンダリング: FunctionSpec（1関数の仕様）
# ---------------------------------------------------------------------------


def _render_function_spec(spec: FunctionSpec) -> str:
    """FunctionSpec IR を Markdown セクションに変換する。"""
    lines = [
        f"## 🔧 関数: `{spec.name}`",
        "",
    ]

    # JSDoc / docstring がある場合はブロッククォートで表示
    if spec.description:
        comment_block = _render_comment_blockquote(spec.description)
        if comment_block:
            lines.append(comment_block)
            lines.append("")

    # 引数テーブル
    if spec.params:
        lines.append(_render_params_section(spec.params))
        lines.append("")

    # 戻り値の型
    if spec.return_type:
        lines.append(f"**戻り値の型:** `{spec.return_type}`")
        lines.append("")

    lines.extend(["### 📄 処理フロー", ""])

    if not spec.body:
        lines.append("*（検出された制御フローはありません）*")
    else:
        for i, ir_node in enumerate(spec.body, 1):
            lines.append(_render_ir_node(ir_node, index=i))
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 公開インターフェース: ModuleSpec → Markdown 文字列
# ---------------------------------------------------------------------------


def render_module_spec(spec: ModuleSpec) -> str:
    """
    ModuleSpec IR をMarkdown 形式の仕様書文字列全体に変換する。

    これがバックエンド層の唯一の公開インターフェース。

    Args:
        spec: ModuleSpec IR オブジェクト（imports / module_variables / type_definitions / functions）

    Returns:
        Markdown 文字列
    """
    sections: list[str] = [
        f"# モジュール仕様: {spec.name}",
        "",
        "---",
        "",
    ]

    # ファイルヘッダーコメント / モジュール docstring
    if spec.file_comment:
        comment_block = _render_comment_blockquote(spec.file_comment)
        if comment_block:
            sections.append(comment_block)
            sections.append("")
            sections.append("---")
            sections.append("")

    # インポートセクション
    if spec.imports:
        sections.append(_render_imports_section(spec.imports))
        sections.append("")
        sections.append("---")
        sections.append("")

    # モジュール変数・定数セクション
    if spec.module_variables:
        sections.append(_render_module_variables_section(spec.module_variables))
        sections.append("")
        sections.append("---")
        sections.append("")

    # 型定義セクション（TypeScript のみ）
    if spec.type_definitions:
        sections.append(_render_type_definitions_section(spec.type_definitions))
        sections.append("")
        sections.append("---")
        sections.append("")

    # クラス定義セクション（Python @dataclass 等）
    if spec.class_definitions:
        sections.append(_render_class_definitions_section(spec.class_definitions))
        sections.append("")
        sections.append("---")
        sections.append("")

    # クラスメソッド詳細セクション
    # メソッドに処理フロー（body）がある場合のみレンダリング（Java 等のクラスベース言語向け）
    for class_spec in spec.class_definitions:
        detailed_methods = [m for m in class_spec.methods if m.body]
        if detailed_methods:
            for method in detailed_methods:
                # クラス名を接頭辞として付けた FunctionSpec でレンダリング
                qualified = _dataclass_replace(
                    method,
                    name=f"{class_spec.name}.{method.name}",
                )
                sections.append(_render_function_spec(qualified))
                sections.append("")
                sections.append("---")
                sections.append("")

    # 関数セクション
    if not spec.functions:
        sections.append("*（トップレベル関数が検出されませんでした）*")
    else:
        for func_spec in spec.functions:
            sections.append(_render_function_spec(func_spec))
            sections.append("")
            sections.append("---")
            sections.append("")

    return "\n".join(sections)
