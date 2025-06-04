import re
from collections.abc import Sequence

from fastcs.attributes import AttrR
from fastcs.cs_methods import Command
from fastcs.datatypes import Bool, Int

from fastcs_odin.odin_adapter_controller import (
    OdinAdapterController,
    StatusSummaryUpdater,
)
from fastcs_odin.odin_data import OdinDataAdapterController, OdinDataController
from fastcs_odin.util import OdinParameter, partition


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
        handler=StatusSummaryUpdater([re.compile("FP*"), "HDF"], "frames_written", sum),
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


class FrameProcessorPluginController(OdinAdapterController):
    """SubController for a plugin in a frameProcessor application."""

    async def initialise(self):
        await self._create_commands()
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

        return await super().initialise()

    async def _create_commands(self):
        command_path = f"command/{self.path[-1].lower()}"
        command_response = await self.connection.get(
            f"{self._api_prefix}/{command_path}/allowed"
        )
        if "allowed" in command_response:
            command_names = command_response["allowed"]
            assert isinstance(command_names, list)
            for command_name in command_names:
                self.construct_command(command_name, command_path)

    def construct_command(self, command_name, command_path):
        async def submit_command() -> None:
            await self.connection.put(
                f"{self._api_prefix}/{command_path}/execute", command_name
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
