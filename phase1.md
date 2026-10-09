# Phase 1 (M1) — Ingestion + AST chunking + metadata

## Goal
`codedoc index <local-path>` walks a repo, parses each `.py` with tree-sitter,
emits AST-aligned `CodeChunk`s with rich metadata, and prints a summary.
No embeddings, no persistence, no GitHub (M4).

Locked from Phase 0: package `codedoc`, Python-only v1, deps via core (tree-sitter
is light; `ml` stay heavy). Decisions confirmed: core deps · pathspec
gitignore-aware · wire `index` CLI · module+class+method+function chunks.

## 0. Dependency & version compatibility [R10]
Add to `[project].dependencies`: `tree-sitter>=0.23.4`, `tree-sitter-python>=0.23.4`,
`pathspec>=0.12`.

Research: the grammar wheel (`tree-sitter-python`) and core (`tree-sitter`) are
versioned independently; a 0.23 grammar works against 0.25 core because the
`language()` capsule + `Language(...)` API is stable, but `Parser`/`Query` APIs
shifted across 0.22→0.25 (e.g. `Query.matches` moved to `QueryCursor` in 0.25,
`Language.query()` deprecated in favor of `Query(language, source)`). Target the
**0.23+ stable surface** and isolate every call behind `parser.py` so future
bumps are one-file changes. Verify at runtime via `Language.abi_version` rather
than assuming compatibility.

## 1. `codedoc/ingestion/__init__.py`
Public exports: `ingest`, `resolve_source`, `iter_files`, `chunk_file`, models.
Keep import-light — do **not** import tree-sitter at package import time (lazy
inside `parser.py`) so `codedoc --help` stays fast.

## 2. `codedoc/ingestion/models.py` — metadata schema

```python
@dataclass(frozen=True)
class Repo:
    root: Path
    name: str

@dataclass(frozen=True)
class CodeFile:
    rel_path: str
    abs_path: Path
    language: str
    source: bytes
    has_syntax_error: bool = False      # [R8]

@dataclass(frozen=True)
class CodeChunk:
    rel_path: str
    language: str
    symbol: str            # qualified: "UserService.get_user", "helper", None for module
    kind: str              # module | class | method | function
    start_line: int        # 1-based
    end_line: int          # 1-based, inclusive
    text: str              # raw source slice, verbatim
    signature: str | None  # first line / def line  [R5]
    docstring: str | None
    imports: list[str]     # module-level imports
    scope: list[str]       # ["UserService"] scope chain  [R5]

    @property
    def chunk_id(self) -> str:  # "{path}:{start}:{end}:{kind}:{symbol}"  [R14]
```

Aligned with production `CodeChunk` schemas (ironclad, rag-code-mcp): symbol,
location, signature, docstring, imports, plus scope chain and stable id.
Content hash / token_count deferred to M5/M2.

## 3. `codedoc/ingestion/source.py`
`resolve_source(source: str) -> Repo`:
- local dir → `Repo(root=resolved, name=root.name)`
- non-existent / not-a-dir → `ValueError` (CLI converts to exit 1)
- `http(s)://` or `git@` → `NotImplementedError("GitHub source deferred to M4")`
- no git dependency needed for local (avoids heavy `gitpython` at M1).

## 4. `codedoc/ingestion/walker.py`

`iter_files(repo: Repo) -> Iterator[CodeFile]`:
- recurse; always-skip dir names: `.git,__pycache__,.venv,venv,node_modules,.codedoc`
  plus dotdirs.
- language map `{".py": "python"}`; ignore everything else.
- skip files > 1 MiB (guard).
- read bytes; `rel_path` = POSIX relative to repo root.
- gitignore: `pathspec.GitIgnoreSpec.from_lines(...)`; match with `negate=True`
  semantics (spec positively matches ignore patterns) [R7].
- syntax errors detected in parser; `has_syntax_error` set on `CodeFile`.

**[R7] caveat:** a single root `GitIgnoreSpec` only handles the top-level
`.gitignore`. Real git honors **nested** `.gitignore` per directory,
`.git/info/exclude`, negation re-includes (`!`), and the rule that a file can be
re-included from an excluded *file* but not from an excluded *directory*.
Options:
(a) `pathspec.util.iter_tree_files` + merged per-dir specs;
(b) shell out to `git ls-files` when `.git` exists, fall back to manual walk;
(c) accept root-only for M1 and document the gap.
Recommend (a) or (b), not a silent root-only.

## 5. `codedoc/ingestion/parser.py`

