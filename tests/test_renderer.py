"""
renderer/markdown.py のユニットテスト

設計方針:
- IR オブジェクトを直接構築してレンダラーに渡す（AST の解析を経由しない）
- 純粋関数のテストなのでセットアップ・ teardown なし
- 出力に特定の文字列が含まれることで意図した変換を確認する
"""
from src.ir.types import (
    CaseNode,
    ClassFieldSpec,
    ClassSpec,
    ConditionBlock,
    DataTransformation,
    FunctionSpec,
    GuardClause,
    ImportSpec,
    LoopNode,
    ModuleSpec,
    ModuleVariableSpec,
    ReturnNode,
    SideEffect,
    TryCatchNode,
    TypeDefinitionSpec,
)
from src.renderer.markdown import render_module_spec


# ---------------------------------------------------------------------------
# ヘルパー: 単一 IR ノードを含む最小 ModuleSpec をレンダリングする
# ---------------------------------------------------------------------------


def _render_single_node(*nodes) -> str:
    """IR ノード列を含む関数仕様をレンダリングして Markdown 文字列を返す。"""
    spec = ModuleSpec(
        name="TestModule",
        functions=(FunctionSpec(name="testFunc", body=nodes),),
    )
    return render_module_spec(spec)


# ---------------------------------------------------------------------------
# ModuleSpec 全体のレンダリング
# ---------------------------------------------------------------------------


class TestRenderModuleSpec:
    def test_module_name_in_h1_header(self):
        spec = ModuleSpec(name="UserBenefitModule", functions=())
        output = render_module_spec(spec)
        assert "# モジュール仕様: UserBenefitModule" in output

    def test_no_functions_shows_placeholder(self):
        spec = ModuleSpec(name="Empty", functions=())
        output = render_module_spec(spec)
        assert "関数が検出されませんでした" in output

    def test_function_name_appears_in_output(self):
        spec = ModuleSpec(
            name="Test",
            functions=(FunctionSpec(name="myFunction", body=()),),
        )
        output = render_module_spec(spec)
        assert "myFunction" in output

    def test_empty_function_body_shows_placeholder(self):
        spec = ModuleSpec(name="Test", functions=(FunctionSpec(name="f", body=()),))
        output = render_module_spec(spec)
        assert "制御フローはありません" in output

    def test_multiple_functions_all_appear(self):
        spec = ModuleSpec(
            name="Test",
            functions=(
                FunctionSpec(name="funcA", body=()),
                FunctionSpec(name="funcB", body=()),
                FunctionSpec(name="funcC", body=()),
            ),
        )
        output = render_module_spec(spec)
        assert "funcA" in output
        assert "funcB" in output
        assert "funcC" in output

    def test_separator_between_functions(self):
        spec = ModuleSpec(
            name="Test",
            functions=(
                FunctionSpec(name="a", body=()),
                FunctionSpec(name="b", body=()),
            ),
        )
        output = render_module_spec(spec)
        assert "---" in output

    def test_extraction_warnings_are_rendered(self):
        spec = ModuleSpec(
            name="Test",
            functions=(),
            extraction_warnings=("関数 `f`: while_statement は未対応です",),
        )
        output = render_module_spec(spec)
        assert "抽出警告" in output
        assert "while_statement" in output


# ---------------------------------------------------------------------------
# GuardClause のレンダリング
# ---------------------------------------------------------------------------


class TestRenderGuardClause:
    def test_section_header_contains_guard_label(self):
        node = GuardClause(kind="GuardClause", condition_text="x == null", action_text="中断する")
        output = _render_single_node(node)
        assert "前提条件（ガード句）" in output

    def test_condition_text_is_in_backticks(self):
        node = GuardClause(kind="GuardClause", condition_text="user.status != ACTIVE", action_text="中断する")
        output = _render_single_node(node)
        assert "`user.status != ACTIVE`" in output

    def test_action_text_appears_after_arrow(self):
        node = GuardClause(kind="GuardClause", condition_text="x < 0", action_text="例外をスローして処理を中断する")
        output = _render_single_node(node)
        assert "例外をスローして処理を中断する" in output
        assert "➔" in output

    def test_section_number_is_1(self):
        node = GuardClause(kind="GuardClause", condition_text="x", action_text="y")
        output = _render_single_node(node)
        assert "### 1." in output

    def test_second_node_has_section_number_2(self):
        node1 = GuardClause(kind="GuardClause", condition_text="a", action_text="b")
        node2 = GuardClause(kind="GuardClause", condition_text="c", action_text="d")
        output = _render_single_node(node1, node2)
        assert "### 1." in output
        assert "### 2." in output


