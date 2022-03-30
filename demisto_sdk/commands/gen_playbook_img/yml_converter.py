from ast import operator
from setuptools import Command
from demisto_sdk.commands.common.tools import get_file
from enum import Enum
from json2html import *
from typing import Any, List, Dict, Union, Optional
import json
import os
import sys


def input_value_to_string(data: dict) -> Union[dict, str]:
    if not data:
        return ''

    if 'simple' in data:
        return data['simple']

    def get_filters(complex_data: dict) -> list:
        if 'filters' not in complex_data:
            return ['No filters applied']
        filters = []
        for f in complex_data['filters']:
            sub_filters = []
            for sub_filter in f:
                left = sub_filter["left"]["value"]["simple"]
                if 'right' not in sub_filter:
                    func = f'{sub_filter["operator"]}({left})'
                    sub_filters.append(func)
                else:
                    right = sub_filter["right"]["value"]["simple"]
                    func = f'{sub_filter["operator"]}({left}, {right})'
                    sub_filters.append(func)
            filter_str = ' OR '.join(sub_filters)
            if len(sub_filters) > 1:
                filter_str = f'({filter_str})'
            filters.append(filter_str)
        return filters

    def get_transformers(complex_data: dict) -> list:
        if 'transformers' not in complex_data:
            return ['No transformers applied']
        transformers = []
        for t in complex_data['transformers']:
            args_list = ['value']
            for arg, val in t.get('args', {}).items():
                args_list.append(f'{arg}={val.get("value", {}).get("simple")}')
            args = ', '.join(args_list)
            func = f'{t["operator"]}({args})'
            transformers.append(func)
        return transformers
    
    complex_data = data['complex']
    root = complex_data['root']
    return {
        'Get': root,
        'Where': get_filters(complex_data),
        'Transformers': get_transformers(complex_data)
    }


def get_task_details_tab_information(data: dict) -> Optional[Dict[str, Any]]:
    res = {}

    if 'tags' in data:
        res['tags'] = data['tags']
    if 'description' in data:
        res['description'] = data['description']

    return res

def get_common_tab_details(data: dict) -> Dict[str, Any]:
    return {
        'details': get_task_details_tab_information(data['task']),
        'timers': data['timertriggers']
    }

def get_inputs_outputs_info(data) -> Dict[str, Any]:
    return {
        'inputs': [{
            'Name': input['key'],
            'Value': input_value_to_string(input['value']),
            'Description': input['description'],
            'Mandatory': input['required']
        } for input in data.get('inputs', [])],
        'outputs': data.get('outputs', [])
    }

def get_script_arguments(data) -> Dict[str, Any]:
    return {
        'inputs': [{
            'Name': arg_name,
            'Value': input_value_to_string(arg_value)
        } for arg_name, arg_value in data.get('scriptarguments', {}).items()]
    }

def escape(s, quote=True):
    s = s.replace("&", "&amp;")
    s = s.replace("<", "&lt;")
    s = s.replace(">", "&gt;")
    s = s.replace("(", "&lpar;")
    s = s.replace(")", "&rpar;")
    s = s.replace("[", "&lbrack;")
    s = s.replace("]", "&rbrack;")
    s = s.replace("{", "&lbrace;")
    s = s.replace("}", "&rbrace;")
    s = s.replace("|", "&vert;")
    if quote:
        s = s.replace('"', "&quot;")
        s = s.replace('\'', "&#x27;")
    return s


class Task(Enum):
    START = 'startTask'
    SECTION_HEADER = 'sectionHeaderTask'
    COMMAND = 'commandTask'
    CONDITION = 'conditionTask'
    SUBPLAYBOOK = 'subplaybookTask'


