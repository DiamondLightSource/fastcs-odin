import logging
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, TypeVar

from fastcs.controller import BaseController, SubController
from fastcs.datatypes import Bool, DataType, Float, Int, String
from pydantic import BaseModel, ConfigDict, ValidationError


def is_metadata_object(v: Any) -> bool:
    return isinstance(v, dict) and "writeable" in v and "type" in v


class AdapterType(str, Enum):
    FRAME_PROCESSOR = "FrameProcessorAdapter"
    FRAME_RECEIVER = "FrameReceiverAdapter"
    META_WRITER = "MetaListenerAdapter"
    EIGER_FAN = "EigerFanAdapter"


class OdinParameterMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: Any
    writeable: bool
    type: Literal["float", "int", "bool", "str"]
    allowed_values: dict[int, str] | None = None

    @property
    def fastcs_datatype(self) -> DataType:
        match self.type:
            case "float":
                return Float()
            case "int":
                return Int()
            case "bool":
                return Bool()
            case "str":
                return String()


@dataclass
class OdinParameter:
    uri: list[str]
    """Full URI."""
    metadata: OdinParameterMetadata
    """JSON response from GET of parameter."""

    _path: list[str] = field(default_factory=list)

    @property
    def path(self) -> list[str]:
        """Reduced path of parameter to override uri when constructing name."""
        return self._path or self.uri

    @property
    def name(self) -> str:
        """Unique name of parameter."""
        return "_".join(self.path)

    def set_path(self, path: list[str]):
        """Set reduced path of parameter to override uri when constructing name."""
        self._path = path


def create_odin_parameters(metadata: Mapping[str, Any]) -> list[OdinParameter]:
    """Walk metadata and create parameters for the leaves, flattening path with '/'s.

    Args:
        metadata: JSON metadata from odin server

    Returns":
        List of ``OdinParameter``

    """
    return [
        OdinParameter(uri=uri, metadata=metadata)
        for uri, metadata in _walk_odin_metadata(metadata, [])
    ]


def _walk_odin_metadata(
    tree: Mapping[str, Any], path: list[str]
) -> Iterator[tuple[list[str], OdinParameterMetadata]]:
    """Walk through tree and yield the leaves and their paths.

    Args:
        tree: Tree to walk
        path: Path down tree so far

    Returns:
        (path to leaf, value of leaf)

    """
    for node_name, node_value in tree.items():
        node_path = path + [node_name]

        # Branches - dict or list[dict] to recurse through
        if isinstance(node_value, dict) and not is_metadata_object(node_value):
            yield from _walk_odin_metadata(node_value, node_path)
        elif (
            isinstance(node_value, list)
            and node_value  # Exclude parameters with an empty list as a value
            and all(isinstance(m, dict) for m in node_value)
        ):
            for idx, sub_node in enumerate(node_value):
                sub_node_path = node_path + [str(idx)]
                yield from _walk_odin_metadata(sub_node, sub_node_path)
        else:
            # Leaves
            try:
                if isinstance(node_value, dict) and is_metadata_object(node_value):
                    yield (node_path, OdinParameterMetadata.model_validate(node_value))
                elif isinstance(node_value, list):
                    if "config" in node_path:
                        # Split list into separate parameters so they can be set
                        for idx, sub_node_value in enumerate(node_value):
                            sub_node_path = node_path + [str(idx)]
                            yield (
                                sub_node_path,
                                infer_metadata(sub_node_value, sub_node_path),
                            )
                    else:
                        # Convert read-only list to a string for display
                        yield (node_path, infer_metadata(str(node_value), node_path))

                else:
                    # TODO: This won't be needed when all parameters provide metadata
                    yield (node_path, infer_metadata(node_value, node_path))
            except ValidationError as e:
                logging.warning(f"Type not supported:\n{e}")


def infer_metadata(parameter: Any, uri: list[str]):
    """Create metadata for a parameter from its type and URI.

    Args:
        parameter: Value of parameter to create metadata for
        uri: URI of parameter in API.

    Raises:
        Validation error if type isn't supported

    """
    metadata_dict = {
        "value": parameter,
        "type": type(parameter).__name__,
        "writeable": "config" in uri,
    }

    return OdinParameterMetadata.model_validate(metadata_dict)


T = TypeVar("T")


def partition(
    elements: list[T], predicate: Callable[[T], bool]
) -> tuple[list[T], list[T]]:
    """Split a list of elements in two based on predicate.

    If the predicate returns ``True``, the element will be placed in the truthy list,
    if it does not, it will be placed in the falsy list.

    Args:
        elements: List of T
        predicate: Predicate to filter the list with

    Returns:
        (truthy, falsy)

    """
    truthy: list[T] = []
    falsy: list[T] = []
    for parameter in elements:
        if predicate(parameter):
            truthy.append(parameter)
        else:
            falsy.append(parameter)

    return truthy, falsy


def get_all_sub_controllers(
    controller: BaseController,
) -> list[SubController]:
    return list(_walk_sub_controllers(controller))


def _walk_sub_controllers(
    controller: BaseController,
) -> Iterable[SubController]:
    for sub_controller in controller.get_sub_controllers().values():
        yield sub_controller
        yield from _walk_sub_controllers(sub_controller)
