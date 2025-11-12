from collections.abc import Sequence

from fastcs.attribute_io import AttributeIO
from fastcs.attribute_io_ref import AttributeIORefT
from fastcs.controller import Controller
from fastcs.datatypes import T

from fastcs_odin.http_connection import HTTPConnection
from fastcs_odin.util import OdinParameter


class OdinAdapterController(Controller):
    """Base class for exposing parameters from an odin control adapter.

    Introspection should work for any odin adapter that implements its API using
    ParameterTree. To implement logic for a specific adapter, make a subclass and
    implement `_process_parameters` to modify the parameters before creating attributes
    and/or statically define additional attributes.
    """

    def __init__(
        self,
        connection: HTTPConnection,
        parameters: list[OdinParameter],
        api_prefix: str,
        ios: Sequence[AttributeIO[T, AttributeIORefT]],
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
