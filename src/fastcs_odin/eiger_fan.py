from fastcs_odin.odin_adapter_controller import OdinAdapterController


class EigerFanAdapterController(OdinAdapterController):
    """Controller for an EigerFan adapter in an odin control server"""

    def _process_parameters(self):
        for parameter in self.parameters:
            # Remove 0 index and status/config
            match parameter.uri:
                case ["0", "status" | "config", *_]:
                    parameter.set_path(parameter.path[2:])
