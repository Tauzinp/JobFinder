import typer

from job_finder import run_pipeline

app = typer.Typer(help="JobFinder - agregateur d'offres de stage, theses et emplois.")


@app.callback(invoke_without_command=True)
def main(
    profil: str = typer.Option(
        "bioinformatique",
        "--profil",
        "-p",
        help="Profil de recherche defini dans parameters/profiles.yaml",
    ),
) -> None:
    """Lance le pipeline de recuperation puis affiche le nombre de nouvelles offres."""
    try:
        new_offers = run_pipeline(profil)
    except ValueError as error:
        raise typer.BadParameter(str(error))

    typer.echo(f"{len(new_offers)} nouvelle(s) offre(s) pour le profil '{profil}'.")


if __name__ == "__main__":
    app()
