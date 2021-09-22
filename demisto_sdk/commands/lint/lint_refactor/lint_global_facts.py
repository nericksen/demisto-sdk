import json
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Set, Optional

import docker
import docker.errors
import requests.exceptions
import urllib3.exceptions
from git import Repo, InvalidGitRepositoryError, NoSuchPathError, GitCommandError
from wcmatch.pathlib import Path

from demisto_sdk.commands.common.constants import DemistoException
from demisto_sdk.commands.common.tools import is_external_repository, print_error, print_v, print_warning

EXTERNAL_REPO_FILE_PATH: Set[Path] = {Path("demistomock.py"),
                                      Path("dev_envs/pytest/conftest.py"),
                                      Path("CommonServerPython.py"),
                                      Path("demistomock.ps1"),
                                      Path("CommonServerPowerShell.ps1")
                                      }

NON_EXTERNAL_REPO_FILE_PATH: Set[Path] = {Path("Tests/demistomock/demistomock.py"),
                                          Path("Tests/scripts/dev_envs/pytest/conftest.py"),
                                          Path("Packs/Base/Scripts/CommonServerPython/CommonServerPython.py"),
                                          Path("Tests/demistomock/demistomock.ps1"),
                                          Path("Packs/Base/Scripts/CommonServerPowerShell/CommonServerPowerShell.ps1")
                                          }


@dataclass
class LintGlobalFacts:
    content_repo: Optional[Repo]
    requirements_python3: List[str]
    requirements_python2: List[str]
    test_modules: Dict
    has_docker_engine: bool
    docker_timeout: int
    keep_container: bool
    verbose: bool


def build_lint_global_facts(docker_timeout: int, keep_container: bool, verbose: bool) -> LintGlobalFacts:
    """
    Builds all the global facts needed for Lint command to be run, including:
    - Repository Lint is being run on.
    - Requirements for python 2/3.
    - Whether machine running Lint has docker engine.
    - Test modules needed (E.g, CSP, demistomock...)
    Args:
        docker_timeout (int): Timeout for Linters using docker.
        keep_container (bool): Whether to keep container for Linters running docker.
        verbose (bool): Verbose, for debugging purposes.

    Returns:
        (LintGlobalFacts): Lint global facts.
    """
    is_external_repo = is_external_repository()

    git_repo: Optional[Repo] = _get_content_repo(is_external_repo, verbose)

    pipfile_dir = Path(__file__).parent / 'resources'
    requirements_python2: List[str] = _get_dev_requirements_from_pipfile_lock(pipfile_dir, '2', verbose)
    requirements_python3: List[str] = _get_dev_requirements_from_pipfile_lock(pipfile_dir, '3', verbose)

    docker_engine: bool = _has_docker_engine(verbose)

    test_modules = _get_test_modules(git_repo, is_external_repo)
    return LintGlobalFacts(
        content_repo=git_repo,
        requirements_python3=requirements_python3,
        requirements_python2=requirements_python2,
        test_modules=test_modules,
        has_docker_engine=docker_engine,
        docker_timeout=docker_timeout,
        keep_container=keep_container,
        verbose=verbose,
    )


def _get_content_repo(is_external_repo: bool, verbose: bool) -> Repo:
    """
    Gets the Content-like repository.
    Args:
        is_external_repo (bool): Whether this is an external repository.
        verbose (bool): Verbose, for debugging purposes.

    Returns:
        (Repo): Git repository.
    """
    try:
        git_repo = Repo(os.getcwd(), search_parent_directories=True)
        remote_url = git_repo.remote().urls.__next__()
        is_fork_repo = 'content' in remote_url

        if not is_fork_repo and not is_external_repo:
            raise InvalidGitRepositoryError

        print_v(f'Content path {git_repo.working_dir}', log_verbose=verbose)
        return git_repo
    except (InvalidGitRepositoryError, NoSuchPathError) as e:
        print_warning('Unable to locate git repository. Are you sure you are running lint from content-like '
                      'repository?')
        print_v(f"can't locate content repo {e}")


