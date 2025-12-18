# FastCS Odin Workshop

<intro>

## Intial Setup

- Configure python environment
```
❯ source <path-to-venv>
>>> python
>>> from fastcs import __version__
>>> __version__
```

- <run phoebus>

## Run Example Odin Deployment

- <run odin deployment>

```
❯ cd <deployment-directory>
❯ zellij -l layout.kdl
```

- Check all applications start without errors

## Example Driver

- Create minimal controller

```python
from fastcs.attributes import AttrRW
from fastcs.control_system import FastCS
from fastcs.controllers import Controller
from fastcs.datatypes import Int


class ExampleOdinController(Controller):
    foo = AttrRW(Int())


fastcs = FastCS(controller=ExampleOdinController(), transports=[])

fastcs.run()
```

- Check in interactive shell

```
In [1]: controller.foo.get()
Out[1]: 0

In [2]: run(controller.foo.put(1))

In [3]: controller.foo.get()
Out[3]: 1
```

### EPICS Channel Access

Add EPICS CA by passing to list of transports. Make sure the PV prefix is unique.

```python
from fastcs.transports.epics import EpicsIOCOptions
from fastcs.transports.epics.ca.transport import EpicsCATransport
...
    transports=[EpicsCATransport(EpicsIOCOptions(pv_prefix="EXAMPLE"))],
```

- List PVs in the IOC

```
In [7]: dbl()
EXAMPLE:Foo_RBV
EXAMPLE:Foo
EXAMPLE:PVI_PV
```

- Interact from terminal

```
❯ caget EXAMPLE:Foo_RBV
EXAMPLE:Foo_RBV            1
❯ caput EXAMPLE:Foo 5
Old : EXAMPLE:Foo                1
New : EXAMPLE:Foo                5
❯ caget EXAMPLE:Foo_RBV
EXAMPLE:Foo_RBV            5
```

### Phoebus UI

- Configure FastCS to generate a UI

```python
from fastcs.transports.epics import EpicsGUIOptions
...
            gui=EpicsGUIOptions(output_path=Path.cwd() / "opis" / "example.bob", title="Odin Example Detector"),
```

- Check `opis/example.bob appears
- Phoebus: File > Open > example.bob
- Try setting some values

### FastCS Odin

Update example controller to inherit from `OdinController`.

```
from fastcs.connections import IPConnectionSettings
...
from fastcs_odin.controllers import OdinController
...
    controller=ExampleController(IPConnectionSettings("127.0.0.1", 8888)),
```

Warnings about parameters failing are OK

- List new PVs

```
In [1]: dbl()
EXAMPLE:DETECTOR:ConfigExposureTime_RBV
...
EXAMPLE:FP:0:HDF:FileUseNumbers_RBV
...
EXAMPLE:FP:1:HDF:Writing
...
EXAMPLE:FR:2:DecoderEnablePacketLogging_RBV
...
EXAMPLE:FP:3:LIVE:FrameFrequency
...
EXAMPLE:DETECTOR:Start
```

List attributes and sub controllers.

```
In [2]: controller.attributes
Out[2]: {'foo': AttrRW(name=foo, datatype=Int, io_ref=None)}

In [3]: controller.sub_controllers
Out[3]:
{'DETECTOR': OdinAdapterController(path=DETECTOR, sub_controllers=None),
 'FR': FrameReceiverAdapterController(path=FR, sub_controllers=['0', '1', '2', '3']),
 'FP': FrameProcessorAdapterController(path=FP, sub_controllers=['0', '1', '2', '3']),
 'LIVE': OdinAdapterController(path=LIVE, sub_controllers=None),
 'SYSTEM': OdinAdapterController(path=SYSTEM, sub_controllers=None)}
