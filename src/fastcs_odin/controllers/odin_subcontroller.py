from collections.abc import Sequence

from fastcs.attributes import AttributeIO, AttributeIORefT
from fastcs.controllers import Controller
from fastcs.datatypes import DType_T
from fastcs.logging import bind_logger
from fastcs.methods import Command
from pydantic import ValidationError

from fastcs_odin.http_connection import HTTPConnection
from fastcs_odin.util import AllowedCommandsResponse, OdinParameter, create_attribute

logger = bind_logger(logger_name=__name__)


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
        await self._create_attributes()

    async def _create_attributes(self):
        """Create an `Attribute` for each parameter"""

        for parameter in self.parameters:
            self.add_attribute(
                parameter.name,
                create_attribute(parameter=parameter, api_prefix=self._api_prefix),
            )

    async def _create_commands(self, path: Sequence[str] = ()):
        """Create a `Command` for each allowed command in the odin server

        Args:
            path: The sub path to the command under ``self._api_prefix``

        """
        response = await self.connection.get(
            f"{self._api_prefix}/command{'/' + '/'.join(path) if path else ''}/allowed"
        )

        try:
            commands = AllowedCommandsResponse.model_validate(response)
        except ValidationError:
            logger.warning(
                "Failed to parse command response",
                path=self.path,
                response=response,
            )
            return

        for command in commands.allowed:
            self._create_command(command, path)

    def _create_command(self, name: str, path: Sequence[str] = ()):
        """Create a `Command` that sends a command to the odin server

        Args:
            name: The name of the command
            path: The sub path to the command under ``self._api_prefix``

        """
        uri = (
            f"{self._api_prefix}/command{'/' + '/'.join(path) if path else ''}/execute"
        )

        async def submit_command() -> None:
            logger.info(
                "Executing command", controller=self.path, command=name, path=path
            )

            await self.connection.put(uri, name)

        setattr(self, name, Command(submit_command))
