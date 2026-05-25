"""
LanguageProfile — 言語ごとの AST ノードタイプ仕様を保持する不変データ構造

設計原則:
- このモジュールはデータを定義するだけ。ロジックは一切持たない
- 新しい言語を追加する際は、LANGUAGE_PROFILES に定数を1つ追加するだけでよい
- mapper.py はこの Profile を参照して言語差異を吸収する
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LanguageProfile:
    """
    1つのプログラミング言語の AST ノードタイプ仕様。

    mapper.py はこの Profile を参照することで、
    言語に依存した AST ノードタイプ名の違いを吸収する。
    """
    # 言語識別子
    name: str  # 例: "typescript", "python", "go"

    # 関数定義ノードのタイプ名
    function_node_type: str
    # 例: TypeScript → "function_declaration"
    #     Python    → "function_definition"
    #     Go        → "function_declaration"

    # for ループのノードタイプ名
    # for_each_node_type: for...of / for...in / range に相当するもの
    for_each_node_type: str
    # 例: TypeScript → "for_in_statement"
    #     Python    → "for_statement"（Python の for は常に FOR_EACH）
    #     Go        → "for_statement"（range / C スタイル両方。内部で range_clause を判定）

    # for_range_node_type: 古典的な C スタイル for ループ（非対応言語は空文字）
    for_range_node_type: str
    # 例: TypeScript → "for_statement"
    #     Python    → ""（空文字は「未対応」を意味する）
    #     Go        → ""（for_statement を for_each_node_type と共用。for_clause で内部判定）

    # ガード句として認識する中断アクションのノードタイプ集合
    guard_action_types: frozenset[str]
    # 例: TypeScript → frozenset({"return_statement", "throw_statement"})
    #     Python    → frozenset({"return_statement", "raise_statement"})
    #     Go        → frozenset({"return_statement"})（panic は call_expression）

    # if 文の条件式が外側の丸括弧で囲まれているか
    condition_has_outer_parens: bool
    # 例: TypeScript → True   （condition フィールドが "(x > 0)" の形）
    #     Python    → False  （condition フィールドが "x > 0" の形）
    #     Go        → False  （Go は if x > 0 { で括弧不要）

    # expression_statement 内の複合代入式タイプ名
    augmented_assignment_type: str
    # 例: TypeScript → "augmented_assignment_expression"
    #     Python    → "augmented_assignment"
    #     Go        → ""（Go は expression_statement に包まれない直接文 assignment_statement）

    # expression_statement 内の単純代入式タイプ名
    assignment_type: str
    # 例: TypeScript → "assignment_expression"
    #     Python    → "assignment"
    #     Go        → ""（short_var_declaration は直接文として処理）

    # expression_statement 内の関数呼び出し式タイプ名
    call_type: str
    # 例: TypeScript → "call_expression"
    #     Python    → "call"
    #     Go        → "call_expression"

    # elif/else の構造タイプ
    # "nested": else 節の中に if_statement が入れ子（TypeScript / Go スタイル）
    # "flat":   elif_clause / else_clause が if_statement の名前付き子として並列（Python スタイル）
    elif_structure: str

    # 変数宣言文（初期化付き）のノードタイプ集合
    # Python は assignment が expression_statement 内に入るため空集合
    # Go は assignment_statement / short_var_declaration を _map_statement_to_ir で直接処理
    lexical_declaration_types: frozenset[str]
    # 例: TypeScript → frozenset({"lexical_declaration", "variable_declaration"})
    #     Python    → frozenset()
    #     Go        → frozenset()

    # ---------- モジュールレベル構造の抽出に使用するフィールド ----------

    # インポート文のノードタイプ集合
    import_node_types: frozenset[str]
    # 例: TypeScript → frozenset({"import_statement"})
    #     Python    → frozenset({"import_statement", "import_from_statement"})
    #     Go        → frozenset({"import_declaration"})

    # モジュールレベルの変数定義ノードタイプ集合（トップレベル直下のみ）
    module_var_node_types: frozenset[str]
    # 例: TypeScript → frozenset({"lexical_declaration"})
    #     Python    → frozenset({"expression_statement"})
    #     Go        → frozenset({"var_declaration", "const_declaration"})

    # 型エイリアス定義のノードタイプ（未対応言語は空文字）
    type_alias_node_type: str
    # 例: TypeScript → "type_alias_declaration"
    #     Python    → ""
    #     Go        → ""（Go の type 宣言は構造体・インターフェース等が混在するため将来対応）

    # インターフェース定義のノードタイプ（未対応言語は空文字）
    interface_node_type: str
    # 例: TypeScript → "interface_declaration"
    #     Python    → ""
    #     Go        → ""

    # ブロック内部のラッパーノードタイプ（なければ空文字）
    # TypeScript / Python は block の named_children が直接文ノードを含む
    # Go は block → statement_list → 文ノード の2段構造になっている
    block_inner_node_type: str
    # 例: TypeScript → ""
    #     Python    → ""
    #     Go        → "statement_list"


# ---------------------------------------------------------------------------
# 各言語の定数プロファイル
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
)

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
)

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
)