```

Sub controllers are adapter controllers. These can be mapped to specific classes, or the
fallback `OdinAdapterController`, which just introspects parameter tree and adds no
additional logic.

### FastCS Odin UI

- Phoebus: Right-click > Re-load display
  - Should have buttons for each sub controller
- Open DETECTOR screen. Press start, frame counter should tick up

- See log message `Executing command` in interactive shell

- Open FP screen
- Has top-level attributes that read/write each individual FP
  - Things that have to be different (CtrlEndpoint) are excluded
- There are PVs for the `example` dataset
  - These are detector-specific and defined in the config file

### Capture an Acquisition

Can now run an acquisition and capture frames to a file

- FP.FilePath = /tmp
- FP.FilePrefix = test
- FP.Frames = 10
- FP.StartWriting

- Check FP.Writing set
  - Note path and prefix are cleared for some reason

- DETECTOR.Frames = 10
- DETECTOR.Start

- Watch FP > Frames Written count up and then FP > Writing unset

- Again check the interactive shell for the parameters that are being set

## Improving API

This is a bit fiddly having to move between sub screens.

- Add more top-level PVs like the FP has
- Remove foo attribute

```python
from fastcs.datatypes import String
...
from fastcs_odin.io.config_fan_sender_attribute_io import ConfigFanAttributeIORef
...
    async def initialise(self):
        await super().initialise()

        self.file_path = AttrRW(
            String(),
            io_ref=ConfigFanAttributeIORef([self.FP.file_path]),
        )
        self.file_prefix = AttrRW(
            String(),
            io_ref=ConfigFanAttributeIORef([self.FP.file_prefix]),
        )
        self.frames = AttrRW(
            Int(),
            io_ref=ConfigFanAttributeIORef(
                [self.FP.frames, self.DETECTOR.config_frames]
            ),
        )
```

- Run and reload display
- See new PVs appear

This works, but a good editor will complain about `FP` and `DETECTOR`. These only exist
at runtime and static type checkers cannot resolve them.

### Type Hints

FastCS will validate type-hinted attributes, methods and controllers during
initialisation to fail early if something is wrong.

- Add type hint for `FP`
  - Create `ExampleFrameProcessorAdapterController` with `frames`

```python
from fastcs_odin.controllers.odin_data.frame_processor import FrameProcessorAdapterController
...
class ExampleFrameProcessorAdapterController(FrameProcessorAdapterController):
    frames: AttrRW[int]
...
    FP: ExampleFrameProcessorAdapterController
```

- Add type hint for `DETECTOR`
  - Create `ExampleDetectorAdapterController` with `config_frames`

```python
from fastcs_odin.controllers.odin_adapter_controller import OdinAdapterController
...
class ExampleDetectorAdapterController(OdinAdapterController):
    config_frames: AttrRW[int]
...
    DETECTOR: ExampleDetectorAdapterController
```

- Try running again - there will be an error

```
RuntimeError: Controller 'ExampleOdinController' introspection of hinted sub controller 'DETECTOR' does not match defined type. Expected 'ExampleDetectorAdapterController' got 'OdinAdapterController'.
```

- Override `_create_adapter_controller` to create the correct controllers

```python
from fastcs.controllers import BaseController
...
from fastcs_odin.http_connection import HTTPConnection
...
from fastcs_odin.util import OdinParameter
...
    def _create_adapter_controller(
        self,
        connection: HTTPConnection,
        parameters: list[OdinParameter],
        adapter: str,
        module: str,
    ) -> BaseController:
        match module:
            case "ExampleDetectorAdapter":
                return ExampleDetectorAdapterController(
                    connection, parameters, f"{self.API_PREFIX}/{adapter}", self._ios
                )
            case "FrameProcessorAdapter":
                return ExampleFrameProcessorAdapterController(
                    connection, parameters, f"{self.API_PREFIX}/{adapter}", self._ios
                )
            case _:
                return super()._create_adapter_controller(
                    connection, parameters, adapter, module
                )
```

- Try adding a type hint for attributes and sub controllers that don't exist and running

```
RuntimeError: Controller `ExampleOdinController` failed to introspect hinted controller `FOO` during initialisation
```

```
RuntimeError: Controller `ExampleOdinController` failed to introspect hinted attribute `foo` during initialisation
```

---

Parameters can now be set from the top screen, but acquisitions cannot be run yet.

- Add `start` and `stop` type hints on `ExampleDetectorAdapterController`

```python
from fastcs.methods import Command
...
    start: Command
    stop: Command
```

- Add commands for starting and stopping acquisitions

```python
from fastcs.methods import command
...
    @command()
    async def acquire(self):
        await self.FP.start_writing()
        await self.DETECTOR.start()

    @command()
    async def stop(self):
        await self.FP.stop_writing()
        await self.DETECTOR.stop()
