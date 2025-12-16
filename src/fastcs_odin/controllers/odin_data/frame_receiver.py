from fastcs_odin.controllers.odin_data.odin_data_adapter import (
    OdinDataAdapterController,
)
from fastcs_odin.controllers.odin_subcontroller import OdinSubController
from fastcs_odin.util import create_attribute


class FrameReceiverController(OdinSubController):
    """Controller for a frameReceiver application"""

    async def initialise(self):
        for parameter in self.parameters:
            # Remove duplicate index from uri
            parameter.uri = parameter.uri[1:]
            # Remove redundant status/config from parameter path
            parameter.set_path(parameter.uri[1:])

            if len(parameter.path) > 1 and "decoder" in parameter.path[0]:
                # Combine "decoder" and "decoder_config"
                parameter.path[0] = "decoder"

            self.add_attribute(
                parameter.name,
                create_attribute(parameter=parameter, api_prefix=self._api_prefix),
            )


class FrameReceiverAdapterController(OdinDataAdapterController):
    """Controller for a frame receiver adapter in an odin control serve."""

    _subcontroller_label = "FR"
    _subcontroller_cls = FrameReceiverController
    _unique_config = [
        "rank",
        "number",
        "ctrl_endpoint",
        "fr_ready_cnxn",
        "fr_release_cnxn",
        "frame_ready_endpoint",
        "frame_release_endpoint",
        "shared_buffer_name",
        "rx_address",
        "rx_ports",
    ]
