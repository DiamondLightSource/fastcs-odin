from collections.abc import Sequence

from fastcs.attribute_io import AttributeIO
from fastcs.attribute_io_ref import AttributeIORefT
from fastcs.attributes import AttrR, AttrRW
from fastcs.controller import Controller
from fastcs.datatypes import T
from fastcs.util import snake_to_pascal

from fastcs_odin.http_connection import HTTPConnection
from fastcs_odin.io.parameter_attribute_io import ParameterTreeAttributeIORef
from fastcs_odin.io.status_summary_attribute_io import initialise_summary_attributes
from fastcs_odin.util import OdinParameter

REQUEST_METADATA_HEADER = {"Accept": "application/json;metadata=true"}


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

    async def initialise(self):
        self._process_parameters()
        self._create_attributes()

        initialise_summary_attributes(self)

    def _process_parameters(self):
        """Hook to process ``OdinParameters`` before creating ``Attributes``.

        For example, renaming or removing a section of the parameter path.

        """
        pass

    def _create_attributes(self):
        """Create controller ``Attributes`` from ``OdinParameters``."""
        for parameter in self.parameters:
            if parameter.metadata.writeable:
                attr_class = AttrRW
            else:
                attr_class = AttrR

            if len(parameter.path) >= 2:
                group = snake_to_pascal(f"{parameter.path[0]}")
            else:
                group = None

            attr = attr_class(
                parameter.metadata.fastcs_datatype,
                io_ref=ParameterTreeAttributeIORef(
                    "/".join([self._api_prefix] + parameter.uri),
                ),
                group=group,
            )
            self.add_attribute(parameter.name, attr)
