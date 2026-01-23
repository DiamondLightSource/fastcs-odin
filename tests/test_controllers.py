import json
import re
from functools import partial
from pathlib import Path

import pytest
from fastcs.attributes import AttrR, AttrRW
from fastcs.connections import IPConnectionSettings
from fastcs.controllers import Controller
from fastcs.datatypes import Bool, Float, Int
from pytest_mock import MockerFixture

from fastcs_odin.controllers.odin_controller import OdinController, OdinSubController
from fastcs_odin.controllers.odin_data.frame_processor import (
    FrameProcessorAdapterController,
    FrameProcessorController,
    FrameProcessorPluginController,
)
from fastcs_odin.controllers.odin_data.frame_receiver import (
    FrameReceiverAdapterController,
    FrameReceiverController,
)
from fastcs_odin.controllers.odin_data.meta_writer import MetaWriterAdapterController
from fastcs_odin.http_connection import HTTPConnection
from fastcs_odin.io.config_fan_sender_attribute_io import (
    ConfigFanAttributeIO,
    ConfigFanAttributeIORef,
)
from fastcs_odin.io.parameter_attribute_io import (
    ParameterTreeAttributeIO,
    ParameterTreeAttributeIORef,
)
from fastcs_odin.io.parameter_cache import AdapterResponseError
from fastcs_odin.io.status_summary_attribute_io import (
    StatusSummaryAttributeIO,
    StatusSummaryAttributeIORef,
    initialise_summary_attributes,
)
from fastcs_odin.util import (
    AdapterType,
    OdinParameter,
    OdinParameterMetadata,
    create_attribute,
)

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
    controller = OdinSubController(HTTPConnection("", 0), parameters, "api/0.1", [])

    for parameter in controller.parameters:
        controller.add_attribute(
            parameter.name,
            create_attribute(parameter=parameter, adapter=controller._adapter),
        )

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
        {"allowed": response[str(0)]["command"]["hdf"]["allowed"]},
        {"response": "No commands, path invalid"},
    ]

    controller = FrameProcessorPluginController(mock_connection, [], "api/0.1", [])
    controller._path = ["hdf"]

    await controller._create_commands()

    # Call the command methods that have been bound to the controller
    await controller.command1()  # type: ignore
    await controller.command2()  # type: ignore

    controller = FrameProcessorPluginController(mock_connection, [], "api/0.1", [])
    controller._path = ["offset"]

    await controller._create_commands()


@pytest.mark.asyncio
async def test_fp_process_parameters_during_initialise(mocker: MockerFixture):
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

    mock_connection = mocker.AsyncMock()
    mock_connection.get.return_value = {"names": ["plugin_a", "plugin_b"]}

    fpc = FrameProcessorController(mock_connection, parameters, "api/0.1", [])

    await fpc.initialise()
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
        controller.connection, parameters, "od", "OtherAdapter"
    )
    assert isinstance(ctrl, OdinSubController)


@pytest.mark.parametrize(
    "mock_get, expected_controller",
    [
        [
            [{"": {"value": "test_module"}}],
            OdinSubController,
        ],
        [
            [{"module": {"value": "FrameProcessorAdapter"}}],
            FrameProcessorAdapterController,
        ],
    ],
)
@pytest.mark.asyncio
async def test_controller_initialise(
    mocker: MockerFixture, mock_get, expected_controller
):
    # Status summary attributes won't work without real sub controllers
    mocker.patch(
        "fastcs_odin.controllers.odin_controller.initialise_summary_attributes"
    )
    mocker.patch(
        "fastcs_odin.controllers.odin_data.odin_data_adapter.initialise_summary_attributes"
    )

    controller = OdinController(IPConnectionSettings("", 0))

    controller.connection = mocker.AsyncMock()
    controller.connection.open = mocker.MagicMock()

    controller.connection.get_adapters.side_effect = [{"adapters": ["test_adapter"]}]
    controller.connection.get.side_effect = mock_get

    await controller.initialise()

    assert isinstance(controller.sub_controllers["TESTADAPTER"], expected_controller)


