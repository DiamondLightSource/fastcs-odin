import json
import logging
import time
from collections import deque
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from enum import Enum
from statistics import mean, stdev
from typing import Any, Literal, TypeVar

from fastcs.controller import BaseController, SubController
from fastcs.datatypes import Bool, DataType, Float, Int, String
from pydantic import BaseModel, ConfigDict, ValidationError


def is_metadata_object(v: Any) -> bool:
    return isinstance(v, dict) and "writeable" in v and "type" in v and "value" in v


class AdapterType(str, Enum):
    FRAME_PROCESSOR = "FrameProcessorAdapter"
    FRAME_RECEIVER = "FrameReceiverAdapter"
    META_WRITER = "MetaListenerAdapter"
    EIGER_FAN = "EigerFanAdapter"
    GENERIC = "__generic__"


class OdinParameterMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: Any
    writeable: bool
    type: Literal["float", "int", "bool", "str"]
    allowed_values: dict[int, str] | None = None
    name: str | None = None
    description: str | None = None
    units: str | None = None
    display_precision: int | None = None

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


class AllowedCommandsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed: list[str]


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

        if "command" in node_path:
            # Do not parse and yield any command attributes
            # They are handled by the individual controllers
            continue
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
                # If the parameter has metadata, use it to resolve the parameter
                if isinstance(node_value, dict) and is_metadata_object(node_value):
                    if isinstance(node_value["value"], list):
                        # If the parameter is a list, expand it to separate parameters
                        yield from expand_list_parameter(node_value["value"], node_path)
                    elif isinstance(node_value["value"], dict):
                        # If the parameter is a dict, expand it to separate parameters
                        yield from expand_dict_parameter(node_value["value"], node_path)
                    else:
                        # Otherwise validate the parameter and yield it
                        yield (
                            node_path,
                            OdinParameterMetadata.model_validate(node_value),
                        )
                elif isinstance(node_value, list):
                    # If the parameter is a list, expand it to separate parameters
                    if "config" in node_path:
                        # TODO - treating odin data config lists as a special case is
                        #  likely unnecessary
                        yield from expand_list_parameter(node_value, node_path)
                    else:
                        # Convert read-only list to a string for display
                        yield (node_path, infer_metadata(str(node_value), node_path))

                else:
                    # TODO: This won't be needed when all parameters provide metadata
                    yield (node_path, infer_metadata(node_value, node_path))
            except ValidationError as e:
                logging.warning(
                    f"Type not supported for path {node_path} "
                    f"with value {node_value}:\n{e}"
                )


def expand_list_parameter(
    values: list[Any], path: list[str]
) -> Iterator[tuple[list[str], OdinParameterMetadata]]:
    """Expand a list parameter into separately indexed parameters.

    Args:
        values: list of values to expand
        path: list of path elements to this parameter in tree
    """
    for idx, sub_node_value in enumerate(values):
        # Append list index to parameter path
        sub_node_path = path + [str(idx)]
        # Yield expanded list parameter
        yield (
            sub_node_path,
            infer_metadata(sub_node_value, sub_node_path),
        )


def expand_dict_parameter(
    values: dict[str, Any], path: list[str]
) -> Iterator[tuple[list[str], OdinParameterMetadata]]:
    """Expand a dict parameter into separate parameters.

    Args:
        values: dict of values to expand
        path: list of path elements to this parameter in tree
    """
    for key, sub_node_value in values.items():
        # Append dict item key to parameter path
        sub_node_path = path + [key]
        # Yield expanded dict parameter
        yield (
            sub_node_path,
            infer_metadata(sub_node_value, sub_node_path),
        )


def infer_metadata(parameter: Any, uri: list[str]):
    """Create metadata for a parameter from its type and URI.

    Args:
        parameter: Value of parameter to create metadata for
        uri: URI of parameter in API.

    Raises:
        pydantic.ValidationError: if inferred metadata is not valid

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


def unpack_status_arrays(parameters: list[OdinParameter], uris: list[list[str]]):
    """Takes a list of OdinParameters and a list of uris. Search the parameter
    for elements that match the values in the uris list and split them into one
    new OdinParameter for each value.

    Args:
        parameters: List of OdinParameters
        uris: List of uris to search and replace

    Returns:
        Original list of parameters with elements in uris replaced with
        their indexed equivalent
    """
    removelist = []
    for parameter in parameters:
        if parameter.uri in uris:
            try:
                status_list = json.loads(parameter.metadata.value.replace("'", '"'))
            except (json.JSONDecodeError, AssertionError) as e:
                logging.warning(f"Failed to parse {parameter} value as a list:\n{e}")
                continue
            for idx, value in enumerate(status_list):
                parameters.append(
                    OdinParameter(
                        uri=parameter.uri + [str(idx)],
                        metadata=OdinParameterMetadata(
                            value=value,
                            type=parameter.metadata.type,
                            writeable=parameter.metadata.writeable,
                        ),
                    )
                )
            removelist.append(parameter)

    for value in removelist:
        parameters.remove(value)

    return parameters


class OdinRequestTimer:
    def __init__(
        self, name: str, num_samples: int = 100, log_level: int = logging.DEBUG
    ):
        self._name = name
        self._num_samples = num_samples
        self._samples = deque(maxlen=num_samples)
        self._count = 0
        self._logger = logging.getLogger("odin_request_timer")
        self._logger.setLevel(log_level)

    def __enter__(self):
        self._start = time.time()

    def __exit__(self, exc_type, exc_val, exc_tb):
        delta = (time.time() - self._start) * 1000
        self.add_sample(delta)

    def add_sample(self, sample):
        self._samples.append(sample)
        self._count += 1

        if self._count % (self._num_samples / 2) == 0:
            self._logger.debug(
                f"RequestTimer {self._name}: "
                f"<{mean(self._samples):.3f} +/- {stdev(self._samples):.3f} ms>"
            )
