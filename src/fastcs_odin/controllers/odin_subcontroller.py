from collections.abc import Sequence

from fastcs.attributes import AttributeIO, AttributeIORefT
from fastcs.controllers import Controller
from fastcs.datatypes import DType_T

from fastcs_odin.http_connection import HTTPConnection
from fastcs_odin.util import OdinParameter, create_attribute


class OdinSubController(Controller):
    """Base sub controller for exposing parameters from an odin control server"""

    def __init__(
        self,
        connection: HTTPConnection,
        parameters: list[OdinParameter],
        api_prefix: str,
        ios: Sequence[AttributeIO[DType_T, AttributeIORefT]],
    ):
        """
        Args:
            connection: HTTP connection to communicate with odin server
            parameters: The parameters in the adapter
            api_prefix: The base URL of this adapter in the odin server API

        """
        super().__init__(ios=ios)

        self.connection = connection
        self.parameters = parameters
        self._api_prefix = api_prefix
        self._ios = ios

    async def initialise(self):
        for parameter in self.parameters:
            self.add_attribute(
                parameter.name,
                create_attribute(parameter=parameter, api_prefix=self._api_prefix),
            )
