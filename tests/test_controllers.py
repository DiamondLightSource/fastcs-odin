import json
import re
from pathlib import Path

import pytest
from fastcs.attributes import AttrR, AttrRW
from fastcs.connections.ip_connection import IPConnectionSettings
from fastcs.datatypes import Bool, Float, Int
from pytest_mock import MockerFixture

from fastcs_odin.eiger_fan import EigerFanAdapterController
from fastcs_odin.frame_processor import (
    FrameProcessorAdapterController,
    FrameProcessorController,
    FrameProcessorPluginController,
)
from fastcs_odin.frame_receiver import (
    FrameReceiverAdapterController,
    FrameReceiverController,
    FrameReceiverDecoderController,
)
from fastcs_odin.http_connection import HTTPConnection
from fastcs_odin.meta_writer import MetaWriterAdapterController
from fastcs_odin.odin_adapter_controller import (
    ConfigFanSender,
    ParamTreeHandler,
    StatusSummaryUpdater,
)
from fastcs_odin.odin_controller import OdinAdapterController, OdinController
from fastcs_odin.util import AdapterType, OdinParameter, OdinParameterMetadata

HERE = Path(__file__).parent


def test_create_attributes():
    parameters = [
        OdinParameter(
            uri=["read_int"],
            metadata=OdinParameterMetadata(value=0, type="int", writeable=False),
        ),
        OdinParameter(
            uri=["write_bool"],
            metadata=OdinParameterMetadata(value=True, type="bool", writeable=True),
        ),
        OdinParameter(
            uri=["group", "float"],
            metadata=OdinParameterMetadata(value=0.1, type="float", writeable=True),
        ),
    ]
    controller = OdinAdapterController(HTTPConnection("", 0), parameters, "api/0.1")

    controller._create_attributes()

    match controller.attributes:
        case {
            "read_int": AttrR(datatype=Int()),
            "write_bool": AttrRW(datatype=Bool()),
            "group_float": AttrR(datatype=Float(), group="Group"),
        }:
            pass
        case _:
            pytest.fail("Controller Attributes not as expected")


@pytest.mark.asyncio
async def test_create_commands(mocker: MockerFixture):
    mock_connection = mocker.AsyncMock()
    with (HERE / "input/two_node_fp_response.json").open() as f:
        response = json.loads(f.read())

    mock_connection.get.side_effect = [
        response[str(0)]["command"]["hdf"],
    ]

    controller = FrameProcessorPluginController(mock_connection, [], "api/0.1")
    controller._path = ["hdf"]

    await controller._create_commands()

    # Call the command methods that have been bound to the controller
    await controller.command1()  # type: ignore
    await controller.command2()  # type: ignore


def test_fp_process_parameters():
    parameters = [
        OdinParameter(
            ["0", "status", "hdf", "frames_written"],
            metadata=OdinParameterMetadata(value=0, type="int", writeable=False),
        ),
        OdinParameter(
            ["0", "config", "hdf", "frames"],
            metadata=OdinParameterMetadata(value=0, type="int", writeable=True),
        ),
    ]

    fpc = FrameProcessorController(HTTPConnection("", 0), parameters, "api/0.1")

    fpc._process_parameters()
    assert fpc.parameters == [
        OdinParameter(
            uri=["status", "hdf", "frames_written"],
            _path=["hdf", "frames_written"],
            metadata=OdinParameterMetadata(value=0, type="int", writeable=False),
        ),
        OdinParameter(
            uri=["config", "hdf", "frames"],
            _path=["hdf", "frames"],
            metadata=OdinParameterMetadata(value=0, type="int", writeable=True),
        ),
    ]


