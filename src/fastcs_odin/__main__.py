from pathlib import Path
from typing import Optional

import typer
from fastcs.connections.ip_connection import IPConnectionSettings
from fastcs.launch import FastCS
from fastcs.logging import LogLevel, configure_logging
from fastcs.transport.epics.ca.ioc import EpicsIOCOptions
from fastcs.transport.epics.ca.transport import EpicsCATransport, EpicsGUIOptions

from fastcs_odin.odin_controller import OdinController

from . import __version__

__all__ = ["main"]


app = typer.Typer()


def version_callback(value: bool):
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def main(
    # TODO: typer does not support `bool | None` yet
    # https://github.com/tiangolo/typer/issues/533
    version: Optional[bool] = typer.Option(  # noqa
        None,
        "--version",
        callback=version_callback,
        is_eager=True,
        help="Print the version and exit",
    ),
):
    pass


OdinIp = typer.Option("127.0.0.1", help="IP address of odin server")
OdinPort = typer.Option(8888, help="Port of odin server")


@app.command()
def ioc(
    pv_prefix: str = typer.Argument(),
    ip: str = OdinIp,
    port: int = OdinPort,
    log_level: LogLevel = LogLevel.TRACE,
):
    configure_logging(log_level)

    controller = OdinController(IPConnectionSettings(ip, port))
    options = EpicsCATransport(
        epicsca=EpicsIOCOptions(pv_prefix=pv_prefix),
        gui=EpicsGUIOptions(
            output_path=Path.cwd() / "odin.bob", title=f"Odin - {pv_prefix}"
        ),
    )
    launcher = FastCS(controller, [options])
    launcher.run()


# test with: python -m fastcs_odin
if __name__ == "__main__":
    app()
