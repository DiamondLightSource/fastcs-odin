import asyncio
import re
from collections.abc import Sequence
from functools import cached_property

from fastcs.attributes import AttrR
from fastcs.connections.ip_connection import IPConnectionSettings
from fastcs.controller import Controller
from fastcs.datatypes import Bool, Float, Int, String
from fastcs.wrappers import command

from fastcs_odin.eiger_fan import EigerFanAdapterController
from fastcs_odin.frame_processor import FrameProcessorAdapterController
from fastcs_odin.frame_receiver import FrameReceiverAdapterController
from fastcs_odin.http_connection import HTTPConnection
from fastcs_odin.meta_writer import MetaWriterAdapterController
from fastcs_odin.odin_adapter_controller import (
    OdinAdapterController,
    StatusSummaryUpdater,
    _filter_sub_controllers,
)
from fastcs_odin.util import AdapterType, OdinParameter, create_odin_parameters

types = {"float": Float(), "int": Int(), "bool": Bool(), "str": String()}

REQUEST_METADATA_HEADER = {"Accept": "application/json;metadata=true"}


class AdapterResponseError(Exception): ...


class OdinController(Controller):
    """A root ``Controller`` for an odin control server."""

    API_PREFIX = "api/0.1"

    writing: AttrR = AttrR(
        Bool(), handler=StatusSummaryUpdater([("MW", "FP")], "writing", any)
    )

    def __init__(self, settings: IPConnectionSettings) -> None:
        super().__init__()

        self.connection = HTTPConnection(settings.ip, settings.port)

    def _collect_commands(
        self,
        path_filter: Sequence[str | tuple[str, ...] | re.Pattern],
        command_name: str,
    ):
        commands = []

        controllers = list(_filter_sub_controllers(self, path_filter))

        for controller in controllers:
            if cmd := getattr(controller, command_name, None):
                commands.append(cmd)
        return commands

    @cached_property
    def _start_writing_commands(self):
        return self._collect_commands(("FP", re.compile("FP*"), "HDF"), "start_writing")

    @cached_property
    def _stop_writing_commands(self):
        return self._collect_commands(("FP", re.compile("FP*"), "HDF"), "stop_writing")

    @command()
    async def start_writing(self) -> None:
        await asyncio.gather(
            *(start_writing() for start_writing in self._start_writing_commands)
        )

    @command()
    async def stop_writing(self) -> None:
        await asyncio.gather(
            *(stop_writing() for stop_writing in self._stop_writing_commands)
        )

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
                    module = ""

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
            case AdapterType.FRAME_PROCESSOR:
                return FrameProcessorAdapterController(
                    connection, parameters, f"{self.API_PREFIX}/{adapter}"
                )
            case AdapterType.FRAME_RECEIVER:
                return FrameReceiverAdapterController(
                    connection, parameters, f"{self.API_PREFIX}/{adapter}"
                )
            case AdapterType.META_WRITER:
                return MetaWriterAdapterController(
                    connection, parameters, f"{self.API_PREFIX}/{adapter}"
                )
            case AdapterType.EIGER_FAN:
                return EigerFanAdapterController(
                    connection, parameters, f"{self.API_PREFIX}/{adapter}"
                )
            case _:
                return OdinAdapterController(
                    connection, parameters, f"{self.API_PREFIX}/{adapter}"
                )

    async def connect(self) -> None:
        self.connection.open()
