import inspect

import pytest
from async_generator import isasyncgen

from aioinflux import logger


@pytest.mark.asyncio
async def test_iterpoints_with_parser(iter_client):
    r = await iter_client.query("SELECT * FROM cpu_load LIMIT 3",
                                parser=lambda x, meta: dict(zip(meta['columns'], x)))
    for i in r:
        logger.info(i)
        assert 'time' in i
        assert 'value' in i
        assert 'host' in i


@pytest.mark.asyncio
async def test_aiter_point(iter_client):
    resp = await iter_client.select_all(measurement='cpu_load',
                                        chunked=True, chunk_size=10, wrap=True)
    points = []
    async for point in resp:
        points.append(point)
    assert len(points) == 100


@pytest.mark.asyncio
async def test_aiter_chunk(iter_client):
    resp = await iter_client.select_all(measurement='cpu_load',
                                        chunked=True, chunk_size=10, wrap=True)
    assert isasyncgen(resp.gen)

    chunks = []
    async for chunk in resp.iterchunks():
        chunks.append(chunk)
    logger.info(resp)
    logger.info(chunks[0])
    assert len(chunks) == 10


@pytest.mark.asyncio
async def test_aiter_chunk_wrap(iter_client):
    resp = await iter_client.select_all(measurement='cpu_load',
                                        chunked=True, chunk_size=10, wrap=True)
    points = []
    async for chunk in resp.iterchunks(wrap=True):
        assert 'results' in chunk.data
        for point in chunk:
            points.append(point)
        assert chunk.series_count == 1
        assert 'results' in chunk.data
    assert len(points) == 100


@pytest.mark.asyncio
async def test_iter_wrap(iter_client):
    resp = await iter_client.select_all(measurement='cpu_load', wrap=True)
    assert 'results' in resp.data
    logger.info(resp)
    assert len(resp.show()) == len(resp)