@pytest.mark.asyncio
async def test_fp_create_plugin_sub_controllers(mocker: MockerFixture):
    mock_connection = mocker.AsyncMock()
    with (HERE / "input/two_node_fp_response.json").open() as f:
        response = json.loads(f.read())

    mock_connection.get.side_effect = [
        {"allowed": response[str(0)]["command"]["hdf"]["allowed"]},
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

    fpc = FrameProcessorController(mock_connection, parameters, "api/0.1", [])

    await fpc._create_plugin_sub_controllers(["hdf"])

    # Check that hdf parameter has been split into a sub controller
    assert fpc.parameters == [
        OdinParameter(
            uri=["config", "ctrl_endpoint"],
            _path=["ctrl_endpoint"],
            metadata=OdinParameterMetadata(value="", type="str", writeable=True),
        )
    ]
    controllers = fpc.sub_controllers
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
            sub_controllers = controllers["HDF"].sub_controllers
            assert "DS" in sub_controllers
            assert isinstance(sub_controllers["DS"], OdinSubController)
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
async def test_param_tree_io_update(mocker: MockerFixture):
    connection = mocker.AsyncMock()
    connection.get.return_value = {"hdf": {"frames_written": 20}}
    io = ParameterTreeAttributeIO(connection)
    attr = AttrR(Int(), io_ref=ParameterTreeAttributeIORef("fp", "hdf/frames_written"))

    await io.update(attr)

    connection.get.assert_called_once_with("fp")
    assert attr.get() == 20

    # Check validate called to cast value
    connection.get.return_value = {"frames_written": "20"}

    await io.update(attr)

    assert attr.get() == 20


@pytest.mark.asyncio
async def test_param_tree_io_send(mocker: MockerFixture):
    connection = mocker.AsyncMock()
    connection.get.return_value = {"hdf": {"frames": 10}}

    io = ParameterTreeAttributeIO(connection)
    attr = AttrRW(Int(), io_ref=ParameterTreeAttributeIORef("fp", "hdf/frames"))
    await io.update(attr)

    await io.send(attr, 10)

    connection.put.assert_called_once_with("fp/hdf/frames", 10)


@pytest.mark.asyncio
async def test_param_tree_handler_send_exception(mocker: MockerFixture):
    connection = mocker.AsyncMock()
    connection.put.return_value = {"error": "No, you can't do that"}
    io = ParameterTreeAttributeIO(connection)
    attr = AttrRW(Int(), io_ref=ParameterTreeAttributeIORef("fp", "hdf/frames"))
    await io.update(attr)

    with pytest.raises(AdapterResponseError, match="No, you can't do that"):
        await io.send(attr, -1)

    connection.put.assert_called_once_with("fp/hdf/frames", -1)


@pytest.mark.asyncio
async def test_status_summary_attribute_io():
    controller = Controller()
    fpa_controller = Controller()
    fp1_controller = Controller()
    fp2_controller = Controller()
    hdf1_controller = Controller()
    hdf2_controller = Controller()

    controller.add_sub_controller("FP", fpa_controller)
    fpa_controller.add_sub_controller("FP0", fp1_controller)
    fpa_controller.add_sub_controller("FP1", fp2_controller)
    fp1_controller.add_sub_controller("HDF", hdf1_controller)
    fp2_controller.add_sub_controller("HDF", hdf2_controller)

    io = StatusSummaryAttributeIO()

    frames_written = AttrR(
        Int(),
        io_ref=StatusSummaryAttributeIORef(
            ["FP", re.compile("FP*"), "HDF"], "frames_written", partial(sum, start=0)
        ),
    )
    controller.frames_written = frames_written
    writing = AttrR(
        Bool(),
        io_ref=StatusSummaryAttributeIORef(
            ["FP", re.compile("FP*"), ("HDF",)], "writing", any
        ),
    )
    controller.writing = writing

    hdf1_controller.frames_written = AttrR(Int(), initial_value=50)
    hdf2_controller.frames_written = AttrR(Int(), initial_value=100)
    hdf1_controller.writing = AttrR(Bool(), initial_value=False)
    hdf_writing = AttrR(Bool(), initial_value=True)
    hdf2_controller.writing = hdf_writing

    initialise_summary_attributes(controller)

    await io.update(frames_written)
    assert frames_written.get() == 150

    await io.update(writing)
    assert writing.get()

    await hdf_writing.update(False)
    await io.update(writing)
    assert not writing.get()


@pytest.mark.asyncio
@pytest.mark.parametrize("mock_sub_controller", ("FP", ("FP",), re.compile("FP")))
async def test_status_summary_updater_raise_exception_if_controller_not_found(
    mock_sub_controller, mocker: MockerFixture
):
    controller = Controller()

    controller.writing = AttrR(
        Bool(), StatusSummaryAttributeIORef(["OD", mock_sub_controller], "writing", any)
    )
    with pytest.raises(ValueError, match=r"Sub controller .* not found"):
        initialise_summary_attributes(controller)


@pytest.mark.asyncio
async def test_config_fan_sender(mocker: MockerFixture):
    attr1 = mocker.MagicMock()
    attr1.put = (put1_mock := mocker.AsyncMock())
    attr2 = mocker.MagicMock()
    attr2.put = (put2_mock := mocker.AsyncMock())

    attr = AttrRW(Int(), ConfigFanAttributeIORef([attr1, attr2]))
    io = ConfigFanAttributeIO()

    await io.send(attr, 10)
    put1_mock.assert_called_once_with(10, sync_setpoint=True)
    put2_mock.assert_called_once_with(10, sync_setpoint=True)

    attr1.get.return_value = 10
    attr2.get.return_value = 5

    await io.update(attr)
    assert attr.get() == 0  # attributes don't match -> default value

    attr2.get.return_value = 10

    await io.update(attr)
    assert attr.get() == 10  # attributes match -> set value


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
        HTTPConnection("", 0), parameters, "api/0.1", []
    )
    await fr_controller.initialise()
    assert isinstance(fr_controller, FrameReceiverController)
    assert valid_non_decoder_parameter in fr_controller.parameters
    assert len(fr_controller.parameters) == 2


