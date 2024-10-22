from fastcs.connections.ip_connection import IPConnectionSettings
from fastcs.controller import Controller
from fastcs.datatypes import Bool, Float, Int, String

from fastcs_odin.eiger_fan import EigerFanAdapterController
from fastcs_odin.http_connection import HTTPConnection
from fastcs_odin.meta_writer import MetaWriterAdapterController
from fastcs_odin.odin_adapter_controller import OdinAdapterController
from fastcs_odin.odin_data import (
    FrameProcessorAdapterController,
    FrameReceiverAdapterController,
)
from fastcs_odin.util import OdinParameter, create_odin_parameters

types = {"float": Float(), "int": Int(), "bool": Bool(), "str": String()}

REQUEST_METADATA_HEADER = {"Accept": "application/json;metadata=true"}


class AdapterResponseError(Exception): ...


class OdinController(Controller):
    """A root ``Controller`` for an odin control server."""

    API_PREFIX = "api/0.1"
    MODULE_FRAME_PROCESSOR = "FrameProcessorAdapter"
    MODULE_FRAME_RECEIVER = "FrameReceiverAdapter"
    MODULE_META_WRITER = "MetaListenerAdapter"
    MODULE_EIGER_FAN = "EigerFanAdapter"

    def __init__(self, settings: IPConnectionSettings) -> None:
        super().__init__()

        self.connection = HTTPConnection(settings.ip, settings.port)

    async def initialise(self) -> None:
        self.connection.open()

        adapters_response = await self.connection.get(f"{self.API_PREFIX}/adapters")
        match adapters_response:
            case {"adapters": [*adapter_list]}:
                adapters = tuple(a for a in adapter_list if isinstance(a, str))
                if len(adapters) != len(adapter_list):
                    raise ValueError(f"Received invalid adapters list:\n{adapter_list}")
            case _:
                raise ValueError(
                    f"Did not find valid adapters in response:\n{adapters_response}"
                )

        for adapter in adapters:
            # Get full parameter tree and split into parameters at the root and under
            # an index where there are N identical trees for each underlying process
            response = await self.connection.get(
                f"{self.API_PREFIX}/{adapter}", headers=REQUEST_METADATA_HEADER
            )
            # Extract the module name of the adapter
            match response:
                case {"module": {"value": str() as module}}:
                    pass
                case _:
                    raise ValueError(
                        f"Did not find valid module name in response:\n{response}"
                    )

            adapter_controller = self._create_adapter_controller(
                self.connection, create_odin_parameters(response), adapter, module
            )
            self.register_sub_controller(adapter.upper(), adapter_controller)
            await adapter_controller.initialise()

        await self.connection.close()

    def _create_adapter_controller(
        self,
        connection: HTTPConnection,
        parameters: list[OdinParameter],
        adapter: str,
        module: str,
    ) -> OdinAdapterController:
        """Create a sub controller for an adapter in an odin control server."""

        match module:
            case self.MODULE_FRAME_PROCESSOR:
                return FrameProcessorAdapterController(
                    connection, parameters, f"{self.API_PREFIX}/{adapter}"
                )
            case self.MODULE_FRAME_RECEIVER:
                return FrameReceiverAdapterController(
                    connection, parameters, f"{self.API_PREFIX}/{adapter}"
                )
            case self.MODULE_META_WRITER:
                return MetaWriterAdapterController(
                    connection, parameters, f"{self.API_PREFIX}/{adapter}"
                )
            case self.MODULE_EIGER_FAN:
                return EigerFanAdapterController(
                    connection, parameters, f"{self.API_PREFIX}/{adapter}"
                )
            case _:
                return OdinAdapterController(
                    connection, parameters, f"{self.API_PREFIX}/{adapter}"
                )

    async def connect(self) -> None:
        self.connection.open()
