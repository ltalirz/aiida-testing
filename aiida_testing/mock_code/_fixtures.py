# -*- coding: utf-8 -*-
"""
Defines a pytest fixture for creating mock AiiDA codes.
"""

import uuid
import shutil
import inspect
import pathlib
import typing as ty
import click
import pytest

from aiida.orm import Code

from ._env_keys import EnvKeys
from .._config import Config, CONFIG_FILE_NAME, ConfigActions

__all__ = (
    "pytest_addoption",
    "testing_config_action",
    "mock_regenerate_test_data",
    "testing_config",
    "mock_code_factory",
)


def pytest_addoption(parser):
    """Add pytest command line options."""
    parser.addoption(
        "--testing-config-action",
        type=click.Choice((c.value for c in ConfigActions)),
        default=ConfigActions.READ.value,
        help=f"Read {CONFIG_FILE_NAME} config file if present ('read'), require config file ('require') or " \
             "generate new config file ('generate').",
    )
    parser.addoption(
        "--regenerate-test-data", action="store_true", default=False, help="Regenerate test data."
    )


@pytest.fixture(scope='session')
def testing_config_action(request):
    return request.config.getoption("--testing-config-action")


@pytest.fixture(scope='session')
def mock_regenerate_test_data(request):
    return request.config.getoption("--regenerate-test-data")


@pytest.fixture(scope='session')
def testing_config(testing_config_action):  # pylint: disable=redefined-outer-name
    """Get testing-config-action.

    Specifying CLI parameter --testing-config-action will raise if no config file is found.
    Specifying CLI parameter --generate-testing-config-action results in config
    template being written during test run.
    """
    config = Config.from_file()

    if not config and testing_config_action == ConfigActions.REQUIRE.value:
        raise ValueError(f"Unable to find {CONFIG_FILE_NAME}.")

    yield config

    if testing_config_action == ConfigActions.GENERATE.value:
        config.to_file()


@pytest.fixture(scope='function')
def mock_code_factory(
    aiida_localhost, testing_config, testing_config_action, mock_regenerate_test_data
):  # pylint: disable=redefined-outer-name
    """
    Fixture to create a mock AiiDA Code.

    Specifying CLI parameter --testing-config-action will raise if a required code label is not found.
    Specifying CLI parameter --generate-testing-config-action results in config
    template being written during test run.

    """
    def _get_mock_code(
        label: str,
        entry_point: str,
        data_dir_abspath: ty.Union[str, pathlib.Path],
        ignore_files: ty.Iterable[str] = ('_aiidasubmit.sh'),
        #ignore_files: ty.Iterable[str] = ('_aiidasubmit.sh', '_scheduler-stderr.txt', '_scheduler-stdout.txt',),
        executable_name: str = '',
        config: dict = testing_config,
        config_action: str = testing_config_action,
        regenerate_test_data: bool = mock_regenerate_test_data,
    ):  # pylint: disable=too-many-arguments
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
        executable_name :
            Name of code executable to search for in PATH, if configuration file does not specify location already.
        config :
            Dict with contents of configuration file
        config_action :
            Read config file if present ('read'), require config file ('require') or generate new config file ('generate').
        generate_config :
            Generate configuration file template, if it does not yet exist
        """
        # we want to set a custom prepend_text, which is why the code
        # can not be reused.
        code_label = f'mock-{label}-{uuid.uuid4()}'

        data_dir_abspath = pathlib.Path(data_dir_abspath).absolute()
        if not data_dir_abspath.exists():
            raise ValueError("Data directory '{}' does not exist".format(data_dir_abspath))

        mock_executable_path = shutil.which('aiida-mock-code')
        if not mock_executable_path:
            raise ValueError(
                "'aiida-mock-code' executable not found in the PATH. " +
                "Have you run `pip install aiida-testing` in this python environment?"
            )

        # try determine path to actual code executable
        mock_code_config = config.get('mock_code', {})
        if config_action == ConfigActions.REQUIRE.value and label not in mock_code_config:
            raise ValueError(
                f"Configuration file {CONFIG_FILE_NAME} does not specify path to executable for code label '{label}'."
            )
        code_executable_path = mock_code_config.get(label, 'TO_SPECIFY')
        if (not code_executable_path) and executable_name:
            code_executable_path = shutil.which(executable_name) or 'NOT_FOUND'
        if config_action == ConfigActions.GENERATE.value:
            mock_code_config[label] = code_executable_path

        code = Code(
            input_plugin_name=entry_point,
            remote_computer_exec=[aiida_localhost, mock_executable_path]
        )
        code.label = code_label
        code.set_prepend_text(
            inspect.cleandoc(
                f"""
                export {EnvKeys.LABEL.value}="{label}"
                export {EnvKeys.DATA_DIR.value}="{data_dir_abspath}"
                export {EnvKeys.EXECUTABLE_PATH.value}="{code_executable_path}"
                export {EnvKeys.IGNORE_FILES.value}="{':'.join(ignore_files)}"
                export {EnvKeys.REGENERATE_DATA.value}={'True' if regenerate_test_data else 'False'}
                """
            )
        )

        code.store()
        return code

    return _get_mock_code