```python
import tree_sitter_python as tspython
from tree_sitter import Language, Parser

PY = Language(tspython.language())
_parser = Parser(PY)               # cached module singleton

def parse(source: bytes): return _parser.parse(source)

DOCSTRING_QUERY = """..."""        # see §6
IMPORT_NODES = {"import_statement", "import_from_statement"}
```

Stable API targets: `Language(...)`, `Parser(...)`, `node.child_by_field_name`,
`named_children`, `start_byte/end_byte/start_point/end_point`, `Query` +
`QueryCursor`. `Node.text` returns **bytes** → slice original
`source[start:end]` and decode to stay lossless.

## 6. `codedoc/ingestion/chunker.py` — the core

Recursive descent, **not** a flat query — needed to build scope chains [R11]:

```
chunk_file(cf):
  tree = parse(cf.source)
  root = tree.root_node                    # type == "module"
  imports = collect all top-level import_statement/import_from_statement text
  chunks = []
  walk_scope(root, scope=[], in_class=False)
  # module header chunk:
  emit kind="module" for leading docstring + top-level imports (+ module-level
       statements), symbol=None, scope=[]
```

`walk_scope` dispatch on `child.type`:
- `decorated_definition` → unwrap `child_by_field_name("definition")` **before**
  dispatching [R1]. Include decorator lines in `start_line`/`text` (start from
  `decorated_definition.start_byte`).
- `function_definition` → kind = `method` if inside a class else `function`;
  **async functions use the same node type** (the `async` token is a child) [R2];
  symbol = `".".join(scope+[name])`; docstring = first body statement.
- `class_definition` → kind=`class`, qualified symbol; recurse into `body` with
  `scope+[name]`; **methods become their own chunks** with scope chain
  `["UserService"]`.
- nested `function_definition` inside a function: **folded into the parent's
  text** (documented; [R6] open).

Docstring extraction query (anchored to first body statement) [R3-doc]:
```scheme
(module . (comment)* . (expression_statement (string) @doc))
(class_definition  body: (block . (expression_statement (string) @doc)))
(function_definition body: (block . (expression_statement (string) @doc)))
```
Strip `"""`/`'''`/`r"..."` prefixes; empty string != docstring.

Text slices: `source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")`.
Line numbers: `node.start_point[0] + 1`.

Syntax errors [R8]: if `root.has_error`, still chunk what parses (tree-sitter is
error-tolerant) but mark `CodeFile.has_syntax_error`; never crash. (If strictness
preferred, skip the file and log — decision below.)

Oversized chunks [R3][R4]: M1 does **not** split. `chunk_max_lines` only flags
`oversized` in the summary. The cAST paper argues the budget should be
**non-whitespace characters**, not lines, and oversized nodes should be
recursively split then siblings greedily merged. Deferring is fine for M1, but
the *metric choice* decides the config field added now.

## 7. `codedoc/ingestion/pipeline.py`
`ingest(source: str) -> IngestResult` where `IngestResult(repo, files, chunks)`;
iterate files → parse → chunk. Returns counts by kind for the CLI (no storage).

## 8. `codedoc/cli.py`
Wire `index(source)`: call `ingest`, render a `rich` table (files, chunks,
chunks-by-kind, ignored/skipped counts, syntax-error count). Errors →
`typer.secho(..., err=True); raise typer.Exit(1)`. `--version` unchanged.

## 9. Fixtures & tests

```
tests/fixtures/sample_repo/
  .gitignore                 # ignored.py, build/
  ignored.py
  build/artifact.py          # ignored via dir
  pkg/__init__.py            # module docstring, imports, __all__
  pkg/core.py                # docstring, imports, @decorator fn, async fn,
                             # class UserService(__init__/method/staticmethod),
                             # nested class, nested fn, __main__ guard
  pkg/nested/.gitignore      # + nested/pickme.py, nested/skipme.py  [R7]
  README.md, notes.txt       # non-python
  pkg/bad_syntax.py          # parse-error file  [R8]
```
Tests:
- `test_source.py`: local ok; missing raises; url stub raises.
- `test_walker.py`: finds `pkg/*.py`; skips `ignored.py`, `build/`, `.md`,
  `.txt`; nested-gitignore behavior per chosen strategy.
- `test_chunker.py`: kinds/symbols/scope/line-ranges/imports/docstrings for a
  source string; decorated+async functions; module chunk; syntax-error file
  doesn't raise.
- `test_cli.py`: `index <fixture>` exits 0 and prints counts; `index /nope`
  exits 1.

