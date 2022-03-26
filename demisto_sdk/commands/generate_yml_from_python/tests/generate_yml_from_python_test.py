import copy
import inspect

import pytest

from demisto_sdk.commands.common.handlers import YAML_Handler
from demisto_sdk.commands.generate_yml_from_python.generate_yml import \
    YMLGenerator
from demisto_sdk.commands.generate_yml_from_python.yml_metadata_collector import (
    ConfKey, InputArgument, OutputArgument, YMLMetadataCollector)

yaml = YAML_Handler()


def dedent(code_line, spaces_num):
    indent = spaces_num * ' '
    tab = '\t'
    if code_line.startswith(indent):
        code_line = code_line[spaces_num:]
    if code_line.startswith(tab):
        code_line = code_line[len(tab):]
    return code_line


def save_code_as_integration(code, full_path, configuration=None, conf_in_second_line=False,
                             docstring=''):
    code_snippet_lines = inspect.getsourcelines(code)[0][1:]
    first_indent = len(code_snippet_lines[0]) - len(code_snippet_lines[0].lstrip())
    code_snippet_dedented = [dedent(code_line, first_indent) for code_line in code_snippet_lines]
    code_snippet = ''.join(code_snippet_dedented)
    if docstring:
        code_snippet = code_snippet.replace('**docstring**', docstring)

    full_code = code_snippet
    if configuration:
        if conf_in_second_line:
            code_lines = code_snippet.split('\n')
            rest_of_code = '\n'.join(code_lines[1:])
            full_code = f"{code_lines[0]}\nconfiguration={configuration}\n\n{rest_of_code}"
            full_path.write_text(full_code)
        else:
            full_code = f"configuration={configuration}\n\n{code_snippet}"
            full_path.write_text(full_code)
    else:
        full_path.write_text(full_code)
    # will be printed if the test fails.
    print(f"The code in the test:\n{full_code}")


EMPTY_INTEGRATION_DICT = {'category': 'Utilities',
                          'commonfields': {'id': 'some_name', 'version': -1},
                          'configuration': [],
                          'description': '',
                          'display': 'some name',
                          'fromversion': '6.0.0',
                          'name': 'some_name',
                          'script': {'commands': [],
                                     'dockerimage': 'demisto/python3:latest',
                                     'feed': False,
                                     'isfetch': False,
                                     'longRunning': False,
                                     'longRunningPort': False,
                                     'runonce': False,
                                     'script': '-',
                                     'subtype': 'python3',
                                     'type': 'python'},
                          'tests': ['No tests']}

BASIC_CONF_KEY_DICT = {
    "display": "some_name",
    "name": "some_name",
    "type": 0,
    "required": False
}


class TestImportDependencies:
    def test_unrunnable_code_yml_generation(self, tmp_path):
        integration_path = tmp_path / "integration_name.py"

        def code_snippet():
            import hlem
            hlem.now()

            metadata_collector = YMLMetadataCollector(integration_name="some_name")  # noqa: F841

            def some_func():
                """Some func doc"""
                print("something nice")

        save_code_as_integration(code=code_snippet, full_path=integration_path)
        try:
            yml_generator = YMLGenerator(filename=integration_path)
            yml_generator.generate()
            expected_dict = copy.deepcopy(EMPTY_INTEGRATION_DICT)
            assert expected_dict == yml_generator.get_metadata_dict()
        except Exception as exc:
            assert False, f"Made up imports are not working anymore: {exc}"

    def test_generation_with_implicit_imports_in_declarations(self, tmp_path):
        """Explicit imports from CommonServerPython"""
        integration_path = tmp_path / "integration_name.py"

        def code_snippet():
            metadata_collector = YMLMetadataCollector(integration_name="some_name")  # noqa: F841

            class MyClient(BaseClient):  # noqa: F821, F841
                """Some class doc"""

                def __init__(self):
                    pass

            def some_command(dates: datetime.datetime) -> CommandResults:  # noqa: F821, F841
                return CommandResults()  # noqa: F401, F821

        save_code_as_integration(code=code_snippet, full_path=integration_path)
        try:
            yml_generator = YMLGenerator(filename=integration_path)
            yml_generator.generate()
            expected_dict = copy.deepcopy(EMPTY_INTEGRATION_DICT)
            assert expected_dict == yml_generator.get_metadata_dict()
        except Exception as exc:
            assert False, f"CommomServerPython imports are not working anymore: {exc}"

    def test_generation_with_subscriptable_imports(self, tmp_path):
        """Since the imports are mocked, it is important that they are MagicMocked and not regularly mocked.
        Otherwise they will not be subscriptable."""
        integration_path = tmp_path / "integration_name.py"

        def code_snippet():
            import datetime

            metadata_collector = YMLMetadataCollector(integration_name="some_name")  # noqa: F841

            def some_func():
                """Some func doc"""
                datetime[3] = 5
                print(f"func {datetime[3]}")

        save_code_as_integration(code=code_snippet, full_path=integration_path)
        try:
            yml_generator = YMLGenerator(filename=integration_path)
            yml_generator.generate()
            expected_dict = copy.deepcopy(EMPTY_INTEGRATION_DICT)
            assert expected_dict == yml_generator.get_metadata_dict()
        except Exception as exc:
            assert False, f"Imports are not subscriptable anymore: {exc}"