@pytest.mark.asyncio
async def test_frame_processor_start_and_stop_writing(mocker: MockerFixture):
    fpac = FrameProcessorAdapterController(
        mocker.AsyncMock(), mocker.AsyncMock(), "api/0.1", []
    )
    fpc = FrameProcessorController(
        mocker.AsyncMock(), mocker.AsyncMock(), "api/0.1", []
    )
    await fpc._create_plugin_sub_controllers(["hdf"])

    # Mock the commands to check calls
    hdf = fpc.sub_controllers["HDF"]
    hdf.start_writing = mocker.AsyncMock()  # type: ignore
    hdf.stop_writing = mocker.AsyncMock()  # type: ignore

    fpac[0] = fpc

    # Top level FP commands should collect and call lower level commands
    await fpac.start_writing()
    await fpac.stop_writing()
    assert len(hdf.start_writing.mock_calls) == 1  # type: ignore
    assert len(hdf.stop_writing.mock_calls) == 1  # type: ignore


@pytest.mark.asyncio
async def test_top_level_frame_processor_commands_raise_exception(
    mocker: MockerFixture,
):
    fpac = FrameProcessorAdapterController(
        mocker.AsyncMock(), mocker.AsyncMock(), "api/0.1", []
    )

    fpc = FrameProcessorController(
        mocker.AsyncMock(), mocker.AsyncMock(), "api/0.1", []
    )
    await fpc._create_plugin_sub_controllers(["hdf"])
    fpac[0] = fpc

    with pytest.raises(AttributeError, match="does not have"):
        await fpac.start_writing()


@pytest.mark.asyncio
async def test_status_summary_updater_raises_exception_if_attribute_not_found():
    controller = Controller()
    sub_controller = Controller()

    controller.add_sub_controller("OD", sub_controller)

    controller.writing = AttrR(
        Bool(), StatusSummaryAttributeIORef(["OD"], "some_attribute", any)
    )
    with pytest.raises(KeyError, match=r"Sub controller .* does not have attribute"):
        initialise_summary_attributes(controller)
