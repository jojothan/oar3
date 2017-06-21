# coding: utf-8
from __future__ import unicode_literals, print_function

import os
import pytest

from click.testing import CliRunner

from oar.lib import (db, Job, Resource)
from oar.cli.oarremoveresource import cli
from oar.kao.job import insert_job

@pytest.yield_fixture(scope='function', autouse=True)
def minimal_db_initialization(request):
    with db.session(ephemeral=True):
        # add some resources
        for _ in range(5):
            db['Resource'].create(network_address="localhost")

        db['Queue'].create(name='default')
        yield

def test_oarremoveresource_void():
    runner = CliRunner()
    result = runner.invoke(cli)
    assert result.exit_code == 2

def test_oarremoveresource_bad_user():
    os.environ['OARDO_USER'] = 'Zorglub'
    runner = CliRunner()
    result = runner.invoke(cli,['1'])
    assert result.exit_code == 4

def test_oarremoveresource_not_dead():
    os.environ['OARDO_USER'] = 'oar'
    runner = CliRunner()
    result = runner.invoke(cli,['1'])
    assert result.exit_code == 3
    
def test_oarremoveresource_simple():
    os.environ['OARDO_USER'] = 'oar'
    runner = CliRunner()
    db['Resource'].create(network_address="localhost", state="Dead")
    nb_res1 = len(db.query(Resource).all())
    result = runner.invoke(cli, ['6'])
    nb_res2 = len(db.query(Resource).all())
    assert nb_res1 == 6
    assert nb_res2 == 5
    assert result.exit_code == 0
