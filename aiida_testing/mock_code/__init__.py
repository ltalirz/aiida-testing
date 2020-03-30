# -*- coding: utf-8 -*-
"""
Defines fixtures for mocking AiiDA codes, with caching at the level of
the executable.
"""

from ._fixtures import *

__all__ = (
    "pytest_addoption",
    "testing_config_action",
    "mock_regenerate_test_data",
    "testing_config",
    "mock_code_factory",
)
