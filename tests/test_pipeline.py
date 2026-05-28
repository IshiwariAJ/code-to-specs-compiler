"""
pipeline.py の統合テスト（E2E）

設計方針:
- 実際のソースコード文字列を入力として compile_to_spec() を呼び出す
- 出力 Markdown に期待するラベルや文字列が含まれることで品質を保証する
- TypeScript / Python の両言語で同一フォーマットが出力されることを実証する
"""
import pytest

from src.pipeline import compile_to_spec, get_supported_extensions


# ---------------------------------------------------------------------------
# テスト用ソースコード定数
# （TypeScript と Python で意図的に同一ロジックを記述）
# ---------------------------------------------------------------------------

_TS_SOURCE = (
    "function calculateBenefit(user) {\n"
    '  if (user.status !== "ACTIVE") {\n'
    '    throw new Error("invalid");\n'
    "  }\n"
    "  let total = 0;\n"
    "  for (const h of user.history) {\n"
    "    total += h.price;\n"
    "  }\n"
    "  if (total >= 100000) {\n"
    "    return 1000;\n"
    "  } else {\n"
    "    return 100;\n"
    "  }\n"
    "}\n"
)

_PY_SOURCE = (
    "def calculate_benefit(user):\n"
    '    if user["status"] != "ACTIVE":\n'
    '        raise ValueError("invalid")\n'
    "    total = 0\n"
    '    for h in user["history"]:\n'
    '        total += h["price"]\n'
    "    if total >= 100000:\n"
    "        return 1000\n"
    "    else:\n"
    "        return 100\n"
)

# すべての構造マーカー（TypeScript / Python 共通で出力されるべき日本語ラベル）
_STRUCTURAL_MARKERS = [
    "前提条件（ガード句）",
    "データ変換",
    "繰り返し処理",
    "条件分岐",
]


# ---------------------------------------------------------------------------
# TypeScript パイプラインのテスト
# ---------------------------------------------------------------------------


class TestTypeScriptPipeline:
    def test_output_contains_module_header(self):
        result = compile_to_spec(_TS_SOURCE, "myModule", ".ts")
        assert "# モジュール仕様: myModule" in result

    def test_output_contains_function_name(self):
        result = compile_to_spec(_TS_SOURCE, "test", ".ts")
        assert "calculateBenefit" in result

    def test_guard_clause_label_present(self):
        result = compile_to_spec(_TS_SOURCE, "test", ".ts")
        assert "前提条件（ガード句）" in result

    def test_data_transformation_label_present(self):
        result = compile_to_spec(_TS_SOURCE, "test", ".ts")
        assert "データ変換" in result

    def test_loop_label_present(self):
        result = compile_to_spec(_TS_SOURCE, "test", ".ts")
        assert "繰り返し処理" in result

    def test_condition_block_label_present(self):
        result = compile_to_spec(_TS_SOURCE, "test", ".ts")
        assert "条件分岐" in result

    def test_output_is_markdown_string(self):
        result = compile_to_spec(_TS_SOURCE, "test", ".ts")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_tsx_extension_works(self):
        result = compile_to_spec(_TS_SOURCE, "test", ".tsx")
        assert "calculateBenefit" in result


# ---------------------------------------------------------------------------
# Python パイプラインのテスト
# ---------------------------------------------------------------------------


class TestPythonPipeline:
    def test_output_contains_module_header(self):
        result = compile_to_spec(_PY_SOURCE, "myModule", ".py")
        assert "# モジュール仕様: myModule" in result

    def test_output_contains_function_name(self):
        result = compile_to_spec(_PY_SOURCE, "test", ".py")
        assert "calculate_benefit" in result

    def test_guard_clause_label_present(self):
        result = compile_to_spec(_PY_SOURCE, "test", ".py")
        assert "前提条件（ガード句）" in result

    def test_raise_keyword_in_guard_action(self):
        # Python は throw でなく raise → action_text に「raise」が含まれる
        result = compile_to_spec(_PY_SOURCE, "test", ".py")
        assert "raise" in result

    def test_data_transformation_label_present(self):
        result = compile_to_spec(_PY_SOURCE, "test", ".py")
        assert "データ変換" in result

    def test_loop_label_present(self):
        result = compile_to_spec(_PY_SOURCE, "test", ".py")
        assert "繰り返し処理" in result

    def test_condition_block_label_present(self):
        result = compile_to_spec(_PY_SOURCE, "test", ".py")
        assert "条件分岐" in result


