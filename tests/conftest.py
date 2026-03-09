import logging

import pytest
from fastcs.logging import logger


@pytest.fixture
def loguru_caplog(caplog):
    handler_id = logger.add(caplog.handler, format="{message}", level=logging.DEBUG)
    yield caplog
    logger.remove(handler_id)