def _get_dev_requirements_from_pipfile_lock(pipfile_dir: Path, py_num: str, verbose: bool) -> List[str]:
    """
    Receives the pipfile dir and gets the pipfile lock requirements by given Python number.
    The pipfile is expected to reside in pipfile_python{py_num} directory inside `pipfile_dir`.
    Args:
        pipfile_dir (Path): Path to the Pipfile dir.
        py_num (str): Python number to retrieve its Pipfile.
        verbose (bool): Verbose for debugging purposes.

    Returns:
        (List[str]) Requirements list.
    """
    pipfile_lock_path = pipfile_dir / f'pipfile_python{py_num}/Pipfile.lock'
    try:
        with open(file=pipfile_lock_path) as f:
            lock_file: dict = json.load(fp=f)["develop"]
        requirements_list = [key + value['version'] for key, value in lock_file.items()]
        print_v(f'Successfully collected the following test requirements for python {py_num}:\n{requirements_list}',
                log_verbose=verbose)
        return requirements_list
    except (json.JSONDecodeError, IOError, FileNotFoundError, KeyError) as e:
        # TODO : get rid of all sys exits and do it in one place
        print_error("Can't parse pipfile.lock - Aborting!")
        print_error(f"demisto-sdk-can't parse pipfile.lock {e}")
        sys.exit(1)


def get_modules_from_content_repo(content_repo: Repo, modules: Set[Path], is_external_repo: bool) -> Dict:
    """
    Gets modules content from the expected relative path in the given repository.
    Args:
        content_repo (Repo): Given repository.
        modules (Set[Path]): Set of relative paths of modules to be retrieved from GitHub.
        is_external_repo (bool): Whether this is an external repository.

    Returns:
        (Dict): Dict of {module relative path: module content}.
    """
    non_existence_modules: Set[Path] = {module for module in modules if not os.path.exists(module)}
    if non_existence_modules:
        print_warning(f'Could not find the following modules: {non_existence_modules}')
        if is_external_repo:
            raise DemistoException(f'Unable to locate modules: {modules} in external repository. Aborting.')
    return {module: (content_repo.working_dir / module).read_bytes() for module in (modules - non_existence_modules)}


def _get_modules_content_from_github(modules: Set[Path]) -> Dict:
    """
    Receives set of modules, gets their content from Github.
    Args:
        modules (Set[Path]): Set of relative paths of modules to be retrieved from GitHub.

    Returns:
        (Dict): Dict of {module relative path: module content}.
    """

    def get_module_content(module: Path):
        url = f'https://raw.githubusercontent.com/demisto/content/master/{module}'
        for trial in range(2):
            res = requests.get(url=url, verify=False)
            if res.ok:
                return res.content
            elif trial == 2:
                raise requests.exceptions.ConnectionError(f'Could not get the module: {module} from GitHub. Aborting.')

    return {module: get_module_content(module) for module in modules}


def _get_test_modules(content_repo: Optional[Repo], is_external_repo: bool) -> Dict[Path, bytes]:
    err_msg_prefix: str = 'Unable to get mandatory test-modules demisto-mock.py etc - Aborting!'
    modules = EXTERNAL_REPO_FILE_PATH if is_external_repo else NON_EXTERNAL_REPO_FILE_PATH
    try:
        if content_repo:
            modules_content = get_modules_from_content_repo(content_repo, modules, is_external_repo)
        else:
            modules_content = _get_modules_content_from_github(modules)
    except (DemistoException, GitCommandError) as e:
        if is_external_repo:
            print_error('You are running on an external repo - '
                        'run `.hooks/bootstrap` before running the demisto-sdk lint command\n'
                        'See here for additional information: https://xsoar.pan.dev/docs/concepts/dev-setup')
        else:
            print_error(f'{err_msg_prefix} corrupt repository or pull from master. Error message: {e}')
        sys.exit(1)
    except (requests.exceptions.ConnectionError, urllib3.exceptions.NewConnectionError) as e:
        print_error(f'{err_msg_prefix} (Check your internet connection). Error message: {e}')
        sys.exit(1)

    modules_content[Path("CommonServerUserPython.py")] = b''
    return modules_content


def _has_docker_engine(verbose: bool) -> bool:
    """
    Checks whether the machine running lint has docker engine.
    Args:
        verbose (bool): Verbose, for debugging purposes.

    Returns:
        (bool): True if machine running list has docker engine configured, false otherwise.
    """
    # Validating docker engine connection
    docker_client: docker.DockerClient = docker.from_env()
    try:
        print_v('Sending a ping to Docker client', log_verbose=verbose)
        docker_client.ping()
    except (requests.exceptions.ConnectionError, urllib3.exceptions.ProtocolError, docker.errors.APIError) as ex:
        if os.getenv('CI') and os.getenv('CIRCLE_PROJECT_REPONAME') == 'content':
            # when running lint in content we fail if docker isn't available for some reason
            raise ValueError('Docker engine not available and we are in content CI env. Can not run lint!!') from ex
        print_warning('Cannot communicate with Docker daemon - check your docker Engine is ON - Skipping lint tests '
                      ' which require docker!')
        return False
    print_v('Docker daemon test passed', log_verbose=verbose)
    return True