class TaskInfo:
    def __init__(
        self,
        task_type: Task,
        task_id: str,
        name: str,
        next_tasks: dict,
        task_data: dict
    ) -> None:
        self.task_type = task_type
        self.task_id = task_id
        self.name = name if task_type != Task.START else 'Playbook Triggered'
        self.next_tasks = next_tasks
        self.task_data = task_data
    
    @property
    def identifier(self) -> str:
        return f'TASK_{self.task_id}'
    
    @property
    def icon(self) -> str:
        if self.task_type == Task.CONDITION:
            return 'fa:fa-circle-question '
        if self.task_type == Task.COMMAND:
            return 'fa:fa-code '
        if self.task_type == Task.SUBPLAYBOOK:
            return 'fa:fa-book '
        return ''

    def get_mermaid_definition(self) -> str:
        return f'class {self.identifier} {self.task_type.value}'
    
    def get_mermaid_title(self) -> str:
        title: str = f'{self.icon}<b>#{self.task_id} {self.name}</b>'
        if self.task_type == Task.CONDITION.value:
            title = f'{{"{title}"}}'
        else:
            title = f'("{title}")'
        return f'{self.identifier}{title}'

    def get_mermaid_edges(self) -> List[str]:
        edges: List[str] = []
        for edge_type, tasks in self.next_tasks.items():
            if edge_type == '#none#':
                for t in tasks:
                    edges.append(f'{self.identifier} --> TASK_{t}')
            elif edge_type == '#default#':
                for t in tasks:
                    edges.append(f'{self.identifier} -- ELSE --> TASK_{t}')
            else:
                for t in tasks:
                    edges.append(f'{self.identifier} -- {edge_type.strip("#").upper()} --> TASK_{t}')
        return edges
    
    def get_mermaid_click_statement(self) -> str:
        return f'click {self.identifier} call showTask()'
    
    def to_mermaid(self) -> str:
        mermaid: List[str] = []
        mermaid.append(self.get_mermaid_title())
        mermaid.extend(self.get_mermaid_edges())
        mermaid.append(self.get_mermaid_definition())
        mermaid.append(self.get_mermaid_click_statement())
        return '\n'.join(mermaid)

    def get_task_info(self) -> Dict[str, Any]:
        if self.task_type == Task.START:
            return get_inputs_outputs_info(self.task_data)

        if self.task_type == Task.SECTION_HEADER:
            return self.get_section_header_info()

        if self.task_type == Task.COMMAND:
            return self.get_command_info()

        if self.task_type == Task.CONDITION:
            return self.get_condition_info()

        if self.task_type == Task.SUBPLAYBOOK:
            return self.get_subplaybook_info()
        
        return {}

    def get_section_header_info(self) -> Dict[str, Any]:
        return get_common_tab_details(self.task_data)

    def get_command_info(self) -> Dict[str, Any]:
        res = get_common_tab_details(self.task_data)
        res.update(get_script_arguments(self.task_data))
        return res

    def get_condition_info(self) -> Dict[str, Any]:
        res = get_common_tab_details(self.task_data)
        return res

    def get_subplaybook_info(self) -> Dict[str, Any]:
        res = get_common_tab_details(self.task_data)
        return res


class PlaybookYMLConverter:
    def __init__(self, file_path: str):
        data = get_file(file_path, '.yml')
        self.name = data['name']
        self.tasks = data['tasks']
        self.inputs_and_outputs = {
            'inputs': data['inputs'],
            'outputs': data['outputs']
        }
        self.mermaid_lines = []
        self.playbook_diagram = None
        self.tasks_info = {}
    
    def run(self) -> None:
        self.calculate_mermaid_lines()
        d = 'flowchart TB\n'
        d += '\n'.join(self.mermaid_lines)
        self.playbook_diagram = d
    
    def create_output_files(self):
        self.write_json()
        self.write_html()
    
    def write_json(self):
        with open(f'/Users/dtavori/dev/demisto/demisto-sdk/demisto_sdk/commands/gen_playbook_img/tasks.json', 'w') as f:
            f.write(json.dumps(self.tasks_info, indent=4))
    
    def write_html(self):
        with open('/Users/dtavori/dev/demisto/demisto-sdk/demisto_sdk/commands/gen_playbook_img/template.html', 'r') as t:
            template = t.read()
            output = template.replace('%% PLAYBOOK NAME %%', self.name).replace('%% DIAGRAM %%', self.playbook_diagram)
            with open(f'/Users/dtavori/dev/demisto/demisto-sdk/demisto_sdk/commands/gen_playbook_img/out.html', 'w') as f:
                f.write(output)
                print('Done')
    
    def calculate_mermaid_lines(self):
        for task_id in self.tasks:
            self.collect_task_info(task_id)
        
    def collect_task_info(self, task_id: str):
        t = self.create_task(task_id)
        self.tasks_info[t.identifier] = t.get_task_info()
        self.mermaid_lines.append(t.to_mermaid())
    
    def create_task(self, task_id: str):
        task_data = self.tasks[task_id]
        name = task_data['task'].get('name')
        next_tasks = task_data.get('nexttasks', {})

        if task_data['type'] == 'start':
            return TaskInfo(Task.START, task_id, None, next_tasks, self.inputs_and_outputs)

        if task_data['type'] == 'title':
            return TaskInfo(Task.SECTION_HEADER, task_id, name, next_tasks, task_data)

        if task_data['type'] == 'regular':
            return TaskInfo(Task.COMMAND, task_id, name, next_tasks, task_data)

        if task_data['type'] == 'condition':
            return TaskInfo(Task.CONDITION, task_id, name, next_tasks, task_data)
        
        if task_data['type'] == 'playbook':
            return TaskInfo(Task.SUBPLAYBOOK, task_id, name, next_tasks, task_data)

        return TaskInfo(Task.SECTION_HEADER, task_id, "Not implemented", next_tasks, None)

playbook_converter = PlaybookYMLConverter(sys.argv[1])
playbook_converter.run()
playbook_converter.create_output_files()