@pytest.mark.asyncio
async def test_create_adapter_controller(mocker: MockerFixture):
    controller = OdinController(IPConnectionSettings("", 0))
    controller.connection = mocker.AsyncMock()
    parameters = [
        OdinParameter(
            ["0"], metadata=OdinParameterMetadata(value=0, type="int", writeable=False)
        )
    ]

    ctrl = controller._create_adapter_controller(
        controller.connection, parameters, "fp", AdapterType.FRAME_PROCESSOR
    )
    assert isinstance(ctrl, FrameProcessorAdapterController)

    ctrl = controller._create_adapter_controller(
        controller.connection, parameters, "fr", AdapterType.FRAME_RECEIVER
    )
    assert isinstance(ctrl, FrameReceiverAdapterController)

    ctrl = controller._create_adapter_controller(
        controller.connection, parameters, "mw", AdapterType.META_WRITER
    )
    assert isinstance(ctrl, MetaWriterAdapterController)

    ctrl = controller._create_adapter_controller(
        controller.connection, parameters, "ef", AdapterType.EIGER_FAN
    )
    assert isinstance(ctrl, EigerFanAdapterController)

    ctrl = controller._create_adapter_controller(
        controller.connection, parameters, "od", "OtherAdapter"
    )
    assert isinstance(ctrl, OdinAdapterController)


@pytest.mark.parametrize(
    "mock_get, expected_controller",
    [
        [
            [{"adapters": ["test_adapter"]}, {"": {"value": "test_module"}}],
            OdinAdapterController,
        ],
        [
            [
                {"adapters": ["test_adapter"]},
                {"module": {"value": "FrameProcessorAdapter"}},
            ],
            FrameProcessorAdapterController,
        ],
    ],
)
@pytest.mark.asyncio
async def test_controller_initialise(
    mocker: MockerFixture, mock_get, expected_controller
):
    controller = OdinController(IPConnectionSettings("", 0))

    controller.connection = mocker.AsyncMock()
    controller.connection.open = mocker.MagicMock()

    controller.connection.get.side_effect = mock_get

    await controller.initialise()

    assert isinstance(
        controller.get_sub_controllers()["TEST_ADAPTER"], expected_controller
    )


@pytest.mark.asyncio
async def test_fp_create_plugin_sub_controllers(mocker: MockerFixture):
    mock_connection = mocker.AsyncMock()
    with (HERE / "input/two_node_fp_response.json").open() as f:
        response = json.loads(f.read())

    mock_connection.get.side_effect = [
        response[str(0)]["command"]["hdf"],
    ]

    parameters = [
        OdinParameter(
            uri=["config", "ctrl_endpoint"],
            _path=["ctrl_endpoint"],
            metadata=OdinParameterMetadata(value="", type="str", writeable=True),
        ),
        OdinParameter(
            uri=["status", "hdf", "frames_written"],
            _path=["hdf", "frames_written"],
            metadata=OdinParameterMetadata(value=0, type="int", writeable=False),
        ),
        OdinParameter(
            uri=["status", "hdf", "dataset", "compressed_size", "compression"],
            _path=["hdf", "dataset", "compressed_size", "compression"],
            metadata=OdinParameterMetadata(value="", type="str", writeable=False),
        ),
    ]

    fpc = FrameProcessorController(mock_connection, parameters, "api/0.1")

    await fpc._create_plugin_sub_controllers(["hdf"])

    # Check that hdf parameter has been split into a sub controller
    assert fpc.parameters == [
        OdinParameter(
            uri=["config", "ctrl_endpoint"],
            _path=["ctrl_endpoint"],
            metadata=OdinParameterMetadata(value="", type="str", writeable=True),
        )
    ]
    controllers = fpc.get_sub_controllers()
    match controllers:
        case {
            "HDF": FrameProcessorPluginController(
                parameters=[
                    OdinParameter(
                        uri=["status", "hdf", "frames_written"],
                        _path=["frames_written"],
                        metadata=OdinParameterMetadata(
                            value=0, type="int", writeable=False
                        ),
                    )
                ]
            )
        }:
            sub_controllers = controllers["HDF"].get_sub_controllers()
            assert "DS" in sub_controllers
            assert isinstance(sub_controllers["DS"], OdinAdapterController)
            assert sub_controllers["DS"].parameters == [
                OdinParameter(
                    uri=["status", "hdf", "dataset", "compressed_size", "compression"],
                    _path=["compressed_size", "compression"],
                    metadata=OdinParameterMetadata(
                        value="", type="str", writeable=False
                    ),
                )
            ]
        case _:
            pytest.fail("Sub controllers not as expected")


