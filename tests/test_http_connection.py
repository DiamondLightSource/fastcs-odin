from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import ClientResponseError, ContentTypeError
from pytest_mock import MockerFixture

from fastcs_odin.http_connection import HTTPConnection


@pytest.fixture
def connection():
    return HTTPConnection("127.0.0.1", 8080)


def make_mock_response():
    """Create a mock response and wire it as an async context manager.

    raise_for_status and read are sync; json is async.
    """
    mock_response = MagicMock()
    mock_response.json = AsyncMock()
    mock_response.read = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=mock_response)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx, mock_response


@pytest.fixture
def open_connection(connection):
    mock_session = MagicMock()
    mock_session.close = AsyncMock()
    connection._session = mock_session
    return connection, mock_session


def test_full_url(connection):
    assert (
        connection.full_url("api/0.1/status") == "http://127.0.0.1:8080/api/0.1/status"
    )


def test_get_session_raises_when_not_open(connection):
    with pytest.raises(ConnectionRefusedError, match="Session is not open"):
        connection.get_session()


def test_get_session_returns_session_when_open(open_connection):
    connection, mock_session = open_connection
    assert connection.get_session() is mock_session


@pytest.mark.asyncio
async def test_get_returns_json(open_connection):
    connection, mock_session = open_connection
    ctx, mock_response = make_mock_response()
    mock_response.json.return_value = {"value": 42}
    mock_session.get.return_value = ctx

    result = await connection.get("api/0.1/status")

    mock_session.get.assert_called_once_with(
        "http://127.0.0.1:8080/api/0.1/status", headers=None
    )
    mock_response.raise_for_status.assert_called_once()
    assert result == {"value": 42}


@pytest.mark.asyncio
async def test_get_raises_on_bad_status(open_connection, mocker: MockerFixture):
    connection, mock_session = open_connection
    ctx, mock_response = make_mock_response()
    mock_response.raise_for_status.side_effect = ClientResponseError(
        mocker.Mock(), mocker.Mock()
    )
    mock_session.get.return_value = ctx

    with pytest.raises(ClientResponseError):
        await connection.get("api/0.1/status")


@pytest.mark.asyncio
async def test_get_raises_on_non_json_response(open_connection, mocker: MockerFixture):
    connection, mock_session = open_connection
    ctx, mock_response = make_mock_response()
    mock_response.json.side_effect = ContentTypeError(mocker.Mock(), mocker.Mock())
    mock_session.get.return_value = ctx

    with pytest.raises(ValueError, match="Failed to parse response as json"):
        await connection.get("api/0.1/status")


@pytest.mark.asyncio
async def test_get_passes_headers(open_connection):
    connection, mock_session = open_connection
    ctx, mock_response = make_mock_response()
    mock_response.json.return_value = {}
    mock_session.get.return_value = ctx

    await connection.get("api/0.1/status", headers={"Accept": "application/json"})

    mock_session.get.assert_called_once_with(
        "http://127.0.0.1:8080/api/0.1/status", headers={"Accept": "application/json"}
    )


@pytest.mark.asyncio
async def test_get_bytes_returns_response_and_bytes(open_connection):
    connection, mock_session = open_connection
    ctx, mock_response = make_mock_response()
    mock_response.read.return_value = b"raw data"
    mock_session.get.return_value = ctx

    response, data = await connection.get_bytes("api/0.1/image")

    assert response is mock_response
    assert data == b"raw data"


@pytest.mark.asyncio
async def test_put_returns_json(open_connection):
    connection, mock_session = open_connection
    ctx, mock_response = make_mock_response()
    mock_response.json.return_value = {"result": "ok"}
    mock_session.put.return_value = ctx

    result = await connection.put("api/0.1/config/frames", 10)

    mock_session.put.assert_called_once_with(
        "http://127.0.0.1:8080/api/0.1/config/frames",
        json=10,
        headers={"Content-Type": "application/json"},
    )
    assert result == {"result": "ok"}


@pytest.mark.asyncio
async def test_put_returns_empty_dict_on_non_json_response(
    open_connection, loguru_caplog
):
    connection, mock_session = open_connection
    ctx, mock_response = make_mock_response()
    mock_response.json.side_effect = ContentTypeError(MagicMock(), MagicMock())
    mock_session.put.return_value = ctx

    result = await connection.put("api/0.1/config/frames", 10)

    assert result == {}
    assert "Put response was not json" in loguru_caplog.text


@pytest.mark.asyncio
async def test_close(open_connection):
    connection, mock_session = open_connection

    await connection.close()

    mock_session.close.assert_called_once()
    assert connection._session is None


@pytest.mark.asyncio
async def test_close_raises_when_not_open(connection):
    with pytest.raises(ConnectionRefusedError, match="Session is not open"):
        await connection.close()
