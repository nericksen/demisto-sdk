import io
import os
import sqlite3
from pathlib import Path

import click
import coverage

from demisto_sdk.commands.common.tools import print_v


def coverage_report_editor(coverage_file, code_file_absolute_path):
    """

    Args:
        coverage_file: the .coverage file this contains the coverage data in sqlite format.
        code_file_absolute_path: the real absolute path to the measured code file.

    Notes:
        the .coverage files contain all the files list with their absolute path.
        but our tests (pytest step) are running inside a docker container.
        so we have to change the path to the correct one.
    """
    with sqlite3.connect(coverage_file) as sql_connection:
        cursor = sql_connection.cursor()
        index = cursor.execute('SELECT count(*) FROM file').fetchall()[0][0]
        if not index == 1:
            click.secho('unexpected file list in coverage report', fg='red')
        else:
            cursor.execute('UPDATE file SET path = ? WHERE id = ?', (code_file_absolute_path, 1))
            sql_connection.commit()
        cursor.close()
    if not index == 1:
        os.remove(coverage_file)


def generate_coverage_report(html=False, xml=False, report=True, cov_dir='coverage_report', verbose=False):
    """
    Args:
        html (bool): Should generate an html report. default is false.
        xml (bool): Should generate an xml report. default is false.
        report (bool): Should print the coverage report. default true.
        cov_dir (str): The directory to place the report files (.coverage, html and xml report).
        verbose (bool): Whether to print verbose.
    """
    cov_file = os.path.join(cov_dir, '.coverage')
    cov = coverage.Coverage(data_file=cov_file)
    cov.combine(coverage_files())
    if not os.path.exists(cov_file):
        print_v(f'skipping coverage report {cov_file} file not found.', log_verbose=verbose)
        return

    export_msg = 'exporting {0} coverage report to {1}'
    if report:
        report_data = io.StringIO()
        report_data.write(
            '\n\n############################\n unit-tests coverage report\n############################\n')
        try:
            cov.report(file=report_data)
        except coverage.misc.CoverageException as warning:
            if isinstance(warning.args, tuple) and warning.args and warning.args[0] == 'No data to report.':
                click.secho(f'No coverage data in file {cov_file}')
                return
            raise warning
        report_data.seek(0)
        click.secho(report_data.read())

    if html:
        html_dir = os.path.join(cov_dir, 'html')
        click.secho(export_msg.format('html', os.path.join(html_dir, 'index.html')))
        try:
            cov.html_report(directory=html_dir)
        except coverage.misc.CoverageException as warning:
            click.secho(str(warning), fg='yellow')
            return
    if xml:
        xml_file = os.path.join(cov_dir, 'coverage.xml')
        click.secho(export_msg.format('xml', xml_file))
        try:
            cov.xml_report(outfile=xml_file)
        except coverage.misc.CoverageException as warning:
            click.secho(str(warning), fg='yellow')
            return


def coverage_files():
    packs_pass = Path('Packs')
    for cov_path in packs_pass.glob('*/Integrations/*/.coverage'):
        yield str(cov_path)
    for cov_path in packs_pass.glob('*/Scripts/*/.coverage'):
        yield str(cov_path)
