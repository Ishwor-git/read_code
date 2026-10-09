from codedoc.config import Settings


def test_defaults(monkeypatch):
    for key in ("CHUNK_MAX_LINES", "LLM_MODEL", "EMBEDDING_MODEL", "INDEX_DIR"):
        monkeypatch.delenv(key, raising=False)
    settings = Settings(_env_file=None)
    assert settings.embedding_model == "BAAI/bge-small-en-v1.5"
    assert settings.index_dir == ".codedoc"
    assert settings.chunk_max_lines == 80


def test_env_override(tmp_path):
    env = tmp_path / ".env"
    env.write_text("CHUNK_MAX_LINES=42\nLLM_MODEL=test-model\n")
    settings = Settings(_env_file=env)
    assert settings.chunk_max_lines == 42
    assert settings.llm_model == "test-model"