# ---------------------------------------------------------------------------
# ConditionBlock のレンダリング
# ---------------------------------------------------------------------------


class TestRenderConditionBlock:
    def test_section_header_contains_condition_label(self):
        node = ConditionBlock(kind="ConditionBlock", cases=(
            CaseNode(condition_text="x > 0", body=(
                ReturnNode(kind="ReturnNode", value_text="1"),
            )),
        ))
        output = _render_single_node(node)
        assert "条件分岐" in output

    def test_single_case_condition_text_appears(self):
        node = ConditionBlock(kind="ConditionBlock", cases=(
            CaseNode(condition_text="x > 100", body=(
                ReturnNode(kind="ReturnNode", value_text="1000"),
            )),
        ))
        output = _render_single_node(node)
        assert "x > 100" in output

    def test_single_case_action_text_appears(self):
        node = ConditionBlock(kind="ConditionBlock", cases=(
            CaseNode(condition_text="x > 100", body=(
                ReturnNode(kind="ReturnNode", value_text="1000"),
            )),
        ))
        output = _render_single_node(node)
        assert "返却する: `1000`" in output

    def test_three_cases_have_case_numbers(self):
        node = ConditionBlock(kind="ConditionBlock", cases=(
            CaseNode(condition_text="x >= 90", body=(ReturnNode(kind="ReturnNode", value_text="'A'"),)),
            CaseNode(condition_text="x >= 70", body=(ReturnNode(kind="ReturnNode", value_text="'B'"),)),
            CaseNode(condition_text="デフォルト", body=(ReturnNode(kind="ReturnNode", value_text="'C'"),)),
        ))
        output = _render_single_node(node)
        assert "ケース 1" in output
        assert "ケース 2" in output
        assert "ケース 3" in output

    def test_all_condition_texts_appear(self):
        node = ConditionBlock(kind="ConditionBlock", cases=(
            CaseNode(condition_text="score >= 90"),
            CaseNode(condition_text="score >= 70"),
        ))
        output = _render_single_node(node)
        assert "score >= 90" in output
        assert "score >= 70" in output


# ---------------------------------------------------------------------------
# LoopNode のレンダリング
# ---------------------------------------------------------------------------


class TestRenderLoopNode:
    def test_for_each_header_contains_loop_label(self):
        node = LoopNode(kind="Loop", loop_type="FOR_EACH", collection="items", iterator="item", body=())
        output = _render_single_node(node)
        assert "繰り返し処理" in output

    def test_for_each_collection_appears(self):
        node = LoopNode(kind="Loop", loop_type="FOR_EACH", collection="user.history", iterator="h", body=())
        output = _render_single_node(node)
        assert "user.history" in output

    def test_for_each_iterator_appears(self):
        node = LoopNode(kind="Loop", loop_type="FOR_EACH", collection="arr", iterator="element", body=())
        output = _render_single_node(node)
        assert "element" in output

    def test_for_range_header_contains_loop_label(self):
        node = LoopNode(kind="Loop", loop_type="FOR_RANGE", collection="let i = 0; i < n; i++", iterator="i", body=())
        output = _render_single_node(node)
        assert "繰り返し処理" in output

    def test_for_range_collection_text_appears(self):
        node = LoopNode(kind="Loop", loop_type="FOR_RANGE", collection="let i = 0; i < 10; i++", iterator="i", body=())
        output = _render_single_node(node)
        assert "i < 10" in output

    def test_nested_body_node_is_indented(self):
        nested = DataTransformation(
            kind="DataTransformation", target="total", operation="ADD", value="item"
        )
        node = LoopNode(kind="Loop", loop_type="FOR_EACH", collection="arr", iterator="item", body=(nested,))
        output = _render_single_node(node)
        # ネスト表示: インデントされた箇条書き
        assert "  *" in output

    def test_nested_body_data_transformation_text_appears(self):
        nested = DataTransformation(
            kind="DataTransformation", target="total", operation="ADD", value="item.price"
        )
        node = LoopNode(kind="Loop", loop_type="FOR_EACH", collection="arr", iterator="item", body=(nested,))
        output = _render_single_node(node)
        assert "total" in output
        assert "item.price" in output


