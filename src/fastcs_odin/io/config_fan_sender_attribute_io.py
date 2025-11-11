from dataclasses import dataclass
from typing import Any

from fastcs.attribute_io import AttributeIO
from fastcs.attribute_io_ref import AttributeIORef
from fastcs.attributes import AttrRW, AttrW
from fastcs.datatypes import T


@dataclass
class ConfigFanAttributeIORef(AttributeIORef):
    """IO reference for an internal Attribute that is fanned out to other Attributes

    Args:
        attributes: A list of attributes to fan out to
    """

    attributes: list[AttrW]


class ConfigFanAttributeIO(AttributeIO[T, ConfigFanAttributeIORef]):
    """AttributeIO for ``ConfigFanAttributeIORef`` Attributes"""

    async def send(self, attr: AttrW[T, ConfigFanAttributeIORef], value: Any):
        for attribute in attr.io_ref.attributes:
            await attribute.put(value, sync_setpoint=True)

        if isinstance(attr, AttrRW):
            await attr.update(value)
