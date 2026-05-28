# 自然言語コンパイラ — プロジェクト進捗管理

最終更新: 2026-05-28（レビュー指摘対応: ドキュメント更新 / switch case 警告回帰テスト）

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
Phase R1 ██████████ 完了     リファクタリング: LanguageProfile 構造フラグ化（profile.name ハードコード撤廃）
Phase R2 ██████████ 完了     リファクタリング: 言語プラグインシステム（中核ファイル変更なしで新言語追加）
Phase R3 ██████████ 完了     Python クラス定義対応（@dataclass / class → クラス定義セクション）
Phase R4 ██████████ 完了     クラスメソッド抽出対応（クラス内メソッド一覧を仕様書に表示）
Phase 5B ██████████ 完了     Java 対応（src/languages/java.py 1ファイル追加）
Phase R5 ██████████ 完了     レンダラー強化（Java クラスメソッドの処理フロー詳細を出力）
Phase R6 ██████████ 完了     条件分岐ボディのネスト IR 解析（CaseNode.body）
Phase R7 ██████████ 完了     例外処理のネスト IR 解析（TryCatchNode）
Phase R8 ██████████ 完了     Python 誤警告バグ修正（docstring / pass / ellipsis）
Phase R9 ██████████ 完了     async / await マーカー（is_async / is_awaited フィールド、全言語対応）
Phase R10 ██████████ 完了    レビュー指摘対応（テスト件数更新 / switch case 内未対応文の回帰テスト）
```

---

## 現在の検証状況

**503件 全グリーン**（2026-05-28 時点）

| テストファイル | 件数 |
|---|---|
| `tests/test_mapper.py` | 254件 |
| `tests/test_renderer.py` | 125件 |
| `tests/test_pipeline.py` | 85件 |
| `tests/test_batch.py` | 39件 |

直近の補強として、TypeScript `switch` の `case` 本体に含まれる未対応文（例: `break_statement`）が `extraction_warnings` に記録されることを回帰テストで固定した。

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
| `src/ir/profiles.py` ✨新規 | `LanguageProfile` frozen dataclass 定義（定数は後の R2 で各言語ファイルへ移動）|
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
├── test_mapper.py    ← 当初 39件 → 現在 ~160件: map_source_to_module_spec() 経由で全 IR 型を検証
├── test_renderer.py  ← 当初 30件 → 現在 ~90件:  手動 IR 構築でレンダラーを検証
├── test_pipeline.py  ← 当初 32件 → 現在 ~60件:  compile_to_spec() の E2E テスト
└── test_batch.py     ← 39件: バッチコンパイル機能の検証
```

テストフレームワーク: `pytest 9.0.3`  
当初: **138件 全グリーン**（実行時間 0.15s）  
現在（Phase R4 完了時点）: **328件 全グリーン**（実行時間 0.30s）

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

## Phase 5A — 完了 ✅

**完了日**: 2026-05-25  
**目的**: Go 言語ファイルを解析できるようにする。

### 実装済みの内容

| 新規/変更ファイル | 内容 |
|---|---|
| `src/parser/go_parser.py` ✨新規 | `parse_go_source(source_code: str) -> Node` |
| `src/ir/profiles.py` 変更 | `GO_PROFILE` 定数追加（後の R2 で `src/languages/go.py` に移動）|
| `src/ir/mapper.py` 変更 | Go 用の for-range / for-clause / assignment_statement 等を追加 |
| `src/pipeline.py` 変更 | `_LANGUAGE_CONFIGS` に `.go` エントリ追加 |
| `examples/sample.go` ✨新規 | Go サンプルコード |
| テスト追加 | `TestGoGuardClause` / `TestGoLoopNode` / `TestGoDataTransformation` 等（Go 用 50件超）|

### Go 固有の AST 特性

| 特性 | 詳細 |
|---|---|
| for ループ統合 | `for_statement` が range / C スタイル / 無限ループを兼ねる |
| 直接代入文 | `assignment_statement` / `short_var_declaration`（`:=`）が `expression_statement` を介さない |
| ブロック構造 | `block → statement_list → 文ノード` の2段構造 |
| else if | TypeScript と同じ `nested` スタイル（Go には `elif` がない）|