# ---------------------------------------------------------------------------
# TryCatchNode のレンダリング
# ---------------------------------------------------------------------------


class TestRenderTryCatchNode:
    def test_section_header_contains_exception_label(self):
        node = TryCatchNode(kind="TryCatchNode", try_body=())
        output = _render_single_node(node)
        assert "例外処理" in output

    def test_try_body_is_rendered(self):
        node = TryCatchNode(
            kind="TryCatchNode",
            try_body=(SideEffect(kind="SideEffect", description="work()"),),
        )
        output = _render_single_node(node)
        assert "try ブロック" in output
        assert "work()" in output

    def test_catch_var_is_rendered(self):
        node = TryCatchNode(
            kind="TryCatchNode",
            try_body=(),
            catch_var="error",
            catch_body=(SideEffect(kind="SideEffect", description="log(error)"),),
        )
        output = _render_single_node(node)
        assert "catch ブロック (`error`)" in output
        assert "log(error)" in output

    def test_finally_body_is_rendered(self):
        node = TryCatchNode(
            kind="TryCatchNode",
            try_body=(),
            finally_body=(SideEffect(kind="SideEffect", description="cleanup()"),),
        )
        output = _render_single_node(node)
        assert "finally ブロック" in output
        assert "cleanup()" in output


# ---------------------------------------------------------------------------
# DataTransformation のレンダリング
# ---------------------------------------------------------------------------


class TestRenderDataTransformation:
    def test_add_operation_uses_japanese_label(self):
        node = DataTransformation(kind="DataTransformation", target="total", operation="ADD", value="item.price")
        output = _render_single_node(node)
        assert "加算して更新する" in output

    def test_subtract_operation_uses_japanese_label(self):
        node = DataTransformation(kind="DataTransformation", target="count", operation="SUBTRACT", value="1")
        output = _render_single_node(node)
        assert "減算して更新する" in output

    def test_multiply_operation_uses_japanese_label(self):
        node = DataTransformation(kind="DataTransformation", target="x", operation="MULTIPLY", value="2")
        output = _render_single_node(node)
        assert "乗算して更新する" in output

    def test_divide_operation_uses_japanese_label(self):
        node = DataTransformation(kind="DataTransformation", target="x", operation="DIVIDE", value="2")
        output = _render_single_node(node)
        assert "除算して更新する" in output

    def test_assign_operation_uses_japanese_label(self):
        node = DataTransformation(kind="DataTransformation", target="total", operation="ASSIGN", value="0")
        output = _render_single_node(node)
        assert "代入する" in output

    def test_target_and_value_appear_in_backticks(self):
        node = DataTransformation(kind="DataTransformation", target="totalAmount", operation="ADD", value="history.price")
        output = _render_single_node(node)
        assert "`totalAmount`" in output
        assert "`history.price`" in output

    def test_section_number_is_present(self):
        node = DataTransformation(kind="DataTransformation", target="x", operation="ADD", value="1")
        output = _render_single_node(node)
        assert "### 1." in output


# ---------------------------------------------------------------------------
# SideEffect のレンダリング
# ---------------------------------------------------------------------------


class TestRenderSideEffect:
    def test_description_appears_in_backticks(self):
        node = SideEffect(kind="SideEffect", description="console.log(x)")
        output = _render_single_node(node)
        assert "`console.log(x)`" in output

    def test_side_effect_label_appears(self):
        node = SideEffect(kind="SideEffect", description="arr.push(v)")
        output = _render_single_node(node)
        assert "副作用" in output

    def test_section_number_is_present(self):
        node = SideEffect(kind="SideEffect", description="print(x)")
        output = _render_single_node(node)
        assert "### 1." in output

    def test_nested_side_effect_has_no_section_header(self):
        # ループ内の副作用はセクション番号なしの箇条書き
        nested_se = SideEffect(kind="SideEffect", description="console.log(x)")
        loop = LoopNode(kind="Loop", loop_type="FOR_EACH", collection="arr", iterator="item", body=(nested_se,))
        output = _render_single_node(loop)
        # ネスト表示では ### ヘッダーがつかない
        lines = output.split("\n")
        nested_lines = [l for l in lines if "console.log" in l]
        assert len(nested_lines) == 1
        assert not nested_lines[0].strip().startswith("###")


