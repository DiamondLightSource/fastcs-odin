from fastcs.attributes import AttrR, AttrRW
from fastcs.datatypes import Bool, Int, String
from fastcs.wrappers import command

from fastcs_odin.io.parameter_attribute_io import ParameterTreeAttributeIORef
from fastcs_odin.odin_adapter_controller import OdinAdapterController


class MetaWriterAdapterController(OdinAdapterController):
    """Controller for the meta writer adapter in an odin control server"""

    def _process_parameters(self):
        for parameter in self.parameters:
            # Remove 0 index and status/config
            match parameter.uri:
                case ["0", "status" | "config", *_]:
                    parameter.set_path(parameter.path[2:])

    acquisition_id: AttrRW = AttrRW(
        String(), io_ref=ParameterTreeAttributeIORef("api/0.1/mw/config/acquisition_id")
    )
    directory: AttrRW = AttrRW(
        String(), io_ref=ParameterTreeAttributeIORef("api/0.1/mw/config/directory")
    )
    file_prefix: AttrRW = AttrRW(
        String(), io_ref=ParameterTreeAttributeIORef("api/0.1/mw/config/file_prefix")
    )
    writing: AttrR = AttrR(
        Bool(), io_ref=ParameterTreeAttributeIORef("api/0.1/mw/status/writing")
    )
    written: AttrR = AttrR(
        Int(), io_ref=ParameterTreeAttributeIORef("api/0.1/mw/status/written")
    )

    @command()
    async def stop(self):
        await self.connection.put("api/0.1/mw/config/stop", True)
