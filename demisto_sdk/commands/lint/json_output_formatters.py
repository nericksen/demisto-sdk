import os
from abc import abstractmethod
from typing import List, Dict

from demisto_sdk.commands.common.tools import find_type, get_file_displayed_name, get_content_path, \
    retrieve_file_ending, find_file
from demisto_sdk.commands.lint.lint_constants import UnsuccessfulPackageReport


class Formatter:
    def __init__(self, linter_name: str):
        self.linter_name = linter_name

    @abstractmethod
    def get_format_entry(self, report: UnsuccessfulPackageReport):
        pass

    def enrich_output(self, output: Dict, fail_type: str):
        """Adds an error entry to the JSON file contents

        Args:
            output (Dict): The information about an error entry
            fail_type:
        """
        file_path: str = output.get('filePath', '')
        yml_file_path = file_path.replace('.py', '.yml').replace('.ps1', '.yml')
        file_type = find_type(yml_file_path)
        return {
            'fileType': os.path.splitext(file_path)[1].replace('.', ''),
            'entityType': file_type.value if file_type else '',
            'errorType': 'Code',
            'name': get_file_displayed_name(yml_file_path),
            'linter': self.linter_name,
            'severity': fail_type,
            **output
        }

    def format(self, fail_type: str, unsuccessful_package_report: List[UnsuccessfulPackageReport]) -> List[Dict]:
        return [self.enrich_output(self.get_format_entry(report), fail_type) for report in unsuccessful_package_report]


class Flake8Formatter(Formatter):
    def __init__(self):
        super().__init__('flake8')

    def get_format_entry(self, report: UnsuccessfulPackageReport):
        for output in report.outputs.split('\n'):
            file_path, line_number, column_number, _ = output.split(':', 3)
            code = output.split()[1]
            return {
                'errorCode': code,
                'message': output.split(code)[1].lstrip(),
                'row': line_number,
                'col': column_number,
                'filePath': file_path
            }


class BanditFormatter(Formatter):
    def __init__(self):
        super().__init__('bandit')

    def get_format_entry(self, report: UnsuccessfulPackageReport):
        for output in report.outputs.split('\n'):
            file_path, line_number, _ = output.split(':', 2)
            return {
                'errorCode': output.split(' ')[1],
                'message': output.split('[')[1].replace(']', ' -'),
                'row': line_number,
                'filePath': file_path
            }


class VultureFormatter(Formatter):
    def __init__(self):
        super().__init__('vulture')

    def get_format_entry(self, report: UnsuccessfulPackageReport):
        content_path = get_content_path()
        for output in report.outputs.split('\n'):
            file_name, line_number, error_contents = output.split(':', 2)
            file_path = self._get_full_file_path_for_vulture(file_name, content_path)
            return {
                'message': error_contents.lstrip(),
                'row': line_number,
                'filePath': file_path
            }

    @staticmethod
    def _get_full_file_path_for_vulture(file_name: str, content_path: str) -> str:
        """
        Get the full file path to a file with a given name name from the content path

        Args:
            file_name (str): The file name of the file to find
            content_path (str): The content file path

        Returns:
            str. The path to the file
        """
        file_ending = retrieve_file_ending(file_name)
        if not file_ending:
            file_name = f'{file_name}.py'
        elif file_ending != 'py':
            file_name = file_name.replace(file_ending, 'py')
        return find_file(content_path, file_name)


class MyPyFormatter(Formatter):
    def __init__(self):
        super().__init__('mypy')

    def get_format_entry(self, report: UnsuccessfulPackageReport):
        for output in self._gather_mypy_errors(report.outputs.split('\n')):
            file_path, line_number, column_number, _ = output.split(':', 3)
            output_message = output.split('error:')[1].lstrip() if 'error' in output else output.split('note:')[
                1].lstrip()
            return {
                'message': output_message,
                'row': line_number,
                'col': column_number,
                'filePath': file_path
            }

    @staticmethod
    def _gather_mypy_errors(outputs: List[str]) -> List[str]:
        """Gather multi-line mypy errors to a single line

        Args:
            outputs (List): A list of mypy error outputs

        Returns:
            List. A list of strings, each element is a full mypy error message
        """
        mypy_errors: list = []
        gather_error: list = []
        for line in outputs:
            if os.path.isfile(line.split(':')[0]):
                if gather_error:
                    mypy_errors.append('\n'.join(gather_error))
                    gather_error = []
            gather_error.append(line)

        # handle final error
        # last line is irrelevant
        if gather_error:
            mypy_errors.append('\n'.join(gather_error[:-1]))

        return mypy_errors


class XSOARFormatter(Formatter):
    def __init__(self):
        super().__init__('xsoar_linter')

    def get_format_entry(self, report: UnsuccessfulPackageReport):
        for output in report.outputs.split('\n'):
            split_message = output.split(':')
            file_path = split_message[0] if len(split_message) >= 1 else ''
            code = output.split(' ')[1] if len(output.split(' ')) >= 2 else ''
            return {
                'errorCode': code,
                'message': output.split(code)[-1].lstrip() if len(output.split(code)) >= 1 else '',
                'row': split_message[1] if len(split_message) >= 2 else '',
                'col': split_message[2] if len(split_message) >= 3 else '',
                'filePath': file_path
            }