# ---------------------------------------------------------------------------
# ImportSpec のレンダリング
# ---------------------------------------------------------------------------


def _render_with_imports(*imports: ImportSpec) -> str:
    """インポートを含む最小 ModuleSpec をレンダリングして返す。"""
    spec = ModuleSpec(name="Test", functions=(), imports=imports)
    return render_module_spec(spec)


class TestRenderImportSpec:
    def test_imports_section_header_appears(self):
        spec = ImportSpec(kind="ImportSpec", source_module="react", imported_names=("useState",), alias="")
        output = _render_with_imports(spec)
        assert "依存関係" in output

    def test_source_module_in_backticks(self):
        spec = ImportSpec(kind="ImportSpec", source_module="lodash", imported_names=(), alias="")
        output = _render_with_imports(spec)
        assert "`lodash`" in output

    def test_named_import_names_appear(self):
        spec = ImportSpec(kind="ImportSpec", source_module="react", imported_names=("useState", "useEffect"), alias="")
        output = _render_with_imports(spec)
        assert "`useState`" in output
        assert "`useEffect`" in output

    def test_alias_appears_in_output(self):
        spec = ImportSpec(kind="ImportSpec", source_module="numpy", imported_names=(), alias="np")
        output = _render_with_imports(spec)
        assert "`np`" in output

    def test_namespace_import_shows_asterisk_label(self):
        spec = ImportSpec(kind="ImportSpec", source_module="lodash", imported_names=(), alias="*")
        output = _render_with_imports(spec)
        assert "*" in output

    def test_whole_module_import_shows_label(self):
        spec = ImportSpec(kind="ImportSpec", source_module="os", imported_names=(), alias="")
        output = _render_with_imports(spec)
        assert "モジュール全体" in output

    def test_no_imports_hides_section(self):
        spec = ModuleSpec(name="Test", functions=())
        output = render_module_spec(spec)
        assert "依存関係" not in output


# ---------------------------------------------------------------------------
# ModuleVariableSpec のレンダリング
# ---------------------------------------------------------------------------


def _render_with_vars(*vars_: ModuleVariableSpec) -> str:
    """モジュール変数を含む最小 ModuleSpec をレンダリングして返す。"""
    spec = ModuleSpec(name="Test", functions=(), module_variables=vars_)
    return render_module_spec(spec)


class TestRenderModuleVariableSpec:
    def test_variables_section_header_appears(self):
        v = ModuleVariableSpec(kind="ModuleVariableSpec", name="X", value_text="1", is_constant=True)
        output = _render_with_vars(v)
        assert "定数" in output or "変数" in output

    def test_constant_shows_constant_label(self):
        v = ModuleVariableSpec(kind="ModuleVariableSpec", name="MAX", value_text="100", is_constant=True)
        output = _render_with_vars(v)
        assert "定数" in output

    def test_variable_shows_variable_label(self):
        v = ModuleVariableSpec(kind="ModuleVariableSpec", name="count", value_text="0", is_constant=False)
        output = _render_with_vars(v)
        assert "変数" in output

    def test_name_in_backticks(self):
        v = ModuleVariableSpec(kind="ModuleVariableSpec", name="MAX_RETRY", value_text="3", is_constant=True)
        output = _render_with_vars(v)
        assert "`MAX_RETRY`" in output

    def test_value_in_backticks(self):
        v = ModuleVariableSpec(kind="ModuleVariableSpec", name="X", value_text="42", is_constant=True)
        output = _render_with_vars(v)
        assert "`42`" in output

    def test_no_vars_hides_section(self):
        spec = ModuleSpec(name="Test", functions=())
        output = render_module_spec(spec)
        assert "モジュール定数" not in output


# ---------------------------------------------------------------------------
# TypeDefinitionSpec のレンダリング
# ---------------------------------------------------------------------------