# ---------------------------------------------------------------------------
# 言語間の一貫性テスト（Phase 2-B の核心的な価値実証）
# ---------------------------------------------------------------------------


class TestCrossLanguageConsistency:
    """
    TypeScript と Python で同一ロジックを記述したとき、
    出力 Markdown に同一の構造マーカーが含まれることを保証する。

    これが「Universal IR による多言語統合フォーマット」の核心的な検証。
    """

    def test_all_structural_markers_appear_in_typescript(self):
        result = compile_to_spec(_TS_SOURCE, "test", ".ts")
        for marker in _STRUCTURAL_MARKERS:
            assert marker in result, f"TypeScript 出力に不足: {marker}"

    def test_all_structural_markers_appear_in_python(self):
        result = compile_to_spec(_PY_SOURCE, "test", ".py")
        for marker in _STRUCTURAL_MARKERS:
            assert marker in result, f"Python 出力に不足: {marker}"

    def test_typescript_and_python_section_count_matches(self):
        # TypeScript と Python の出力で ### セクション数が一致する
        ts_result = compile_to_spec(_TS_SOURCE, "test", ".ts")
        py_result = compile_to_spec(_PY_SOURCE, "test", ".py")
        ts_sections = ts_result.count("### ")
        py_sections = py_result.count("### ")
        assert ts_sections == py_sections, (
            f"セクション数不一致: TypeScript={ts_sections}, Python={py_sections}"
        )


# ---------------------------------------------------------------------------
# エッジケースのテスト
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_function_body_shows_placeholder(self):
        result = compile_to_spec("function empty() {}", "test", ".ts")
        assert "制御フローはありません" in result

    def test_no_functions_shows_placeholder(self):
        result = compile_to_spec("const x = 1;", "test", ".ts")
        assert "関数が検出されませんでした" in result

    def test_python_empty_function_shows_placeholder(self):
        result = compile_to_spec("def empty():\n    pass\n", "test", ".py")
        assert "制御フローはありません" in result

    def test_typescript_multiple_functions_all_appear(self):
        src = (
            "function funcA() { if (x > 0) { return 1; } }\n"
            "function funcB() { for (const i of arr) { total += i; } }\n"
        )
        result = compile_to_spec(src, "test", ".ts")
        assert "funcA" in result
        assert "funcB" in result

    def test_module_name_is_customizable(self):
        result = compile_to_spec("function f() {}", "CustomModuleName", ".ts")
        assert "CustomModuleName" in result

    def test_unsupported_extension_raises_error(self):
        with pytest.raises(ValueError, match="サポートされていない拡張子"):
            compile_to_spec("function f() {}", "test", ".js")

    def test_unmapped_statement_warning_is_rendered(self):
        # while ループは対応済みのため警告ではなく仕様書に出力される
        src = (
            "function waitUntilReady() {\n"
            "  while (!ready) {\n"
            "    poll();\n"
            "  }\n"
            "}\n"
        )
        result = compile_to_spec(src, "test", ".ts")
        assert "繰り返し処理（while）" in result
        assert "!ready" in result
        assert "poll()" in result


# ---------------------------------------------------------------------------
# サポート拡張子のテスト
# ---------------------------------------------------------------------------


class TestSupportedExtensions:
    def test_ts_is_supported(self):
        assert ".ts" in get_supported_extensions()

    def test_tsx_is_supported(self):
        assert ".tsx" in get_supported_extensions()

    def test_py_is_supported(self):
        assert ".py" in get_supported_extensions()

    def test_go_is_supported(self):
        assert ".go" in get_supported_extensions()

    def test_returns_frozenset(self):
        assert isinstance(get_supported_extensions(), frozenset)


# ---------------------------------------------------------------------------
# Go 言語 E2E テスト
# ---------------------------------------------------------------------------

_GO_SOURCE = (
    "package main\n"
    'import "fmt"\n'
    "const MAX = 100\n"
    "// calculateBenefit は特典を計算する\n"
    "func calculateBenefit(user User) int {\n"
    '  if user.Status != "ACTIVE" {\n'
    "    return 0\n"
    "  }\n"
    "  total := 0\n"
    "  for _, h := range user.History {\n"
    "    total += h.Price\n"
    "  }\n"
    "  if total >= 100000 {\n"
    "    return 1000\n"
    "  } else {\n"
    "    return 100\n"
    "  }\n"
    "}\n"
)


