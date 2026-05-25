# 自然言語コンパイラ — プロジェクト進捗管理

最終更新: 2026-05-25（Phase 5A 完了: Go 対応）

---

## 全体ロードマップ

```
Phase 1  ██████████ 完了     TypeScript の if/for → Markdown 変換（基礎実装）
Phase 2A ██████████ 完了     精度向上: ループ本体の代入・副作用を IR に取り込む
Phase 2B ██████████ 完了     Python 対応: tree-sitter-python でフロントエンドを追加
Phase 3  ██████████ 完了     テスト整備: 138件（test_batch を含む）
Phase 4  ██████████ 完了     プロジェクト一括コンパイル（ディレクトリ再帰処理）
Phase 4+ ██████████ 完了     コメント抽出（JSDoc/docstring/インライン）+ __future__ 対応 + OSS公開（Apache 2.0）
Phase 5A ██████████ 完了     Go 対応（for range / C スタイル for / := / assignment_statement）
Phase 5B ░░░░░░░░░░ 未着手   Java 対応
```

---

## Phase 1 — 完了 ✅

**完了日**: 2026-05-25  
**スコープ**: TypeScript 1ファイルを対象に、`if` 文と `for` 文を Markdown 仕様書に変換する

### 実装済みの機能

| 機能 | 詳細 |
|---|---|
| TypeScript パース | tree-sitter 0.25.x + tree-sitter-typescript 0.23.x |
| ガード句の検出 | `if (...) { return/throw }` パターンを自動識別 |
| 条件分岐の変換 | `if/else if/else` チェーン全体を構造化テキストに変換 |
| for...of の変換 | コレクションとイテレータ変数を抽出 |
| 古典的 for の変換 | `init; condition; increment` を構造化テキストに変換 |
| Markdown 出力 | 絵文字付きの階層化日本語仕様書 |
| CLI | `python main.py <ファイル> [出力先]` で動作 |

### Phase 1 の出力サンプル（`examples/sample.ts`）

```markdown
# モジュール仕様: sample

## 🔧 関数: `calculateUserBenefit`

### 1. 📢 前提条件（ガード句）
* **条件:** `user.status !== "ACTIVE"` の場合
  * ➔ 例外 `new Error("エラー: 無効なユーザーです")` をスローして処理を中断する

### 2. 🔄 繰り返し処理
* `user.purchaseHistory` の各要素（`history`）に対して以下をループ実行:

### 3. 🔀 条件分岐
* **ケース 1: totalAmount >= 100000 && user.rank === "Gold"**
  * ➔ `return { points: 1000, message: "プレミアム特典付与" };`
...
```

---

## Phase 2-A — 完了 ✅

**完了日**: 2026-05-25  
**目的**: ループ本体・関数本体の代入文・副作用を IR に取り込み、出力品質を向上する。

### 実装済みの内容

| 追加した IR 型 | 対応する TypeScript 構文 | 例 |
|---|---|---|
| `DataTransformation` | `+=`, `-=`, `*=`, `/=` | `totalAmount += history.price` |
| `DataTransformation` | `=`（単純代入） | `x = y + 1` |
| `DataTransformation` | `let/const x = 値` （初期化） | `let totalAmount = 0` |
| `SideEffect` | 関数呼び出し | `console.log(x)`, `arr.push(v)` |

**operation 識別子**: `ADD / SUBTRACT / MULTIPLY / DIVIDE / MODULO / ASSIGN / LOGICAL_OR_ASSIGN / LOGICAL_AND_ASSIGN / NULLISH_ASSIGN`  
（マッパーが記録 → レンダラーが `_OPERATION_LABELS` 辞書で日本語に変換）

### Phase 2-A の出力サンプル

```markdown
### 2. 🔁 データ変換
* `totalAmount` に代入する: `0`

### 3. 🔄 繰り返し処理
* `user.purchaseHistory` の各要素（`history`）に対して以下をループ実行:
  * `totalAmount` に加算して更新する: `history.price`
```

---

## Phase 2-B — 完了 ✅

**完了日**: 2026-05-25  
**目的**: Python ファイルを解析できるようにし、多言語共通出力の実証をする。

### 実装済みの内容

