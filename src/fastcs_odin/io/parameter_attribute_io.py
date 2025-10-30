from dataclasses import KW_ONLY, dataclass

from fastcs.attribute_io import AttributeIO
from fastcs.attribute_io_ref import AttributeIORef
from fastcs.attributes import AttrR, AttrW
from fastcs.datatypes import T
from fastcs.logging import logger as _logger

from fastcs_odin.http_connection import HTTPConnection, ValueType

logger = _logger.bind(logger_name=__name__)


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


class ParameterTreeAttributeIO(AttributeIO[T, ParameterTreeAttributeIORef]):
    """AttributeIO for ``ParameterTreeAttributeIORef`` Attributes"""

    def __init__(self, connection: HTTPConnection):
        super().__init__()

        self._connection = connection

    async def update(self, attr: AttrR[T, ParameterTreeAttributeIORef]) -> None:
        # TODO: We should use pydantic validation here
        response = await self._connection.get(attr.io_ref.path)

        # TODO: This would be nicer if the key was 'value' so we could match
        parameter = attr.io_ref.path.split("/")[-1]
        if parameter not in response:
            raise ValueError(f"{parameter} not found in response:\n{response}")

        value = response.get(parameter)
        await attr.update(attr.datatype.validate(value))

    async def send(self, attr: AttrW[T, ParameterTreeAttributeIORef], value: T) -> None:
        assert isinstance(value, ValueType)
        response = await self._connection.put(attr.io_ref.path, value)

        match response:
            case {"error": error}:
                raise AdapterResponseError(error)
