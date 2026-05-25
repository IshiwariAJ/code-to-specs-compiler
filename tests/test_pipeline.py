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

    def test_returns_frozenset(self):
        assert isinstance(get_supported_extensions(), frozenset)
