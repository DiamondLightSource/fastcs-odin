from dataclasses import KW_ONLY, dataclass

from fastcs.attributes import AttributeIO, AttributeIORef, AttrR, AttrW
from fastcs.datatypes import DType_T
from fastcs.logging import bind_logger

from fastcs_odin.http_connection import HTTPConnection, ValueType

logger = bind_logger(logger_name=__name__)


class AdapterResponseError(Exception): ...


@dataclass
class ParameterTreeAttributeIORef(AttributeIORef):
    """IO ref for for a parameter in an odin adapter ParameterTree

    Args:
        path: The path to the parameter in the tree
    """

    path: str
    _: KW_ONLY
    update_period: float | None = 0.2


class ParameterTreeAttributeIO(AttributeIO[DType_T, ParameterTreeAttributeIORef]):
    """AttributeIO for ``ParameterTreeAttributeIORef`` Attributes"""

    def __init__(self, connection: HTTPConnection):
        super().__init__()

        self._connection = connection

    async def update(self, attr: AttrR[DType_T, ParameterTreeAttributeIORef]) -> None:
        try:
            response = await self._connection.get(attr.io_ref.path)
        except Exception:
            logger.error("Failed to get parameter", path=attr.io_ref.path)
            raise

        self.log_event(
            "Query for parameter",
            uri=attr.io_ref.path,
            response=response,
            topic=attr,
        )

        match response:
            case {"value": value}:
                pass
            case _:
                parameter_name = attr.io_ref.path.split("/")[-1]
                for k, v in response.items():
                    if k == parameter_name:  # e.g. {"api": 0.1}
                        value = v
                        break
                else:
                    raise ValueError(
                        f"Failed to parse response for {attr.io_ref.path}:\n{response}"
                    )

        await attr.update(value)

    async def send(
        self, attr: AttrW[DType_T, ParameterTreeAttributeIORef], value: DType_T
    ) -> None:
        assert isinstance(value, ValueType)
        logger.info("Sending parameter", path=attr.io_ref.path, value=value)
        response = await self._connection.put(attr.io_ref.path, value)

        match response:
            case {"error": error}:
                raise AdapterResponseError(error)
