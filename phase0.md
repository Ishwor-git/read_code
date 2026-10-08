# Phase 0 — Scaffolding

## Goal
Installable `codedoc` CLI skeleton: config loads, all 5 commands exist as stubs,
tests green. No ingestion/indexing logic yet.

## Prerequisite: environment
- Python 3.14 has no torch/chromadb wheels -> use a dedicated env on 3.12.
  `conda create -n codedoc python=3.12 && conda activate codedoc`
- `requires-python = ">=3.11,<3.13"` in pyproject to match.

## Deliverables
1. pyproject.toml
   - build backend hatchling; package `codedoc`
   - console script: codedoc = "codedoc.cli:app"
   - deps: typer, rich, pydantic-settings
   - optional-dependencies:
       ml  = chromadb, sentence-transformers, tree-sitter, tree-sitter-python,
             rank-bm25, tiktoken, openai, gitpython
       dev = pytest, ruff
   - ruff + pytest config
2. codedoc/__init__.py        # __version__ = "0.0.1"
3. codedoc/config.py          # pydantic-settings Settings:
                              #   llm_base_url, llm_model, llm_api_key,
                              #   embedding_model=BAAI/bge-small-en-v1.5,
                              #   index_dir, chunk_max_lines
                              #   sources: .env, codedoc.toml
4. codedoc/cli.py             # typer app "codedoc"
                              #   index/ask/chat/status/clear -> stub output
5. .env.example               # documented config keys
6. .gitignore                 # .env, __pycache__/, .venv/, .codedoc/
7. tests/test_cli.py          # --help shows all commands; --version smoke
   tests/test_config.py       # defaults + .env override

## Out of scope (later phases)
ingestion/, indexing/, retrieval/, generation/, session.py

## Verification
- pip install -e ".[dev]"
- codedoc --help   -> index, ask, chat, status, clear
- codedoc status   -> stub, exit 0
- pytest          -> green
- ruff check .    -> clean

## Exit criteria
Repo installs cleanly in the 3.12 env, CLI runs, config parses, tests pass.
