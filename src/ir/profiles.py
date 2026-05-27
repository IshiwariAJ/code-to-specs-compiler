"""
LanguageProfile — 言語ごとの AST ノードタイプ仕様を保持する不変データ構造

設計原則:
- このモジュールはデータ型を定義するだけ。ロジックは一切持たない
- 各言語のプロファイル定数は src/languages/<言語名>.py に定義する
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

    各言語のプロファイル定数は src/languages/<言語名>.py に定義されている:
      - TYPESCRIPT_PROFILE → src/languages/typescript.py
      - PYTHON_PROFILE     → src/languages/python.py
      - GO_PROFILE         → src/languages/go.py
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

    # ---------- mapper.py の分岐を言語名ではなく設定値で行うためのフラグ ----------

    # 関数説明の取得スタイル
    # "comment":   関数直前のコメント（TypeScript / Go）
    # "docstring": 関数本体先頭の文字列リテラル（Python）
    function_description_style: str

    # ファイル先頭にモジュール docstring（expression_statement 内の string）が存在しうるか
    # Python: True / TypeScript, Go: False
    has_module_docstring: bool

    # for ループのセマンティクス判定方法
    # "of_keyword":     for_in_statement 内の 'of' 子ノードで for-of/for-in を区別（TypeScript）
    # "range_clause":   range_clause / for_clause の有無で種別を判定（Go）
    # "always_foreach": 常に FOR_EACH として扱う（Python）
    for_loop_flavor: str

    # expression_statement を介さない直接代入文のノードタイプ集合
    # TypeScript / Python → frozenset()（すべて expression_statement 経由）
    # Go → frozenset({"assignment_statement", "short_var_declaration", "var_declaration"})
    direct_statement_types: frozenset[str]

    # クラス定義のノードタイプ集合（対応しない言語は空集合）
    # Python → frozenset({"decorated_definition", "class_definition"})
    #   decorated_definition: @dataclass 等のデコレータ付きクラス
    #   class_definition:     素のクラス定義
    # TypeScript / Go → frozenset()（クラスは TypeDefinitionSpec / 将来対応で処理）
    class_node_types: frozenset[str]

    # ---------- 言語固有の AST 構造差異を吸収するフィールド（デフォルト値あり）----------

    # if 文の「then ブロック」ノードへのアクセス方法
    # "consequence_field":   child_by_field_name("consequence")（TypeScript / Python / Go デフォルト）
    # "statement_block_child": named_children[1] の statement_block（PowerShell 用）
    if_then_block_access: str = "consequence_field"

    # 関数定義の「名前」ノードへのアクセス方法
    # "name_field":          child_by_field_name("name")（TypeScript / Python / Go デフォルト）
    # "function_name_child": type == "function_name" の named_child（PowerShell 用）
    function_name_access: str = "name_field"

    # 関数定義の「本体」ノードへのアクセス方法
    # "body_field":          child_by_field_name("body")（TypeScript / Python / Go デフォルト）
    # "script_block_body":   script_block → script_block_body（PowerShell 用）
    function_body_access: str = "body_field"

    # foreach 文の変数・コレクション・本体へのアクセス方法
    # "left_right_body_fields": child_by_field_name(left/right/body)（TypeScript / Python デフォルト）
    # "var_pipeline_block_children": named_children[0,1,2]（PowerShell 用）
    foreach_access: str = "left_right_body_fields"

    # 関数説明コメントのアクセス方法（function_description_style の拡張）
    # "comment":       直前の sibling コメント（TypeScript / Go デフォルト）
    # "docstring":     関数本体先頭の文字列リテラル（Python）
    # "inner_comment": 関数ノードの named_child コメント（PowerShell: <# .SYNOPSIS ... #>）
    # ※ function_description_style フィールドと重複するが、そちらは既存コードとの互換性のため温存

    # トップレベルのラッパーノードタイプ（""=ルート直下に関数が存在）
    # "" (デフォルト): root_node.named_children から直接検索
    # "statement_list": root → statement_list → 関数（PowerShell 用）
    top_level_wrapper_type: str = ""
