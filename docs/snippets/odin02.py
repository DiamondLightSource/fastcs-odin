from fastcs.attributes import AttrRW
from fastcs.control_system import FastCS
from fastcs.controllers import Controller
from fastcs.datatypes import Int
from fastcs.transports.epics import EpicsIOCOptions
from fastcs.transports.epics.ca.transport import EpicsCATransport


class ExampleOdinController(Controller):
    foo = AttrRW(Int())


fastcs = FastCS(
    ExampleOdinController(),
    [EpicsCATransport(EpicsIOCOptions(pv_prefix="EXAMPLE"))],
)

if __name__ == "__main__":
    fastcs.run()
