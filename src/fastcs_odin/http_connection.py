from collections.abc import Mapping

from aiohttp import ClientResponse, ClientSession

ValueType = bool | int | float | str
JsonElementary = str | int | float | bool | None
JsonType = JsonElementary | list["JsonType"] | Mapping[str, "JsonType"]


class HTTPConnection:
    DEFAULT_API_PREFIX = "api/0.1"
    REQUEST_METADATA_HEADER = {"Accept": "application/json;metadata=true"}

    def __init__(self, ip: str, port: int, api_prefix: str = DEFAULT_API_PREFIX):
        self._session: ClientSession | None = None
        self._ip = ip
        self._port = port
        self._api_prefix = api_prefix

    def full_url(self, uri: str) -> str:
        """Expand IP address, port and URI into full URL.

        Args:
            uri: Identifier for a resource for the current connection

        """
        return f"http://{self._ip}:{self._port}/{self._api_prefix}/{uri}"

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

    async def get_adapters(self) -> dict[str, JsonType]:
        """Get a list of adapters from the server.

        Returns: Response payload as JSON

        """
        return await self.get("adapters")

    async def get(self, uri: str, with_metadata: bool = False) -> dict[str, JsonType]:
        """Perform HTTP GET request and return response content as JSON.

        Args:
            uri: Identifier for resource

        Returns: Response payload as JSON

        """
        session = self.get_session()

        headers = self.REQUEST_METADATA_HEADER if with_metadata else None

        async with session.get(self.full_url(uri), headers=headers) as response:
            match await response.json():
                case dict() as d:
                    return d
                case _:
                    raise ValueError(f"Got unexpected response:\n{response}")

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
            return await response.json()

    async def close(self):
        """Close the underlying aiohttp ClientSession."""
        session = self.get_session()
        await session.close()
        self._session = None