def _render_with_type_defs(*defs: TypeDefinitionSpec) -> str:
    """型定義を含む最小 ModuleSpec をレンダリングして返す。"""
    spec = ModuleSpec(name="Test", functions=(), type_definitions=defs)
    return render_module_spec(spec)


class TestRenderTypeDefinitionSpec:
    def test_type_defs_section_header_appears(self):
        d = TypeDefinitionSpec(kind="TypeDefinitionSpec", name="UserId", definition_kind="alias", type_text="string")
        output = _render_with_type_defs(d)
        assert "型定義" in output

    def test_type_alias_label(self):
        d = TypeDefinitionSpec(kind="TypeDefinitionSpec", name="UserId", definition_kind="alias", type_text="string")
        output = _render_with_type_defs(d)
        assert "type エイリアス" in output

    def test_interface_label(self):
        d = TypeDefinitionSpec(kind="TypeDefinitionSpec", name="User", definition_kind="interface", type_text="{ name: string; }")
        output = _render_with_type_defs(d)
        assert "interface" in output

    def test_name_appears_in_backticks(self):
        d = TypeDefinitionSpec(kind="TypeDefinitionSpec", name="AppConfig", definition_kind="interface", type_text="{ host: string; }")
        output = _render_with_type_defs(d)
        assert "`AppConfig`" in output

    def test_type_text_appears(self):
        d = TypeDefinitionSpec(kind="TypeDefinitionSpec", name="Status", definition_kind="alias", type_text="'ACTIVE' | 'INACTIVE'")
        output = _render_with_type_defs(d)
        assert "ACTIVE" in output

    def test_union_type_pipe_is_escaped_for_markdown_table(self):
        """
        ユニオン型の | は Markdown テーブルのカラム区切りと衝突するため \\| にエスケープされること。
        例: "ACTIVE" | "INACTIVE" | "BANNED" → "ACTIVE" \\| "INACTIVE" \\| "BANNED"
        """
        d = TypeDefinitionSpec(
            kind="TypeDefinitionSpec",
            name="UserStatus",
            definition_kind="alias",
            type_text='"ACTIVE" | "INACTIVE" | "BANNED"',
        )
        output = _render_with_type_defs(d)
        # すべての値が出力に含まれること
        assert "ACTIVE" in output
        assert "INACTIVE" in output
        assert "BANNED" in output
        # | がエスケープされていること（生の | だけの行は存在しない）
        assert r"\|" in output

    def test_interface_long_body_not_truncated(self):
        """
        インターフェースのボディが長くても省略記号（...）なしで全文が出力されること。
        例: purchaseHistory: { price: number }[] が切り捨てられないことを保証する。
        """
        d = TypeDefinitionSpec(
            kind="TypeDefinitionSpec",
            name="User",
            definition_kind="interface",
            type_text="{ status: UserStatus; rank: string; purchaseHistory: { price: number }[]; }",
        )
        output = _render_with_type_defs(d)
        assert "purchaseHistory" in output
        assert "{ price: number }[]" in output
        assert "..." not in output

    def test_no_type_defs_hides_section(self):
        spec = ModuleSpec(name="Test", functions=())
        output = render_module_spec(spec)
        assert "型定義" not in output


# ---------------------------------------------------------------------------
# コメント正規化ユーティリティ（_normalize_comment）
# ---------------------------------------------------------------------------

from src.renderer.markdown import _normalize_comment, _render_comment_blockquote


class TestNormalizeComment:
    def test_ts_line_comment_strips_prefix(self):
        assert _normalize_comment("// 合計を計算する") == "合計を計算する"

    def test_ts_line_comment_strips_spaces(self):
        assert _normalize_comment("//   スペース   ") == "スペース"

    def test_ts_jsdoc_single_line(self):
        result = _normalize_comment("/** 説明文 */")
        assert "説明文" in result

    def test_ts_jsdoc_multiline(self):
        result = _normalize_comment("/**\n * 行1\n * 行2\n */")
        assert "行1" in result
        assert "行2" in result

    def test_python_comment(self):
        assert _normalize_comment("# Pythonコメント") == "Pythonコメント"

    def test_python_triple_double_quote_docstring(self):
        result = _normalize_comment('"""これは docstring"""')
        assert "docstring" in result

    def test_python_triple_single_quote_docstring(self):
        result = _normalize_comment("'''これは docstring'''")
        assert "docstring" in result

    def test_python_single_line_string(self):
        result = _normalize_comment('"単行"')
        assert "単行" in result

    def test_empty_string_returns_empty(self):
        assert _normalize_comment("") == ""


