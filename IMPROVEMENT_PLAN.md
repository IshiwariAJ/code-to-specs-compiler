# 自然言語コンパイラ 改善計画

**目標**: コードを完全に再現できるレベルの自然言語出力を実現する  
**作成日**: 2026-05-26  
**最終更新**: 2026-05-26（Step 1 / Step 2 実装完了）

---

## 現状の出力範囲

現在キャプチャできている要素：

| カテゴリ | 対応済み要素 |
|---|---|
| モジュールレベル | インポート文、モジュール変数/定数、TypeScript型定義、Pythonクラス定義(@dataclass) |
| 関数 | 関数名、JSDoc/docstring、**引数リスト（名前・型・デフォルト値）**、**戻り値の型** |
| 制御フロー | ガード句(if→throw/return/raise)、条件分岐(if/elif/else)、ループ(for...of / for range / Python for / Go range)、**return / throw / raise 文** |
| データ操作 | 代入・演算更新(+=, -=, = など)、副作用(関数呼び出し) |

---

## 欠落している要素と対応計画

### 🔴 優先度 HIGH — これがないと関数すら完全に再現できない

#### ~~① 関数の引数・戻り値の型~~ ✅ 実装済み（2026-05-26）

**変更ファイル**: `src/ir/types.py`, `src/languages/__init__.py`, `src/ir/mapper.py`,  
`src/languages/typescript.py`, `src/languages/python.py`, `src/languages/go.py`, `src/renderer/markdown.py`

**実装内容**:
- `ParamSpec` dataclass を追加（name / type_text / default_text / is_rest）
- `FunctionSpec` に `params: tuple[ParamSpec, ...]` と `return_type: str` を追加
- `LanguagePlugin` に `param_extractor` / `return_type_extractor` を追加
- TypeScript / Python / Go の3言語すべてで引数・戻り値を抽出

**実際の出力**:
```markdown
## 🔧 関数: `calculateUserBenefit`

**引数:**
| 引数名 | 型 | デフォルト値 |
|---|---|---|
| `user` | `User` | — |

**戻り値の型:** `BenefitResult`
```

---

#### ~~② return 文（ガード句以外）~~ ✅ 実装済み（2026-05-26）

**変更ファイル**: `src/ir/types.py`, `src/ir/mapper.py`, `src/renderer/markdown.py`

**実装内容**:
- `ReturnNode` dataclass を追加（value_text / action: "return" | "throw" | "raise" / comment）
- `_map_statement_to_ir` に `return_statement` / `throw_statement` / `raise_statement` のハンドリングを追加
- ループ本体内のネスト `return` にも対応

**実際の出力**:
```markdown
### 4. ↩️ 返却
* ↩️ 返却する: `total`
```

---

#### ③ try / catch / finally

**問題**: 例外処理が IR に存在しないため、エラーハンドリングが出力から完全に消える。

**対象コード例**:
```typescript
try {
    const result = await fetch(url);
} catch (error) {
    logger.error(error);
    throw error;
} finally {
    cleanup();
}
```

**追加する IR**:
```python
@dataclass(frozen=True)
class TryCatchNode:
    kind: Literal["TryCatchNode"]
    try_body: tuple[IRNode, ...]
    catch_var: str = ""           # catch (error) の変数名
    catch_body: tuple[IRNode, ...] = ()
    finally_body: tuple[IRNode, ...] = ()
    comment: str = ""
```

**期待する出力例**:
```markdown
### N. 🛡️ 例外処理
* **try ブロック:**
  * 🔔 副作用: `fetch(url)` の結果を `result` に代入する
* **catch ブロック (`error`):**
  * 🔔 副作用: `logger.error(error)`
  * ➔ 例外を再スロー: `error`
* **finally ブロック:**
  * 🔔 副作用: `cleanup()`
```

---

#### ④ while / do-while ループ

**問題**: `LoopNode` は `FOR_EACH` と `FOR_RANGE` のみ対応。while ループが出力されない。

**対象コード例**:
```typescript
while (queue.length > 0) {
    process(queue.shift());
}
```
```python
while retries < MAX_RETRIES:
    result = attempt()
```

**対応方法**: `LoopNode.loop_type` に `WHILE` を追加する。

```python
loop_type: Literal["FOR_EACH", "FOR_RANGE", "WHILE"]
# WHILE の場合、collection フィールドを条件式として流用する
```

**期待する出力例**:
```markdown
### N. 🔄 繰り返し処理（while）
* `queue.length > 0` の間、以下をループ実行:
  * 🔔 副作用: `process(queue.shift())`
```

---

### 🟠 優先度 MEDIUM — 実用上よく使われる構文

#### ⑤ アロー関数の検出

**問題**: TypeScript で `const fn = (x) => ...` 形式の関数が検出されない。  
現在は `function_declaration` のみを対象にしている。

**対象コード例**:
```typescript
const greet = (name: string): string => `Hello, ${name}`;

const processItems = async (items: Item[]): Promise<void> => {
    for (const item of items) {
        await save(item);
    }
};
```

**対応方法**: `src/languages/typescript.py` の関数抽出処理に  
`lexical_declaration` → `variable_declarator` → `arrow_function` のパスを追加する。

---

#### ⑥ クラスメソッドの検出

**問題**: TypeScript の `class` 内のメソッドが検出されない。  
Python の `class` 内のメソッドも同様。

**対象コード例**:
```typescript
class UserService {
    private repository: UserRepository;

    constructor(repository: UserRepository) {
        this.repository = repository;
    }

    async getUser(id: string): Promise<User> {
        return await this.repository.findById(id);
    }
}
```

**対応方法**:
1. `ClassSpec` にメソッド一覧 `methods: tuple[FunctionSpec, ...]` を追加する
2. 各言語プラグインの class 抽出処理でメソッドを `FunctionSpec` として抽出する

