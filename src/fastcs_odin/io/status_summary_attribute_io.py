import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import KW_ONLY, dataclass
from typing import Generic, TypeVar

from fastcs.attributes import AttributeIO, AttributeIORef, AttrR
from fastcs.controllers import BaseController

In = TypeVar("In", float, int, bool, str)
Out = TypeVar("Out", float, int, bool, str)


@dataclass
class StatusSummaryAttributeIORef(AttributeIORef, Generic[In, Out]):
    """IO ref to accumulate underlying attributes into a high-level summary

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
    accumulator: Callable[[Iterable[In]], Out]
    _attributes: Sequence[AttrR[In]] | None = None
    _: KW_ONLY
    update_period: float | None = 0.2

    @property
    def attributes(self) -> Sequence[AttrR[In, AttributeIORef]]:
        if self._attributes is None:
            raise ValueError("Attributes must be set before using this IO")

        return self._attributes

    def set_attributes(self, attributes: Sequence[AttrR[In, AttributeIORef]]):
        self._attributes = attributes


class StatusSummaryAttributeIO(AttributeIO[Out, StatusSummaryAttributeIORef]):
    """AttributeIO for ``StatusSummaryAttributeIORef`` Attributes"""

    async def update(self, attr: AttrR[Out, StatusSummaryAttributeIORef[In, Out]]):
        values = [attribute.get() for attribute in attr.io_ref.attributes]
        await attr.update(attr.io_ref.accumulator(values))


def initialise_summary_attributes(controller):
    """Initialise summary attributes with dynamically created attributes"""

    for attribute in controller.attributes.values():
        if isinstance(attribute.io_ref, StatusSummaryAttributeIORef):
            attributes: Sequence[AttrR] = []
            for sub_controller in _filter_sub_controllers(
                controller, attribute.io_ref.path_filter
            ):
                try:
                    attr = sub_controller.attributes[attribute.io_ref.attribute_name]
                except KeyError as err:
                    raise KeyError(
                        f"Sub controller {sub_controller} does not have attribute "
                        f"'{attribute.io_ref.attribute_name}' required by {controller} "
                        f"status summary {attribute.io_ref.path_filter}"
                    ) from err
                if isinstance(attr, AttrR):
                    attributes.append(attr)

            attribute.io_ref.set_attributes(attributes)


def _filter_sub_controllers(
    controller: BaseController,
    path_filter: Sequence[str | tuple[str, ...] | re.Pattern],
) -> Iterable[BaseController]:
    sub_controller_map = controller.sub_controllers
    step = path_filter[0]
    is_leaf = len(path_filter) == 1

    match step:
        case str() as key:
            if key not in sub_controller_map:
                raise ValueError(f"Sub controller {key} not found in {controller}")
            sub_controller = sub_controller_map[key]
            if is_leaf:
                yield sub_controller
            else:
                yield from _filter_sub_controllers(sub_controller, path_filter[1:])

        case tuple() as keys:
            for key in keys:
                if key not in sub_controller_map:
                    raise ValueError(f"Sub controller {key} not found in {controller}")
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
                    f"Sub controller matching {pattern} not found in {controller}"
                )

            for sub_controller in sub_controllers:
                if is_leaf:
                    yield sub_controller
                else:
                    yield from _filter_sub_controllers(sub_controller, path_filter[1:])