class TestGoE2E:
    """Go ソースコードの E2E 変換テスト"""

    def test_go_compiles_without_error(self):
        result = compile_to_spec(_GO_SOURCE, "test", ".go")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_go_output_contains_module_header(self):
        result = compile_to_spec(_GO_SOURCE, "test", ".go")
        assert "# モジュール仕様: test" in result

    def test_go_output_contains_import_section(self):
        result = compile_to_spec(_GO_SOURCE, "test", ".go")
        assert "依存関係" in result
        assert "fmt" in result

    def test_go_output_contains_module_constant(self):
        result = compile_to_spec(_GO_SOURCE, "test", ".go")
        assert "MAX" in result
        assert "100" in result

    def test_go_output_contains_function_name(self):
        result = compile_to_spec(_GO_SOURCE, "test", ".go")
        assert "calculateBenefit" in result

    def test_go_output_contains_guard_clause(self):
        result = compile_to_spec(_GO_SOURCE, "test", ".go")
        assert "前提条件（ガード句）" in result

    def test_go_output_contains_for_each_loop(self):
        result = compile_to_spec(_GO_SOURCE, "test", ".go")
        assert "繰り返し処理" in result

    def test_go_output_contains_condition_block(self):
        result = compile_to_spec(_GO_SOURCE, "test", ".go")
        assert "条件分岐" in result

    def test_go_output_contains_data_transformation(self):
        result = compile_to_spec(_GO_SOURCE, "test", ".go")
        assert "データ変換" in result

    def test_go_output_contains_function_description(self):
        result = compile_to_spec(_GO_SOURCE, "test", ".go")
        assert "calculateBenefit は特典を計算する" in result

    def test_go_same_structural_markers_as_typescript(self):
        """Go と TypeScript が同一の構造マーカーを出力することを確認（Universal IR の実証）"""
        go_result = compile_to_spec(_GO_SOURCE, "test", ".go")
        ts_source = (
            "function calculateBenefit(user) {\n"
            '  if (user.status !== "ACTIVE") { return 0; }\n'
            "  let total = 0;\n"
            "  for (const h of user.history) { total += h.price; }\n"
            "  if (total >= 100000) { return 1000; } else { return 100; }\n"
            "}\n"
        )
        ts_result = compile_to_spec(ts_source, "test", ".ts")
        for marker in ["前提条件（ガード句）", "繰り返し処理", "条件分岐", "データ変換"]:
            assert marker in go_result, f"Go 出力に {marker} がない"
            assert marker in ts_result, f"TS 出力に {marker} がない"


# ---------------------------------------------------------------------------
# PowerShell 言語 E2E テスト
# ---------------------------------------------------------------------------

_PS_SOURCE = (
    "function Get-Benefit {\n"
    "    <#\n"
    "    .SYNOPSIS\n"
    "    特典ポイントを計算する\n"
    "    #>\n"
    "    param(\n"
    "        [string]$Status,\n"
    "        [int]$Total\n"
    "    )\n"
    "    if (-not $Status) {\n"
    '        throw "Status is required"\n'
    "    }\n"
    '    if ($Status -ne "ACTIVE") {\n'
    "        return 0\n"
    "    }\n"
    "    foreach ($item in $items) {\n"
    "        Write-Output $item\n"
    "    }\n"
    "    if ($Total -gt 100000) {\n"
    "        return 1000\n"
    "    } elseif ($Total -gt 10000) {\n"
    "        return 500\n"
    "    } else {\n"
    "        return 100\n"
    "    }\n"
    "}\n"
)