---

## Phase 5A 後 — バグ修正 ✅

**完了日**: 2026-05-25  
**内容**: Go 対応後に発見された出力品質の不具合を修正。

### 修正内容

| 不具合 | 原因 | 修正箇所 |
|---|---|---|
| Python 関数先頭コメントが出力されない | tree-sitter-python が関数ブロック先頭コメントを `block` の外（`function_definition` 直下）に配置する | `mapper.py` `_get_preceding_comment` にフォールバック追加 |
| TypeScript ユニオン型が途中で切れる（`"ACTIVE"` のみ表示） | `\|` が Markdown テーブルの列区切りと衝突 | `renderer.py` `_render_type_definition_row` で `\|` エスケープ |
| interface ボディが `{...` で打ち切られる | `_truncate_text(max_len=60)` を型定義に誤用 | `mapper.py` の型定義抽出に `_normalize_whitespace` を使用 |
| モジュール変数値が途中で切れる（`LanguageProfile(...)` が途切れる）| 同上 | `mapper.py` の変数抽出 3箇所に `_normalize_whitespace` を使用 |

---

## Phase R1 — 完了 ✅（リファクタリング）

**完了日**: 2026-05-25  
**目的**: `mapper.py` 内に散在していた `profile.name == "go"` 等のハードコードを撤廃し、新言語追加時の修正箇所を明確化する。

### 問題（リファクタリング前）

`mapper.py` の複数箇所で言語名による分岐が発生していた:
```python
if profile.name == "python":    # _get_function_description
if profile.name == "python":    # _get_file_header_comment
if profile.name == "typescript" and not _is_for_of(...):  # for ループ
elif profile.name == "go":      # for ループ（×1）
elif profile.name == "go" and node_type == "assignment_statement":  # 直接代入（×3）
if profile.name == "typescript":  # import 抽出
elif profile.name == "go":        # import 抽出
if profile.name == "typescript":  # モジュール変数
elif profile.name == "go":        # モジュール変数
_extract_ts_type_definition(child)  # 型定義（ベタ書き）
```

### 解決策

#### ① `LanguageProfile` に構造フラグを追加

| 追加フィールド | 型 | 意味 |
|---|---|---|
| `function_description_style` | `str` | `"comment"` または `"docstring"` |
| `has_module_docstring` | `bool` | ファイル先頭にモジュール docstring を持つか |
| `for_loop_flavor` | `str` | `"of_keyword"` / `"range_clause"` / `"always_foreach"` |
| `direct_statement_types` | `frozenset[str]` | 直接代入文のノードタイプ集合 |

#### ② mapper.py にディスパッチテーブルを追加

```python
_DIRECT_STATEMENT_MAPPER  ← ノードタイプ → 変換関数
_IMPORT_NODE_EXTRACTOR    ← 言語名 → import 抽出関数
_MODULE_VAR_NODE_EXTRACTOR← 言語名 → モジュール変数抽出関数
_TYPE_DEF_NODE_EXTRACTOR  ← 言語名 → 型定義抽出関数
```

### 結果

`mapper.py` のロジック関数内から `profile.name == "..."` が完全に消滅。
新言語追加時はテーブルへの追記のみ。**285件 全グリーン**。

---

## Phase R2 — 完了 ✅（リファクタリング）

**完了日**: 2026-05-25  
**目的**: 新言語対応を「既存の中核ファイルを変更せず、言語プラグインとして追加できる」アーキテクチャに刷新する。

### 問題（R2 前）

新言語 C++ を追加しようとすると、既存の4ファイルを修正する必要があった:
```
src/ir/profiles.py    ← CPP_PROFILE 定数追加
src/ir/mapper.py      ← 抽出関数追加 + テーブル4箇所にエントリ追加
src/pipeline.py       ← _LANGUAGE_CONFIGS に1行追加
src/parser/           ← パーサー新規追加（これは不可避）
```

### 解決策: 言語プラグインシステム

#### 新しいファイル構造