---

#### ⑦ 条件分岐ボディのネスト IR 解析

**問題**: 現在 `CaseNode.action_texts` は生テキスト（`tuple[str, ...]`）のまま。  
条件分岐の各ケース内に代入・ループ・副作用があっても、生コードとして出力される。

**対象コード例**:
```typescript
if (user.rank === "Gold") {
    totalPoints += 1000;        // これは DataTransformation として解析してほしい
    sendEmail(user.email);      // これは SideEffect として解析してほしい
    return { status: "premium" };  // これは ReturnNode として解析してほしい
}
```

**対応方法**: `CaseNode` の `action_texts` を `body: tuple[IRNode, ...]` に変更し、  
マッパーが条件分岐ボディを再帰的に解析するようにする。

> ⚠️ **注意**: この変更は `CaseNode` の型定義・マッパー・レンダラーの全層に影響する大きな変更。  
> テスト (`test_mapper.py`, `test_renderer.py`) の大幅な更新も必要。

---

#### ⑧ switch / match 文

**問題**: TypeScript の `switch` 文、Python の `match` 文が出力されない。

**対象コード例**:
```typescript
switch (status) {
    case "ACTIVE":   return handleActive(user);
    case "INACTIVE": return handleInactive(user);
    default:         throw new Error("Unknown status");
}
```
```python
match command:
    case "start": start_service()
    case "stop":  stop_service()
    case _:       raise ValueError(f"Unknown: {command}")
```

**対応方法**: `ConditionBlock` を再利用するか、新たに `SwitchNode` を追加する。

---

#### ⑨ 非同期処理（async / await）

**問題**: 関数が `async` かどうか、`await` がついている式かどうかが出力されない。

**対象コード例**:
```typescript
async function fetchUser(id: string): Promise<User> {
    const data = await api.get(`/users/${id}`);
    return data;
}
```

**対応方法**:
- `FunctionSpec` に `is_async: bool = False` を追加
- `SideEffect` や `DataTransformation` に `is_awaited: bool = False` を追加

---

### 🟡 優先度 LOW — あると完全性が上がる

#### ⑩ TypeScript クラス定義

**問題**: TypeScript の `class` 定義（フィールド・コンストラクタ・メソッド）が出力されない。

**対応方法**: Python の `ClassSpec` を TypeScript にも拡張する。  
`src/languages/typescript.py` に `extract_ts_class` 関数を追加する。

---

#### ⑪ Go の struct 定義

**問題**: Go の `type User struct { ... }` が出力されない。

**対応方法**: Python の `ClassSpec` / `ClassFieldSpec` を Go struct に流用する。  
`src/languages/go.py` に `extract_go_struct` 関数を追加する。

---

#### ⑫ break / continue 文

**問題**: ループ内の `break` / `continue` が出力されない。

**対応方法**: `IRNode` に `FlowControlNode` を追加する。

```python
@dataclass(frozen=True)
class FlowControlNode:
    kind: Literal["FlowControlNode"]
    action: Literal["break", "continue", "pass"]
    label: str = ""  # TypeScript のラベル付き break
```

---

#### ⑬ 分割代入

**問題**: `const { a, b } = obj` や `const [x, y] = arr` が DataTransformation として捕捉されない。

---

## 実装順序（推奨）

```
Step 1  ① 関数の引数・戻り値の型          ✅ 完了（2026-05-26）
Step 2  ② return 文（ReturnNode 追加）     ✅ 完了（2026-05-26）
Step 3  ③ try / catch / finally           ← TryCatchNode 追加（全言語対応）
Step 4  ④ while / do-while ループ         ← LoopNode に WHILE 種別追加
Step 5  ⑤ アロー関数の検出               ← TypeScript 限定の追加
Step 6  ⑥ クラスメソッドの検出           ← ClassSpec 拡張
Step 7  ⑦ 条件分岐ボディのネスト IR 解析  ← 大規模変更（最後のほうが安全）
Step 8  ⑧ switch / match 文
Step 9  ⑨ async / await マーカー
Step 10 ⑩ TypeScript class 定義
Step 11 ⑪ Go struct 定義
Step 12 ⑫ break / continue
Step 13 ⑬ 分割代入
```

---

## 各ステップの影響範囲

| Step | types.py | mapper.py | 言語プラグイン | renderer.py | テスト |
|---|---|---|---|---|---|
| ~~① 引数・戻り値~~ ✅ | ParamSpec 追加 / FunctionSpec 拡張 | _map_function_to_spec 拡張 | TS / Py / Go 全対応 | params テーブル・return_type 追加 | 既存319件グリーン維持 |
| ~~② return 文~~ ✅ | ReturnNode 追加 / IRNode 拡張 | return/throw/raise ハンドリング追加 | 変更なし（全言語共通） | _render_return_node 追加 | 既存319件グリーン維持 |
| ③ try/catch | TryCatchNode 追加 | 全言語 | TS / Py / Go | TryCatchNode レンダリング追加 | 追加 |
| ④ while | LoopNode 変更 | 全言語 | TS / Py / Go | LoopNode レンダリング更新 | 追加 |
| ⑤ アロー関数 | 変更なし | — | TS のみ | 変更なし | 追加 |
| ⑥ クラスメソッド | ClassSpec 拡張 | — | 全言語 | ClassSpec レンダリング更新 | 追加 |
| ⑦ 条件分岐ネスト | CaseNode 変更 | 全関数 | 全言語 | 大幅更新 | 大幅更新 |
| ⑧ switch/match | SwitchNode 追加 | 全言語 | TS / Py | 追加 | 追加 |
| ⑨ async/await | FunctionSpec 拡張 | 全言語 | TS / Py / Go | 更新 | 追加 |
