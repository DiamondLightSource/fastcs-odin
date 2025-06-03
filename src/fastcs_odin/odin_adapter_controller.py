import logging
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from fastcs.attributes import (
    AttrHandlerR,
    AttrHandlerRW,
    AttrHandlerW,
    AttrR,
    AttrRW,
    AttrW,
)
from fastcs.controller import BaseController, SubController
from fastcs.util import snake_to_pascal

from fastcs_odin.http_connection import HTTPConnection
from fastcs_odin.util import OdinParameter

REQUEST_METADATA_HEADER = {"Accept": "application/json;metadata=true"}


class AdapterResponseError(Exception): ...


@dataclass
class ParamTreeHandler(AttrHandlerRW):
    path: str
    update_period: float | None = 0.2
    allowed_values: dict[int, str] | None = None

    async def initialise(self, controller: BaseController):
        assert isinstance(controller, OdinAdapterController)
        self._controller = controller

    @property
    def controller(self) -> "OdinAdapterController":
        return self._controller

    async def put(
        self,
        attr: AttrW[Any],
        value: Any,
    ) -> None:
        try:
            response = await self.controller.connection.put(self.path, value)
            match response:
                case {"error": error}:
                    raise AdapterResponseError(error)
        except Exception as e:
            logging.error("Put %s = %s failed:\n%s", self.path, value, e)

    async def update(
        self,
        attr: AttrR[Any],
    ) -> None:
        try:
            response = await self.controller.connection.get(self.path)

            # TODO: This would be nicer if the key was 'value' so we could match
            parameter = self.path.split("/")[-1]
            if parameter not in response:
                raise ValueError(f"{parameter} not found in response:\n{response}")

            value = response.get(parameter)
            await attr.set(
                attr.dtype(value)
            )  # TODO: https://github.com/DiamondLightSource/FastCS/issues/159
        except Exception as e:
            logging.error("Update loop failed for %s:\n%s", self.path, e)


@dataclass
class StatusSummaryUpdater(AttrHandlerR):
    """Updater to accumulate underlying attributes into a high-level summary.

    Args:
        path_filter: A list of filters to apply to the sub controller hierarchy. This is
        used to match one or more sub controller paths under the parent controller. Each
        element can be a string or tuple of string for one or more exact matches, or a
        regular expression to match on.
        attribute_name: The name of the attribute to get from the sub controllers
        matched by `path_filter`.
        accumulator: A function that takes a sequence of values from each matched
        attribute and returns a summary value.
    """

    path_filter: list[str | tuple[str, ...] | re.Pattern]
    attribute_name: str
    accumulator: Callable[[Iterable[Any]], float | int | bool | str]
    update_period: float | None = 0.2

    async def initialise(self, controller):
        self.controller = controller

    async def update(self, attr: AttrR):
        values = []
        for sub_controller in _filter_sub_controllers(
            self.controller, self.path_filter
        ):
            sub_attribute: AttrR = sub_controller.attributes[self.attribute_name]  # type: ignore
            values.append(sub_attribute.get())

        await attr.set(self.accumulator(values))


@dataclass
class ConfigFanSender(AttrHandlerW):
    """Handler to fan out puts to underlying Attributes.

    Args:
        attributes: A list of attributes to fan out to.
    """

    attributes: list[AttrW]

    async def put(self, attr: AttrW, value: Any):
        for attribute in self.attributes:
            await attribute.process(value)

        if isinstance(attr, AttrRW):
            await attr.set(value)


def _filter_sub_controllers(
    controller: BaseController,
    path_filter: Sequence[str | tuple[str, ...] | re.Pattern],
) -> Iterable[SubController]:
    sub_controller_map = controller.get_sub_controllers()
    step = path_filter[0]
    is_leaf = len(path_filter) == 1

    match step:
        case str() as key:
            if key not in sub_controller_map:
                raise ValueError(f"SubController {key} not found in {controller}")
            sub_controller = sub_controller_map[key]
            if is_leaf:
                yield sub_controller
            else:
                yield from _filter_sub_controllers(sub_controller, path_filter[1:])

        case tuple() as keys:
            for key in keys:
                if key not in sub_controller_map:
                    raise ValueError(f"SubController {key} not found in {controller}")
                sub_controller = sub_controller_map[key]
                if is_leaf:
                    yield sub_controller
                else:
                    yield from _filter_sub_controllers(sub_controller, path_filter[1:])

        case pattern:
            for key in sub_controller_map:
                if pattern.match(key):
                    sub_controller = sub_controller_map[key]
                    if is_leaf:
                        yield sub_controller
                    else:
                        yield from _filter_sub_controllers(
                            sub_controller, path_filter[1:]
                        )


class OdinAdapterController(SubController):
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
    ):
        """
        Args:
            connection: HTTP connection to communicate with odin server
            parameters: The parameters in the adapter
            api_prefix: The base URL of this adapter in the odin server API
        """
        super().__init__()

        self.connection = connection
        self.parameters = parameters
        self._api_prefix = api_prefix

    async def initialise(self):
        self._process_parameters()
        self._create_attributes()

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
                handler=ParamTreeHandler(
                    "/".join([self._api_prefix] + parameter.uri),
                    allowed_values=parameter.metadata.allowed_values,
                ),
                group=group,
            )
            self.attributes[parameter.name] = attr
