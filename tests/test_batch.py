"""
batch.py のユニットテスト

設計方針:
- pytest の tmp_path フィクスチャを使い、実際のファイルシステムを操作する
- 外部サービスへの依存なし（tree-sitter のみ依存）
- compile_project() が純粋関数であることを確認する（戻り値のみ検証）
"""
import pytest
from pathlib import Path

from src.batch import (
    CompileResult,
    collect_source_files,
    compile_project,
    derive_output_path,
    generate_index_markdown,
)
from src.pipeline import get_supported_extensions


# ---------------------------------------------------------------------------
# テスト用ソースコード定数
# ---------------------------------------------------------------------------

_TS_SOURCE = "function greet(name) { return name; }\n"
_PY_SOURCE = "def greet(name):\n    return name\n"
_UNSUPPORTED_SOURCE = "console.log('hello');\n"  # .js は非対応


# ---------------------------------------------------------------------------
# collect_source_files のテスト
# ---------------------------------------------------------------------------


class TestCollectSourceFiles:
    def test_finds_ts_file(self, tmp_path: Path):
        (tmp_path / "a.ts").write_text(_TS_SOURCE)
        result = collect_source_files(tmp_path, get_supported_extensions())
        assert any(p.name == "a.ts" for p in result)

    def test_finds_py_file(self, tmp_path: Path):
        (tmp_path / "b.py").write_text(_PY_SOURCE)
        result = collect_source_files(tmp_path, get_supported_extensions())
        assert any(p.name == "b.py" for p in result)

    def test_ignores_unsupported_extension(self, tmp_path: Path):
        (tmp_path / "c.js").write_text(_UNSUPPORTED_SOURCE)
        result = collect_source_files(tmp_path, get_supported_extensions())
        assert all(p.suffix != ".js" for p in result)

    def test_returns_tuple(self, tmp_path: Path):
        (tmp_path / "a.ts").write_text(_TS_SOURCE)
        result = collect_source_files(tmp_path, get_supported_extensions())
        assert isinstance(result, tuple)

    def test_recursive_search(self, tmp_path: Path):
        subdir = tmp_path / "src" / "auth"
        subdir.mkdir(parents=True)
        (subdir / "user.ts").write_text(_TS_SOURCE)
        result = collect_source_files(tmp_path, get_supported_extensions())
        assert any(p.name == "user.ts" for p in result)

    def test_excludes_node_modules(self, tmp_path: Path):
        nm = tmp_path / "node_modules" / "some-lib"
        nm.mkdir(parents=True)
        (nm / "index.ts").write_text(_TS_SOURCE)
        (tmp_path / "main.ts").write_text(_TS_SOURCE)
        result = collect_source_files(tmp_path, get_supported_extensions())
        # 相対パスのパーツで判定（tmp_path 自体のディレクトリ名は除外）
        assert all(
            "node_modules" not in p.relative_to(tmp_path).parts
            for p in result
        )
        assert any(p.name == "main.ts" for p in result)

    def test_excludes_git_directory(self, tmp_path: Path):
        git_dir = tmp_path / ".git" / "hooks"
        git_dir.mkdir(parents=True)
        (git_dir / "pre-commit.py").write_text(_PY_SOURCE)
        result = collect_source_files(tmp_path, get_supported_extensions())
        assert all(".git" not in str(p) for p in result)

    def test_excludes_pycache(self, tmp_path: Path):
        cache = tmp_path / "__pycache__"
        cache.mkdir()
        (cache / "module.py").write_text(_PY_SOURCE)
        result = collect_source_files(tmp_path, get_supported_extensions())
        assert all("__pycache__" not in str(p) for p in result)

    def test_excludes_venv(self, tmp_path: Path):
        venv = tmp_path / "venv" / "lib"
        venv.mkdir(parents=True)
        (venv / "site.py").write_text(_PY_SOURCE)
        result = collect_source_files(tmp_path, get_supported_extensions())
        assert all("venv" not in str(p) for p in result)

    def test_empty_directory_returns_empty_tuple(self, tmp_path: Path):
        result = collect_source_files(tmp_path, get_supported_extensions())
        assert result == ()

    def test_multiple_files_are_sorted(self, tmp_path: Path):
        (tmp_path / "z.ts").write_text(_TS_SOURCE)
        (tmp_path / "a.ts").write_text(_TS_SOURCE)
        (tmp_path / "m.ts").write_text(_TS_SOURCE)
        result = collect_source_files(tmp_path, get_supported_extensions())
        paths_str = [str(p) for p in result]
        assert paths_str == sorted(paths_str)


