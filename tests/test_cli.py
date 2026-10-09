from typer.testing import CliRunner

from codedoc import __version__
from codedoc.cli import app

runner = CliRunner()


def test_help_lists_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("index", "ask", "chat", "status", "clear"):
        assert cmd in result.output


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output
