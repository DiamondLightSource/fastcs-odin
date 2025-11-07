import asyncio
import re
from collections.abc import Sequence
from functools import cached_property, partial

from fastcs.attributes import AttrR
from fastcs.cs_methods import Command
from fastcs.datatypes import Bool, Int
from fastcs.wrappers import command
from pydantic import ValidationError

from fastcs_odin.odin_adapter_controller import (
    OdinAdapterController,
    StatusSummaryUpdater,
    _filter_sub_controllers,
)
from fastcs_odin.odin_data import OdinDataAdapterController, OdinDataController
from fastcs_odin.util import AllowedCommandsResponse, OdinParameter, partition


class FrameProcessorController(OdinDataController):
    """Sub controller for a frame processor application."""

    async def initialise(self):
        plugins_response = await self.connection.get(
            f"{self._api_prefix}/status/plugins/names"
        )
        match plugins_response:
            case {"names": [*plugin_list]}:
                plugins = tuple(a for a in plugin_list if isinstance(a, str))
                if len(plugins) != len(plugin_list):
                    raise ValueError(f"Received invalid plugins list:\n{plugin_list}")
            case _:
                raise ValueError(
                    f"Did not find valid plugins in response:\n{plugins_response}"
                )

        self._process_parameters()
        await self._create_plugin_sub_controllers(plugins)
        self._create_attributes()

    async def _create_plugin_sub_controllers(self, plugins: Sequence[str]):
        for plugin in plugins:

            def __parameter_in_plugin(
                parameter: OdinParameter, plugin: str = plugin
            ) -> bool:
                return parameter.path[0] == plugin

            plugin_parameters, self.parameters = partition(
                self.parameters, __parameter_in_plugin
            )
            plugin_controller = FrameProcessorPluginController(
                self.connection,
                plugin_parameters,
                f"{self._api_prefix}",
            )
            self.register_sub_controller(plugin.upper(), plugin_controller)
            await plugin_controller.initialise()


class FrameProcessorAdapterController(OdinDataAdapterController):
    frames_written: AttrR = AttrR(
        Int(),
        handler=StatusSummaryUpdater(
            [re.compile("FP*"), "HDF"], "frames_written", partial(sum, start=0)
        ),
    )
    writing: AttrR = AttrR(
        Bool(),
        handler=StatusSummaryUpdater([re.compile("FP*"), "HDF"], "writing", any),
    )
    _unique_config = [
        "rank",
        "number",
        "ctrl_endpoint",
        "meta_endpoint",
        "fr_ready_cnxn",
        "fr_release_cnxn",
    ]
    _subcontroller_label = "FP"
    _subcontroller_cls = FrameProcessorController

    def _collect_commands(
        self,
        path_filter: Sequence[str | tuple[str, ...] | re.Pattern],
        command_name: str,
    ):
        commands = []

        controllers = list(_filter_sub_controllers(self, path_filter))

        for controller in controllers:
            try:
                cmd = getattr(controller, command_name)
                commands.append(cmd)
            except AttributeError as err:
                raise AttributeError(
                    f"Sub controller {controller} "
                    f"does not have command '{command_name}'."
                ) from err
        return commands

    @cached_property
    def _start_writing_commands(self):
        return self._collect_commands((re.compile("FP*"), "HDF"), "hi")

    @cached_property
    def _stop_writing_commands(self):
        return self._collect_commands((re.compile("FP*"), "HDF"), "stop_writing")

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


class FrameProcessorPluginController(OdinAdapterController):
    """SubController for a plugin in a frameProcessor application."""

    async def initialise(self):
        await self._create_commands()
        await self._create_dataset_controllers()
        return await super().initialise()

    async def _create_commands(self):
        plugin_name = self.path[-1].lower()
        command_response = await self.connection.get(
            f"{self._api_prefix}/command/{plugin_name}/allowed"
        )

        try:
            commands = AllowedCommandsResponse.model_validate(command_response)
            for command in commands.allowed:
                self._construct_command(command, plugin_name)
        except ValidationError:
            pass

    async def _create_dataset_controllers(self):
        if any("dataset" in p.path for p in self.parameters):

            def __dataset_parameter(param: OdinParameter):
                return "dataset" in param.path

            dataset_parameters, self.parameters = partition(
                self.parameters, __dataset_parameter
            )
            if dataset_parameters:
                dataset_controller = FrameProcessorDatasetController(
                    self.connection, dataset_parameters, f"{self._api_prefix}"
                )
                self.register_sub_controller("DS", dataset_controller)
                await dataset_controller.initialise()

    def _construct_command(self, command_name, plugin_name):
        async def submit_command() -> None:
            await self.connection.put(
                f"{self._api_prefix}/command/{plugin_name}/execute", command_name
            )

        setattr(self, command_name, Command(submit_command))

    def _process_parameters(self):
        for parameter in self.parameters:
            # Remove plugin name included in controller base path
            parameter.set_path(parameter.path[1:])


class FrameProcessorDatasetController(OdinAdapterController):
    def _process_parameters(self):
        for parameter in self.parameters:
            parameter.set_path(parameter.uri[3:])
