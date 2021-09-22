import os
from dataclasses import dataclass
from typing import Optional, List, Dict, Union
from demisto_sdk.commands.common.content.objects.pack_objects.integration.integration import Integration
from demisto_sdk.commands.common.content.objects.pack_objects.script.script import Script
from demisto_sdk.commands.common.tools import get_all_docker_images
from demisto_sdk.commands.lint.lint_refactor.lint_global_facts import LintGlobalFacts


@dataclass
class LintPackageFacts:
    images: List[str]
    python_version: Optional[int]
    env_vars: Dict
    lint_files: List
    additional_requirements: List[str]


def build_package_facts(lint_global_facts: LintGlobalFacts, package: Union[Script, Integration]) -> LintPackageFacts:
    images = get_package_images(lint_global_facts, package)
    return LintPackageFacts(
        images=images,
        python_version=None,
        env_vars={},
        lint_files=[],
        additional_requirements=[]
    )


def get_package_images(lint_global_facts: LintGlobalFacts, package: Union[Script, Integration]) -> List[str]:
    # logger.info(f"{log_prompt} - Pulling docker images, can take up to 1-2 minutes if not exists locally ")
    # TODO replace with TYPE_PYTHON
    if package.script_type == 'python' and lint_global_facts.has_docker_engine:
        return [image for image in get_all_docker_images(script_obj=package.script)]
    return []