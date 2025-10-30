from fastcs.attributes import AttrR, AttrRW, AttrW
from fastcs.datatypes import Bool, String

from fastcs_odin.io.parameter_attribute_io import ParameterTreeAttributeIORef
from fastcs_odin.odin_adapter_controller import OdinAdapterController


class MetaWriterAdapterController(OdinAdapterController):
    """SubController for the meta writer adapter in an odin control server."""

    acquisition_id: AttrRW = AttrRW(
        String(), io_ref=ParameterTreeAttributeIORef("api/0.1/mw/config/acquisition_id")
    )
    directory: AttrRW = AttrRW(
        String(), io_ref=ParameterTreeAttributeIORef("api/0.1/mw/config/directory")
    )
    file_prefix: AttrRW = AttrRW(
        String(), io_ref=ParameterTreeAttributeIORef("api/0.1/mw/config/file_prefix")
    )
    stop: AttrW = AttrW(
        Bool(), io_ref=ParameterTreeAttributeIORef("api/0.1/mw/config/stop")
    )
    writing: AttrR = AttrR(
        Bool(), io_ref=ParameterTreeAttributeIORef("api/0.1/mw/status/writing")
    )
