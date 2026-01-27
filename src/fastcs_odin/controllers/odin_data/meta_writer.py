from fastcs.attributes import AttrR, AttrRW
from fastcs.datatypes import Bool, Int, String
from fastcs.methods import command

from fastcs_odin.controllers.odin_subcontroller import OdinSubController
from fastcs_odin.util import ParameterTreeAttributeIORef, create_attribute


class MetaWriterAdapterController(OdinSubController):
    """Controller for the meta writer adapter in an odin control server"""

    async def initialise(self):
        for parameter in self.parameters:
            # Remove 0 index and status/config
            match parameter.uri:
                case ["0", "status" | "config", *_]:
                    parameter.set_path(parameter.path[2:])

            if "acquisitions" in parameter.uri:
                continue

            self.add_attribute(
                parameter.name,
                create_attribute(parameter=parameter, api_prefix=self._api_prefix),
            )

    acquisition_id = AttrRW(
        String(), io_ref=ParameterTreeAttributeIORef("api/0.1/mw/config/acquisition_id")
    )
    directory = AttrRW(
        String(), io_ref=ParameterTreeAttributeIORef("api/0.1/mw/config/directory")
    )
    file_prefix = AttrRW(
        String(), io_ref=ParameterTreeAttributeIORef("api/0.1/mw/config/file_prefix")
    )
    writing = AttrR(
        Bool(), io_ref=ParameterTreeAttributeIORef("api/0.1/mw/status/writing")
    )
    written = AttrR(
        Int(), io_ref=ParameterTreeAttributeIORef("api/0.1/mw/status/written")
    )

    @command()
    async def stop(self):
        await self.connection.put("api/0.1/mw/config/stop", True)