| 新規/変更ファイル | 内容 |
|---|---|
| `src/ir/profiles.py` ✨新規 | `LanguageProfile` frozen dataclass + `TYPESCRIPT_PROFILE` / `PYTHON_PROFILE` 定数 |
| `src/ir/mapper.py` 変更 | `LanguageProfile` を受け取るよう全関数をリファクタリング。言語差異を Profile に集約 |
| `src/parser/python_parser.py` ✨新規 | `parse_python_source(source_code: str) -> Node` （ts_parser と同一インターフェース）|
| `src/pipeline.py` 変更 | `_LANGUAGE_CONFIGS` 辞書で拡張子 → (パーサー, Profile) を管理。新言語追加は1行追加のみ |
| `main.py` 変更 | `source_path.suffix` を `compile_to_spec` に渡して自動言語判定 |
| `requirements.txt` 変更 | `tree-sitter-python>=0.21.0` 追加 |
| `examples/sample.py` ✨新規 | TypeScript 版 sample.ts と同一ロジックの Python コード（比較実証用）|

### TypeScript と Python の主要な AST 差異

| 差異 | TypeScript | Python |
|---|---|---|
| 関数定義 | `function_declaration` | `function_definition` |
| elif/else 構造 | `else_clause → if_statement`（入れ子） | `elif_clause`, `else_clause`（兄弟フラット） |
| ガード中断 | `throw_statement` | `raise_statement` |
| 複合代入 | `augmented_assignment_expression` | `augmented_assignment` |
| 関数呼び出し | `call_expression` | `call` |
| for ループ | `for_in_statement`（of/in 共用） | `for_statement`（常に FOR_EACH）|

### 実証結果: 同一ロジック・同一フォーマットの確認

`examples/sample.ts` と `examples/sample.py` は同一のビジネスロジックを持ち、
どちらも **同一のMarkdownフォーマット** で仕様書が出力されることを確認。
これが「Universal IR による多言語統合」の中核的な価値実証となった。

---

## Phase 3 — 完了 ✅

**完了日**: 2026-05-25  
**目的**: 各層の純粋関数をユニットテストで保護し、リファクタリング耐性を確保する。

### 実装済みの内容

```
tests/
├── test_mapper.py    ← 39件: map_source_to_module_spec() 経由で全 IR 型を検証
├── test_renderer.py  ← 30件: 手動 IR 構築でレンダラーを検証
├── test_pipeline.py  ← 32件: compile_to_spec() の E2E テスト
└── test_batch.py     ← 37件: バッチコンパイル機能の検証（Phase 4 と同時追加）
```

テストフレームワーク: `pytest 9.0.3`  
合計: **138件 全グリーン**（実行時間 0.15s）

---

## Phase 4 — 完了 ✅

**完了日**: 2026-05-25  
**目的**: VS Code に依存しないスタンドアロンCLI として、プロジェクトフォルダ全体を再帰的にコンパイルできるようにする。

### 実装済みの内容

| 新規/変更ファイル | 内容 |
|---|---|
| `src/batch.py` ✨新規 | `CompileResult` frozen dataclass + `collect_source_files()` / `compile_project()` / `generate_index_markdown()` |
| `main.py` 変更 | 入力がファイルかディレクトリかを自動判定。ディレクトリなら全ファイルを再帰コンパイル |
| `tests/test_batch.py` ✨新規 | バッチ層の 37 件ユニットテスト |

### 機能仕様

**除外ディレクトリ**: `node_modules`, `.git`, `__pycache__`, `.venv`, `venv`, `dist`, `build` など自動スキップ  
**出力形式**: ソース構造をミラーリングし、`<name>.<ext>.md` 形式で保存（同名異言語ファイルも衝突なし）

```
myproject/
  src/auth.ts   →  myproject_specs/src/auth.ts.md
  src/user.py   →  myproject_specs/src/user.py.md
                +  myproject_specs/INDEX.md（モジュール一覧・リンク付き）
```

### 使用方法

```bash
# 単一ファイル（従来どおり）
python main.py examples/sample.ts

# プロジェクト全体（新機能）
python main.py myproject/
python main.py myproject/ output_dir/
```

---

## 未来のフェーズ（参考）

| フェーズ | 内容 |
|---|---|
| Phase 5 | Go / Java 対応（新しい `LanguageProfile` + パーサーを追加するだけ） |
| Phase 6 | Git フック連携（コミット時に自動再生成） |

---

## 既知の制限事項（Phase 1 時点）

1. **アロー関数・メソッドは未対応**: `const fn = () => {}` や クラスメソッドは検出しない
2. **ネストした関数は未対応**: 内部関数宣言は無視される
3. **型情報なし**: 変数の型（`User`, `number` 等）は仕様書に含まれない
4. **変数名依存**: 意味不明な変数名（`x`, `tmp`）の場合、出力も意味不明になる

---

## 環境情報

| 項目 | バージョン |
|---|---|
| Python | 3.14.3 |
| tree-sitter | 0.25.2 |
| tree-sitter-typescript | 0.23.2 |
| OS | Windows 11 Pro |
