from fastcs_odin.odin_adapter_controller import OdinSubController
from fastcs_odin.util import create_attribute


class EigerFanAdapterController(OdinSubController):
    """Controller for an EigerFan adapter in an odin control server"""

    async def initialise(self):
        self._process_parameters()
        for parameter in self.parameters:
            self.add_attribute(
                parameter.name,
                create_attribute(parameter=parameter, api_prefix=self._api_prefix),
            )

    def _process_parameters(self):
        for parameter in self.parameters:
            # Remove 0 index and status/config
            match parameter.uri:
                case ["0", "status" | "config", *_]:
                    parameter.set_path(parameter.path[2:])
                case ["0", _]:
                    parameter.set_path(parameter.path[1:])