@pytest.mark.asyncio
async def test_param_tree_handler_update(mocker: MockerFixture):
    controller = OdinAdapterController(mocker.AsyncMock(), [], "")
    controller.connection = mocker.AsyncMock()
    attr = mocker.MagicMock(dtype=int)

    handler = ParamTreeHandler("hdf/frames_written")

    controller.connection.get.return_value = {"frames_written": 20}
    await handler.initialise(controller)
    await handler.update(attr)
    attr.set.assert_called_once_with(20)


@pytest.mark.asyncio
async def test_param_tree_handler_update_exception(mocker: MockerFixture):
    controller = OdinAdapterController(mocker.AsyncMock(), [], "")
    controller.connection = mocker.AsyncMock()
    attr = mocker.MagicMock(dtype=int)

    handler = ParamTreeHandler("hdf/frames_written")

    controller.connection.get.return_value = {"frames_wroted": 20}
    error_mock = mocker.patch("fastcs_odin.odin_adapter_controller.logging.error")
    await handler.initialise(controller)
    await handler.update(attr)
    error_mock.assert_called_once_with(
        "Update loop failed for %s:\n%s", "hdf/frames_written", mocker.ANY
    )


@pytest.mark.asyncio
async def test_param_tree_handler_put(mocker: MockerFixture):
    controller = OdinAdapterController(mocker.AsyncMock(), [], "")
    controller.connection = mocker.AsyncMock()
    attr = mocker.MagicMock()

    handler = ParamTreeHandler("hdf/frames")

    # Test put
    await handler.initialise(controller)
    await handler.put(attr, 10)
    controller.connection.put.assert_called_once_with("hdf/frames", 10)


@pytest.mark.asyncio
async def test_param_tree_handler_put_exception(mocker: MockerFixture):
    controller = OdinAdapterController(mocker.AsyncMock(), [], "")
    controller.connection = mocker.AsyncMock()
    attr = mocker.MagicMock()

    handler = ParamTreeHandler("hdf/frames")

    controller.connection.put.return_value = {"error": "No, you can't do that"}
    error_mock = mocker.patch("fastcs_odin.odin_adapter_controller.logging.error")
    await handler.initialise(controller)
    await handler.put(attr, -1)
    error_mock.assert_called_once_with(
        "Put %s = %s failed:\n%s", "hdf/frames", -1, mocker.ANY
    )


@pytest.mark.asyncio
async def test_param_tree_handler_casts_value_to_attr_dtype(mocker: MockerFixture):
    controller_mock = mocker.MagicMock()
    get_mock = mocker.AsyncMock()
    get_mock.return_value = {"error": ["error1", "error2"]}
    controller_mock.connection.get = get_mock
    attribute_mock = mocker.MagicMock()
    set_mock = mocker.AsyncMock()
    attribute_mock.set = set_mock
    handler = ParamTreeHandler("fp/0/status/error")
    handler._controller = controller_mock
    await handler.update(attribute_mock)
    attribute_mock.dtype.assert_called_once_with(["error1", "error2"])
    set_mock.assert_called_once_with(attribute_mock.dtype.return_value)