# ---------------------------------------------------------------------------
# derive_output_path のテスト
# ---------------------------------------------------------------------------


class TestDeriveOutputPath:
    def test_ts_file_gets_ts_md_extension(self, tmp_path: Path):
        project = tmp_path / "proj"
        output = tmp_path / "out"
        source = project / "src" / "auth.ts"
        result = derive_output_path(source, project, output)
        assert result.name == "auth.ts.md"

    def test_py_file_gets_py_md_extension(self, tmp_path: Path):
        project = tmp_path / "proj"
        output = tmp_path / "out"
        source = project / "utils.py"
        result = derive_output_path(source, project, output)
        assert result.name == "utils.py.md"

    def test_directory_structure_is_mirrored(self, tmp_path: Path):
        project = tmp_path / "proj"
        output = tmp_path / "out"
        source = project / "src" / "auth" / "user.ts"
        result = derive_output_path(source, project, output)
        assert result == output / "src" / "auth" / "user.ts.md"

    def test_root_level_file_maps_directly(self, tmp_path: Path):
        project = tmp_path / "proj"
        output = tmp_path / "out"
        source = project / "index.ts"
        result = derive_output_path(source, project, output)
        assert result == output / "index.ts.md"

    def test_same_stem_different_extension_no_collision(self, tmp_path: Path):
        # sample.ts と sample.py が同じディレクトリにあっても衝突しない
        project = tmp_path / "proj"
        output = tmp_path / "out"
        ts_result = derive_output_path(project / "sample.ts", project, output)
        py_result = derive_output_path(project / "sample.py", project, output)
        assert ts_result != py_result
        assert ts_result == output / "sample.ts.md"
        assert py_result == output / "sample.py.md"


# ---------------------------------------------------------------------------
# compile_project のテスト（純粋関数の検証）
# ---------------------------------------------------------------------------


class TestCompileProject:
    def test_returns_tuple(self, tmp_path: Path):
        project = tmp_path / "proj"
        project.mkdir()
        results = compile_project(project, tmp_path / "out")
        assert isinstance(results, tuple)

    def test_empty_project_returns_empty_tuple(self, tmp_path: Path):
        project = tmp_path / "proj"
        project.mkdir()
        results = compile_project(project, tmp_path / "out")
        assert results == ()

    def test_does_not_write_files(self, tmp_path: Path):
        project = tmp_path / "proj"
        project.mkdir()
        (project / "a.ts").write_text(_TS_SOURCE)
        output = tmp_path / "out"
        compile_project(project, output)
        # 純粋関数: 出力ディレクトリが作成されていないことを確認
        assert not output.exists()

    def test_single_ts_file_produces_one_result(self, tmp_path: Path):
        project = tmp_path / "proj"
        project.mkdir()
        (project / "main.ts").write_text(_TS_SOURCE)
        results = compile_project(project, tmp_path / "out")
        assert len(results) == 1

    def test_result_status_is_ok_for_valid_ts(self, tmp_path: Path):
        project = tmp_path / "proj"
        project.mkdir()
        (project / "main.ts").write_text(_TS_SOURCE)
        results = compile_project(project, tmp_path / "out")
        assert results[0].status == "ok"

    def test_result_status_is_ok_for_valid_py(self, tmp_path: Path):
        project = tmp_path / "proj"
        project.mkdir()
        (project / "main.py").write_text(_PY_SOURCE)
        results = compile_project(project, tmp_path / "out")
        assert results[0].status == "ok"

    def test_result_markdown_contains_function_name(self, tmp_path: Path):
        project = tmp_path / "proj"
        project.mkdir()
        (project / "main.ts").write_text(_TS_SOURCE)
        results = compile_project(project, tmp_path / "out")
        assert "greet" in results[0].markdown

    def test_multiple_files_all_compiled(self, tmp_path: Path):
        project = tmp_path / "proj"
        project.mkdir()
        (project / "a.ts").write_text(_TS_SOURCE)
        (project / "b.py").write_text(_PY_SOURCE)
        results = compile_project(project, tmp_path / "out")
        assert len(results) == 2

    def test_output_path_has_md_extension(self, tmp_path: Path):
        project = tmp_path / "proj"
        project.mkdir()
        (project / "main.ts").write_text(_TS_SOURCE)
        results = compile_project(project, tmp_path / "out")
        assert results[0].output_path.suffix == ".md"

    def test_result_is_compile_result_instance(self, tmp_path: Path):
        project = tmp_path / "proj"
        project.mkdir()
        (project / "main.ts").write_text(_TS_SOURCE)
        results = compile_project(project, tmp_path / "out")
        assert isinstance(results[0], CompileResult)

    def test_recursive_files_are_all_compiled(self, tmp_path: Path):
        project = tmp_path / "proj"
        (project / "src" / "auth").mkdir(parents=True)
        (project / "main.ts").write_text(_TS_SOURCE)
        (project / "src" / "auth" / "user.py").write_text(_PY_SOURCE)
        results = compile_project(project, tmp_path / "out")
        assert len(results) == 2

    def test_node_modules_files_are_excluded(self, tmp_path: Path):
        project = tmp_path / "proj"
        nm = project / "node_modules" / "lib"
        nm.mkdir(parents=True)
        (nm / "index.ts").write_text(_TS_SOURCE)
        (project / "main.ts").write_text(_TS_SOURCE)
        results = compile_project(project, tmp_path / "out")
        assert len(results) == 1
        assert results[0].source_path.name == "main.ts"

    def test_error_file_has_error_status(self, tmp_path: Path):
        project = tmp_path / "proj"
        project.mkdir()
        # UTF-8 で読めない壊れたファイルを作成
        (project / "broken.ts").write_bytes(b"\xff\xfe broken")
        results = compile_project(project, tmp_path / "out")
        assert results[0].status == "error"
        assert results[0].error_message != ""


