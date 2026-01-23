from dataclasses import KW_ONLY, dataclass

from fastcs.attributes import AttributeIO, AttributeIORef, AttrR, AttrW
from fastcs.datatypes import DType_T
from fastcs.logging import bind_logger

from fastcs_odin.http_connection import HTTPConnection, ValueType
from fastcs_odin.io.parameter_cache import ParameterTreeCache

logger = bind_logger(logger_name=__name__)


@dataclass
class ParameterTreeAttributeIORef(AttributeIORef):
    """IO ref for for a parameter in an odin adapter ParameterTree

    Args:
        path: The path to the parameter in the tree
    """

    adapter: str
    path: str
    _: KW_ONLY
    update_period: float | None = 0.2


class ParameterTreeAttributeIO(AttributeIO[DType_T, ParameterTreeAttributeIORef]):
    """AttributeIO for ``ParameterTreeAttributeIORef`` Attributes"""

    def __init__(self, connection: HTTPConnection):
        super().__init__()

        self._connection = connection
        self._cache: dict[str, ParameterTreeCache] = {}

    async def update(self, attr: AttrR[DType_T, ParameterTreeAttributeIORef]) -> None:
        # TODO: We should use pydantic validation here

        if attr.io_ref.adapter not in self._cache:
            logger.debug(
                "Creating ParameterTree cache for {adapter}",
                adapter=attr.io_ref.adapter,
            )
            self._cache[attr.io_ref.adapter] = ParameterTreeCache(
                path_prefix=attr.io_ref.adapter, connection=self._connection
            )

        value = await self._cache[attr.io_ref.adapter].get(
            attr.io_ref.path, attr.io_ref.update_period
        )

        self.log_event(
            "Query for parameter",
            adapter=attr.io_ref.adapter,
            uri=attr.io_ref.path,
            value=value,
            topic=attr,
        )

        await attr.update(attr.datatype.validate(value))

    async def send(
        self, attr: AttrW[DType_T, ParameterTreeAttributeIORef], value: DType_T
    ) -> None:
        assert isinstance(value, ValueType)
        assert attr.io_ref.adapter in self._cache
        logger.info("Sending parameter", path=attr.io_ref.path, value=value)
        await self._cache[attr.io_ref.adapter].put(attr.io_ref.path, value)

    def enable_request_timers(self):
        """Enable request timers on all parameter tree caches."""
        for cache in self._cache.values():
            cache.request_timer.enable_tracing()

    def disable_request_timers(self):
        """Disable request timers on all caches."""
        for cache in self._cache.values():
            cache.request_timer.disable_tracing()
