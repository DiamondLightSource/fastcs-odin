import glob
import runpy

import pytest


@pytest.mark.parametrize("filename", glob.glob("docs/snippets/*.py"))
def test_snippet(filename):
    runpy.run_path(filename)