## 10. Verification
- `pip install -e ".[dev]"`
- `pytest` → green
- `ruff check .` → clean
- `codedoc index tests/fixtures/sample_repo` → summary
- `codedoc index /nope` → exit 1

## Exit criteria
Local repo ingests without crashing, chunks are AST-aligned with correct kinds,
symbols, line ranges and metadata, tests pass, ruff clean.

---

## Areas that can be improved with research [R]

| # | Area | Finding | Proposed action |
|---|------|---------|-----------------|
| R1 | **Decorators** | Accessing only `function_definition` misses any decorated function/class (tree-sitter wraps them in `decorated_definition`). | Must unwrap `child_by_field_name("definition")`; include decorator lines in chunk. Correctness, not optional. |
| R2 | **async** | `async def` is still `function_definition`; `async` is a child token. | Handle automatically; add fixture test. |
| R3 | **Size metric** | cAST (EMNLP 2025) shows non-whitespace **chars** beat lines as a budget; equal line counts carry very different code density. | Decide now: keep `chunk_max_lines` or add `chunk_max_chars`. Research says chars; changing config shape is a Phase-0 touch. |
| R4 | **Split-then-merge** | cAST recursively splits oversized AST nodes then greedily merges small siblings; concatenation == original. | Defer to M5, but store `oversized` flag now so the splitter has a target list. |
| R5 | **Contextual enrichment** | Prepending `# file: …` `# scope: …` `# symbol: …` before embedding materially improves retrieval ("syntactically whole but semantically homeless"). | Store `scope`/`signature`/`imports` now; build `embed_text` at M2 rather than duplicating text in M1. |
| R6 | **Nested defs** | Nested functions/classes can be separate chunks with scope chains, or folded. | Default folded for M1 (fewer, denser chunks); revisit with eval. |
| R7 | **Gitignore fidelity** | `GitIgnoreSpec` on one file != git: nested `.gitignore`, `!` re-includes, `.git/info/exclude`, dir-exclusion semantics. | Choose strategy (pathspec multi-spec vs `git ls-files` vs accept gap). |
| R8 | **Syntax errors** | tree-sitter is error-tolerant; `root.has_error` detects partial parses. | Don't crash; mark and continue. Decide skip-vs-best-effort. |
| R9 | **Module-level code** | Assignments/constants/`if __name__` guards aren't functions/classes; naive handling drops them or makes a giant module chunk. | Consider a `module`/`code` chunk for non-def module statements. |
| R10 | **Version/ABI** | Core and grammar versions move independently; API moved between 0.23–0.25. | Pin `>=0.23.4`, isolate all calls in `parser.py`, assert `abi_version` in a test. |
| R11 | **Query vs traversal** | Queries are clean for docstrings/imports but don't carry scope; ckg-lang uses recursive traversal for qualified names. | Traversal for structure + query for docstrings; hybrid. |
| R12 | **Encoding** | Non-UTF-8 files and PEP 263 `# -*- coding: -*-` declarations exist. | Read bytes, decode `utf-8` with `errors="replace"` (or honor coding cookie later). |
| R13 | **Perf/DoS guards** | Pathological files + `QueryCursor` can blow match limits/timeouts (0.25 moved limits to `QueryCursor`). | Add size guard now; consider `QueryCursor.match_limit`. |
| R14 | **Symbol identity** | Overloads, properties, `__init__`, nested/qualname collisions affect chunk IDs and dedup. | Use qualified names + `{path}:{start}:{end}` id; dedup at M2. |
| R15 | **Chunk dedup/overlap** | Large classes produce a class chunk whose body duplicates every method chunk. | Decide: class chunk = header+signatures only vs full body (see R9/decision). |

## Open decisions before execution

1. **cAST scope** — implement split-then-merge now (R4) or defer to M5
   (recommended: defer, flag oversized)?
2. **Size metric** — keep `chunk_max_lines`, or add `chunk_max_chars`
   (R3, cAST-recommended)?
3. **Gitignore** — root `.gitignore` only, or full fidelity via `git ls-files`/
   multi-spec (R7, recommended: `git ls-files` when repo has `.git`)?
4. **Syntax errors** — best-effort chunk (recommended) or skip file?
5. **Class chunk** — full body (duplicates methods) or header+method signatures
   only (recommended, matches AgenticSkillset guidance)?
6. **Enrichment** — store metadata only now and build `embed_text` at M2
   (recommended), or add `contextualized_text` in M1 (R5)?

## Out of scope (later phases)
`indexing/`, `retrieval/`, `generation/`, `session.py`, GitHub clone (M4),
incremental indexing (M5), multi-turn chat (M6).