class TestPowerShellE2E:
    """PowerShell ソースコードの E2E 変換テスト"""

    def test_ps1_compiles_without_error(self):
        result = compile_to_spec(_PS_SOURCE, "test", ".ps1")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_psm1_compiles_without_error(self):
        result = compile_to_spec(_PS_SOURCE, "test", ".psm1")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_ps1_is_supported_extension(self):
        assert ".ps1" in get_supported_extensions()

    def test_psm1_is_supported_extension(self):
        assert ".psm1" in get_supported_extensions()

    def test_output_contains_module_header(self):
        result = compile_to_spec(_PS_SOURCE, "sample", ".ps1")
        assert "# モジュール仕様: sample" in result

    def test_output_contains_function_name(self):
        result = compile_to_spec(_PS_SOURCE, "test", ".ps1")
        assert "Get-Benefit" in result

    def test_output_contains_synopsis_description(self):
        result = compile_to_spec(_PS_SOURCE, "test", ".ps1")
        assert "特典ポイントを計算する" in result

    def test_output_contains_params(self):
        result = compile_to_spec(_PS_SOURCE, "test", ".ps1")
        assert "$Status" in result
        assert "string" in result

    def test_output_contains_throw_guard_clause(self):
        result = compile_to_spec(_PS_SOURCE, "test", ".ps1")
        assert "前提条件（ガード句）" in result
        assert "スローして処理を中断する" in result

    def test_output_contains_return_guard_clause(self):
        result = compile_to_spec(_PS_SOURCE, "test", ".ps1")
        assert "処理を終了する" in result

    def test_output_contains_foreach_loop(self):
        result = compile_to_spec(_PS_SOURCE, "test", ".ps1")
        assert "繰り返し処理" in result
        assert "$item" in result

    def test_output_contains_condition_block(self):
        result = compile_to_spec(_PS_SOURCE, "test", ".ps1")
        assert "条件分岐" in result

    def test_output_contains_elseif_case(self):
        result = compile_to_spec(_PS_SOURCE, "test", ".ps1")
        # elseif 節が ConditionBlock の 2つ目のケースとして現れる
        assert "$Total -gt 10000" in result

    def test_output_contains_else_default_case(self):
        result = compile_to_spec(_PS_SOURCE, "test", ".ps1")
        assert "上記のいずれにも該当しない場合" in result

    def test_ps_same_structural_markers_as_typescript(self):
        """PowerShell と TypeScript が同一の構造マーカーを出力することを確認（Universal IR の実証）"""
        ps_result = compile_to_spec(_PS_SOURCE, "test", ".ps1")
        ts_source = (
            "function getBenefit(status, total, items) {\n"
            '  if (!status) { throw new Error("required"); }\n'
            '  if (status !== "ACTIVE") { return 0; }\n'
            "  for (const item of items) { console.log(item); }\n"
            "  if (total > 100000) { return 1000; }\n"
            "  else if (total > 10000) { return 500; }\n"
            "  else { return 100; }\n"
            "}\n"
        )
        ts_result = compile_to_spec(ts_source, "test", ".ts")
        for marker in ["前提条件（ガード句）", "繰り返し処理", "条件分岐"]:
            assert marker in ps_result, f"PS 出力に {marker} がない"
            assert marker in ts_result, f"TS 出力に {marker} がない"

    def test_go_c_style_for_loop(self):
        src = (
            "package main\n"
            "func countUp(n int) {\n"
            "  for i := 0; i < n; i++ {\n"
            "  }\n"
            "}\n"
        )
        result = compile_to_spec(src, "test", ".go")
        assert "繰り返し処理" in result


# ---------------------------------------------------------------------------
# Python @dataclass / class の E2E テスト
# ---------------------------------------------------------------------------


class TestPyClassE2E:
    """Python クラス定義が Markdown 仕様書に正しく出力されることを E2E で検証する。"""

    def test_dataclass_section_appears_in_output(self):
        src = (
            "from dataclasses import dataclass\n"
            "@dataclass(frozen=True)\n"
            "class Config:\n"
            "    host: str\n"
            "    port: int = 8080\n"
        )
        result = compile_to_spec(src, "config", ".py")
        assert "🏛️ クラス定義" in result
        assert "`Config` (dataclass)" in result

    def test_class_fields_rendered_as_table(self):
        src = (
            "@dataclass\n"
            "class Point:\n"
            "    x: int\n"
            "    y: float\n"
        )
        result = compile_to_spec(src, "point", ".py")
        assert "`x`" in result
        assert "`int`" in result
        assert "`y`" in result
        assert "`float`" in result

    def test_plain_class_also_extracted(self):
        src = (
            "class MyError(Exception):\n"
            "    message: str\n"
        )
        result = compile_to_spec(src, "errors", ".py")
        assert "🏛️ クラス定義" in result
        assert "`MyError` (class)" in result

    def test_field_with_default_value_shown(self):
        src = (
            "@dataclass\n"
            "class Config:\n"
            "    debug: bool = False\n"
        )
        result = compile_to_spec(src, "config", ".py")
        assert "`False`" in result

    def test_class_docstring_shown_in_output(self):
        src = (
            "@dataclass\n"
            "class Config:\n"
            '    """設定値クラス。"""\n'
            "    host: str\n"
        )
        result = compile_to_spec(src, "config", ".py")
        assert "設定値クラス" in result

    def test_class_section_before_function_section(self):
        src = (
            "@dataclass\n"
            "class Config:\n"
            "    host: str\n"
            "def run(cfg): pass\n"
        )
        result = compile_to_spec(src, "main", ".py")
        class_pos = result.index("🏛️ クラス定義")
        func_pos = result.index("🔧 関数")
        assert class_pos < func_pos


