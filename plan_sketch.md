# Plan: RAG Code Documentation Engine (Python)

## 1. Goal
CLI tool that ingests a codebase (GitHub URL or local path), builds a searchable RAG index, and answers natural-language documentation questions with grounded, cited answers (`path:line`).

> Locked: project/package name = `codedoc`; v1 language support = Python only
> (non-Python files skipped; line-window fallback deferred). See `phase0.md`.

## 2. Architecture (5 layers)

**Ingestion** → **Index** → **Retrieval** → **Generation** → **CLI**

```
Source resolver → File walker → Tree-sitter parser → AST chunker
      → Embeddings + BM25 → Chroma store
      → Hybrid retrieval (+rerank) → Prompt assembly → LLM → cited answer
```

## 3. Proposed project layout
```
read_code/
  pyproject.toml
  README.md
  .env.example
  codedoc/
    cli.py                 # typer commands
    config.py              # pydantic settings (.env / codedoc.toml)
    ingestion/
      source.py            # local path + github clone
      walker.py            # gitignore-aware, language detection
      parser.py            # tree-sitter AST per language
      chunker.py           # AST-aware chunks + line-window fallback
      models.py            # CodeChunk, CodeFile, Repo dataclasses
    indexing/
      embeddings.py        # EmbeddingProvider interface (local default)
      store.py             # Chroma wrapper (collection per repo)
      bm25.py              # keyword index
      pipeline.py          # orchestration + incremental manifest
    retrieval/
      retriever.py         # vector + BM25 + reciprocal rank fusion
      rerank.py            # optional local cross-encoder
      context.py           # token budget, dedupe, file-tree summary
    generation/
      llm.py               # LLMProvider interface (OpenAI-compatible default)
      prompts.py           # grounded Q&A / explain / locate templates
      answer.py            # citation extraction, "I don't know" guard
    session.py             # multi-turn chat state
  tests/
```

## 4. Key design decisions
- **Chunking**: AST-aware (functions, classes, methods, module headers) via tree-sitter; metadata = path, language, symbol, kind, line range, imports, docstring. v1 is Python-only via `tree-sitter-python`; non-Python files are skipped (line-window fallback deferred). This beats naive line splitting for code quality.
- **Retrieval**: Hybrid — vector top-k + BM25 top-k merged with Reciprocal Rank Fusion, then optional local cross-encoder rerank. Strongly recommended for code (identifiers/names matter).
- **Embeddings**: local `sentence-transformers` (start with `BAAI/bge-small-en-v1.5`, optionally `jina-embeddings-v2-base-code`).
- **Vector store**: Chroma persistent, one collection per repo (keyed by resolved path/URL hash) for isolation.
- **Incremental**: file-hash manifest; re-embed only changed/deleted files.
- **LLM**: pluggable provider; default OpenAI-compatible base URL, model set via config. Prompt forces grounding + citations + refusal when context is insufficient.
- **Citations**: every answer returns `file:line` references; CLI renders with `rich`.

## 5. CLI surface
```
codedoc index <path|github-url> [--lang ...] [--rebuild]
codedoc ask "question" [--repo ...] [--top-k N]
codedoc chat
codedoc status
codedoc clear
```

## 6. Dependencies
`typer`, `rich`, `pydantic-settings`, `chromadb`, `sentence-transformers`, `tree-sitter` + `tree-sitter-python` (Python only for v1), `rank-bm25`, `tiktoken`, `openai`, `gitpython`, `pytest`.

## 7. Milestones
- **M0** Scaffolding: pyproject, config, CLI skeleton, logging.
- **M1** Ingestion for local paths + AST chunker + metadata.
- **M2** Embeddings + Chroma index + `status`/`clear`.
- **M3** Vector retrieval + LLM answer + citations (MVP end-to-end).
- **M4** GitHub URL clone source.
- **M5** Hybrid retrieval + rerank + incremental indexing.
- **M6** Multi-turn `chat`, query modes (locate/explain/generate docs), eval harness.
- **M7** Polish, README, packaging.

## 8. Testing
Unit tests for walker/chunker/retriever; a small golden Q&A eval set run against a fixture repo (ragas-style or hand-rolled).

## Open decisions before execution
1. ~~**Initial language support**~~ **RESOLVED**: Python only for v1 (`tree-sitter-python`); non-Python files skipped.
2. **Hybrid + rerank in M1 or defer to M5?** Recommend building vector-only MVP first (M3), then adding hybrid.
3. ~~**Project name**~~ **RESOLVED**: `codedoc`.
4. **Private repo auth** — needed now (token support) or public repos only for v1?
