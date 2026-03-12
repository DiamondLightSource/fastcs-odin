from fastcs.attributes import AttrRW
from fastcs.control_system import FastCS
from fastcs.controllers import Controller
from fastcs.datatypes import Int


class ExampleOdinController(Controller):
    foo = AttrRW(Int())


fastcs = FastCS(ExampleOdinController(), [])

if __name__ == "__main__":
    fastcs.run()