```

Note `FrameProcessorAdapterController` already has `start_writing` and `stop_writing`
defined statically, so they do not need to be added to
`ExampleFrameProcessorAdapterController`.

- Run and re-load phoebus

An acquisition can now be run from the top screen, but there is no status.

- Add `status_acquiring` and `status_frames` to `ExampleDetectorAdapterController`

```python
from fastcs.attributes import AttrR
...
    status_acquiring: AttrR[bool]
    status_frames: AttrR[int]
```

- Add top-level status PVs

```python
from fastcs.datatypes import Bool
...
from fastcs_odin.io.status_summary_attribute_io import StatusSummaryAttributeIORef
...
        self.acquiring = AttrR(
            Bool(),
            io_ref=StatusSummaryAttributeIORef(
                [], "", any, [self.FP.writing, self.DETECTOR.status_acquiring]
            ),
        )
        self.frames_captured = AttrR(
            Int(),
            io_ref=StatusSummaryAttributeIORef(
                [], "", min, [self.DETECTOR.status_frames, self.FP.frames_written]
            ),
        )
```

Note: The API for this will be improved. It was initially created to search for the
attributes, rather than be passed them directly. Ignore the first two arguments.

## Controller Logic

There is a risk that the file writer is slower to start than the detector and frames
will be missed.

- Use `AttrR.wait_for_value` to ensure that the file writers have started before
  starting the detector

```python
        await self.FP.writing.wait_for_value(True, timeout=1)
```

## Scan Methods - Live View Display

Currently the output file is the only way to check the data stream. The live view
adapter can be used to see the frames as they pass through. Add this to
`ExampleOdinController`. It could be added to a `LiveViewAdapterController`, but the
adapter does not provide a module name to match on, so that would be fiddly.

- Create a `Waveform` attribute to display the image
- Add a `@scan` methods to query the live view adapter for images to display

```python
from io import BytesIO
...
from PIL import Image
import numpy as np
...
from fastcs.datatypes import Waveform
from fastcs.methods import scan
...
    live_view_image = AttrR(Waveform("uint8", shape=(256, 256)))
...
    @scan(1)
    async def monitor_live_view(self):
        response, image_bytes = await self.connection.get_bytes(
            f"{self.API_PREFIX}/live/image"
        )

        if response.status != 200:
            return

        image = Image.open(BytesIO(image_bytes))
        numpy_array = np.asarray(image)
        await self.live_view_image.update(numpy_array[:, :, 0])
```

The image dimensions and dtype could be queried from `LIVE.Shape` and `Live.FrameDtype`
at runtime to create `live_view_image` dynamically.

The EPICS CA transport does not support images, so this will give an error

```
TypeError: Unsupported shape (256, 256), the EPICS transport only supports to 1D arrays
```

### PV Access Transport

- Update to use the PVA transport instead of CA - they take the same arguments

```python
from fastcs.transports.epics.pva.transport import EpicsPVATransport
...
        EpicsPVATransport(
```

Known Issues:
- No `dbl()`
- Setpoints are cleared
- Does not exit cleanly - Have to Ctrl-C

Run an acquisition and watch the live view (LiveViewImage button)

- `DETECTOR.Frames` = 0
- `DETECTOR.Start`

## Logging and Tracing

- Configure TRACE level logging

This will not produce any additional output until enabled at runtime, although it will
enable DEBUG level output.

```python
from fastcs.logging import LogLevel, configure_logging
...
configure_logging(LogLevel.TRACE)
```

- Enable tracing on a single attribute

```
In [1]: controller.FP[0].HDF.file_path.enable_tracing()
```

This shows trace events from the connection, through the attribute and into the
transport.

Path seems to get cleared in the adapter

```
[2025-12-23 12:07:31.510+0000 I] Executing command   [fastcs_odin.controllers.odin_subcontroller] controller=['FP', '0', 'HDF'], command=start_writing, path=['hdf']
...
[2025-12-23 12:07:31.615+0000 T] Query for parameter [ParameterTreeAttributeIO] uri=api/0.1/fp/0/config/hdf/file/path, response={'path': '/tmp'}
...
[2025-12-23 12:07:31.780+0000 T] Query for parameter [ParameterTreeAttributeIO] uri=api/0.1/fp/0/config/hdf/file/path, response={'path': ''}
```

- Disable tracing

```
In [2]: controller.FP[0].HDF.file_path.disable_tracing()
```
