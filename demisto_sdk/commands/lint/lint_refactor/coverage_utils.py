import sqlite3
import click
import os


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
