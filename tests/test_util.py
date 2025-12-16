from fastcs_odin.util import create_odin_parameters


def test_create_parameters():
    data = {"count": {"value": 1, "writeable": False, "type": "int"}}
    parameters = create_odin_parameters(data)
    assert len(parameters) == 1

    # Test name and description ignored
    data = {
        "name": {"value": "foo", "writeable": False, "type": "str"},
        "description": {"value": "foo", "writeable": False, "type": "str"},
    }
    parameters = create_odin_parameters(data)
    assert len(parameters) == 0
