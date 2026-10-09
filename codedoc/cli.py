import typer

from codedoc import __version__

app = typer.Typer(no_args_is_help=True)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    pass


@app.command()
def index(source: str) -> None:
    typer.echo(f"TODO index {source}")


@app.command()
def ask(question: str) -> None:
    typer.echo(f"TODO ask {question!r}")


@app.command()
def chat() -> None:
    typer.echo("TODO chat")


@app.command()
def status() -> None:
    typer.echo("TODO status")


@app.command()
def clear() -> None:
    typer.echo("TODO clear")
