import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from pytest_mock import MockerFixture

from fastcs_odin.frame_processor import (
    FrameProcessorAdapterController,
    FrameProcessorController,
)
from fastcs_odin.frame_receiver import (
    FrameReceiverAdapterController,
    FrameReceiverController,
)
from fastcs_odin.util import (
    OdinParameter,
    OdinParameterMetadata,
    create_odin_parameters,
    infer_metadata,
)

HERE = Path(__file__).parent


def test_one_node_fp():
    with (HERE / "input/one_node_fp_response.json").open() as f:
        response = json.loads(f.read())

    parameters = create_odin_parameters(response)
    assert len(parameters) == 97


def test_two_node_fp():
    with (HERE / "input/two_node_fp_response.json").open() as f:
        response = json.loads(f.read())

    parameters = create_odin_parameters(response)
    assert len(parameters) == 190


@pytest.mark.asyncio
async def test_fp_initialise(mocker: MockerFixture):
    with (HERE / "input/two_node_fp_response.json").open() as f:
        response = json.loads(f.read())

    async def get_plugins(idx: int):
        return response[str(idx)]["status"]["plugins"]

    mock_connection = mocker.MagicMock()
    mock_connection.get.side_effect = [get_plugins(0), get_plugins(1)]

    parameters = create_odin_parameters(response)
    controller = FrameProcessorAdapterController(mock_connection, parameters, "prefix")
    await controller.initialise()
    assert all(fpx in controller.get_sub_controllers() for fpx in ("FP0", "FP1"))
    assert all(
        isinstance(fpx, FrameProcessorController)
        for fpx in controller.get_sub_controllers().values()
    )


def test_two_node_fr():
    with (HERE / "input/two_node_fr_response.json").open() as f:
        response = json.loads(f.read())

    parameters = create_odin_parameters(response)
    assert len(parameters) == 82


@pytest.mark.asyncio
async def test_fr_initialise(mocker: MockerFixture):
    with (HERE / "input/two_node_fr_response.json").open() as f:
        response = json.loads(f.read())

    mock_connection = mocker.MagicMock()

    parameters = create_odin_parameters(response)
    controller = FrameReceiverAdapterController(mock_connection, parameters, "prefix")
    await controller.initialise()
    assert all(frx in controller.get_sub_controllers() for frx in ("FR0", "FR1"))
    assert all(
        isinstance(frx, FrameReceiverController)
        for frx in controller.get_sub_controllers().values()
    )


def test_node_with_empty_list_is_correctly_counted():
    parameters = create_odin_parameters({"test": []})
    names = [p.name for p in parameters]
    assert "test" in names
    assert len(parameters) == 1


def test_node_that_has_metadata_only_counts_once():
    data = {"count": {"value": 1, "writeable": False, "type": "int"}}
    parameters = create_odin_parameters(data)
    assert len(parameters) == 1


def test_nested_node_gives_correct_name():
    data = {"top": {"nest-1": {"nest-2": 1}}}
    parameters = create_odin_parameters(data)
    assert len(parameters) == 1
    assert parameters[0].name == "top_nest-1_nest-2"


def test_config_node_splits_list_into_mutiples():
    data = {"config": {"param": [1, 2]}}
    parameters = create_odin_parameters(data)
    assert len(parameters) == 2


def test_invalid_list_param():
    data = {
        "count": {"value": 1, "writeable": False, "type": "list"},
    }
    parameters = create_odin_parameters(data)
    assert len(parameters) == 0


def test_infer_metadata():
    metadata = infer_metadata(1, ["status", "count"])

    assert metadata == OdinParameterMetadata(value=1, type="int", writeable=False)


def test_infer_metadata_config():
    metadata = infer_metadata(1, ["config", "count"])

    assert metadata == OdinParameterMetadata(value=1, type="int", writeable=True)


def test_infer_metadata_raises():
    with pytest.raises(ValidationError):
        infer_metadata([], ["count"])


def test_walk_odin_metadata():
    # Test each possible case for parameter generation
    data = {
        "count": {"value": 1, "writeable": False, "type": "int"},  # Metadata provided
        "config": {"chunks": [1]},  # List value, no metadata and writeable
        "status": {"values": [1]},  # List value, no metadata and read only
        "test": True,  # No metadata provided
    }
    parameters = create_odin_parameters(data)
    metadata = OdinParameterMetadata(value=1, type="int", writeable=False)
    assert parameters[0] == OdinParameter(uri=["count"], metadata=metadata)

    metadata_config = OdinParameterMetadata(value=1, type="int", writeable=True)
    uri_config = ["config", "chunks", "0"]
    assert parameters[1] == OdinParameter(uri=uri_config, metadata=metadata_config)

    metadata_config = OdinParameterMetadata(value="[1]", type="str", writeable=False)
    uri_config = ["status", "values"]
    assert parameters[2] == OdinParameter(uri=uri_config, metadata=metadata_config)

    metadata_config = OdinParameterMetadata(value=True, type="bool", writeable=False)
    assert parameters[3] == OdinParameter(uri=["test"], metadata=metadata_config)