```
src/
  ir/
    node_utils.py   ← ★ 新規: extract_node_text 等の共有ユーティリティ
    profiles.py     → LanguageProfile 定義のみ（定数は各言語ファイルへ移動）
    mapper.py       → 言語名参照ゼロ。LanguagePlugin を受け取る純粋な変換エンジン
  languages/
    __init__.py     ← ★ 新規: LanguagePlugin 型 + discover_plugins() 自動探索エンジン
    typescript.py   ← ★ 新規: TypeScript のすべて（Profile + 抽出関数 + PLUGIN 定数）
    python.py       ← ★ 新規: Python のすべて
    go.py           ← ★ 新規: Go のすべて
  pipeline.py       → _LANGUAGE_CONFIGS 廃止 → discover_plugins() に切り替え
```

#### `LanguagePlugin` frozen dataclass

```python
@dataclass(frozen=True)
class LanguagePlugin:
    extensions:                   tuple[str, ...]
    profile:                      LanguageProfile
    parse_source:                 Callable[[str], Node]
    import_extractor:             Callable[[Node], list[ImportSpec]]
    module_var_extractor:         Callable[[Node], Optional[ModuleVariableSpec]]
    type_def_extractor:           Callable[[Node], Optional[TypeDefinitionSpec]]
    direct_statement_extractors:  tuple[tuple[str, Callable], ...]
    class_extractor:              Callable[[Node], Optional[ClassSpec]]  # R3 追加
```

#### 自動探索エンジン

`src/languages/` 内のすべての `*.py` ファイルを走査し、
`PLUGIN` 定数を持つモジュールを自動的に登録する。

### 結果: Java を追加するとき

```
1. src/parser/java_parser.py   ← パーサー新規作成（不可避）
2. src/languages/java.py       ← JAVA_PROFILE + 抽出関数 + PLUGIN 定数（これだけ）
   ↑ 既存ファイルへの変更ゼロ。pipeline.py も profiles.py も mapper.py も触らない
```

**285件 全グリーン**（実行時間 0.25s）  
※ Phase R4 完了後は **328件**。

---

## Phase R3 — 完了 ✅（Python クラス定義対応）

**完了日**: 2026-05-25  
**目的**: Python ファイルに含まれる `@dataclass` / `class` 定義をMarkdown仕様書に出力する。

### 問題（R3 前）

`src/ir/profiles.py` のように「関数を持たない・クラス定義だけ」の Python ファイルをコンパイルすると、
`@dataclass` 定義（14行以降全体）が完全に出力されなかった。

### 実装内容

#### ① 新 IR 型（`src/ir/types.py`）

| 型名 | 意味 |
|---|---|
| `ClassFieldSpec` | クラスの1フィールド（名前・型・デフォルト値・インラインコメント）|
| `ClassSpec` | クラス定義全体（名前・is_dataclass フラグ・docstring・フィールド列・メソッド列）|

`ClassSpec` のフィールド:
```python
fields:   tuple[ClassFieldSpec, ...] = ()  # 型アノテーション付きフィールド（@dataclass 等）
methods:  tuple[FunctionSpec, ...] = ()    # クラス内メソッド一覧（R4 追加）
```

`ModuleSpec` に `class_definitions: tuple[ClassSpec, ...] = ()` フィールドを追加。

#### ② 言語プロファイル（`src/ir/profiles.py`）

`class_node_types: frozenset[str]` フィールドを追加:
- Python: `frozenset({"decorated_definition", "class_definition"})`
- TypeScript / Go: `frozenset()` （未対応）

#### ③ 言語プラグイン（`src/languages/__init__.py`）

`class_extractor: Callable[[Node], Optional[ClassSpec]]` フィールドを追加。

#### ④ Python クラス抽出（`src/languages/python.py`）

| 関数 | 役割 |
|---|---|
| `_is_dataclass_decorator(decorator_node)` | `@dataclass` デコレータを検出 |
| `_extract_class_docstring(block_node)` | クラス先頭の docstring を抽出 |
| `_extract_class_fields(block_node)` | フィールド一覧を抽出（型・デフォルト・インラインコメント）|
| `extract_py_class(node)` | 公開インターフェース（PLUGIN に登録）|

**インラインコメントの判定**: `comment` ノードの `start_point[0]`（行番号）がフィールドの `expression_statement` と同一なら同行のインラインコメントとして付与する。別行の前置ブロックコメントは無視する。

