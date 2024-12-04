from fastcs_odin.odin_adapter_controller import (
    OdinAdapterController,
)
from fastcs_odin.odin_data import OdinDataAdapterController, OdinDataController
from fastcs_odin.util import OdinParameter, partition


class FrameReceiverController(OdinDataController):
    async def initialise(self):
        self._process_parameters()

        def __decoder_parameter(parameter: OdinParameter):
            return "decoder" in parameter.path[:-1]

        decoder_parameters, self.parameters = partition(
            self.parameters, __decoder_parameter
        )
        decoder_controller = FrameReceiverDecoderController(
            self.connection, decoder_parameters, f"{self._api_prefix}"
        )
        self.register_sub_controller("DECODER", decoder_controller)
        await decoder_controller.initialise()
        self._create_attributes()


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


class FrameReceiverDecoderController(OdinAdapterController):
    def _process_parameters(self):
        for parameter in self.parameters:
            # remove redundant status/decoder part from path
            parameter.set_path(parameter.uri[2:])
