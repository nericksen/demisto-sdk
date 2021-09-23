import io
import os
import shlex
import tarfile
from functools import lru_cache
from pathlib import Path
from typing import Union

import docker
import docker.errors
import docker.errors
from docker.models.containers import Container

from demisto_sdk.commands.common.tools import print_warning


def get_file_from_container(container_obj: Container, container_path: str, encoding: str = "") -> Union[str, bytes]:
    """
    Copy file from container.
    Args:
        container_obj(Container): Container ID to copy file from.
        container_path(Path): Path in container image (file).
        encoding(str): Valid encoding e.g. utf-8.

    Returns:
        (Union[str,bytes]): File as string decoded in utf-8.

    Raises:
        IOError: Raise IO error if unable to create temp file
    """
    data: Union[str, bytes] = b''
    archive, stat = container_obj.get_archive(container_path)
    file_like = io.BytesIO(b"".join(b for b in archive))
    tar = tarfile.open(fileobj=file_like)
    before_read = tar.extractfile(stat['name'])
    if isinstance(before_read, io.BufferedReader):
        data = before_read.read()
    if encoding and isinstance(data, bytes):
        data = data.decode(encoding)

    return data


@lru_cache(maxsize=100)
def get_python_version_from_image(image: str, timeout: int = 60, log_prompt: str = '') -> float:
    """
    Get python version from docker image.
    Args:
        image(str): Docker image id or name.
        timeout(int): Docker client request timeout.
        log_prompt (str): Log prompt. For debugging purposes.
    Returns:
        (float): Python version X.Y (3.7, 3.6, ..).
    """
    # skip powershell images
    if 'pwsh' in image or 'powershell' in image:
        return 3.8

    docker_user = os.getenv('DOCKERHUB_USER')
    docker_pass = os.getenv('DOCKERHUB_PASSWORD')
    docker_client = docker.from_env(timeout=timeout)
    docker_client.login(username=docker_user,
                        password=docker_pass,
                        registry="https://index.docker.io/v1")
    py_num = 3.8
    # Run three times
    for attempt in range(3):
        try:
            command = "python -c \"import sys; print('{}.{}'.format(sys.version_info[0], sys.version_info[1]))\""

            container_obj: Container = docker_client.containers.run(
                image=image,
                command=shlex.split(command),
                detach=True
            )
            # Wait for container to finish
            container_obj.wait(condition="exited")
            # Get python version
            py_num = container_obj.logs()
            if isinstance(py_num, bytes):
                py_num = float(py_num)
                for _ in range(2):
                    # Try to remove the container two times.
                    try:
                        container_obj.remove(force=True)
                        break
                    except docker.errors.APIError:
                        print_warning(f'{log_prompt} - Could not remove the image {image}')
                return py_num
            else:
                raise docker.errors.ContainerError

        except Exception:
            print_warning(
                f'{log_prompt} - Failed detecting Python version (in attempt {attempt}) for image {image}')
            continue

    return py_num