class TestConfigurationGeneration:

    @pytest.mark.parametrize("configuration, expected_update",
                             [({"integration_name": "some_other_name"}, {"commonfields": {"id": "some_other_name",
                                                                                          "version": -1},
                                                                         "name": "some_other_name",
                                                                         "display": "some other name"}),
                              ({"display": "not_some_name"}, {"display": "not_some_name"}),
                              ({"image": "some_image"}, {"image": "some_image"}),
                              ({"detailed_description": "some_detailed_description"},
                               {"detaileddescription": "some_detailed_description"}),
                              ({"description": "some_description"}, {"description": "some_description"}),
                              ({"category": "some_category"}, {"category": "some_category"}),
                              ({"tests": ["Test1", "Test2"]}, {"tests": ["Test1", "Test2"]}),
                              ({"fromversion": "7.0.0"}, {"fromversion": "7.0.0"}),
                              ({"system": True}, {"system": True}),
                              ({"system": False}, {"system": False}),
                              ({"timeout": "5s"}, {"timeout": "5s"}),
                              ({"default_classifier": "TheCalssifier"}, {"defaultclassifier": "TheCalssifier"}),
                              ({"default_mapper_in": "TheCalssifierIn"}, {"defaultmapperin": "TheCalssifierIn"}),
                              ({"default_enabled": True}, {"defaultEnabled": True}),
                              ({"default_enabled": False}, {"defaultEnabled": False}),
                              ({"deprecated": True}, {"deprecated": True}),
                              ({"deprecated": False}, {"deprecated": False}),
                              ({"default_enabled_x2": True}, {"defaultEnabled_x2": True}),
                              ({"default_enabled_x2": False}, {"defaultEnabled_x2": False}),
                              ({"integration_name_x2": "some_x2_name"},
                               {"commonfields": {"id": "some_name",
                                                 "version": -1,
                                                 "name_x2": "some_x2_name"}})],
                             ids=["integration_name", "display", "image", "detailed_description",
                                  "description", "category", "tests", "fromversion", "system=True", "system=False",
                                  "timeout", "default_classifier", "default_mapper_in", "default_enabled=True",
                                  "default_enabled=False", "deprecated=True", "deprecated=False",
                                  "default_enabled_x2=True", "default_enabled_x2=False", "integration_name_x2"])
    def test_generate_general_configuration(self, tmp_path, configuration, expected_update):
        integration_path = tmp_path / "integration_name.py"
        if "integration_name" not in configuration.keys():
            configuration.update({"integration_name": "some_name"})

        def code_snippet():
            metadata_collector = YMLMetadataCollector(**configuration)  # noqa: F841

            def some_func():
                """Some func doc"""
                print("func")

        save_code_as_integration(code=code_snippet, full_path=integration_path, configuration=configuration)
        yml_generator = YMLGenerator(filename=integration_path)
        yml_generator.generate()
        expected_dict = copy.deepcopy(EMPTY_INTEGRATION_DICT)
        expected_dict.update(expected_update)
        assert expected_dict == yml_generator.get_metadata_dict()

    @pytest.mark.parametrize("configuration, expected_update",
                             [({"docker_image": "some_dockerimage"}, {"dockerimage": "some_dockerimage"}),
                              ({"is_feed": True}, {"feed": True}),
                              ({"is_feed": False}, {"feed": False}),
                              ({"is_fetch": True}, {"isfetch": True}),
                              ({"is_fetch": False}, {"isfetch": False}),
                              ({"is_runonce": False}, {"runonce": False}),
                              ({"is_runonce": True}, {"runonce": True}),
                              ({"long_running": True}, {"longRunning": True}),
                              ({"long_running": False}, {"longRunning": False}),
                              ({"long_running_port": "8080"}, {"longRunningPort": "8080"}),
                              ({"integration_type": "java"}, {"type": "java"}),
                              ({"integration_subtype": "javascript"}, {"subtype": "javascript"})],
                             ids=["docker_image", "is_feed=True", "is_feed=False", "is_fetch=True", "is_fetch=False",
                                  "is_runonce=False", "is_runonce=True", "long_running=True", "long_running=False",
                                  "long_running_port", "type", "subtype"])
    def test_generate_general_script_configuration(self, tmp_path, configuration, expected_update):
        integration_path = tmp_path / "integration_name.py"
        if "integration_name" not in configuration.keys():
            configuration.update({"integration_name": "some_name"})

        def code_snippet():
            metadata_collector = YMLMetadataCollector(**configuration)  # noqa: F841

            def some_func():
                """Some func doc"""
                print("func")

        save_code_as_integration(code=code_snippet, full_path=integration_path, configuration=configuration)
        yml_generator = YMLGenerator(filename=integration_path)
        yml_generator.generate()
        expected_dict = copy.deepcopy(EMPTY_INTEGRATION_DICT)
        expected_dict["script"].update(expected_update)
        assert expected_dict == yml_generator.get_metadata_dict()

    @pytest.mark.parametrize("configuration, expected_update",
                             [({"name": "some_confkey_name"},
                               {"name": "some_confkey_name", "display": "some_confkey_name"}),
                              ({"display": "some_display_name"}, {"display": "some_display_name"}),
                              ({"default_value": "1337"}, {"defaultvalue": "1337"}),
                              ({"required": True}, {"required": True}),
                              ({"required": False}, {"required": False}),
                              ({"additional_info": "some more info"}, {"additionalinfo": "some more info"}),
                              ({"options": ["A", "B"]}, {"options": ["A", "B"]})],
                             ids=["name", "display", "default_value", "required=True", "required=False",
                                  "additional_info", "options"])
    def test_generate_conf_keys(self, tmp_path, configuration, expected_update):
        integration_path = tmp_path / "integration_name.py"
        if "name" not in configuration.keys():
            configuration.update({"name": "some_name"})

        def code_snippet():
            metadata_collector = YMLMetadataCollector(integration_name="some_name",  # noqa: F841
                                                      conf=[ConfKey(**configuration)])

            def some_func():
                """Some func doc"""
                print("func")

        save_code_as_integration(code=code_snippet, full_path=integration_path, configuration=configuration)
        yml_generator = YMLGenerator(filename=integration_path)
        yml_generator.generate()
        expected_dict = copy.deepcopy(EMPTY_INTEGRATION_DICT)
        expected_conf = copy.deepcopy(BASIC_CONF_KEY_DICT)
        expected_conf.update(expected_update)
        expected_dict["configuration"] = [expected_conf]
        assert expected_dict == yml_generator.get_metadata_dict()

    @pytest.mark.parametrize("configuration, expected_update",
                             [("ParameterTypes.STRING", {"type": 0}),
                              ("ParameterTypes.NUMBER", {"type": 1}),
                              ("ParameterTypes.ENCRYPTED", {"type": 4}),
                              ("ParameterTypes.BOOLEAN", {"type": 8}),
                              ("ParameterTypes.AUTH", {"type": 9}),
                              ("ParameterTypes.DOWNLOAD_LINK", {"type": 11}),
                              ("ParameterTypes.TEXT_AREA", {"type": 12}),
                              ("ParameterTypes.INCIDENT_TYPE", {"type": 13}),
                              ("ParameterTypes.TEXT_AREA_ENCRYPTED", {"type": 14}),
                              ("ParameterTypes.SINGLE_SELECT", {"type": 15}),
                              ("ParameterTypes.MULTI_SELECT", {"type": 16})],
                             ids=["key_type=STRING",
                                  "key_type=NUMBER", "key_type=ENCRYPTED", "key_type=BOOLEAN", "key_type=AUTH",
                                  "key_type=DOWNLOAD_LINK", "key_type=TEXT_AREA", "key_type=INCIDENT_TYPE",
                                  "key_type=TEXT_AREA_ENCRYPTED", "key_type=SINGLE_SELECT", "key_type=MULTI_SELECT"])
    def test_conf_keys_parameter_types(self, tmp_path, configuration, expected_update):
        integration_path = tmp_path / "integration_name.py"

        def code_snippet():
            metadata_collector = YMLMetadataCollector(integration_name="some_name",  # noqa: F841
                                                      conf=[ConfKey(name="some_name",
                                                                    key_type=configuration)])

            def some_func():
                """Some func doc"""
                print("func")

        save_code_as_integration(code=code_snippet, full_path=integration_path, configuration=configuration)
        yml_generator = YMLGenerator(filename=integration_path)
        yml_generator.generate()
        expected_dict = copy.deepcopy(EMPTY_INTEGRATION_DICT)
        expected_conf = copy.deepcopy(BASIC_CONF_KEY_DICT)
        expected_conf.update(expected_update)
        expected_dict["configuration"] = [expected_conf]
        assert expected_dict == yml_generator.get_metadata_dict()

    def test_enum_inputs_in_conf_key(self, tmp_path):
        integration_path = tmp_path / "integration_name.py"

        def code_snippet():
            import enum

            class InputOptions(enum.Enum):
                A = "a"
                B = "b"

            metadata_collector = YMLMetadataCollector(integration_name="some_name",  # noqa: F841
                                                      conf=[ConfKey(name="some_name",
                                                                    input_type=InputOptions)])

            def funky_command():
                """Some other description"""
                print("func")

        save_code_as_integration(code=code_snippet, full_path=integration_path)
        yml_generator = YMLGenerator(filename=integration_path)
        yml_generator.generate()
        expected_dict = copy.deepcopy(EMPTY_INTEGRATION_DICT)
        expected_conf = copy.deepcopy(BASIC_CONF_KEY_DICT)
        expected_conf.update({"options": ["a", "b"]})
        expected_dict["configuration"] = [expected_conf]
        assert expected_dict == yml_generator.get_metadata_dict()


