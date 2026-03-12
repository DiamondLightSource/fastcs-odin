from pathlib import Path

from fastcs.attributes import AttrRW
from fastcs.connections import IPConnectionSettings
from fastcs.control_system import FastCS
from fastcs.datatypes import Int
from fastcs.transports.epics import EpicsGUIOptions, EpicsIOCOptions
from fastcs.transports.epics.ca.transport import EpicsCATransport

from fastcs_odin.controllers import OdinController


class ExampleOdinController(OdinController):
    foo = AttrRW(Int())


fastcs = FastCS(
    ExampleOdinController(IPConnectionSettings("127.0.0.1", 8888)),
    [
        EpicsCATransport(
            EpicsIOCOptions(pv_prefix="EXAMPLE"),
            gui=EpicsGUIOptions(
                output_path=Path.cwd() / "opis" / "example.bob",
                title="Odin Example Detector",
            ),
        )
    ],
)

if __name__ == "__main__":
    fastcs.run()