class TestRenderCommentBlockquote:
    def test_line_comment_becomes_blockquote(self):
        result = _render_comment_blockquote("// 注釈")
        assert result == "> 注釈"

    def test_empty_comment_returns_empty(self):
        result = _render_comment_blockquote("")
        assert result == ""

    def test_multiline_jsdoc_each_line_quoted(self):
        result = _render_comment_blockquote("/**\n * 行A\n * 行B\n */")
        lines = [l for l in result.splitlines() if l]
        assert all(line.startswith("> ") for line in lines)

    def test_python_comment_becomes_blockquote(self):
        result = _render_comment_blockquote("# Pythonの注釈")
        assert result == "> Pythonの注釈"


# ---------------------------------------------------------------------------
# コメント付き IR ノードのレンダリング
# ---------------------------------------------------------------------------


class TestRenderWithComments:
    def test_guard_clause_with_comment_shows_blockquote(self):
        node = GuardClause(
            kind="GuardClause",
            condition_text="x < 0",
            action_text="例外をスロー",
            comment="// 前提条件チェック",
        )
        output = _render_single_node(node)
        assert "> 前提条件チェック" in output

    def test_guard_clause_without_comment_no_extra_blockquote(self):
        node = GuardClause(kind="GuardClause", condition_text="x < 0", action_text="例外をスロー")
        output = _render_single_node(node)
        lines = output.splitlines()
        assert not any(line.startswith("> ") for line in lines)

    def test_data_transformation_with_comment_top_level(self):
        node = DataTransformation(
            kind="DataTransformation",
            target="count",
            operation="ASSIGN",
            value="0",
            comment="// カウンター初期化",
        )
        output = _render_single_node(node)
        assert "> カウンター初期化" in output

    def test_data_transformation_with_comment_nested_in_loop(self):
        """LoopNode の body 内（index=0）でもコメントが表示される。"""
        inner = DataTransformation(
            kind="DataTransformation",
            target="total",
            operation="ADD",
            value="x",
            comment="// 合計に加算",
        )
        loop = LoopNode(
            kind="Loop",
            loop_type="FOR_EACH",
            collection="items",
            iterator="x",
            body=(inner,),
        )
        output = _render_single_node(loop)
        assert "> 合計に加算" in output

    def test_side_effect_with_comment(self):
        node = SideEffect(
            kind="SideEffect",
            description="console.log(x)",
            comment="// デバッグ出力",
        )
        output = _render_single_node(node)
        assert "> デバッグ出力" in output

    def test_condition_block_with_comment(self):
        node = ConditionBlock(
            kind="ConditionBlock",
            cases=(CaseNode(
                condition_text="x > 0",
                body=(ReturnNode(kind="ReturnNode", value_text="x"),),
            ),),
            comment="// 条件によって分岐",
        )
        output = _render_single_node(node)
        assert "> 条件によって分岐" in output

    def test_loop_node_with_comment(self):
        node = LoopNode(
            kind="Loop",
            loop_type="FOR_EACH",
            collection="items",
            iterator="item",
            body=(),
            comment="// 各アイテムを処理",
        )
        output = _render_single_node(node)
        assert "> 各アイテムを処理" in output


class TestRenderFunctionWithDescription:
    def test_jsdoc_description_shown_as_blockquote(self):
        spec = FunctionSpec(
            name="myFunc",
            body=(),
            description="/** ユーザーの特典を計算する */",
        )
        module = ModuleSpec(name="Test", functions=(spec,))
        output = render_module_spec(module)
        assert "> ユーザーの特典を計算する" in output

    def test_line_comment_description_shown_as_blockquote(self):
        spec = FunctionSpec(
            name="myFunc",
            body=(),
            description="// 合計を計算する関数",
        )
        module = ModuleSpec(name="Test", functions=(spec,))
        output = render_module_spec(module)
        assert "> 合計を計算する関数" in output

    def test_function_without_description_no_blockquote(self):
        spec = FunctionSpec(name="myFunc", body=())
        module = ModuleSpec(name="Test", functions=(spec,))
        output = render_module_spec(module)
        lines = output.splitlines()
        assert not any(line.startswith("> ") for line in lines)

    def test_description_appears_before_processing_flow(self):
        spec = FunctionSpec(
            name="myFunc",
            body=(),
            description="// この関数の説明",
        )
        module = ModuleSpec(name="Test", functions=(spec,))
        output = render_module_spec(module)
        desc_pos = output.index("> この関数の説明")
        flow_pos = output.index("処理フロー")
        assert desc_pos < flow_pos