@pytest.mark.asyncio
async def test_status_summary_updater(mocker: MockerFixture):
    controller = mocker.MagicMock()
    od_controller = mocker.MagicMock()
    fp_controller = mocker.MagicMock()
    fpx_controller = mocker.MagicMock()
    hdf_controller = mocker.MagicMock()
    attr = mocker.AsyncMock()

    controller.get_sub_controllers.return_value = {"OD": od_controller}
    od_controller.get_sub_controllers.return_value = {"FP": fp_controller}
    fp_controller.get_sub_controllers.return_value = {
        "FP0": fpx_controller,
        "FP1": fpx_controller,
    }
    fpx_controller.get_sub_controllers.return_value = {"HDF": hdf_controller}

    hdf_controller.attributes["frames_written"].get.return_value = 50

    handler = StatusSummaryUpdater(
        ["OD", ("FP",), re.compile("FP*"), "HDF"], "frames_written", sum
    )
    await handler.initialise(controller)
    await handler.update(attr)
    attr.set.assert_called_once_with(100)

    handler = StatusSummaryUpdater(
        ["OD", ("FP",), re.compile("FP*"), ("HDF",)], "writing", any
    )

    hdf_controller.attributes["writing"].get.side_effect = [True, False]
    await handler.initialise(controller)
    await handler.update(attr)
    attr.set.assert_called_with(True)

    hdf_controller.attributes["writing"].get.side_effect = [False, False]
    await handler.initialise(controller)
    await handler.update(attr)
    attr.set.assert_called_with(False)


@pytest.mark.asyncio
@pytest.mark.parametrize("mock_sub_controller", ("FP", ("FP",), re.compile("FP")))
async def test_status_summary_updater_raise_exception(
    mock_sub_controller, mocker: MockerFixture
):
    controller = mocker.MagicMock()
    attr = mocker.AsyncMock()
    controller.get_sub_controllers.return_value = {"OD": mocker.MagicMock()}

    handler = StatusSummaryUpdater(["OD", mock_sub_controller], "writing", any)
    await handler.initialise(controller)

    with pytest.raises(ValueError, match="not found"):
        await handler.update(attr)


@pytest.mark.asyncio
async def test_config_fan_sender(mocker: MockerFixture):
    controller = mocker.MagicMock()
    attr = mocker.MagicMock(AttrRW)
    attr1 = mocker.AsyncMock()
    attr2 = mocker.AsyncMock()

    handler = ConfigFanSender([attr1, attr2])

    await handler.initialise(controller)
    await handler.put(attr, 10)
    attr1.process.assert_called_once_with(10)
    attr2.process.assert_called_once_with(10)
    attr.set.assert_called_once_with(10)


@pytest.mark.asyncio
async def test_frame_reciever_controllers():
    valid_non_decoder_parameter = OdinParameter(
        uri=["0", "status", "buffers", "total"],
        metadata=OdinParameterMetadata(value=292, type="int", writeable=True),
    )
    valid_decoder_parameter = OdinParameter(
        uri=["0", "status", "decoder", "packets_dropped"],
        metadata=OdinParameterMetadata(value=0, type="int", writeable=False),
    )

    invalid_decoder_parameter = OdinParameter(
        uri=["0", "status", "decoder", "name"],
        metadata=OdinParameterMetadata(
            value="DummyUDPFrameDecoder", type="str", writeable=False
        ),
    )
    parameters = [
        valid_non_decoder_parameter,
        valid_decoder_parameter,
        invalid_decoder_parameter,
    ]
    fr_controller = FrameReceiverController(
        HTTPConnection("", 0), parameters, "api/0.1"
    )
    await fr_controller.initialise()
    assert isinstance(fr_controller, FrameReceiverController)
    assert valid_non_decoder_parameter in fr_controller.parameters
    assert len(fr_controller.parameters) == 1
    assert "DECODER" in fr_controller.get_sub_controllers()

    decoder_controller = fr_controller.get_sub_controllers()["DECODER"]
    assert isinstance(decoder_controller, FrameReceiverDecoderController)
    assert valid_decoder_parameter in decoder_controller.parameters
    assert invalid_decoder_parameter not in decoder_controller.parameters
    # index, status, decoder parts removed from path
    assert decoder_controller.parameters[0]._path == ["packets_dropped"]
