"""Parameter tree caching for odin adapters."""

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from statistics import mean, stdev

from fastcs.logging import bind_logger
from fastcs.tracer import Tracer

from fastcs_odin.http_connection import HTTPConnection, JsonType, ValueType

TreeType = dict[str, JsonType]

logger = bind_logger(logger_name=__name__)


class AdapterResponseError(Exception):
    """Error raised when adapter returns an error response."""


class CacheRequestTimer(Tracer):
    """Context manager to time requests and log statistics."""

    def __init__(self, name: str, num_samples: int = 100):
        super().__init__()
        self._name = name
        self._num_samples = num_samples
        self._samples = deque(maxlen=num_samples)
        self._count = 0

    def __enter__(self):
        self._start = time.time()

    def __exit__(self, exc_type, exc_val, exc_tb):
        delta = (time.time() - self._start) * 1000
        self.add_sample(delta)

    def add_sample(self, sample):
        self._samples.append(sample)
        self._count += 1

        if self._count % (self._num_samples / 2) == 0:
            self.log_event(
                "CacheRequestTimer {name}: <{mean:.3f} +/- {stdev:.3f} ms>",
                name=self._name,
                mean=mean(self._samples),
                stdev=stdev(self._samples),
            )


@dataclass
class ParameterTreeCache:
    """Cache for parameter tree data from Odin adapters."""

    path_prefix: str
    connection: HTTPConnection
    _last_update: datetime | None = None
    _tree: TreeType = field(default_factory=dict)
    _update_event: asyncio.Event = field(default_factory=asyncio.Event)

    def __post_init__(self):
        """Intitialize the cache request timer and set the update event."""
        self._update_event.set()
        self.request_timer = CacheRequestTimer(self.path_prefix)

    def _has_expired(self, time_step: float) -> bool:
        """Check if the cache has expired based on the time step."""
        if self._last_update is None:
            return True
        delta_t = datetime.now() - self._last_update
        return delta_t.total_seconds() > time_step

    def _update_tree(self, tree: TreeType) -> None:
        """Update the cached parameter tree."""
        self._tree = tree
        self._last_update = datetime.now()

    def _resolve_value(self, path_elems: list[str], tree):
        """Resolve value for given path elements from tree."""
        if len(path_elems) == 1:
            if isinstance(tree, list):
                return tree[int(path_elems[0])]
            else:
                return tree[path_elems[0]]

        return self._resolve_value(path_elems[1:], tree[path_elems[0]])

    def _update_value(self, path_elems: list[str], value: JsonType, tree) -> None:
        """Update value for given path elements in tree."""
        if len(path_elems) == 1:
            tree[path_elems[0]] = value
            return

        self._update_value(path_elems[1:], value, tree[path_elems[0]])

    async def get(self, path: str, update_period: float | None) -> JsonType:
        """Get value from parameter tree cache, updating if expired."""
        if not update_period or self._has_expired(update_period):
            if self._update_event.is_set():
                self._update_event.clear()
                try:
                    with self.request_timer:
                        response = await self.connection.get(self.path_prefix)
                    match response:
                        case {"error": error}:
                            raise AdapterResponseError(error)
                        case _:
                            self._update_tree(response)
                except Exception as error:
                    logger.error(
                        "Update failed",
                        path_prefix=self.path_prefix,
                        path=path,
                        error=error,
                    )
                    raise AdapterResponseError(error) from error
                finally:
                    self._update_event.set()
            else:
                await self._update_event.wait()

        path_elems = path.split("/")
        value = self._resolve_value(path_elems, self._tree)
        return value

    async def put(self, path: str, value: ValueType) -> None:
        """Put value to parameter tree and update cache."""
        try:
            uri = f"{self.path_prefix}/{path}"
            response = await self.connection.put(uri, value)
            match response:
                case {"error": error}:
                    raise AdapterResponseError(error)
                case _:
                    path_elems = path.split("/")
                    new_value = response.get(path_elems[-1])  # type: ignore
                    self._update_value(path_elems[1:], new_value, self._tree)
        except Exception as error:
            logger.error(
                "Put {path} = {value} failed:\n{error}",
                path=path,
                value=value,
                error=error,
            )
            raise AdapterResponseError(error) from error
