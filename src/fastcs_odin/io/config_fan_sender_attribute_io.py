import asyncio
from dataclasses import dataclass
from typing import Any

from fastcs.attributes import AttributeIO, AttributeIORef, AttrRW, AttrW
from fastcs.datatypes import DType_T
from fastcs.logging import bind_logger

logger = bind_logger(logger_name=__name__)


@dataclass
class ConfigFanAttributeIORef(AttributeIORef):
    """IO reference for an internal Attribute that is fanned out to other Attributes

    Args:
        attributes: A list of attributes to fan out to
    """

    attributes: list[AttrW]


class ConfigFanAttributeIO(AttributeIO[DType_T, ConfigFanAttributeIORef]):
    """AttributeIO for ``ConfigFanAttributeIORef`` Attributes"""

    async def send(self, attr: AttrW[DType_T, ConfigFanAttributeIORef], value: Any):
        logger.info("Fanning out put", value=value, attribute=attr)
        await asyncio.gather(
            *[
                attribute.put(value, sync_setpoint=True)
                for attribute in attr.io_ref.attributes
            ]
        )

        if isinstance(attr, AttrRW):
            await attr.update(value)