# ---------------------------------------------------------------------------
# generate_index_markdown のテスト
# ---------------------------------------------------------------------------


class TestGenerateIndexMarkdown:
    def _make_ok_result(self, project: Path, output: Path, name: str) -> CompileResult:
        return CompileResult(
            source_path=project / f"{name}.ts",
            output_path=output / f"{name}.md",
            status="ok",
            markdown="# dummy",
            error_message="",
        )

    def _make_error_result(self, project: Path, output: Path, name: str) -> CompileResult:
        return CompileResult(
            source_path=project / f"{name}.ts",
            output_path=output / f"{name}.md",
            status="error",
            markdown="",
            error_message="SyntaxError: unexpected token",
        )

    def test_returns_string(self, tmp_path: Path):
        project = tmp_path / "proj"
        output = tmp_path / "out"
        result = generate_index_markdown(project, output, ())
        assert isinstance(result, str)

    def test_contains_project_name(self, tmp_path: Path):
        project = tmp_path / "myproject"
        output = tmp_path / "out"
        result = generate_index_markdown(project, output, ())
        assert "myproject" in result

    def test_contains_total_count(self, tmp_path: Path):
        project = tmp_path / "proj"
        output = tmp_path / "out"
        results = (
            self._make_ok_result(project, output, "a"),
            self._make_ok_result(project, output, "b"),
        )
        index = generate_index_markdown(project, output, results)
        assert "2" in index

    def test_ok_file_has_link(self, tmp_path: Path):
        project = tmp_path / "proj"
        output = tmp_path / "out"
        results = (self._make_ok_result(project, output, "auth"),)
        index = generate_index_markdown(project, output, results)
        assert "[auth]" in index
        assert "auth.md" in index

    def test_error_file_shows_warning_icon(self, tmp_path: Path):
        project = tmp_path / "proj"
        output = tmp_path / "out"
        results = (self._make_error_result(project, output, "broken"),)
        index = generate_index_markdown(project, output, results)
        assert "❌" in index

    def test_error_message_appears_in_error_section(self, tmp_path: Path):
        project = tmp_path / "proj"
        output = tmp_path / "out"
        results = (self._make_error_result(project, output, "broken"),)
        index = generate_index_markdown(project, output, results)
        assert "SyntaxError: unexpected token" in index

    def test_no_error_section_when_all_ok(self, tmp_path: Path):
        project = tmp_path / "proj"
        output = tmp_path / "out"
        results = (self._make_ok_result(project, output, "main"),)
        index = generate_index_markdown(project, output, results)
        assert "エラー詳細" not in index

    def test_ends_with_newline(self, tmp_path: Path):
        project = tmp_path / "proj"
        output = tmp_path / "out"
        result = generate_index_markdown(project, output, ())
        assert result.endswith("\n")