# ---------------------------------------------------------------------------
# Java 言語 E2E テスト
# ---------------------------------------------------------------------------

# 最小限の Java ソース（ガード句・ループ・条件分岐・データ変換を含む）
_JAVA_SOURCE = (
    "import java.util.List;\n"
    "\n"
    "/**\n"
    " * ユーザーの購入履歴からポイント特典を計算するサービスクラス\n"
    " */\n"
    "public class UserBenefitService {\n"
    "\n"
    "    /**\n"
    "     * ユーザーの購入履歴からポイント特典を計算して返す\n"
    "     */\n"
    "    public static BenefitResult getUserBenefit(\n"
    "            String status, String rank, List<Purchase> purchaseHistory) {\n"
    '        if (!status.equals("ACTIVE")) {\n'
    '            throw new IllegalArgumentException("エラー: 無効なユーザーです");\n'
    "        }\n"
    "        int totalAmount = 0;\n"
    "        for (Purchase history : purchaseHistory) {\n"
    "            totalAmount += history.getPrice();\n"
    "        }\n"
    "        if (totalAmount >= 100000) {\n"
    '            return new BenefitResult(1000, "プレミアム特典付与");\n'
    "        } else {\n"
    '            return new BenefitResult(100, "通常特典付与");\n'
    "        }\n"
    "    }\n"
    "\n"
    "    /**\n"
    "     * スコアを評価してグレード文字列を返す\n"
    "     */\n"
    "    public static String evaluateScore(int score) {\n"
    "        if (score < 0 || score > 100) {\n"
    '            throw new IllegalArgumentException("スコアは0〜100の範囲で指定してください");\n'
    "        }\n"
    "        if (score >= 90) {\n"
    '            return "S";\n'
    "        } else {\n"
    '            return "C以下";\n'
    "        }\n"
    "    }\n"
    "}\n"
)