class TestRenderModuleWithFileComment:
    def test_ts_file_comment_shown_as_blockquote(self):
        spec = ModuleSpec(
            name="Test",
            functions=(),
            file_comment="// このモジュールは認証処理を担当する",
        )
        output = render_module_spec(spec)
        assert "> このモジュールは認証処理を担当する" in output

    def test_py_module_docstring_shown_as_blockquote(self):
        spec = ModuleSpec(
            name="Test",
            functions=(),
            file_comment='"""Python モジュールの説明。"""',
        )
        output = render_module_spec(spec)
        assert "> Python モジュールの説明。" in output

    def test_no_file_comment_no_blockquote_lines(self):
        spec = ModuleSpec(name="Test", functions=())
        output = render_module_spec(spec)
        lines = output.splitlines()
        blockquote_lines = [l for l in lines if l.startswith("> ")]
        assert blockquote_lines == []


# ---------------------------------------------------------------------------
# クラス定義レンダリングのテスト
# ---------------------------------------------------------------------------


def _make_class_module(*classes: ClassSpec) -> ModuleSpec:
    """ClassSpec を含む最小 ModuleSpec を作成するヘルパー。"""
    return ModuleSpec(name="TestModule", functions=(), class_definitions=classes)


class TestRenderClassDefinitions:
    """ClassSpec → Markdown 変換の網羅的なテスト。"""

    def test_class_definitions_section_heading(self):
        cls = ClassSpec(kind="ClassSpec", name="Config", is_dataclass=True)
        output = render_module_spec(_make_class_module(cls))
        assert "## 🏛️ クラス定義" in output

    def test_dataclass_label_shown(self):
        cls = ClassSpec(kind="ClassSpec", name="Config", is_dataclass=True)
        output = render_module_spec(_make_class_module(cls))
        assert "`Config` (dataclass)" in output

    def test_plain_class_label_shown(self):
        cls = ClassSpec(kind="ClassSpec", name="MyClass", is_dataclass=False)
        output = render_module_spec(_make_class_module(cls))
        assert "`MyClass` (class)" in output

    def test_class_docstring_shown_as_blockquote(self):
        cls = ClassSpec(
            kind="ClassSpec",
            name="Config",
            is_dataclass=True,
            description='"""設定値を保持する。"""',
        )
        output = render_module_spec(_make_class_module(cls))
        assert "> 設定値を保持する。" in output

    def test_field_name_and_type_in_table(self):
        field = ClassFieldSpec(name="host", type_text="str")
        cls = ClassSpec(kind="ClassSpec", name="Config", is_dataclass=True, fields=(field,))
        output = render_module_spec(_make_class_module(cls))
        assert "`host`" in output
        assert "`str`" in output

    def test_field_default_value_shown(self):
        field = ClassFieldSpec(name="port", type_text="int", default_text="8080")
        cls = ClassSpec(kind="ClassSpec", name="Config", is_dataclass=True, fields=(field,))
        output = render_module_spec(_make_class_module(cls))
        assert "`8080`" in output

    def test_field_no_default_shows_dash(self):
        field = ClassFieldSpec(name="host", type_text="str", default_text="")
        cls = ClassSpec(kind="ClassSpec", name="Config", is_dataclass=True, fields=(field,))
        output = render_module_spec(_make_class_module(cls))
        # デフォルトなし → "—" が表示される
        assert "| — |" in output

    def test_field_inline_comment_shown(self):
        field = ClassFieldSpec(name="host", type_text="str", comment="サーバーホスト名")
        cls = ClassSpec(kind="ClassSpec", name="Config", is_dataclass=True, fields=(field,))
        output = render_module_spec(_make_class_module(cls))
        assert "サーバーホスト名" in output

    def test_field_no_comment_shows_dash(self):
        field = ClassFieldSpec(name="host", type_text="str", comment="")
        cls = ClassSpec(kind="ClassSpec", name="Config", is_dataclass=True, fields=(field,))
        output = render_module_spec(_make_class_module(cls))
        # コメントなし → "—" が表示される
        # テーブルヘッダー行の "説明" 列直下に "—" がある
        assert "| — |" in output

    def test_no_fields_renders_without_placeholder(self):
        """フィールドがないクラスは、クラス名のみを表示し誤解を招くプレースホルダーを出さない。"""
        cls = ClassSpec(kind="ClassSpec", name="EmptyClass", is_dataclass=True, fields=())
        output = render_module_spec(_make_class_module(cls))
        assert "EmptyClass" in output
        assert "フィールド定義が検出されませんでした" not in output
        assert "フィールド名" not in output  # テーブルヘッダーも出ない

    def test_class_section_appears_before_function_section(self):
        field = ClassFieldSpec(name="x", type_text="int")
        cls = ClassSpec(kind="ClassSpec", name="Config", is_dataclass=True, fields=(field,))
        func = FunctionSpec(name="myFunc", body=())
        spec = ModuleSpec(name="TestModule", functions=(func,), class_definitions=(cls,))
        output = render_module_spec(spec)
        class_pos = output.index("🏛️ クラス定義")
        func_pos = output.index("🔧 関数: `myFunc`")
        assert class_pos < func_pos

    def test_multiple_classes_rendered(self):
        cls_a = ClassSpec(kind="ClassSpec", name="A", is_dataclass=True)
        cls_b = ClassSpec(kind="ClassSpec", name="B", is_dataclass=False)
        output = render_module_spec(_make_class_module(cls_a, cls_b))
        assert "`A` (dataclass)" in output
        assert "`B` (class)" in output

    def test_table_header_row_present(self):
        field = ClassFieldSpec(name="x", type_text="int")
        cls = ClassSpec(kind="ClassSpec", name="Config", is_dataclass=True, fields=(field,))
        output = render_module_spec(_make_class_module(cls))
        assert "| フィールド名 | 型 | デフォルト値 | 説明 |" in output

    def test_class_not_rendered_when_empty_tuple(self):
        """class_definitions=() の場合はクラスセクション自体が出力されない。"""
        spec = ModuleSpec(name="Test", functions=())
        output = render_module_spec(spec)
        assert "🏛️ クラス定義" not in output

    def test_class_methods_rendered_as_list(self):
        """クラスのメソッドが「メソッド:」見出し付きの箇条書きで表示される。"""
        method_a = FunctionSpec(name="do_something", body=())
        method_b = FunctionSpec(name="validate", body=())
        cls = ClassSpec(
            kind="ClassSpec", name="MyClass", is_dataclass=False,
            methods=(method_a, method_b),
        )
        output = render_module_spec(_make_class_module(cls))
        assert "**メソッド:**" in output
        assert "* `do_something`" in output
        assert "* `validate`" in output

    def test_class_method_with_description_shown_inline(self):
        """description 付きメソッドは「`名前` — 説明」形式で表示される。"""
        method = FunctionSpec(name="process", body=(), description="データを処理する。")
        cls = ClassSpec(
            kind="ClassSpec", name="Processor", is_dataclass=False,
            methods=(method,),
        )
        output = render_module_spec(_make_class_module(cls))
        assert "* `process` — データを処理する。" in output

    def test_fields_and_methods_both_rendered(self):
        """フィールドとメソッドが共存するクラスで両方が出力される。"""
        field = ClassFieldSpec(name="host", type_text="str")
        method = FunctionSpec(name="connect", body=())
        cls = ClassSpec(
            kind="ClassSpec", name="Client", is_dataclass=True,
            fields=(field,), methods=(method,),
        )
        output = render_module_spec(_make_class_module(cls))
        assert "| `host` |" in output       # フィールドテーブル
        assert "* `connect`" in output       # メソッド一覧

    def test_no_methods_section_when_empty(self):
        """methods=() の場合は「メソッド:」見出しが出力されない。"""
        cls = ClassSpec(kind="ClassSpec", name="Data", is_dataclass=True)
        output = render_module_spec(_make_class_module(cls))
        assert "**メソッド:**" not in output
