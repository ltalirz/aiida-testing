#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Implements the executable for running a mock AiiDA code.
"""

import os
import sys
import shutil
import hashlib
import subprocess
import typing as ty
import fnmatch
from pathlib import Path

from ._env_keys import EnvKeys

SUBMIT_FILE = '_aiidasubmit.sh'


def run() -> None:
    """
    Run the mock AiiDA code. If the corresponding result exists, it is
    simply copied over to the current working directory. Otherwise,
    the code will replace the executable in the aiidasubmit file,
    launch the "real" code, and then copy the results into the data
    directory.
    """
    pass


def get_hash() -> 'hashlib._Hash':
    """
    Get the MD5 hash for the current working directory.
    """
    md5sum = hashlib.md5()
    # Here the order needs to be consistent, thus globbing
    # with 'sorted'.
    for path in sorted(Path('.').glob('**/*')):
        if path.is_file() and not path.match('.aiida/**'):
            with open(path, 'rb') as file_obj:
                file_content_bytes = file_obj.read()
            if path.name == SUBMIT_FILE:
                file_content_bytes = strip_submit_content(file_content_bytes)
            md5sum.update(path.name.encode())
            md5sum.update(file_content_bytes)

    return md5sum


def strip_submit_content(aiidasubmit_content_bytes: bytes) -> bytes:
    """
    Helper function to strip content which changes between
    test runs from the aiidasubmit file.
    """
    aiidasubmit_content = aiidasubmit_content_bytes.decode()
    lines: ty.Iterable[str] = aiidasubmit_content.splitlines()
    # Strip lines containing the aiida_testing.mock_code environment variables.
    lines = (line for line in lines if 'export AIIDA_MOCK' not in line)
    # Remove abspath of the aiida-mock-code, but keep cmdline
    # arguments.
    lines = (line.split("aiida-mock-code'")[-1] for line in lines)
    return '\n'.join(lines).encode()


def replace_submit_file(executable_path: str, working_directory='.') -> None:
    """
    Replace the executable specified in the AiiDA submit file, and
    strip the AIIDA_MOCK environment variables.
    """
    with open(Path(working_directory) / SUBMIT_FILE, 'r') as submit_file:
        submit_file_content = submit_file.read()

    submit_file_res_lines = []
    for line in submit_file_content.splitlines():
        if 'export AIIDA_MOCK' in line:
            continue
        if 'aiida-mock-code' in line:
            submit_file_res_lines.append(
                f"'{executable_path}' " + line.split("aiida-mock-code'")[1]
            )
        else:
            submit_file_res_lines.append(line)
    with open(Path(working_directory) / SUBMIT_FILE, 'w') as submit_file:
        submit_file.write('\n'.join(submit_file_res_lines))


def copy_files(
    src_dir: Path, dest_dir: Path, ignore_files: ty.Iterable[str], ignore_paths: ty.Iterable[str]
) -> None:
    """Copy files from source to destination directory while ignoring certain files/folders.

    :param src_dir: Source directory
    :param dest_dir: Destination directory
    :param ignore_files: A list of file names (UNIX shell style patterns allowed) which are not copied to the
        destination.
    :param ignore_paths: A list of paths (UNIX shell style patterns allowed) which are not copied to the destination.
    """
    exclude_paths: ty.Set = {filepath for path in ignore_paths for filepath in src_dir.glob(path)}
    exclude_files = {path.relative_to(src_dir) for path in exclude_paths if path.is_file()}
    exclude_dirs = {path.relative_to(src_dir) for path in exclude_paths if path.is_dir()}

    # Here we rely on getting the directory name before
    # accessing its content, hence using os.walk.
    for dirpath, _, filenames in os.walk(src_dir):
        relative_dir = Path(dirpath).relative_to(src_dir)
        dirs_to_check = list(relative_dir.parents) + [relative_dir]

        if relative_dir.parts and relative_dir.parts[0] == ('.aiida'):
            continue

        if any(exclude_dir in dirs_to_check for exclude_dir in exclude_dirs):
            continue

        for filename in filenames:
            if any(fnmatch.fnmatch(filename, expr) for expr in ignore_files):
                continue

            if relative_dir / filename in exclude_files:
                continue

            os.makedirs(dest_dir / relative_dir, exist_ok=True)

            relative_file_path = relative_dir / filename
            shutil.copyfile(src_dir / relative_file_path, dest_dir / relative_file_path)
