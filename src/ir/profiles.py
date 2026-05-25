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
    name: str  # 例: "typescript", "python"

    # 関数定義ノードのタイプ名
    function_node_type: str
    # 例: TypeScript → "function_declaration"
    #     Python    → "function_definition"

    # for ループのノードタイプ名
    # for_each_node_type: for...of / for...in に相当するもの
    for_each_node_type: str
    # 例: TypeScript → "for_in_statement"
    #     Python    → "for_statement"（Python の for は常に FOR_EACH）

    # for_range_node_type: 古典的な C スタイル for ループ（Python は空文字 = 非対応）
    for_range_node_type: str
    # 例: TypeScript → "for_statement"
    #     Python    → ""（空文字は「未対応」を意味する）

    # ガード句として認識する中断アクションのノードタイプ集合
    guard_action_types: frozenset[str]
    # 例: TypeScript → frozenset({"return_statement", "throw_statement"})
    #     Python    → frozenset({"return_statement", "raise_statement"})

    # if 文の条件式が外側の丸括弧で囲まれているか
    condition_has_outer_parens: bool
    # 例: TypeScript → True   （condition フィールドが "(x > 0)" の形）
    #     Python    → False  （condition フィールドが "x > 0" の形）

    # expression_statement 内の複合代入式タイプ名
    augmented_assignment_type: str
    # 例: TypeScript → "augmented_assignment_expression"
    #     Python    → "augmented_assignment"

    # expression_statement 内の単純代入式タイプ名
    assignment_type: str
    # 例: TypeScript → "assignment_expression"
    #     Python    → "assignment"

    # expression_statement 内の関数呼び出し式タイプ名
    call_type: str
    # 例: TypeScript → "call_expression"
    #     Python    → "call"

    # elif/else の構造タイプ
    # "nested": else_clause の中に if_statement が入れ子（TypeScript スタイル）
    # "flat":   elif_clause / else_clause が if_statement の名前付き子として並列（Python スタイル）
    elif_structure: str

    # 変数宣言文（初期化付き）のノードタイプ集合
    # Python は assignment が expression_statement 内に入るため空集合
    lexical_declaration_types: frozenset[str]
    # 例: TypeScript → frozenset({"lexical_declaration", "variable_declaration"})
    #     Python    → frozenset()（空集合 = 未対応、expression_statement で処理する）

    # ---------- モジュールレベル構造の抽出に使用するフィールド ----------

    # インポート文のノードタイプ集合
    import_node_types: frozenset[str]
    # 例: TypeScript → frozenset({"import_statement"})
    #     Python    → frozenset({"import_statement", "import_from_statement"})

    # モジュールレベルの変数定義ノードタイプ集合（トップレベル直下のみ）
    # TypeScript: lexical_declaration（const/let）
    # Python: expression_statement の中の assignment を後続処理で取り出す
    module_var_node_types: frozenset[str]
    # 例: TypeScript → frozenset({"lexical_declaration"})
    #     Python    → frozenset({"expression_statement"})

    # 型エイリアス定義のノードタイプ（未対応言語は空文字）
    type_alias_node_type: str
    # 例: TypeScript → "type_alias_declaration"
    #     Python    → ""

    # インターフェース定義のノードタイプ（未対応言語は空文字）
    interface_node_type: str
    # 例: TypeScript → "interface_declaration"
    #     Python    → ""


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
)