#### ⑤ レンダリング（`src/renderer/markdown.py`）

```markdown
## 🏛️ クラス定義

### 🏛️ `LanguageProfile` (dataclass)

> docstring の内容...

| フィールド名 | 型 | デフォルト値 | 説明 |
|---|---|---|---|
| `name` | `str` | — | 例: "typescript", "python", "go" |
| `port` | `int` | `8080` | — |
```

### テスト追加

| テストクラス | 件数 | 内容 |
|---|---|---|
| `TestPyClassDefinition` (test_mapper.py) | 14件 | クラス・フィールド抽出の単体テスト |
| `TestRenderClassDefinitions` (test_renderer.py) | 14件 | Markdown レンダリングの単体テスト |
| `TestPyClassE2E` (test_pipeline.py) | 6件 | E2E テスト |

**319件 全グリーン**（実行時間 0.33s）

---

## Phase R4 — 完了 ✅（クラスメソッド抽出対応）

**完了日**: 2026-05-25  
**目的**: クラス定義セクションの中身が空になっていた問題を解決し、クラス内のメソッド一覧を仕様書に表示する。

### 問題（R4 前）

- クラス定義セクションにクラス名しか表示されず中身が空だった（特にメソッドのみのクラス）
- フィールドがないクラスで「*（フィールド定義が検出されませんでした）*」という誤解を招くメッセージが出ていた

### 実装内容

#### ① `src/ir/types.py` — `ClassSpec` に `methods` フィールド追加

```python
@dataclass(frozen=True)
class ClassSpec:
    ...
    fields:  tuple[ClassFieldSpec, ...] = ()
    methods: tuple[FunctionSpec, ...] = ()  # ← R4 追加
```

`from __future__ import annotations` により、`FunctionSpec` は文字列アノテーションとして前方参照が可能。

#### ② `src/ir/mapper.py` — クラスボディからメソッドを抽出する関数を追加

| 関数 | 役割 |
|---|---|
| `_get_class_body_node(class_ast_node)` | `decorated_definition` / `class_definition` の両方から body ブロックを返す |
| `_extract_class_methods(class_ast_node, profile, direct_stmt_map)` | body 内の `function_definition` ノードを `FunctionSpec` に変換して返す |

`_extract_all_class_definitions()` が `direct_stmt_map` を受け取るように更新し、抽出したメソッドを `dataclasses.replace()` で `ClassSpec` に付与する。

#### ③ `src/renderer/markdown.py` — クラス内メソッド一覧の描画

```markdown
### 🏛️ `TestModuleSpec` (class)

**メソッド:**

* `test_module_name_is_preserved`
* `test_empty_typescript_function_has_no_body_nodes`
* `do_something` — データを処理する。   ← docstring がある場合は inline 表示
```

- `fields` あり → フィールドテーブルを表示
- `methods` あり → `**メソッド:**` 見出し + 箇条書き
- どちらもなし → 何も表示しない（プレースホルダーメッセージ廃止）

### テスト追加

| テストクラス | 件数 | 内容 |
|---|---|---|
| `TestPyClassDefinition` に追加 (test_mapper.py) | 3件 | メソッド抽出・docstring 付きメソッド・フィールドとメソッド共存 |
| `TestRenderClassDefinitions` に追加 (test_renderer.py) | 4件 | メソッド一覧描画・説明付き・フィールドと共存・空メソッドの非表示 |

**328件 全グリーン**（実行時間 0.30s）

---

## Phase 5B + R5 — 完了 ✅（Java 対応 + レンダラー強化）

**完了日**: 2026-05-27  
**目的**: Java (.java) ファイルを解析できるようにし、クラスメソッドの処理フローを Markdown に出力する。

### 実装内容

