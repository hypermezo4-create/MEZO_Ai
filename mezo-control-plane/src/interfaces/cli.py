import click

@click.group()
def cli():
    """MEZO Control Plane CLI Interface"""
    pass

@cli.command()
def status():
    click.echo("MEZO Control Plane is running active.")

if __name__ == "__main__":
    cli()
