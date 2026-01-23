from collections.abc import Mapping

from aiohttp import ClientResponse, ClientSession, ContentTypeError
from fastcs.logging import bind_logger

ValueType = bool | int | float | str
JsonElementary = str | int | float | bool | None
JsonType = JsonElementary | list["JsonType"] | Mapping[str, "JsonType"]


logger = bind_logger(__name__)


class HTTPConnection:
    def __init__(self, ip: str, port: int):
        self._session: ClientSession | None = None
        self._ip = ip
        self._port = port

    def full_url(self, uri: str) -> str:
        """Expand IP address, port and URI into full URL.

        Args:
            uri: Identifier for a resource for the current connection

        """
        return f"http://{self._ip}:{self._port}/{uri}"

    def open(self):
        """Create the underlying aiohttp ClientSession.

        When called the session will be created in the context of the current running
        asyncio loop.

        """
        self._session = ClientSession()

    def get_session(self) -> ClientSession:
        """Get session or raise exception if session is not open.

        Returns: Current aiohttp session if connection is open

        Raises: ConnectionRefusedError if the connection is not open

        """
        if self._session is not None:
            return self._session

        raise ConnectionRefusedError("Session is not open")

    async def get(self, uri: str, headers: dict | None = None) -> dict[str, JsonType]:
        """Perform HTTP GET request and return response content as JSON.

        Args:
            uri: Identifier for resource

        Returns: Response payload as JSON

        Raises:
            ClientResponseError: if response is not successful
            ValueError: if response is not json

        """
        session = self.get_session()
        async with session.get(self.full_url(uri), headers=headers) as response:
            response.raise_for_status()

            try:
                return await response.json()
            except ContentTypeError as e:
                raise ValueError("Failed to parse response as json") from e

    async def get_bytes(self, uri: str) -> tuple[ClientResponse, bytes]:
        """Perform HTTP GET request and return response content as bytes.

        Args:
            uri: Identifier for resource

        Returns: ClientResponse header and response payload as bytes

        """
        session = self.get_session()
        async with session.get(self.full_url(uri)) as response:
            return response, await response.read()

    async def put(self, uri: str, value: ValueType) -> JsonType:
        """Perform HTTP PUT request and return response content as json.

        If successful, the response is a list of parameters whose values may have
        changed as a result of the change.

        Args:
            uri: Identifier for resource

        Returns: ClientResponse header and response payload as bytes

        """
        session = self.get_session()
        async with session.put(
            self.full_url(uri),
            json=value,
            headers={"Content-Type": "application/json"},
        ) as response:
            response.raise_for_status()

            try:
                return await response.json()
            except ContentTypeError:
                logger.warning("Put response was not json", uri=uri, response=response)
                return {}

    async def close(self):
        """Close the underlying aiohttp ClientSession."""
        session = self.get_session()
        await session.close()
        self._session = None
