# -*- coding: utf-8 -*-
"""
Defines a pytest fixture for creating mock AiiDA codes.
"""

import os
import sys
import uuid
import shutil
import pathlib
import typing as ty
import warnings
import collections

import click
import pytest

from aiida.engine.daemon import execmanager
from aiida.orm import Code

from ._env_keys import EnvKeys
from ._helpers import get_hash, copy_files
from .._config import Config, CONFIG_FILE_NAME, ConfigActions

__all__ = (
    "pytest_addoption", "testing_config_action", "mock_regenerate_test_data", "testing_config",
    "mock_code_factory", "patch_calculation_execution"
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
        "--mock-regenerate-test-data",
        action="store_true",
        default=False,
        help="Regenerate test data."
    )


@pytest.fixture(scope='session')
def testing_config_action(request):
    """Read action for testing configuration from command line option."""
    return request.config.getoption("--testing-config-action")


@pytest.fixture(scope='session')
def mock_regenerate_test_data(request):
    """Read whether to regenerate test data from command line option."""
    return request.config.getoption("--mock-regenerate-test-data")


@pytest.fixture(scope='session')
def testing_config(testing_config_action):  # pylint: disable=redefined-outer-name
    """Get content of .aiida-testing-config.yml

    testing_config_action :
        Read config file if present ('read'), require config file ('require') or generate new config file ('generate').
    """
    config = Config.from_file()

    if not config and testing_config_action == ConfigActions.REQUIRE.value:
        raise ValueError(f"Unable to find {CONFIG_FILE_NAME}.")

    yield config

    if testing_config_action == ConfigActions.GENERATE.value:
        config.to_file()


@pytest.fixture(scope='function')
def mock_code_factory(
    aiida_localhost, testing_config, testing_config_action, mock_regenerate_test_data,
    patch_calculation_execution
):  # pylint: disable=redefined-outer-name, unused-argument
    """
    Fixture to create a mock AiiDA Code.

    testing_config_action :
        Read config file if present ('read'), require config file ('require') or generate new config file ('generate').


    """
    def _get_mock_code( # pylint: disable=too-many-arguments
        label: str,
        entry_point: str,
        data_dir_abspath: ty.Union[str, pathlib.Path],
        ignore_files: ty.Iterable[str] = ('_aiidasubmit.sh', ),
        ignore_paths: ty.Iterable[str] = ('_aiidasubmit.sh', ),
        executable_name: str = '',
        _config: dict = testing_config,
        _config_action: str = testing_config_action,
        _regenerate_test_data: bool = mock_regenerate_test_data,
    ) -> Code:
        """
        Creates a mock AiiDA code. If the same inputs have been run previously,
        the results are copied over from the corresponding sub-directory of
        the ``data_dir_abspath``. Otherwise, the code is executed.

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
            A list of file names (UNIX shell style patterns allowed) which are not copied to the results directory
            after the code has been executed.
        ignore_paths :
            A list of paths (UNIX shell style patterns allowed) that are not copied to the results directory
            after the code has been executed.
        executable_name :
            Name of code executable to search for in PATH, if configuration file does not specify location already.
        _config :
            Dict with contents of configuration file
        _config_action :
            If 'require', raise ValueError if config dictionary does not specify path of executable.
            If 'generate', add new key (label) to config dictionary.
        _regenerate_test_data :
            If True, regenerate test data instead of reusing.

        .. deprecated:: 0.1.0
            Keyword `ingore_files` is deprecated and will be removed in `v1.0`. Use `ignore_paths` instead.
        """
        if ignore_files != ('_aiidasubmit.sh', ):
            warnings.warn(
                'keyword `ignore_files` is deprecated and will be removed in `v1.0`. Use `ignore_paths` instead.',
                DeprecationWarning
            )  # pylint: disable=no-member

        # It's easy to forget the final comma and pass a string, e.g. `ignore_paths = ('_aiidasubmit.sh')`
        for arg in (ignore_paths, ignore_files):
            assert isinstance(arg, collections.Iterable) and not isinstance(arg, str), \
                f"'ignore_files' and 'ignore_paths' arguments must be tuples or lists, found {type(arg)}"

        # we want to set a custom prepend_text, which is why the code
        # can not be reused.
        code_label = f'mock-{label}-{uuid.uuid4()}'

        data_dir_pl = pathlib.Path(data_dir_abspath)
        if not data_dir_pl.exists():
            raise ValueError("Data directory '{}' does not exist".format(data_dir_abspath))
        if not data_dir_pl.is_absolute():
            raise ValueError("Please provide absolute path to data directory.")

        mock_executable_path = shutil.which('aiida-mock-code')
        if not mock_executable_path:
            raise ValueError(
                "'aiida-mock-code' executable not found in the PATH. " +
                "Have you run `pip install aiida-testing` in this python environment?"
            )

        # try determine path to actual code executable
        mock_code_config = _config.get('mock_code', {})
        if _config_action == ConfigActions.REQUIRE.value and label not in mock_code_config:
            raise ValueError(
                f"Configuration file {CONFIG_FILE_NAME} does not specify path to executable for code label '{label}'."
            )
        code_executable_path = mock_code_config.get(label, 'TO_SPECIFY')
        if (not code_executable_path) and executable_name:
            code_executable_path = shutil.which(executable_name) or 'NOT_FOUND'
        if _config_action == ConfigActions.GENERATE.value:
            mock_code_config[label] = code_executable_path

        if code_executable_path in {'TO_SPECIFY', 'NOT_FOUND'}:
            remote_executable_path = mock_executable_path
        else:
            remote_executable_path = code_executable_path

        code = Code(
            input_plugin_name=entry_point,
            remote_computer_exec=[aiida_localhost, remote_executable_path]
        )
        code.label = code_label

        code.store()

        code.set_extra(EnvKeys.LABEL.value, label)
        code.set_extra(EnvKeys.DATA_DIR.value, str(data_dir_abspath))
        code.set_extra(EnvKeys.EXECUTABLE_PATH.value, str(code_executable_path))
        code.set_extra(EnvKeys.IGNORE_FILES.value, ignore_files)
        code.set_extra(EnvKeys.IGNORE_PATHS.value, ignore_paths)
        code.set_extra(EnvKeys.REGENERATE_DATA.value, _regenerate_test_data)

        return code

    return _get_mock_code


