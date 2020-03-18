# -*- coding: utf-8 -*-
"""
Defines a pytest fixture for creating mock AiiDA codes.
"""

import uuid
import shutil
import inspect
import pathlib
import typing as ty

import pytest

from ._env_keys import EnvKeys
from .._config import Config, CONFIG_FILE_NAME

__all__ = ("mock_code_factory", "mock_require_config", "mock_write_config")


def pytest_addoption(parser):
    """Add pytest options for managing testing config file."""
    parser.addoption(
        "--require-aiida-testing-config",
        action="store_true",
        default=False,
        help="Fail if testing configuration is missing for any mocked code."
    )
    parser.addoption(
        "--write-aiida-testing-config",
        action="store_true",
        default=False,
        help="(Over-)write testing configuration."
    )


@pytest.fixture(scope='session')
def mock_require_config(request):
    return request.config.getoption("--require-aiida-testing-config")


@pytest.fixture(scope='session')
def mock_write_config(request):
    return request.config.getoption("--write-aiida-testing-config")


@pytest.fixture(scope='session')
def testing_config(mock_write_config, mock_require_config):  # pylint: disable=redefined-outer-name
    """Get aiida-testing-config.

    Specifying CLI parameter --require-aiida-testing-config will raise if no config file is found.
    Specifying CLI parameter --write-aiida-testing-config results in config
    template being written during test run.
    """
    config = Config.from_file()

    if not config and mock_require_config:
        raise ValueError(f"Unable to find {CONFIG_FILE_NAME}.")

    yield config

    if mock_write_config:
        config.to_file()


@pytest.fixture(scope='function')
def mock_code_factory(aiida_localhost, mock_require_config, mock_write_config, testing_config):  # pylint: disable=redefined-outer-name
    """
    Fixture to create a mock AiiDA Code.

    Specifying CLI parameter --require-aiida-testing-config will raise if a required code label is not found.
    Specifying CLI parameter --write-aiida-testing-config results in config
    template being written during test run.

    """
    config = testing_config.get('mock_code', {})

    def _get_mock_code(
        label: str,
        entry_point: str,
        data_dir_abspath: ty.Union[str, pathlib.Path],
        ignore_files: ty.Iterable[str] = ('_aiidasubmit.sh', )
    ):
        """
        Creates a mock AiiDA code. If the same inputs have been run previously,
        the results are copied over from the corresponding sub-directory of
        the ``data_dir_abspath``. Otherwise, the code is executed if an
        executable is specified in the configuration, or fails if it is not.

        Parameters
        ----------
        label :
            Label by which the code is identified in the configuration file.
        entry_point :
            The AiiDA calculation entry point for the default calculation
            of the code.
        data_dir_abspath :
            Absolute path of the directory where the code results are
            stored.
        ignore_files :
            A list of files which are not copied to the results directory
            when the code is executed.
        """
        from aiida.orm import Code

        # we want to set a custom prepend_text, which is why the code
        # can not be reused.
        code_label = f'mock-{label}-{uuid.uuid4()}'

        executable_path = shutil.which('aiida-mock-code')
        code_executable = config.get(label, '')
        if not code_executable and mock_require_config:
            raise ValueError(
                f"Configuration file does not specify executable code label '{label}'."
            )
        if mock_write_config:
            config[label] = None

        code = Code(
            input_plugin_name=entry_point, remote_computer_exec=[aiida_localhost, executable_path]
        )
        code.label = code_label
        code.set_prepend_text(
            inspect.cleandoc(
                f"""
                export {EnvKeys.LABEL.value}={label}
                export {EnvKeys.DATA_DIR.value}={data_dir_abspath}
                export {EnvKeys.EXECUTABLE_PATH.value}={code_executable}
                export {EnvKeys.IGNORE_FILES.value}={':'.join(ignore_files)}
                """
            )
        )

        code.store()
        return code

    testing_config['mock_code'] = config

    return _get_mock_code
