import asyncio
from dataclasses import KW_ONLY, dataclass
from typing import Any

from fastcs.attributes import AttributeIO, AttributeIORef, AttrR, AttrRW, AttrW
from fastcs.datatypes import DType_T
from fastcs.logging import bind_logger

logger = bind_logger(logger_name=__name__)


@dataclass
class ConfigFanAttributeIORef(AttributeIORef):
    """IO reference for an internal Attribute that is fanned out to other Attributes

    Args:
        attributes: A list of attributes to fan out to
    """

    attributes: list[AttrRW]
    _: KW_ONLY
    update_period: float | None = 0.2


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

    async def update(self, attr: AttrR[DType_T, ConfigFanAttributeIORef]):
        values = [attribute.get() for attribute in attr.io_ref.attributes]

        if attr.datatype.all_equal(values):
            await attr.update(values[0])
        else:
            # TODO: Set an alarm - https://github.com/DiamondLightSource/FastCS/issues/286
            await attr.update(attr.datatype.initial_value)
