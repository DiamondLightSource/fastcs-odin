from fastcs_odin.odin_data import OdinDataAdapterController
from fastcs_odin.odin_subcontroller import OdinSubController
from fastcs_odin.util import create_attribute, remove_metadata_fields_paths


class FrameReceiverController(OdinSubController):
    async def initialise(self):
        self.parameters = remove_metadata_fields_paths(self.parameters)

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