BASIC_COMMAND_DICT = {'arguments': [],
                      'deprecated': False,
                      'description': 'Some other description',
                      'name': 'some-command',
                      'outputs': []}

BASIC_IN_ARG_DICT = {'default': False,
                     'name': 'some_arg',
                     'description': 'some_description',
                     'isArray': False,
                     'required': True,
                     'secret': False}

BASIC_OUT_ARG_DICT = {"contextPath": "some.some_out",
                      "description": "some desc",
                      "type": "Unknown"}


class TestCommandGeneration:
    @pytest.mark.parametrize("configuration, expected_update",
                             [({"command_name": "funky-command"}, {"name": "funky-command",
                                                                   "description": "Some funky command"}),
                              ({"command_name": "funky-command", "deprecated": True},
                               {"name": "funky-command", "description": "Some funky command", "deprecated": True}),
                              ({"command_name": "funky-command", "deprecated": False},
                               {"name": "funky-command", "description": "Some funky command", "deprecated": False}),
                              ({"command_name": "funky-command", "execution": True},
                               {"name": "funky-command", "description": "Some funky command", "execution": True}),
                              ({"command_name": "funky-command", "execution": False},
                               {"name": "funky-command", "description": "Some funky command", "execution": False})
                              ],
                             ids=["name", "deprecated=True", "deprecated=False", "execution=True", "execution=False"])
    def test_generate_command_generic(self, tmp_path, configuration, expected_update):
        integration_path = tmp_path / "integration_name.py"

        def code_snippet():
            metadata_collector = YMLMetadataCollector(integration_name="some_name")

            @metadata_collector.command(**configuration)
            def funky_command():
                """Some funky command"""
                print("func")

        save_code_as_integration(code=code_snippet, full_path=integration_path, configuration=configuration)
        yml_generator = YMLGenerator(filename=integration_path)
        yml_generator.generate()
        expected_dict = copy.deepcopy(EMPTY_INTEGRATION_DICT)
        expected_command = copy.deepcopy(BASIC_COMMAND_DICT)
        expected_command.update(expected_update)
        expected_dict["script"]["commands"] = [expected_command]
        assert expected_dict == yml_generator.get_metadata_dict()

    def test_long_description(self, tmp_path):
        integration_path = tmp_path / "integration_name.py"

        def code_snippet():
            metadata_collector = YMLMetadataCollector(integration_name="some_name")

            @metadata_collector.command(command_name="funky-command")
            def funky_command():
                """Some funky command
                Some interesting details and stuff

                other stuff
                """
                print("func")

        save_code_as_integration(code=code_snippet, full_path=integration_path, configuration="")
        yml_generator = YMLGenerator(filename=integration_path)
        yml_generator.generate()
        expected_dict = copy.deepcopy(EMPTY_INTEGRATION_DICT)
        expected_dict["script"]["commands"] = [{
            'arguments': [],
            'deprecated': False,
            'description': 'Some funky command\n    Some interesting details and stuff',
            'name': 'funky-command',
            'outputs': []
        }]
        assert expected_dict == yml_generator.get_metadata_dict()

    def test_restored_args_not_in_command_metadata(self, tmp_path):
        integration_path = tmp_path / "integration_name.py"

        def code_snippet():
            metadata_collector = YMLMetadataCollector(integration_name="some_name")

            @metadata_collector.command(command_name="funky-command", outputs_prefix='funk', execution=False,
                                        outputs_list=[OutputArgument(name="out1", output_type=str,
                                                                     description='desc1')],
                                        inputs_list=[InputArgument(name="in1")])
            def funky_command(client, outputs_prefix, execution, args):
                """Some funky command"""
                print("func")

        save_code_as_integration(code=code_snippet, full_path=integration_path, configuration="")
        yml_generator = YMLGenerator(filename=integration_path)
        yml_generator.generate()
        generated_dict = yml_generator.get_metadata_dict()

        # Make sure something was generated.
        assert "out1" in generated_dict["script"]["commands"][0]["outputs"][0]["contextPath"]

        arguments = generated_dict["script"]["commands"][0]["arguments"]
        args_names = [arguments[i]["name"] for i in range(len(arguments))]
        for restored_arg in YMLMetadataCollector.RESTORED_ARGS:
            assert restored_arg not in args_names

    def test_restored_args(self):
        # return it as a dict in the command and assert its right
        pass

    def test_enum_inputs_from_input_list(self, tmp_path):
        integration_path = tmp_path / "integration_name.py"

        def code_snippet():
            import enum

            class InputOptions(enum.Enum):
                A = "a"
                B = "b"

            metadata_collector = YMLMetadataCollector(integration_name="some_name")

            @metadata_collector.command(command_name="some-command",
                                        inputs_list=[InputArgument(name="some_arg",
                                                                   description="some_description",
                                                                   input_type=InputOptions)])
            def funky_command():
                """Some other description"""
                print("func")

        save_code_as_integration(code=code_snippet, full_path=integration_path)
        yml_generator = YMLGenerator(filename=integration_path)
        yml_generator.generate()
        expected_dict = copy.deepcopy(EMPTY_INTEGRATION_DICT)
        expected_command = copy.deepcopy(BASIC_COMMAND_DICT)
        expected_arg = copy.deepcopy(BASIC_IN_ARG_DICT)
        expected_arg.update({"auto": "PREDEFINED", "predefined": ["a", "b"]})
        expected_command["arguments"] = [expected_arg]
        expected_dict["script"]["commands"] = [expected_command]
        assert expected_dict == yml_generator.get_metadata_dict()

    @pytest.mark.parametrize("configuration, expected_update",
                             [({"name": "some_input_arg"}, {"name": "some_input_arg"}),
                              ({"description": "some desc"}, {"description": "some desc"}),
                              ({"required": True}, {"required": True}),
                              ({"default": True}, {"default": True, "defaultValue": True, "required": False}),
                              ({"is_array": True}, {"isArray": True}),
                              ({"secret": True}, {"secret": True}),
                              ({"execution": True}, {"execution": True}),
                              ({"options": ["a", "b"]}, {"auto": "PREDEFINED", "predefined": ["a", "b"]}),
                              ],
                             ids=["name", "description", "required", "default", "is_array", "secret", "execution",
                                  "options"])
    def test_inputs_from_input_list(self, tmp_path, configuration, expected_update):
        integration_path = tmp_path / "integration_name.py"

        if "name" not in configuration.keys():
            configuration.update({"name": "some_arg"})
        if "description" not in configuration.keys():
            configuration.update({"description": "some_description"})

        def code_snippet():
            metadata_collector = YMLMetadataCollector(integration_name="some_name")

            @metadata_collector.command(command_name="some-command",
                                        inputs_list=[InputArgument(**configuration)])
            def funky_command():
                """Some other description"""
                print("func")

        save_code_as_integration(code=code_snippet, full_path=integration_path, configuration=configuration)
        yml_generator = YMLGenerator(filename=integration_path)
        yml_generator.generate()
        expected_dict = copy.deepcopy(EMPTY_INTEGRATION_DICT)
        expected_command = copy.deepcopy(BASIC_COMMAND_DICT)
        expected_arg = copy.deepcopy(BASIC_IN_ARG_DICT)
        expected_arg.update(expected_update)
        expected_command["arguments"] = [expected_arg]
        expected_dict["script"]["commands"] = [expected_command]
        assert expected_dict == yml_generator.get_metadata_dict()

    @pytest.mark.parametrize("docstring, expected_update",
                             [('Some other description\n'
                               '\n    Args:'
                               '\n        some_input_arg: some desc.',
                               {"name": "some_input_arg", "description": "some desc."}),
                              ('Some other description\n'
                               '\n    Args:'
                               '\n        some_input_arg: required. some desc.\n',
                               {"name": "some_input_arg", "description": "some desc.", "required": True}),
                              ('Some other description\n'
                               '\n    Args:'
                               '\n        some_input_arg: default=5. some desc.\n',
                               {"name": "some_input_arg", "description": "some desc.", "required": False,
                                "defaultValue": "5", "default": True}),
                              ('Some other description\n'
                               '\n    Args:'
                               '\n        some_input_arg: secret. some desc.\n',
                               {"name": "some_input_arg", "description": "some desc.", "secret": True}),
                              ('Some other description\n'
                               '\n    Args:'
                               '\n        some_input_arg: execution. some desc.\n',
                               {"name": "some_input_arg", "description": "some desc.", "execution": True}),
                              ('Some other description\n'
                               '\n    Args:'
                               '\n        some_input_arg: options=[A, B]. some desc.\n',
                               {'auto': 'PREDEFINED', "name": "some_input_arg", "description": "some desc.",
                                "predefined": ["A", "B"]}),
                              ('Some other description\n'
                               '\n    Args:'
                               '\n        some_input_arg (list): some desc.\n',
                               {"name": "some_input_arg", "description": "some desc.", "isArray": True}),
                              ('Some other description\n'
                               '\n    Args:'
                               '\n        some_input_arg (int): some desc.\n',
                               {"name": "some_input_arg", "description": "some desc.", "isArray": False}),
                              ('Some other description\n'
                               '\n    Args:'
                               '\n        some_input_arg: required. some desc. secret.\n',
                               {"name": "some_input_arg", "description": "some desc.", "required": True,
                                "secret": True}),
                              ('Some other description\n'
                               '\n    Args:'
                               '\n        some_input_arg (InputOptions): some desc.\n    ',
                               {'auto': 'PREDEFINED', "name": "some_input_arg", "description": "some desc.",
                                "predefined": ["a", "b"]}),
                              ],
                             ids=["basic", "required", "default", "secret", "execution", "options", "isArray=True",
                                  "isArray=False", "multiple flags", "type is enum"])
    def test_inputs_from_declaration(self, tmp_path, docstring, expected_update):
        integration_path = tmp_path / "integration_name.py"

        def code_snippet():
            import enum

            metadata_collector = YMLMetadataCollector(integration_name="some_name")

            class InputOptions(enum.Enum):
                A = "a"
                B = "b"

            @metadata_collector.command(command_name="some-command")
            def funky_command():
                """**docstring**"""
                print("func")

        save_code_as_integration(code=code_snippet, full_path=integration_path, docstring=docstring)
        yml_generator = YMLGenerator(filename=integration_path)
        yml_generator.generate()
        expected_dict = copy.deepcopy(EMPTY_INTEGRATION_DICT)
        expected_command = copy.deepcopy(BASIC_COMMAND_DICT)
        expected_arg = copy.deepcopy(BASIC_IN_ARG_DICT)
        expected_arg.update(expected_update)
        expected_command["arguments"] = [expected_arg]
        expected_dict["script"]["commands"] = [expected_command]
        assert expected_dict == yml_generator.get_metadata_dict()

    @pytest.mark.parametrize("docstring, expected_update",
                             [('Some other description\n'
                               '\n    Context Outputs:'
                               '\n        some_out_arg (str): some desc.\n',
                               {"contextPath": "some_name.some_out_arg", "description": "some desc.",
                                "type": "String"}),
                              ('Some other description\n'
                               '\n    Context Outputs:'
                               '\n        some_out_arg (int): some desc.\n',
                               {"contextPath": "some_name.some_out_arg", "description": "some desc.",
                                "type": "Number"}),
                              ('Some other description\n'
                               '\n    Context Outputs:'
                               '\n        some_out_arg (float): some desc.\n',
                               {"contextPath": "some_name.some_out_arg", "description": "some desc.",
                                "type": "Number"}),
                              ('Some other description\n'
                               '\n    Context Outputs:'
                               '\n        some_out_arg (bool): some desc.\n',
                               {"contextPath": "some_name.some_out_arg", "description": "some desc.",
                                "type": "Boolean"}),
                              ('Some other description\n'
                               '\n    Context Outputs:'
                               '\n        some_out_arg (datetime.datetime): some desc.\n',
                               {"contextPath": "some_name.some_out_arg", "description": "some desc.",
                                "type": "Date"}),
                              ('Some other description\n'
                               '\n    Context Outputs:'
                               '\n        some_out_arg (dict): some desc.\n',
                               {"contextPath": "some_name.some_out_arg", "description": "some desc.",
                                "type": "Unknown"}),
                              ('Some other description\n'
                               '\n    Context Outputs:'
                               '\n        some_out_arg (dict): some interesting\n very long description.\n',
                               {"contextPath": "some_name.some_out_arg",
                                "description": "some interesting\n very long description.",
                                "type": "Unknown"})
                              ],
                             ids=["type str", "type int", "type float", "type bool", "type date",
                                  "type dict", "long description"])
    def test_outputs_from_declaration(self, tmp_path, docstring, expected_update):
        integration_path = tmp_path / "integration_name.py"

        def code_snippet():
            metadata_collector = YMLMetadataCollector(integration_name="some_name")

            @metadata_collector.command(command_name="some-command")
            def funky_command():
                """**docstring**"""
                print("func")

        save_code_as_integration(code=code_snippet, full_path=integration_path, docstring=docstring)
        yml_generator = YMLGenerator(filename=integration_path)
        yml_generator.generate()
        expected_dict = copy.deepcopy(EMPTY_INTEGRATION_DICT)
        expected_command = copy.deepcopy(BASIC_COMMAND_DICT)
        expected_arg = copy.deepcopy(BASIC_OUT_ARG_DICT)
        expected_arg.update(expected_update)
        expected_command["outputs"] = [expected_arg]
        expected_dict["script"]["commands"] = [expected_command]
        assert expected_dict == yml_generator.get_metadata_dict()

    def test_outputs_from_output_list(self, tmp_path):
        integration_path = tmp_path / "integration_name.py"

        def code_snippet():
            metadata_collector = YMLMetadataCollector(integration_name="some_name")

            @metadata_collector.command(command_name="some-command", outputs_prefix="some",
                                        outputs_list=[OutputArgument(name="some_out",
                                                                     description="some desc")])
            def funky_command():
                """Some other description"""
                print("func")

        save_code_as_integration(code=code_snippet, full_path=integration_path)
        yml_generator = YMLGenerator(filename=integration_path)
        yml_generator.generate()
        expected_dict = copy.deepcopy(EMPTY_INTEGRATION_DICT)
        expected_command = copy.deepcopy(BASIC_COMMAND_DICT)
        expected_out = copy.deepcopy(BASIC_OUT_ARG_DICT)
        expected_command["outputs"] = [expected_out]
        expected_dict["script"]["commands"] = [expected_command]
        assert expected_dict == yml_generator.get_metadata_dict()

    @pytest.mark.parametrize("configuration, expected_update",
                             [('str', {"type": "String"}),
                              ('int', {"type": "Number"}),
                              ('float', {"type": "Number"}),
                              ('bool', {"type": "Boolean"}),
                              ('dict', {"type": "Unknown"}),
                              ('list', {"type": "Unknown"}),
                              ('datetime.datetime', {"type": "Date"})
                              ],
                             ids=["str", "int", "float", "bool", "dict", "list", "datetime"])
    def test_outputs_types_from_output_list(self, tmp_path, configuration, expected_update):
        integration_path = tmp_path / "integration_name.py"

        def code_snippet():
            import datetime  # noqa: F401

            metadata_collector = YMLMetadataCollector(integration_name="some_name")

            @metadata_collector.command(command_name="some-command", outputs_prefix="some",
                                        outputs_list=[OutputArgument(name="some_out",
                                                                     description="some desc",
                                                                     output_type=configuration)])
            def funky_command():
                """Some other description"""
                print("func")

        save_code_as_integration(code=code_snippet, full_path=integration_path, configuration=configuration,
                                 conf_in_second_line=True)
        yml_generator = YMLGenerator(filename=integration_path)
        yml_generator.generate()
        expected_dict = copy.deepcopy(EMPTY_INTEGRATION_DICT)
        expected_command = copy.deepcopy(BASIC_COMMAND_DICT)
        expected_out = copy.deepcopy(BASIC_OUT_ARG_DICT)
        expected_out.update(expected_update)
        expected_command["outputs"] = [expected_out]
        expected_dict["script"]["commands"] = [expected_command]
        assert expected_dict == yml_generator.get_metadata_dict()

    def test_input_list_overrides_docstring(self, tmp_path):
        integration_path = tmp_path / "integration_name.py"

        def code_snippet():
            metadata_collector = YMLMetadataCollector(integration_name="some_name")

            @metadata_collector.command(command_name="some-command",
                                        inputs_list=[InputArgument(name="listed_name",
                                                                   description="listed desc")])
            def funky_command():
                """Some other description

                Args:
                    doc_name: some doc.
                """
                print("func")

        save_code_as_integration(code=code_snippet, full_path=integration_path)
        yml_generator = YMLGenerator(filename=integration_path)
        yml_generator.generate()
        expected_dict = copy.deepcopy(EMPTY_INTEGRATION_DICT)
        expected_command = copy.deepcopy(BASIC_COMMAND_DICT)
        expected_arg = copy.deepcopy(BASIC_IN_ARG_DICT)
        expected_arg.update({"name": "listed_name", "description": "listed desc"})
        expected_command["arguments"] = [expected_arg]
        expected_dict["script"]["commands"] = [expected_command]
        assert expected_dict == yml_generator.get_metadata_dict()

    def test_output_list_overrides_docstring(self, tmp_path):
        integration_path = tmp_path / "integration_name.py"

        def code_snippet():
            import datetime  # noqa: 401

            metadata_collector = YMLMetadataCollector(integration_name="some_name")

            @metadata_collector.command(command_name="some-command", outputs_prefix="some",
                                        outputs_list=[OutputArgument(name="some_list_out",
                                                                     description="some list desc",
                                                                     output_type=str)])
            def funky_command():
                """Some other description

                Context Outputs:
                    some_doc_out (int): some doc desc

                """
                print("func")

        save_code_as_integration(code=code_snippet, full_path=integration_path)
        yml_generator = YMLGenerator(filename=integration_path)
        yml_generator.generate()
        expected_dict = copy.deepcopy(EMPTY_INTEGRATION_DICT)
        expected_command = copy.deepcopy(BASIC_COMMAND_DICT)
        expected_out = copy.deepcopy(BASIC_OUT_ARG_DICT)
        expected_out.update({"contextPath": "some.some_list_out",
                             "description": "some list desc",
                             "type": "String"})
        expected_command["outputs"] = [expected_out]
        expected_dict["script"]["commands"] = [expected_command]
        assert expected_dict == yml_generator.get_metadata_dict()

    def test_multiple_output_prefixes_in_declaration(self, tmp_path):
        integration_path = tmp_path / "integration_name.py"

        def code_snippet():
            metadata_collector = YMLMetadataCollector(integration_name="some_name")

            @metadata_collector.command(command_name="some-command", multiple_output_prefixes=True)
            def funky_command():
                """Some other description

                Context Outputs:
                    first_prefix.out1 (dict): first out in first prefix.
                    second_prefix.out1 (dict): first out in second prefix.
                    first_prefix.out2 (dict): second out in first prefix.
                    no_prefix_out (dict): no explicit prefix.
                """
                print("func")

        save_code_as_integration(code=code_snippet, full_path=integration_path)
        yml_generator = YMLGenerator(filename=integration_path)
        yml_generator.generate()
        expected_dict = copy.deepcopy(EMPTY_INTEGRATION_DICT)
        expected_command = copy.deepcopy(BASIC_COMMAND_DICT)
        arg1_pre1 = copy.deepcopy(BASIC_OUT_ARG_DICT)
        arg1_pre1.update({"contextPath": "first_prefix.out1", "description": "first out in first prefix."})
        arg2_pre1 = copy.deepcopy(BASIC_OUT_ARG_DICT)
        arg2_pre1.update({"contextPath": "second_prefix.out1", "description": "first out in second prefix."})
        arg1_pre2 = copy.deepcopy(BASIC_OUT_ARG_DICT)
        arg1_pre2.update({"contextPath": "first_prefix.out2", "description": "second out in first prefix."})
        no_prefix_arg = copy.deepcopy(BASIC_OUT_ARG_DICT)
        no_prefix_arg.update({"contextPath": "some_name.no_prefix_out", "description": "no explicit prefix."})
        expected_command["outputs"] = [arg1_pre1, arg2_pre1, arg1_pre2, no_prefix_arg]
        expected_dict["script"]["commands"] = [expected_command]
        assert expected_dict == yml_generator.get_metadata_dict()

    def test_multiple_output_prefixes_in_list(self, tmp_path):
        integration_path = tmp_path / "integration_name.py"

        def code_snippet():
            metadata_collector = YMLMetadataCollector(integration_name="some_name")

            @metadata_collector.command(command_name="some-command", multiple_output_prefixes=True,
                                        outputs_list=[OutputArgument(name="out1",
                                                                     prefix="first_prefix",
                                                                     description="first out in first prefix."),
                                                      OutputArgument(name="out2",
                                                                     prefix="first_prefix",
                                                                     description="second out in first prefix."),
                                                      OutputArgument(name="out1",
                                                                     prefix="second_prefix",
                                                                     description="first out in second prefix."),
                                                      OutputArgument(name="no_prefix_out",
                                                                     description="no explicit prefix.")
                                                      ])
            def funky_command():
                """Some other description"""
                print("func")

        save_code_as_integration(code=code_snippet, full_path=integration_path)
        yml_generator = YMLGenerator(filename=integration_path)
        yml_generator.generate()
        expected_dict = copy.deepcopy(EMPTY_INTEGRATION_DICT)
        expected_command = copy.deepcopy(BASIC_COMMAND_DICT)
        arg1_pre1 = copy.deepcopy(BASIC_OUT_ARG_DICT)
        arg1_pre1.update({"contextPath": "first_prefix.out1", "description": "first out in first prefix."})
        arg2_pre1 = copy.deepcopy(BASIC_OUT_ARG_DICT)
        arg2_pre1.update({"contextPath": "second_prefix.out1", "description": "first out in second prefix."})
        arg1_pre2 = copy.deepcopy(BASIC_OUT_ARG_DICT)
        arg1_pre2.update({"contextPath": "first_prefix.out2", "description": "second out in first prefix."})
        no_prefix_arg = copy.deepcopy(BASIC_OUT_ARG_DICT)
        no_prefix_arg.update({"contextPath": "some_name.no_prefix_out", "description": "no explicit prefix."})
        expected_command["outputs"] = [arg1_pre1, arg1_pre2, arg2_pre1, no_prefix_arg]
        expected_dict["script"]["commands"] = [expected_command]
        assert expected_dict == yml_generator.get_metadata_dict()


