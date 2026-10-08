import typer

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
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