| 新規/変更ファイル | 内容 |
|---|---|
| `src/parser/java_parser.py` ✨新規 | `parse_java_source()` — tree-sitter-java を遅延インポート |
| `src/languages/java.py` ✨新規 | `JAVA_PROFILE` + 全抽出関数 + `PLUGIN` 定数 |
| `src/renderer/markdown.py` 変更 | クラスメソッドに処理フロー（body）がある場合の詳細レンダリングを追加 |
| `requirements.txt` 変更 | `tree-sitter-java>=0.21.0` 追加 |
| `examples/sample.java` ✨新規 | Java サンプルコード（他言語版と同一ロジック） |
| テスト追加 | `TestJavaClassDefinition` / `TestJavaImports` / `TestJavaGuardClause` / `TestJavaForEachLoop` / `TestJavaDataTransformation` / `TestJavaConditionBlock` (mapper: 38件) + `TestJavaE2E` (pipeline: 22件) |

### Java 固有の AST 特性

| 特性 | 詳細 |
|---|---|
| トップレベル関数なし | すべてのメソッドは `class_declaration` 内の `method_declaration` |
| for-each | `enhanced_for_statement` — フィールドが `left`/`right` でなく `name`/`value` |
| 条件式の括弧 | `condition_has_outer_parens=True` — `parenthesized_expression` を unwrap |
| 代入 | `assignment_expression` が `=` と `+=` 等の両方を兼ねる（operator フィールドで区別）|
| JavaDoc | `prev_named_sibling` が `block_comment` → `/** ... */` から説明文を抽出 |
| ワイルドカード import | `import java.util.*;` → named child に `asterisk` ノードが来る（`.*` でなく）|
| else if | Go と同じ `nested` スタイル（`alternative = if_statement`）|

### レンダラー強化（R5）

`render_module_spec()` にクラスメソッド詳細セクションを追加:
- `method.body` が空でないメソッドのみ対象
- `dataclasses.replace(method, name=f"{class_name}.{method.name}")` で修飾名を生成
- 既存の `_render_function_spec()` を再利用（コード重複ゼロ）
- 出力例: `## 🔧 関数: UserBenefitService.getUserBenefit`

既存の `test_class_methods_rendered_as_list` は `body=()` のため影響なし。

### テスト結果

**411件 全グリーン**（実行時間 0.42s）

| テストファイル | 件数 |
|---|---|
| `tests/test_mapper.py` | 186件 |
| `tests/test_renderer.py` | 101件 |
| `tests/test_pipeline.py` | 85件 |
| `tests/test_batch.py` | 39件 |

---

## Phase R6 — 完了 ✅（条件分岐ボディのネスト IR 解析）

**完了日**: 2026-05-27  
**目的**: `if / else if / else` の各ケース内の処理を、生テキストではなく Universal IR として再帰的に抽出する。

### 実装内容

| 変更ファイル | 内容 |
|---|---|
| `src/ir/types.py` | `CaseNode.action_texts` を `body: tuple[IRNode, ...]` に変更 |
| `src/ir/mapper.py` | 条件分岐ケースの本体を `_extract_body_ir_nodes()` で再帰解析 |
| `src/renderer/markdown.py` | ケース内の `ReturnNode` / `DataTransformation` / `SideEffect` / `LoopNode` 等を通常IRとして描画 |
| `tests/test_mapper.py` | ケース内 return / データ変換 / 副作用のIR化テストを追加 |

### 効果

以前は条件分岐ケース内の処理が `return ...` などの生コード表示だったが、現在は以下のように構造化される:

```markdown
* **ケース 1: totalAmount >= PREMIUM_THRESHOLD**
  * ↩️ 返却する: `{ points: MAX_POINTS, message: "プレミアム特典付与" }`
```

これにより、条件分岐内部の代入・副作用・返却も、ループ本体と同じIR表現で監査できるようになった。

### テスト結果

**411件 全グリーン**（実行時間 0.42s）

---

## Phase R7 — 完了 ✅（例外処理のネスト IR 解析）

**完了日**: 2026-05-27  
**目的**: `try / catch / finally` と `try / except / finally` の各ブロック内の処理を、
生テキストではなく Universal IR として再帰的に抽出する。

### 実装内容

