import asyncio
from dataclasses import dataclass
from typing import Any

from fastcs.attribute_io import AttributeIO
from fastcs.attribute_io_ref import AttributeIORef
from fastcs.attributes import AttrRW, AttrW
from fastcs.datatypes import T
from fastcs.logging import bind_logger

logger = bind_logger(logger_name=__name__)


@dataclass
class ConfigFanAttributeIORef(AttributeIORef):
    """IO to fan out puts to underlying Attributes

    Args:
        attributes: A list of attributes to fan out to.
    """

    attributes: list[AttrW]


class ConfigFanAttributeIO(AttributeIO[T, ConfigFanAttributeIORef]):
    """IO to fan out puts to underlying Attributes"""

    async def send(self, attr: AttrW[T, ConfigFanAttributeIORef], value: Any):
        logger.info("Fanning out put", value=value)
        await asyncio.gather(
            *[
                attribute.put(value, sync_setpoint=True)
                for attribute in attr.io_ref.attributes
            ]
        )

        if isinstance(attr, AttrRW):
            await attr.update(value)
