import logging
from collections.abc import Iterable

from fastcs.attributes import AttrW
from fastcs.controller import BaseController, SubController

from fastcs_odin.odin_adapter_controller import (
    ConfigFanSender,
    OdinAdapterController,
)
from fastcs_odin.util import OdinParameter, partition


class OdinDataController(OdinAdapterController):
    def _remove_metadata_fields_paths(self):
        # paths ending in name or description are invalid in Odin's BaseParameterTree
        self.parameters, invalid = partition(
            self.parameters, lambda p: p.uri[-1] not in ["name", "description"]
        )
        if invalid:
            invalid_names = ["/".join(param.uri) for param in invalid]
            logging.warning(f"Removing parameters with invalid names: {invalid_names}")

    def _process_parameters(self):
        self._remove_metadata_fields_paths()
        for parameter in self.parameters:
            # Remove duplicate index from uri
            parameter.uri = parameter.uri[1:]
            # Remove redundant status/config from parameter path
            parameter.set_path(parameter.uri[1:])


class OdinDataAdapterController(OdinAdapterController):
    """Sub controller for the frame processor adapter in an odin control server."""

    _unique_config: list[str] = []
    _subcontroller_label: str = "OD"
    _subcontroller_cls: type[OdinDataController] = OdinDataController

    async def initialise(self):
        idx_parameters, self.parameters = partition(
            self.parameters, lambda p: p.uri[0].isdigit()
        )

        while idx_parameters:
            idx = idx_parameters[0].uri[0]
            fp_parameters, idx_parameters = partition(
                idx_parameters, lambda p, idx=idx: p.uri[0] == idx
            )

            adapter_controller = self._subcontroller_cls(
                self.connection,
                fp_parameters,
                f"{self._api_prefix}/{idx}",
            )
            self.register_sub_controller(
                f"{self._subcontroller_label}{idx}", adapter_controller
            )
            await adapter_controller.initialise()

        self._create_attributes()
        self._create_config_fan_attributes()

    def _create_config_fan_attributes(self):
        """Search for config attributes in sub controllers to create fan out PVs."""
        parameter_attribute_map: dict[str, tuple[OdinParameter, list[AttrW]]] = {}
        for sub_controller in get_all_sub_controllers(self):
            for parameter in sub_controller.parameters:
                mode, key = parameter.uri[0], parameter.uri[-1]
                if mode == "config" and key not in self._unique_config:
                    try:
                        attr = getattr(sub_controller, parameter.name)
                    except AttributeError:
                        logging.warning(
                            f"Controller has parameter {parameter}, "
                            f"but no corresponding attribute {parameter.name}"
                        )

                    if parameter.name not in parameter_attribute_map:
                        parameter_attribute_map[parameter.name] = (parameter, [attr])
                    else:
                        parameter_attribute_map[parameter.name][1].append(attr)

        for parameter, sub_attributes in parameter_attribute_map.values():
            setattr(
                self,
                parameter.name,
                sub_attributes[0].__class__(
                    sub_attributes[0].datatype,
                    group=sub_attributes[0].group,
                    handler=ConfigFanSender(sub_attributes),
                ),
            )


def get_all_sub_controllers(
    controller: "OdinAdapterController",
) -> list["OdinAdapterController"]:
    return list(_walk_sub_controllers(controller))


def _walk_sub_controllers(controller: BaseController) -> Iterable[SubController]:
    for sub_controller in controller.get_sub_controllers().values():
        yield sub_controller
        yield from _walk_sub_controllers(sub_controller)