| 変更ファイル | 内容 |
|---|---|
| `src/ir/types.py` | `TryCatchNode` を追加し、`IRNode` ユニオンを拡張 |
| `src/ir/mapper.py` | `try_statement` から `try_body` / `catch_body` / `finally_body` を抽出 |
| `src/renderer/markdown.py` | 例外処理セクションを追加し、各ブロックのIRを描画 |
| `tests/test_mapper.py` | TS / Python / Java / PowerShell の try/catch/finally IR化テストを追加 |
| `tests/test_renderer.py` | TryCatchNode の Markdown 出力テストを追加 |

### テスト結果

**422件 全グリーン**（実行時間 0.42s）

| テストファイル | 件数 |
|---|---|
| `tests/test_mapper.py` | 193件 |
| `tests/test_renderer.py` | 105件 |
| `tests/test_pipeline.py` | 85件 |
| `tests/test_batch.py` | 39件 |

※ R8 完了後は **440件**（test_mapper.py が 211件に増加）。

---

## Phase R8 — 完了 ✅（Python 誤警告バグ修正）

**完了日**: 2026-05-28  
**目的**: Python ファイルのコンパイル時に `extraction_warnings` に不要な警告が出るバグを修正する。

### 問題（R8 前）

| 不具合 | 原因 |
|---|---|
| 関数の docstring が「未対応構文」として警告に出る | function body の先頭 `string-only expression_statement` を IR 変換しようとしていた |
| `pass` が「未対応構文」として警告に出る | `pass_statement` を no-op として扱っていなかった |
| `...`（ellipsis）が「未対応構文」として警告に出る | `expression_statement → ellipsis` を no-op として扱っていなかった |

### 実装内容

| 変更ファイル | 内容 |
|---|---|
| `src/ir/profiles.py` | `LanguageProfile` に `function_docstring_in_body: bool = False` フィールドを追加 |
| `src/languages/python.py` | `PYTHON_PROFILE` に `function_docstring_in_body=True` を設定 |
| `src/ir/mapper.py` | `_is_docstring_statement()` / `_is_no_op_statement()` を追加。body 先頭 docstring と `pass` / `...` を silent skip。トップレベル未対応宣言の警告化ロジック `_collect_top_level_extraction_warnings()` を追加 |
| `tests/test_mapper.py` | 誤警告が出ないことを確認するテストを +18件追加 |

### テスト結果

**440件 全グリーン**（実行時間 0.53s）

| テストファイル | 件数 |
|---|---|
| `tests/test_mapper.py` | 211件 |
| `tests/test_renderer.py` | 105件 |
| `tests/test_pipeline.py` | 85件 |
| `tests/test_batch.py` | 39件 |

---

## 未来のフェーズ（参考）

| フェーズ | 内容 |
|---|---|
| Phase 5C | C# 対応（Java と構造が近い）|
| Phase 6 | Git フック連携（コミット時に自動再生成） |

---

## 既知の制限事項

1. **アロー関数は未対応**: `const fn = () => {}` 形式の関数は検出しない（TypeScript のみ）
2. **Python クラスメソッドの本体は展開しない**: Python のクラスメソッドは名前一覧のみ表示（Java / クラスベース言語ではメソッド処理フローを詳細出力）
3. **ネストした関数は未対応**: 内部関数宣言は無視される
4. **型情報なし**: 変数の型（`User`, `number` 等）は仕様書に含まれない
5. **変数名依存**: 意味不明な変数名（`x`, `tmp`）の場合、出力も意味不明になる
6. **Go の for ループ関数は mapper.py に残存**: for-range / for-clause 関数は `_extract_body_ir_nodes` に依存するため循環インポート回避のため `mapper.py` に保持している
7. **Python クラスのフィールド説明はインラインコメントのみ取得**: `name: str  # 説明` の形式のみ対応。フィールド前の複数行ブロックコメントは仕様上無視する（次フィールドの前置コメントと区別できないため）
8. **TypeScript / Go のクラス定義は未対応**: TypeScript `class` / Go の `struct` は将来フェーズで対応予定

---

## 環境情報

| 項目 | バージョン |
|---|---|
| Python | 3.14.3 |
| pytest | 9.0.3 |
| tree-sitter | 0.25.2 |
| tree-sitter-typescript | 0.23.2 |
| tree-sitter-python | 0.25.0 |
| tree-sitter-go | 0.25.0 |
| OS | Windows 11 Pro |
