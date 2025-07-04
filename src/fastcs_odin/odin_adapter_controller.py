import asyncio
import logging
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
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
from fastcs_odin.util import OdinParameter, OdinRequestTimer


class AdapterResponseError(Exception): ...


@dataclass
class ParamTreeCache:
    path_prefix: str
    connection: HTTPConnection
    _last_update: datetime | None = None
    _tree: dict[str, Any] = field(default_factory=dict)
    _update_event: asyncio.Event = field(default_factory=asyncio.Event)

    def __post_init__(self):
        self._update_event.set()
        self.request_timer = OdinRequestTimer(self.path_prefix)

    def _has_expired(self, time_step: float) -> bool:
        if self._last_update is None:
            return True
        delta_t = datetime.now() - self._last_update
        return delta_t.total_seconds() > time_step

    def _update_tree(self, tree: dict[str, Any]) -> None:
        self._tree = tree
        self._last_update = datetime.now()

    def _resolve_value(self, path_elems: list[str], tree) -> Any:
        if len(path_elems) == 1:
            if isinstance(tree, list):
                return tree[int(path_elems[0])]
            else:
                return tree[path_elems[0]]

        return self._resolve_value(path_elems[1:], tree[path_elems[0]])

    def _update_value(
        self, path_elems: list[str], value: Any, tree: dict[str, Any]
    ) -> None:
        if len(path_elems) == 1:
            tree[path_elems[0]] = value
            return

        self._update_value(path_elems[1:], value, tree[path_elems[0]])

    async def get(self, path: str, update_period: float | None) -> Any:
        if not update_period or self._has_expired(update_period):
            if self._update_event.is_set():
                self._update_event.clear()
                try:
                    with self.request_timer:
                        response = await self.connection.get(self.path_prefix)
                    self._update_tree(response)
                except Exception as e:
                    logging.error(
                        "Update failed for %s/%s:\n%s", self.path_prefix, path, e
                    )
                finally:
                    self._update_event.set()
            else:
                await self._update_event.wait()

        path_elems = path.split("/")
        value = self._resolve_value(path_elems[1:], self._tree)
        return value

    async def put(self, path: str, value: Any) -> None:
        try:
            response = await self.connection.put(path, value)
            match response:
                case {"error": error}:
                    raise AdapterResponseError(error)
                case _:
                    path_elems = path.split("/")
                    new_value = response.get(path_elems[-1])  # type: ignore
                    self._update_value(path_elems[1:], new_value, self._tree)
        except Exception as e:
            logging.error("Put %s = %s failed:\n%s", path, value, e)


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
        if attr.dtype == bool:
            value = bool(value)

        try:
            await self.controller.cache.put(self.path, value)
        except Exception as e:
            logging.error("Put %s = %s failed:\n%s", self.path, value, e)

    async def update(
        self,
        attr: AttrR[Any],
    ) -> None:
        try:
            value = await self.controller.cache.get(self.path, self.update_period)
            await attr.set(value)
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
            sub_controllers = [
                sub_controller_map[key]
                for key in sub_controller_map
                if pattern.match(key)
            ]

            if not sub_controllers:
                raise ValueError(
                    f"SubController matching {pattern} not found in {controller}"
                )

            for sub_controller in sub_controllers:
                if is_leaf:
                    yield sub_controller
                else:
                    yield from _filter_sub_controllers(sub_controller, path_filter[1:])


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
        self.cache = ParamTreeCache(api_prefix, connection)

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
