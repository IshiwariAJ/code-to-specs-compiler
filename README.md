# code-to-specs-compiler

**AIを一切使わず、コンパイラ技術（AST解析）だけでソースコードを構造化日本語仕様書に変換するツール。**  
**A compiler-based tool that converts source code into structured Japanese specification documents — no AI, no hallucination, 100% deterministic.**

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/tests-236%20passing-brightgreen.svg)](#テスト--testing)

---

## 日本語

### 概要

`code-to-specs-compiler` は、**ソースコードを決定論的にMarkdown仕様書へ変換する**CLIツールです。  
LLMは使用しません。[tree-sitter](https://tree-sitter.github.io/tree-sitter/) によるAST解析と、言語共通のIR（中間表現）を組み合わせた3層パイプラインで動作します。

#### コア価値

| 特長 | 説明 |
|---|---|
| 🎯 **ハルシネーションなし** | AIを使わないため、コードに書いていないことが仕様書に現れない |
| 🔒 **完全ローカル実行** | 機密コード・社内コードも外部送信なしで安全に処理 |
| 🌐 **多言語・統一フォーマット** | TypeScript / Python の両方から同一Markdownフォーマットで出力 |
| ⚡ **高速・決定論的** | 同じ入力からは常に同じ出力（236テスト全グリーン） |

---

### 対応言語

| 言語 | 拡張子 | 対応状況 |
|---|---|---|
| TypeScript | `.ts`, `.tsx` | ✅ 対応済み |
| Python | `.py` | ✅ 対応済み |
| Go / Java | — | 🔜 将来対応予定 |

---

### インストール

```bash
git clone https://github.com/ToshikiIshiwari/code-to-specs-compiler.git
cd code-to-specs-compiler
pip install -r requirements.txt
```

**依存ライブラリ:**

| パッケージ | バージョン | 用途 |
|---|---|---|
| `tree-sitter` | ≥ 0.21.0 | AST パーサーエンジン |
| `tree-sitter-typescript` | ≥ 0.21.0 | TypeScript文法定義 |
| `tree-sitter-python` | ≥ 0.21.0 | Python文法定義 |

---

### 使い方

```bash
# 単一ファイル → 標準出力に表示
python main.py examples/sample.ts

# 単一ファイル → ファイルに保存
python main.py examples/sample.ts output.md

# プロジェクト全体を再帰コンパイル（<プロジェクト名>_specs/ に自動生成）
python main.py myproject/

# 出力先を指定
python main.py myproject/ docs/specs/
```

---

### 出力例

**入力: TypeScript**
```typescript
/**
 * ユーザーの特典ポイントを計算する
 */
function calculateUserBenefit(user: User): BenefitResult {
    if (user.status !== "ACTIVE") {
        throw new Error("エラー: 無効なユーザーです");
    }
    let totalAmount = 0;
    for (const history of user.purchaseHistory) {
        totalAmount += history.price;
    }
    // ランクに応じてポイントを付与
    if (totalAmount >= 100000 && user.rank === "Gold") {
        return { points: 1000, message: "プレミアム特典付与" };
    } else {
        return { points: 100, message: "通常特典付与" };
    }
}
```

**出力: Markdown仕様書**
```markdown
## 🔧 関数: `calculateUserBenefit`

> ユーザーの特典ポイントを計算する

### 📄 処理フロー

### 1. 📢 前提条件（ガード句）
* **条件:** `user.status !== "ACTIVE"` の場合
  * ➔ 例外 `new Error("エラー: 無効なユーザーです")` をスローして処理を中断する

### 2. 🔁 データ変換
* `totalAmount` に代入する: `0`

### 3. 🔄 繰り返し処理
* `user.purchaseHistory` の各要素（`history`）に対して以下をループ実行:
  * `totalAmount` に加算して更新する: `history.price`

### 4. 🔀 条件分岐
> ランクに応じてポイントを付与
* **ケース 1: totalAmount >= 100000 && user.rank === "Gold"**
  * ➔ `return { points: 1000, message: "プレミアム特典付与" };`
* **ケース 2: それ以外**
  * ➔ `return { points: 100, message: "通常特典付与" };`
```

---

### アーキテクチャ

```
[ソースコード (.ts / .py)]
        │
        ▼  src/parser/   【フロントエンド】
  tree-sitter で AST を生成
        │
        ▼  src/ir/mapper.py  【ミドルウェア】
  AST → Universal IR (frozen dataclass)
        │
        ▼  src/renderer/markdown.py  【バックエンド】
  Universal IR → Markdown 日本語仕様書
        │
        ▼
[Markdown 仕様書 (.md)]
```

- **フロントエンド**: 言語ごとの tree-sitter パーサー（`src/parser/`）
- **ミドルウェア**: `LanguageProfile` による言語差異の吸収と Universal IR へのマッピング（`src/ir/`）
- **バックエンド**: 言語非依存の Markdown レンダラー（`src/renderer/`）

新言語の追加は `_LANGUAGE_CONFIGS` 辞書と `LanguageProfile` の定数を1つ追加するだけです。

---

### 検出できる構造

| IR型 | 検出対象 |
|---|---|
| `GuardClause` | `if (...) { return / throw / raise }` — 早期中断パターン |
| `ConditionBlock` | `if / elif / else` チェーン全体 |
| `LoopNode` | `for...of`（FOR_EACH）/ 古典的`for`（FOR_RANGE）/ Python `for` |
| `DataTransformation` | `+=`, `-=`, `=` などの代入・演算更新 |
| `SideEffect` | 関数呼び出し（`console.log`, `arr.push` など） |
| `ImportSpec` | インポート文（`import`, `from...import`, `__future__`） |
| `ModuleVariableSpec` | モジュールレベルの定数・変数 |
| `TypeDefinitionSpec` | TypeScript の `type` エイリアス・`interface` |

コメント情報（JSDoc、docstring、インラインコメント）も抽出してブロッククォート形式で出力します。

---

### テスト / Testing

```bash
pip install pytest
pytest
```

| テストファイル | 件数 | 内容 |
|---|---|---|
| `tests/test_mapper.py` | 〜80件 | AST → IR マッピングのユニットテスト |
| `tests/test_renderer.py` | 〜60件 | IR → Markdown レンダリングのユニットテスト |
| `tests/test_pipeline.py` | 〜32件 | E2E 統合テスト |
| `tests/test_batch.py` | 〜37件 | バッチコンパイル機能のテスト |
| **合計** | **236件** | **全グリーン** |

---

### ライセンス / License

Apache License 2.0 — 詳細は [LICENSE](LICENSE) を参照してください。

Copyright 2026 Toshiki Ishiwari

---

## English

### Overview

`code-to-specs-compiler` is a CLI tool that **deterministically converts source code into structured Markdown specification documents**.  
It uses no LLMs — only compiler technology ([tree-sitter](https://tree-sitter.github.io/tree-sitter/) AST analysis) via a 3-layer pipeline.

#### Core Value

| Feature | Description |
|---|---|
| 🎯 **Zero hallucination** | No AI means the spec only contains what the code actually says |
| 🔒 **Fully local** | Confidential code never leaves your machine |
| 🌐 **Multi-language, unified format** | TypeScript and Python produce identical Markdown structure |
| ⚡ **Fast & deterministic** | Same input always produces the same output (236 tests passing) |

---

### Supported Languages

| Language | Extension | Status |
|---|---|---|
| TypeScript | `.ts`, `.tsx` | ✅ Supported |
| Python | `.py` | ✅ Supported |
| Go / Java | — | 🔜 Planned |

---

### Installation

```bash
git clone https://github.com/ToshikiIshiwari/code-to-specs-compiler.git
cd code-to-specs-compiler
pip install -r requirements.txt
```

---

### Usage

```bash
# Single file → print to stdout
python main.py examples/sample.ts

# Single file → save to file
python main.py examples/sample.ts output.md

# Compile entire project recursively (outputs to <project>_specs/)
python main.py myproject/

# Specify output directory
python main.py myproject/ docs/specs/
```

---

### Architecture

```
[Source Code (.ts / .py)]
        │
        ▼  src/parser/          [Frontend]
  tree-sitter AST generation
        │
        ▼  src/ir/mapper.py     [Middleware]
  AST → Universal IR (frozen dataclass)
        │
        ▼  src/renderer/markdown.py  [Backend]
  Universal IR → Markdown specification
        │
        ▼
[Markdown Spec (.md)]
```

Adding a new language requires only one `LanguageProfile` constant and one entry in `_LANGUAGE_CONFIGS`.

---

### Detectable Structures

| IR Type | Detects |
|---|---|
| `GuardClause` | Early-return / throw / raise patterns |
| `ConditionBlock` | `if / elif / else` chains |
| `LoopNode` | `for...of` (FOR_EACH), C-style `for` (FOR_RANGE), Python `for` |
| `DataTransformation` | `+=`, `-=`, `=` assignments |
| `SideEffect` | Function calls with side effects |
| `ImportSpec` | Import statements (including `__future__`) |
| `ModuleVariableSpec` | Module-level constants and variables |
| `TypeDefinitionSpec` | TypeScript `type` aliases and `interface` declarations |

Comments (JSDoc, docstrings, inline comments) are also extracted and rendered as blockquotes.

---

### Testing

```bash
pip install pytest
pytest
```

236 tests, all green.

---

### License

Apache License 2.0 — see [LICENSE](LICENSE) for details.

Copyright 2026 Toshiki Ishiwari
