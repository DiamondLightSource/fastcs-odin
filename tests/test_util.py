import pytest
from fastcs.attributes import AttrR, AttrRW
from fastcs.datatypes import Int

from fastcs_odin.util import (
    OdinParameter,
    OdinParameterMetadata,
    create_attribute,
    create_odin_parameters,
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