_CALC_NEEDS_COPY_TO_RES_DIR_KEY = '_aiida_testing_needs_copy_to_datadir'
_CALC_RES_DIR_KEY = '_aiida_testing_res_dir'


@pytest.fixture(scope='function', autouse=True)
def patch_calculation_execution(monkeypatch):
    """Patch execmanager.submit_calculation such as to take data from test data directory.
    """

    unpatched_submit_calculation = execmanager.submit_calculation
    unpatched_retrieve_calculation = execmanager.retrieve_calculation

    def mock_submit_calculation(calculation, transport):
        """
        Run the mock AiiDA code. If the corresponding result exists, it is
        simply copied over to the current working directory. Otherwise,
        the code will replace the executable in the aiidasubmit file,
        launch the "real" code, and then copy the results into the data
        directory.
        :param calculation:
        :param transport:
        :return:
        """
        code = calculation.inputs.code
        label = code.get_extra(EnvKeys.LABEL.value)
        data_dir = code.get_extra(EnvKeys.DATA_DIR.value)
        executable_path = code.get_extra(EnvKeys.EXECUTABLE_PATH.value)

        regenerate_data = code.get_extra(EnvKeys.REGENERATE_DATA.value)

        workdir = pathlib.Path(calculation.get_remote_workdir())
        hash_digest = get_hash(workdir, code=code).hexdigest()
        res_dir = pathlib.Path(data_dir) / f"mock-{label}-{hash_digest}"

        calculation.set_extra(_CALC_RES_DIR_KEY, str(res_dir.absolute()))

        if regenerate_data and res_dir.exists():
            shutil.rmtree(res_dir)

        if not res_dir.exists():
            if not executable_path:
                sys.exit("No existing output, and no executable specified.")

            calculation.set_extra(_CALC_NEEDS_COPY_TO_RES_DIR_KEY, True)
            res_jobid = unpatched_submit_calculation(calculation, transport)

        else:
            # copy outputs from data directory to working directory
            for path in res_dir.iterdir():
                out_path = workdir / path.name
                if path.is_dir():
                    shutil.rmtree(out_path, ignore_errors=True)
                    shutil.copytree(path, out_path)
                elif path.is_file():
                    shutil.copyfile(path, out_path)
                else:
                    sys.exit(f"Can not copy '{path.name}'.")

            # return a non-existing jobid
            res_jobid = -1
        return res_jobid

    def mock_retrieve_calculation(calculation, transport, retrieved_temporary_folder):
        # back up results to data directory
        if calculation.get_extra(_CALC_NEEDS_COPY_TO_RES_DIR_KEY, False):
            code = calculation.inputs.code

            ignore_files = code.get_extra(EnvKeys.IGNORE_FILES.value)
            ignore_paths = code.get_extra(EnvKeys.IGNORE_PATHS.value)

            res_dir = calculation.get_extra(_CALC_RES_DIR_KEY)
            os.makedirs(res_dir)
            copy_files(
                src_dir=pathlib.Path(calculation.get_remote_workdir()),
                dest_dir=res_dir,
                ignore_files=ignore_files,
                ignore_paths=ignore_paths
            )

        unpatched_retrieve_calculation(calculation, transport, retrieved_temporary_folder)

    monkeypatch.setattr(execmanager, 'submit_calculation', mock_submit_calculation)
    monkeypatch.setattr(execmanager, 'retrieve_calculation', mock_retrieve_calculation)
