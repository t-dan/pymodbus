"""Test client async."""
import asyncio
from tempfile import gettempdir

import pytest
import pytest_asyncio

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.datastore import (
    ModbusSequentialDataBlock,
    ModbusServerContext,
    ModbusSlaveContext,
)
from pymodbus.server import ServerAsyncStop, StartAsyncUnixServer
from pymodbus.transaction import ModbusSocketFramer


PATH = gettempdir() + "/unix_domain_socket"
HOST = f"unix:{PATH}"


@pytest_asyncio.fixture(name="_mock_run_server")
async def _helper_server(path_addon):
    """Run server."""
    datablock = ModbusSequentialDataBlock(0x00, [17] * 100)
    context = ModbusSlaveContext(
        di=datablock, co=datablock, hr=datablock, ir=datablock, slave=1
    )
    asyncio.create_task(  # noqa: RUF006
        StartAsyncUnixServer(
            context=ModbusServerContext(slaves=context, single=True),
            path=PATH + path_addon,
            framer=ModbusSocketFramer,
        )
    )
    await asyncio.sleep(0.1)
    yield
    await ServerAsyncStop()


@pytest.mark.skipif(pytest.IS_WINDOWS, reason="Windows have a timeout problem.")
@pytest.mark.parametrize("path_addon", ["_1"])
async def test_unix_server(_mock_run_server):
    """Run async server with unix domain socket."""
    await asyncio.sleep(0.1)


@pytest.mark.skipif(pytest.IS_WINDOWS, reason="Windows have a timeout problem.")
@pytest.mark.parametrize("path_addon", ["_2"])
async def test_unix_async_client(path_addon, _mock_run_server):
    """Run async client with unix domain socket."""
    await asyncio.sleep(1)
    client = AsyncModbusTcpClient(
        HOST + path_addon,
        framer=ModbusSocketFramer,
    )
    await client.connect()
    assert client.connected

    rr = await client.read_coils(1, 1, slave=1)
    assert not rr.isError()
