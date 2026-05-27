"""
自然言語コンパイラ CLI エントリーポイント

使用方法:
    # 単一ファイルをコンパイル
    python main.py <ソースファイルパス> [出力ファイルパス]

    # プロジェクト全体を再帰的にコンパイル
    python main.py <プロジェクトディレクトリ> [出力ディレクトリ]

対応言語（拡張子で自動判定）:
    .ts / .tsx  →  TypeScript
    .py         →  Python

例:
    python main.py examples/sample.ts
    python main.py examples/sample.py output.md
    python main.py myproject/
    python main.py myproject/ myproject_specs/
"""
import sys
from pathlib import Path

# Windows のコンソールが CP932 のときも絵文字・日本語を正しく出力するため UTF-8 に設定する
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

from src.batch import CompileResult, compile_project, generate_index_markdown
from src.pipeline import compile_to_spec, get_supported_extensions


# ---------------------------------------------------------------------------
# 単一ファイルモード
# ---------------------------------------------------------------------------


def _read_source_file(path: Path) -> str:
    """ソースファイルを読み込んで文字列を返す。ファイルが存在しない場合はエラー終了する。"""
    if not path.exists():
        print(f"エラー: ファイルが見つかりません: {path}", file=sys.stderr)
        sys.exit(1)

    if path.suffix not in get_supported_extensions():
        supported = ", ".join(sorted(get_supported_extensions()))
        print(
            f"エラー: サポートされていない拡張子 '{path.suffix}' です。"
            f"対応拡張子: {supported}",
            file=sys.stderr,
        )
        sys.exit(1)

    return path.read_text(encoding="utf-8")


def _write_or_print_result(result: str, output_path: Path | None) -> None:
    """結果をファイルに書き出すか、標準出力に表示する。"""
    if output_path is not None:
        output_path.write_text(result, encoding="utf-8")
        print(f"✅ 仕様書を出力しました: {output_path}", file=sys.stderr)
    else:
        print(result)


def _run_file_mode(source_path: Path, output_path: Path | None) -> None:
    """単一ファイルをコンパイルして出力する。"""
    source_code = _read_source_file(source_path)
    module_name = source_path.stem
    result = compile_to_spec(source_code, module_name, extension=source_path.suffix)
    _write_or_print_result(result, output_path)


# ---------------------------------------------------------------------------
# プロジェクトモード
# ---------------------------------------------------------------------------


def _default_output_dir(project_dir: Path) -> Path:
    """プロジェクトディレクトリに対応するデフォルト出力ディレクトリを返す。

    例: myproject/ → myproject_specs/（同じ親ディレクトリに作成）
    """
    return project_dir.parent / f"{project_dir.name}_specs"


def _write_compile_results(
    results: tuple[CompileResult, ...],
    project_dir: Path,
    output_dir: Path,
) -> None:
    """CompileResult をファイルに書き込む（I/O を一箇所に集約）。"""
    # ディレクトリ作成・Markdown 書き込み
    for result in results:
        if result.status == "ok":
            result.output_path.parent.mkdir(parents=True, exist_ok=True)
            result.output_path.write_text(result.markdown, encoding="utf-8")

    # INDEX.md を生成して書き込む
    index_path = output_dir / "INDEX.md"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_content = generate_index_markdown(project_dir, output_dir, results)
    index_path.write_text(index_content, encoding="utf-8")


def _print_project_summary(
    results: tuple[CompileResult, ...],
    output_dir: Path,
) -> None:
    """プロジェクトコンパイルの結果サマリーを stderr に出力する。"""
    ok_count = sum(1 for r in results if r.status == "ok")
    error_count = sum(1 for r in results if r.status == "error")
    total = len(results)

    print(f"\n📂 コンパイル完了: {total} ファイル", file=sys.stderr)
    print(f"   ✅ 成功: {ok_count}", file=sys.stderr)

    if error_count > 0:
        print(f"   ❌ エラー: {error_count}", file=sys.stderr)
        for result in results:
            if result.status == "error":
                print(f"      - {result.source_path}: {result.error_message}", file=sys.stderr)

    print(f"\n📁 出力先: {output_dir}", file=sys.stderr)
    print(f"📋 インデックス: {output_dir / 'INDEX.md'}", file=sys.stderr)


def _run_project_mode(project_dir: Path, output_dir: Path) -> None:
    """プロジェクトディレクトリ全体を再帰的にコンパイルして出力する。"""
    if not project_dir.is_dir():
        print(f"エラー: ディレクトリが見つかりません: {project_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"🔍 スキャン中: {project_dir}", file=sys.stderr)
    results = compile_project(project_dir, output_dir)

    if len(results) == 0:
        supported = ", ".join(sorted(get_supported_extensions()))
        print(
            f"警告: 対応ファイルが見つかりませんでした。\n"
            f"対応拡張子: {supported}",
            file=sys.stderr,
        )
        return

    print(f"⚙️  コンパイル中: {len(results)} ファイル ...", file=sys.stderr)
    _write_compile_results(results, project_dir, output_dir)
    _print_project_summary(results, output_dir)


# ---------------------------------------------------------------------------
# エントリーポイント
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str]) -> tuple[Path, Path | None]:
    """コマンドライン引数を解析して (入力パス, 出力パス|None) を返す。"""
    if len(argv) < 2:
        print(
            "使用方法:\n"
            "  ファイル  : python main.py <ソースファイルパス> [出力ファイルパス]\n"
            "  プロジェクト: python main.py <プロジェクトディレクトリ> [出力ディレクトリ]",
            file=sys.stderr,
        )
        sys.exit(1)

    input_path = Path(argv[1])
    output_path = Path(argv[2]) if len(argv) >= 3 else None
    return input_path, output_path


def main() -> None:
    """CLI エントリーポイント。入力がファイルかディレクトリかで動作を切り替える。"""
    input_path, output_path = _parse_args(sys.argv)

    if input_path.is_dir():
        resolved_output = output_path if output_path is not None else _default_output_dir(input_path)
        _run_project_mode(input_path, resolved_output)
    else:
        _run_file_mode(input_path, output_path)


if __name__ == "__main__":
    main()