class TestJavaE2E:
    """Java ソースコードの E2E 変換テスト"""

    def test_java_compiles_without_error(self):
        result = compile_to_spec(_JAVA_SOURCE, "sample", ".java")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_java_extension_is_supported(self):
        assert ".java" in get_supported_extensions()

    def test_output_contains_module_header(self):
        result = compile_to_spec(_JAVA_SOURCE, "sample", ".java")
        assert "# モジュール仕様: sample" in result

    def test_output_contains_import_section(self):
        result = compile_to_spec(_JAVA_SOURCE, "sample", ".java")
        assert "📦 依存関係（インポート）" in result

    def test_output_contains_import_module(self):
        result = compile_to_spec(_JAVA_SOURCE, "sample", ".java")
        assert "java.util" in result

    def test_output_contains_import_class(self):
        result = compile_to_spec(_JAVA_SOURCE, "sample", ".java")
        assert "List" in result

    def test_output_contains_class_section(self):
        result = compile_to_spec(_JAVA_SOURCE, "sample", ".java")
        assert "🏛️ クラス定義" in result

    def test_output_contains_class_name(self):
        result = compile_to_spec(_JAVA_SOURCE, "sample", ".java")
        assert "UserBenefitService" in result

    def test_output_contains_class_description_from_javadoc(self):
        result = compile_to_spec(_JAVA_SOURCE, "sample", ".java")
        assert "ユーザーの購入履歴からポイント特典を計算するサービスクラス" in result

    def test_output_contains_method_names_in_list(self):
        result = compile_to_spec(_JAVA_SOURCE, "sample", ".java")
        assert "getUserBenefit" in result
        assert "evaluateScore" in result

    def test_output_contains_method_description_from_javadoc(self):
        result = compile_to_spec(_JAVA_SOURCE, "sample", ".java")
        assert "ユーザーの購入履歴からポイント特典を計算して返す" in result
        assert "スコアを評価してグレード文字列を返す" in result

    def test_output_contains_guard_clause(self):
        result = compile_to_spec(_JAVA_SOURCE, "sample", ".java")
        assert "前提条件（ガード句）" in result

    def test_output_contains_throw_action(self):
        result = compile_to_spec(_JAVA_SOURCE, "sample", ".java")
        assert "スローして処理を中断する" in result

    def test_output_contains_foreach_loop(self):
        result = compile_to_spec(_JAVA_SOURCE, "sample", ".java")
        assert "繰り返し処理" in result
        assert "purchaseHistory" in result

    def test_output_contains_loop_iterator(self):
        result = compile_to_spec(_JAVA_SOURCE, "sample", ".java")
        assert "history" in result

    def test_output_contains_data_transformation(self):
        result = compile_to_spec(_JAVA_SOURCE, "sample", ".java")
        assert "データ変換" in result
        assert "totalAmount" in result

    def test_output_contains_condition_block(self):
        result = compile_to_spec(_JAVA_SOURCE, "sample", ".java")
        assert "条件分岐" in result

    def test_output_contains_method_detail_section(self):
        """メソッドの処理フロー詳細がクラスメソッドとして出力されることを確認する"""
        result = compile_to_spec(_JAVA_SOURCE, "sample", ".java")
        # クラス名.メソッド名 形式で詳細セクションが出力される
        assert "UserBenefitService.getUserBenefit" in result

    def test_output_contains_method_params(self):
        result = compile_to_spec(_JAVA_SOURCE, "sample", ".java")
        assert "status" in result
        assert "String" in result

    def test_output_contains_return_type(self):
        result = compile_to_spec(_JAVA_SOURCE, "sample", ".java")
        assert "BenefitResult" in result

    def test_no_top_level_functions_message_suppressed_when_methods_present(self):
        """クラスメソッドの処理フロー詳細がある場合は「トップレベル関数なし」メッセージを出さない。"""
        result = compile_to_spec(_JAVA_SOURCE, "sample", ".java")
        assert "トップレベル関数が検出されませんでした" not in result

    def test_java_same_structural_markers_as_typescript(self):
        """Java と TypeScript が同一の構造マーカーを出力することを確認（Universal IR の実証）"""
        java_result = compile_to_spec(_JAVA_SOURCE, "sample", ".java")
        ts_source = (
            "function getUserBenefit(status, rank, purchaseHistory) {\n"
            '  if (status !== "ACTIVE") { throw new Error("invalid"); }\n'
            "  let totalAmount = 0;\n"
            "  for (const history of purchaseHistory) { totalAmount += history.price; }\n"
            "  if (totalAmount >= 100000) { return 1000; } else { return 100; }\n"
            "}\n"
        )
        ts_result = compile_to_spec(ts_source, "test", ".ts")
        for marker in ["前提条件（ガード句）", "繰り返し処理", "条件分岐", "データ変換"]:
            assert marker in java_result, f"Java 出力に {marker} がない"
            assert marker in ts_result, f"TS 出力に {marker} がない"


# ---------------------------------------------------------------------------
# PowerShell $Script:* モジュール変数 E2E テスト
# ---------------------------------------------------------------------------

_PS_MODULE_VAR_SOURCE = (
    "$Script:MaxPoints = 1000\n"
    "$Script:PremiumThreshold = 100000\n"
    "$Script:AuditCounter = 0\n"
    "function Get-Benefit {\n"
    "    param([string]$Status)\n"
    "    if (-not $Status) { throw 'required' }\n"
    "    return $Script:MaxPoints\n"
    "}\n"
)


class TestPowerShellModuleVariableE2E:
    """PowerShell $Script:Name = value がモジュール変数として仕様書に出力されることを E2E で確認する"""

    def test_module_variable_section_appears(self):
        result = compile_to_spec(_PS_MODULE_VAR_SOURCE, "test", ".ps1")
        assert "モジュール定数・変数" in result

    def test_module_variable_name_in_output(self):
        result = compile_to_spec(_PS_MODULE_VAR_SOURCE, "test", ".ps1")
        assert "MaxPoints" in result

    def test_module_variable_value_in_output(self):
        result = compile_to_spec(_PS_MODULE_VAR_SOURCE, "test", ".ps1")
        assert "1000" in result

    def test_multiple_module_variables_in_output(self):
        result = compile_to_spec(_PS_MODULE_VAR_SOURCE, "test", ".ps1")
        assert "PremiumThreshold" in result
        assert "AuditCounter" in result

    def test_no_pipeline_warning_for_script_scope_variable(self):
        """$Script:* 変数がトップレベル pipeline 警告として出力されないことを確認する。"""
        result = compile_to_spec(_PS_MODULE_VAR_SOURCE, "test", ".ps1")
        assert "MaxPoints" not in result.split("## ⚠️")[1] if "## ⚠️" in result else True
        assert "pipeline は未対応" not in result
