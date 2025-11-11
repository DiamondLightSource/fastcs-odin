from fastcs.attributes import AttrRW
from fastcs.datatypes import Int, String

from fastcs_odin.io.parameter_attribute_io import ParameterTreeAttributeIORef
from fastcs_odin.odin_adapter_controller import OdinAdapterController


class EigerFanAdapterController(OdinAdapterController):
    """SubController for an eigerfan adapter in an odin control server."""

    acquisition_id: AttrRW = AttrRW(
        String(), io_ref=ParameterTreeAttributeIORef("api/0.1/ef/0/config/acqid")
    )
    block_size: AttrRW = AttrRW(
        Int(), io_ref=ParameterTreeAttributeIORef("api/0.1/ef/0/config/block_size")
    )
