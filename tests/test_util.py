import pytest
from fastcs.attributes import AttrR, AttrRW
from fastcs.datatypes import Int

from fastcs_odin.util import (
    OdinParameter,
    OdinParameterMetadata,
    create_attribute,
    create_odin_parameters,
    unpack_status_arrays,
)


def test_create_parameters():
    data = {"count": {"value": 1, "writeable": False, "type": "int"}}
    parameters = create_odin_parameters(data)
    assert len(parameters) == 1

    # Test name and description ignored
    data = {
        "name": {"value": "foo", "writeable": False, "type": "str"},
        "description": {"value": "foo", "writeable": False, "type": "str"},
        "foo/bar": {"value": 1, "writeable": False, "type": "int"},
        "foo": {"baz/": {"value": 1, "writeable": False, "type": "int"}},
    }
    parameters = create_odin_parameters(data)
    assert len(parameters) == 0


@pytest.mark.parametrize(
    "metadata, uri, expected_attr, group",
    [
        (
            OdinParameterMetadata(value=0, type="int", writeable=False),
            ["name"],
            AttrR(Int(), io_ref=None, group=None),
            None,
        ),
        (
            OdinParameterMetadata(value=0, type="int", writeable=True),
            ["name"],
            AttrRW(Int(), io_ref=None, group=None),
            None,
        ),
        (
            OdinParameterMetadata(value=0, type="int", writeable=False),
            ["my_group", "name"],
            AttrR(Int(), io_ref=None, group="MyGroup"),
            None,
        ),
        (
            OdinParameterMetadata(value=0, type="int", writeable=True),
            ["my_group", "name"],
            AttrRW(Int(), io_ref=None, group="MyOtherGroup"),
            "MyOtherGroup",
        ),
    ],
)
def test_create_parameters_groups(metadata, uri, expected_attr, group):
    param = OdinParameter(uri, metadata)

    attr = create_attribute(param, "test", group=group)

    assert attr.group == expected_attr.group


@pytest.mark.parametrize(
    "values, expected_type",
    [
        ([0, 1, 2, 3], "int"),
        ([0.0, 1.0, 2.0, 3.0], "float"),
        (["0", "1", "2", "3"], "str"),
    ],
)
def test_unpack_array(values, expected_type):
    uris = [["0", "status", "arr"]]
    attr = {"0": {"status": {"arr": values}}}
    parameters = create_odin_parameters(attr)
    parameters = unpack_status_arrays(parameters, uris)

    assert len(parameters) == len(values)

    assert all(parameter.metadata.type == expected_type for parameter in parameters)

    for idx, value in enumerate(values):
        assert parameters[idx] == OdinParameter(
            uri=["0", "status", "arr", str(idx)],
            metadata=OdinParameterMetadata(
                value=value,
                type=expected_type,
                writeable=False,
            ),
        )


def test_unpack_array_assert():
    uris = [["0", "status", "arr"]]
    attr = {"0": {"status": {"arr": [1, 2, [1, 2]]}}}
    parameters = create_odin_parameters(attr)
    with pytest.raises(
        ValueError, match=r"Unsupported type for \[1, 2\] in 0_status_arr"
    ):
        unpack_status_arrays(parameters, uris)
