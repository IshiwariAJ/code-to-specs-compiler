"""
バッチコンパイル: プロジェクトディレクトリ全体を再帰的にコンパイルする

責務:
  - プロジェクト内の全ソースファイルを収集する
  - 各ファイルをコンパイルした結果を CompileResult として返す
  - ファイル I/O（書き込み）を行わない（書き込みは CLI 層に委譲）

設計方針（構造化プログラミング原則）:
  - compile_project() は副作用なし（純粋関数）
  - 失敗ファイルも例外を伝播せずに status="error" の CompileResult として返す
  - シーケンスはすべて tuple で表現する
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from src.pipeline import compile_to_spec, get_supported_extensions


# ---------------------------------------------------------------------------
# 除外ディレクトリ: よくある非ソースディレクトリを再帰探索から除く
# ---------------------------------------------------------------------------

_EXCLUDED_DIRS: frozenset[str] = frozenset({
    "node_modules",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
    ".next",
    ".turbo",
    "coverage",
    ".tox",
})

_EXCLUDED_DIR_PREFIXES: tuple[str, ...] = (
    ".pytest_tmp",
)


# ---------------------------------------------------------------------------
# データ型
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CompileResult:
    """1ファイルのコンパイル結果（純粋データ）。"""

    source_path: Path
    output_path: Path
    status: Literal["ok", "error"]
    markdown: str       # status == "ok" の場合のみ有効
    error_message: str  # status == "error" の場合のみ有効


# ---------------------------------------------------------------------------
# ファイル収集
# ---------------------------------------------------------------------------


def collect_source_files(
    project_dir: Path,
    extensions: frozenset[str],
) -> tuple[Path, ...]:
    """
    ディレクトリを再帰的に走査して対応拡張子のファイル一覧を返す。
    _EXCLUDED_DIRS に含まれるディレクトリは除外する。

    Args:
        project_dir: 走査するプロジェクトルートディレクトリ
        extensions:  対象拡張子の集合（例: frozenset({".ts", ".py"})）

    Returns:
        見つかったソースファイルのパス tuple（パス文字列順でソート済み）
    """
    def _is_excluded_dir_name(part: str) -> bool:
        return part in _EXCLUDED_DIRS or any(
            part.startswith(prefix)
            for prefix in _EXCLUDED_DIR_PREFIXES
        )

    def _is_under_excluded_dir(path: Path) -> bool:
        return any(
            _is_excluded_dir_name(part)
            for part in path.relative_to(project_dir).parts
        )

    return tuple(
        sorted(
            path
            for ext in extensions
            for path in project_dir.rglob(f"*{ext}")
            if not _is_under_excluded_dir(path)
        )
    )


# ---------------------------------------------------------------------------
# 出力パスの計算
# ---------------------------------------------------------------------------


def derive_output_path(
    source_path: Path,
    project_dir: Path,
    output_dir: Path,
) -> Path:
    """
    ソースファイルのパスから出力 Markdown ファイルのパスを計算する。

    ディレクトリ構造を output_dir にミラーリングし、ファイル名に ".md" を追加する。
    元の拡張子を保持することで、同一ディレクトリに同名別言語のファイルが
    存在しても衝突しない。

    例:
        source_path: myproject/src/auth/user.ts
        project_dir: myproject/
        output_dir:  myproject_specs/
        →            myproject_specs/src/auth/user.ts.md

        source_path: myproject/src/auth/user.py
        →            myproject_specs/src/auth/user.py.md

    Args:
        source_path: ソースファイルの絶対パス
        project_dir: プロジェクトルート（source_path の祖先）
        output_dir:  出力先ルートディレクトリ

    Returns:
        出力 Markdown ファイルの絶対パス
    """
    relative = source_path.relative_to(project_dir)
    # 元の拡張子を残して .md を追加する（例: user.ts → user.ts.md）
    new_name = relative.name + ".md"
    return output_dir / relative.parent / new_name


# ---------------------------------------------------------------------------
# 単一ファイルのコンパイル
# ---------------------------------------------------------------------------


def _compile_single_file(
    source_path: Path,
    project_dir: Path,
    output_dir: Path,
) -> CompileResult:
    """
    1ファイルをコンパイルして CompileResult を返す。
    例外はキャッチして status="error" に変換する（例外を伝播しない）。
    """
    output_path = derive_output_path(source_path, project_dir, output_dir)
    try:
        source_code = source_path.read_text(encoding="utf-8")
        module_name = source_path.stem
        markdown = compile_to_spec(source_code, module_name, source_path.suffix)
        return CompileResult(
            source_path=source_path,
            output_path=output_path,
            status="ok",
            markdown=markdown,
            error_message="",
        )
    except Exception as exc:  # noqa: BLE001
        return CompileResult(
            source_path=source_path,
            output_path=output_path,
            status="error",
            markdown="",
            error_message=str(exc),
        )


# ---------------------------------------------------------------------------
# プロジェクト全体のコンパイル（副作用なし）
# ---------------------------------------------------------------------------


def compile_project(
    project_dir: Path,
    output_dir: Path,
) -> tuple[CompileResult, ...]:
    """
    プロジェクトディレクトリ内の全ソースファイルをコンパイルする。

    ファイルの書き込みは行わない（純粋関数）。
    呼び出し元が CompileResult を受け取って書き込みを行う。

    Args:
        project_dir: ソースファイルを収集するディレクトリ
        output_dir:  出力パス計算に使用するディレクトリ（実際の書き込みは行わない）

    Returns:
        各ファイルの CompileResult の tuple
    """
    source_files = collect_source_files(project_dir, get_supported_extensions())
    return tuple(
        _compile_single_file(path, project_dir, output_dir)
        for path in source_files
    )


# ---------------------------------------------------------------------------
# インデックス Markdown の生成（副作用なし）
# ---------------------------------------------------------------------------


def generate_index_markdown(
    project_dir: Path,
    output_dir: Path,
    results: tuple[CompileResult, ...],
) -> str:
    """
    プロジェクト全体の仕様書インデックス Markdown を生成する（副作用なし）。

    Args:
        project_dir: 元のプロジェクトディレクトリ
        output_dir:  出力ディレクトリ（相対リンク計算に使用）
        results:     compile_project() の戻り値

    Returns:
        INDEX.md に書き込む Markdown 文字列
    """
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ok_count = sum(1 for r in results if r.status == "ok")
    error_count = sum(1 for r in results if r.status == "error")
    total = len(results)

    lines: list[str] = [
        f"# プロジェクト仕様書: {project_dir.name}",
        "",
        f"- **生成日時**: {timestamp}",
        f"- **対象ファイル数**: {total}  （✅ 成功: {ok_count} / ❌ エラー: {error_count}）",
        f"- **元ディレクトリ**: `{project_dir}`",
        "",
        "---",
        "",
        "## モジュール一覧",
        "",
        "| ステータス | モジュール | ソースファイル |",
        "|---|---|---|",
    ]

    for result in sorted(results, key=lambda r: r.source_path):
        status_icon = "✅" if result.status == "ok" else "❌"
        relative_source = result.source_path.relative_to(project_dir)
        relative_output = result.output_path.relative_to(output_dir)
        module_name = result.source_path.stem

        if result.status == "ok":
            module_cell = f"[{module_name}]({relative_output.as_posix()})"
        else:
            module_cell = f"`{module_name}` ⚠️ エラー"

        lines.append(
            f"| {status_icon} | {module_cell} | `{relative_source.as_posix()}` |"
        )

    if error_count > 0:
        lines += [
            "",
            "---",
            "",
            "## エラー詳細",
            "",
        ]
        for result in sorted(results, key=lambda r: r.source_path):
            if result.status == "error":
                relative_source = result.source_path.relative_to(project_dir)
                lines += [
                    f"### `{relative_source.as_posix()}`",
                    "",
                    "```",
                    result.error_message,
                    "```",
                    "",
                ]

    return "\n".join(lines) + "\n"