class TestYMLGeneration:
    FULL_INTEGRATION_DICT = {'category': 'Utilities',
                             'commonfields': {'id': 'some_name', 'version': -1},
                             'configuration': [{
                                 "display": "confkey1",
                                 "name": "confkey1",
                                 "type": 0,
                                 "required": False
                             }, {
                                 "display": "confkey2",
                                 "name": "confkey2",
                                 "type": 0,
                                 "required": False
                             }],
                             'description': '',
                             'display': 'some name',
                             'fromversion': '6.0.0',
                             'name': 'some_name',
                             'script': {'commands': [{
                                 'arguments': [{
                                     'default': False,
                                     'name': 'classy_arg1',
                                     'description': 'some classy first arg.',
                                     'isArray': False,
                                     'required': True,
                                     'secret': False
                                 }, {
                                     'default': False,
                                     'name': 'classy_arg2',
                                     'description': 'some classy second arg.',
                                     'isArray': False,
                                     'required': True,
                                     'secret': False
                                 }
                                 ],
                                 'deprecated': False,
                                 'description': 'Some classy description.',
                                 'name': 'some-classy-command',
                                 'outputs': [{
                                     "contextPath": "some_name.classy_out1",
                                     "description": "some classy first out.",
                                     "type": "String"
                                 }, {
                                     "contextPath": "some_name.classy_out2",
                                     "description": "some classy second out.",
                                     "type": "Number"
                                 }]},
                                 {
                                     'arguments': [{
                                         'default': False,
                                         'name': 'some_in1',
                                         'description': 'in one desc',
                                         'isArray': False,
                                         'required': True,
                                         'secret': False
                                     }, {
                                         'default': False,
                                         'name': 'some_in2',
                                         'description': 'in two desc',
                                         'isArray': False,
                                         'required': True,
                                         'secret': False
                                     }],
                                     'deprecated': False,
                                     'description': 'Some funky description.',
                                     'name': 'some-funky-command',
                                     'outputs': [{
                                         "contextPath": "some_name.some_out1",
                                         "description": "some one desc",
                                         "type": "String"
                                     }, {
                                         "contextPath": "some_name.some_out2",
                                         "description": "some two desc",
                                         "type": "Unknown"
                                     }]}],
                                 'dockerimage': 'demisto/python3:latest',
                                 'feed': False,
                                 'isfetch': False,
                                 'longRunning': False,
                                 'longRunningPort': False,
                                 'runonce': False,
                                 'script': '-',
                                 'subtype': 'python3',
                                 'type': 'python'},
                             'tests': ['No tests']}

    def full_integration_code_snippet(self):
        metadata_collector = YMLMetadataCollector(integration_name="some_name",
                                                  conf=[ConfKey(name="confkey1"),
                                                        ConfKey(name="confkey2")])

        @metadata_collector.command(command_name="some-funky-command",
                                    inputs_list=[InputArgument(name="some_in1",
                                                               description="in one desc"),
                                                 InputArgument(name="some_in2",
                                                               description="in two desc")],
                                    outputs_list=[OutputArgument(name="some_out1",
                                                                 description="some one desc",
                                                                 output_type=str),
                                                  OutputArgument(name="some_out2",
                                                                 description="some two desc",
                                                                 output_type=dict)])
        def funky_command():
            """Some funky description."""
            print("func")

        @metadata_collector.command(command_name="some-classy-command")
        def classy_command():
            """Some classy description.

            Args:
                classy_arg1: some classy first arg.
                classy_arg2: some classy second arg.

            Context Outputs:
                classy_out1 (str): some classy first out.
                classy_out2 (int): some classy second out.
            """
            print("func")

    def test_yml_file_making(self, tmp_path):
        integration_path = tmp_path / "integration_name.py"
        save_code_as_integration(code=TestYMLGeneration.full_integration_code_snippet, full_path=integration_path)
        yml_generator = YMLGenerator(filename=integration_path)
        yml_generator.generate()
        yml_generator.save_to_yml_file()
        with open(tmp_path / "integration_name.yml", "r") as generated_yml:
            metadata_dict = yaml.load(generated_yml)

        assert metadata_dict == yml_generator.get_metadata_dict()

    def test_complete_integration_generation(self, tmp_path):
        integration_path = tmp_path / "integration_name.py"
        save_code_as_integration(code=TestYMLGeneration.full_integration_code_snippet, full_path=integration_path)
        yml_generator = YMLGenerator(filename=integration_path)
        yml_generator.generate()
        assert self.FULL_INTEGRATION_DICT == yml_generator.get_metadata_dict()

    def test_no_metadata_collector_defined(self, tmp_path, capsys):
        integration_path = tmp_path / "integration_name.py"

        def code_snippet():
            def funky_command():
                """Some other description"""
                print("func")

        save_code_as_integration(code=code_snippet, full_path=integration_path)

        yml_generator = YMLGenerator(filename=integration_path)
        yml_generator.generate()
        out, err = capsys.readouterr()

        assert "No metadata collector found in" in out
        assert not yml_generator.is_generatable_file
        assert not yml_generator.metadata_collector
