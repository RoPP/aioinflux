import asyncio
import logging.config
from pathlib import Path

import pytest
import yaml
from async_generator import async_generator, yield_

from aioinflux import InfluxDBClient
from aioinflux import testing_utils as utils

with open(str(Path(__file__).parent / 'logging.yml')) as f:
    logging.config.dictConfig(yaml.load(f))


@pytest.yield_fixture(scope='module')
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope='module')
@async_generator
async def async_client():
    async with InfluxDBClient(db='async_client_test', mode='async') as client:
        await client.create_database()
        await yield_(client)
        await client.drop_database()


@pytest.fixture(scope='module')
def sync_client():
    with InfluxDBClient(db='sync_client_test', mode='blocking') as client:
        client.create_database()
        yield client
        client.drop_database()


@pytest.fixture(scope='module')
def df_client():
    if utils.pd is None:
        return
    with InfluxDBClient(db='df_client_test', mode='blocking', output='dataframe') as client:
        client.create_database()
        yield client
        client.drop_database()


@pytest.fixture(scope='module')
@async_generator
async def iter_client():
    async with InfluxDBClient(db='iter_client_test', mode='async', output='iterable') as client:
        await client.create_database()
        await client.write([p for p in utils.cpu_load_generator(100)])
        await yield_(client)
        await client.drop_database()
