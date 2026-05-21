import math
from dataclasses import dataclass
from pathlib import Path

import h5py
from fastcs.logging import logger

UNLIMITED = h5py.h5s.UNLIMITED


@dataclass
class FileFrames:
    frames: int
    start: int
    frames_per_block: int

    @property
    def blocks(self):
        return self.frames // self.frames_per_block

    @property
    def remainder_frames(self):
        return self.frames % self.frames_per_block


class VDSGenerator:
    def __init__(self, path: Path, prefix: str):
        self.path = path
        self.prefix = prefix

    @staticmethod
    def _get_frames_per_file_writer(
        frame_count: int, frames_per_block: int, n_file_writers: int
    ) -> list[int]:
        n_blocks = math.ceil(frame_count / frames_per_block)
        min_blocks_per_file = n_blocks // n_file_writers
        remainder = n_blocks - min_blocks_per_file * n_file_writers

        frames_per_file_writer = []
        for i in range(n_file_writers):
            blocks = min_blocks_per_file + (i < remainder)
            frames_per_file_writer.append(blocks * frames_per_block)

        overflow = sum(frames_per_file_writer) - frame_count
        frames_per_file_writer[remainder - 1] -= overflow
        return frames_per_file_writer

    @staticmethod
    def _calculate_frame_distribution(
        frame_count: int,
        frames_per_block: int,
        blocks_per_file: int,
        n_file_writers: int,
    ) -> dict[int, FileFrames]:
        assert frame_count
        assert frames_per_block
        assert n_file_writers
        frame_distribution: dict[int, FileFrames] = {}

        max_frames_per_file = (
            frames_per_block * blocks_per_file if blocks_per_file else frame_count
        )
        # total frames written before one of the file writers has to start a new file
        frames_before_new_file = n_file_writers * max_frames_per_file
        frames_per_file_writer = VDSGenerator._get_frames_per_file_writer(
            frame_count, frames_per_block, n_file_writers
        )
        for file_writer_idx, n_frames in enumerate(frames_per_file_writer):
            n_files = math.ceil(n_frames / max_frames_per_file)
            for i in range(n_files):
                file_idx = file_writer_idx + i * n_file_writers

                frame_distribution[file_idx + 1] = FileFrames(
                    frames=min(n_frames - i * max_frames_per_file, max_frames_per_file),
                    frames_per_block=frames_per_block,
                    start=frames_per_block * file_writer_idx
                    + file_idx // n_file_writers * frames_before_new_file,
                )

        return frame_distribution

    def _get_bounded_v_layout(
        self,
        dataset_name: str,
        frame_count: int,
        frames_per_block: int,
        frame_shape: tuple[int, int],
        dtype: str,
        stride: int,
        frame_distribution: dict[int, FileFrames],
    ) -> h5py.VirtualLayout:
        v_layout = h5py.VirtualLayout(
            shape=(frame_count, frame_shape[0], frame_shape[1]),
            dtype=dtype,
        )
        for file_number, file_frames in frame_distribution.items():
            full_block_frames = file_frames.blocks * frames_per_block
            v_source = h5py.VirtualSource(
                f"{self.prefix}_{str(file_number).zfill(6)}.h5",
                name=dataset_name,
                shape=(file_frames.frames, frame_shape[0], frame_shape[1]),
                dtype=dtype,
            )
            if file_frames.blocks:
                source = v_source[:full_block_frames, :, :]
                v_layout[
                    h5py.MultiBlockSlice(
                        start=file_frames.start,
                        stride=stride,
                        count=file_frames.blocks,
                        block=frames_per_block,
                    ),
                    :,
                    :,
                ] = source
            if file_frames.remainder_frames:
                # Last few frames that don't fit into a block
                source = v_source[full_block_frames : file_frames.frames, :, :]
                v_layout[
                    frame_count - file_frames.remainder_frames : frame_count,
                    :,
                    :,
                ] = source
        return v_layout

    def _create_bounded_vds(
        self,
        datasets: list[str],
        frame_count: int,
        frames_per_block: int,
        blocks_per_file: int,
        frame_shape: tuple[int, int],
        dtype: str,
        n_file_writers: int,
        stride: int,
    ):
        frame_distribution = self._calculate_frame_distribution(
            frame_count, frames_per_block, blocks_per_file, n_file_writers
        )

        with h5py.File(f"{self.path / self.prefix}_vds.h5", "w", libver="latest") as f:
            for dataset_name in datasets:
                v_layout = self._get_bounded_v_layout(
                    dataset_name,
                    frame_count,
                    frames_per_block,
                    frame_shape,
                    dtype,
                    stride,
                    frame_distribution,
                )
                f.create_virtual_dataset(dataset_name, v_layout)

    def _create_unbounded_vds(
        self,
        datasets: list[str],
        frames_per_block: int,
        frame_shape: tuple[int, int],
        dtype: str,
        n_file_writers: int,
        stride: int,
    ):
        with h5py.File(f"{self.path / self.prefix}_vds.h5", "w", libver="latest") as f:
            for dataset_name in datasets:
                v_layout = h5py.VirtualLayout(
                    shape=(UNLIMITED, frame_shape[0], frame_shape[1]),
                    dtype=dtype,
                )
                for i in range(n_file_writers):
                    v_source = h5py.VirtualSource(
                        f"{self.prefix}_{str(i + 1).zfill(6)}.h5",
                        shape=(1000, frame_shape[0], frame_shape[1]),
                        name=dataset_name,
                        maxshape=(None, frame_shape[0], frame_shape[1]),
                        dtype=dtype,
                    )
                    multi_slice = h5py.MultiBlockSlice(
                        start=frames_per_block * i,
                        stride=stride,
                        count=UNLIMITED,
                        block=frames_per_block,
                    )
                    v_layout[multi_slice, :, :] = v_source[:, :, :]
                f.create_virtual_dataset(dataset_name, v_layout)

    def create_interleave_vds(
        self,
        datasets: list[str],
        frame_count: int,
        frames_per_block: int,
        blocks_per_file: int,
        frame_shape: tuple[int, int],
        dtype: str = "float",
        n_file_writers: int = 4,
    ) -> None:
        if frame_count == 0 and blocks_per_file != 0:
            raise ValueError(
                "Cannot create VDS if frame_count is unknown and blocks_per_file is not"
                + " unlimited! "
                + f"frame_count={frame_count}, blocks_per_file={blocks_per_file}"
            )

        filepath = f"{self.path / self.prefix}_vds.h5"
        logger.info(f"Writing virtual dataset at {filepath}")
        stride = n_file_writers * frames_per_block

        if frame_count == 0:
            self._create_unbounded_vds(
                datasets=datasets,
                frames_per_block=frames_per_block,
                frame_shape=frame_shape,
                dtype=dtype,
                n_file_writers=n_file_writers,
                stride=stride,
            )
        else:
            self._create_bounded_vds(
                datasets=datasets,
                frame_count=frame_count,
                frames_per_block=frames_per_block,
                blocks_per_file=blocks_per_file,
                frame_shape=frame_shape,
                dtype=dtype,
                n_file_writers=n_file_writers,
                stride=stride,
            )


vds = VDSGenerator(Path("/workspaces/fastcs-odin"), "test")
vds.create_interleave_vds(
    ["data"], frame_count=0, frames_per_block=10, blocks_per_file=0, frame_shape=(1, 1)
)
