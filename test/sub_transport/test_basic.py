"""Test transport."""
import asyncio
from unittest import mock

import pytest
from serial import SerialException

from pymodbus.transport.nullmodem import DummyTransport


class TestBasicTransport:
    """Test transport module, base part."""

    async def test_init(self, transport, commparams):
        """Test init()"""
        commparams.done = False
        assert transport.comm_params == commparams
        assert (
            transport.cb_connection_made._extract_mock_name()  # pylint: disable=protected-access
            == "cb_connection_made"
        )
        assert (
            transport.cb_connection_lost._extract_mock_name()  # pylint: disable=protected-access
            == "cb_connection_lost"
        )
        assert (
            transport.cb_handle_data._extract_mock_name()  # pylint: disable=protected-access
            == "cb_handle_data"
        )
        assert not transport.reconnect_delay_current
        assert not transport.reconnect_task

    async def test_property_done(self, transport):
        """Test done property"""
        transport.comm_params.check_done()
        with pytest.raises(RuntimeError):
            transport.comm_params.check_done()

    async def test_with_magic(self, transport):
        """Test magic."""
        transport.close = mock.MagicMock()
        async with transport:
            pass
        transport.close.assert_called_once()

    async def test_str_magic(self, params, transport):
        """Test magic."""
        assert str(transport) == f"Transport({params.comm_name})"

    async def test_connection_made(self, transport, commparams):
        """Test connection_made()."""
        transport.loop = None
        transport.connection_made(DummyTransport())
        assert transport.transport
        assert not transport.recv_buffer
        assert not transport.reconnect_task
        assert transport.reconnect_delay_current == commparams.reconnect_delay
        transport.cb_connection_made.assert_called_once()
        transport.cb_connection_lost.assert_not_called()
        transport.cb_handle_data.assert_not_called()
        transport.close()

    async def test_connection_lost(self, transport):
        """Test connection_lost()."""
        transport.connection_lost(RuntimeError("not implemented"))
        assert not transport.transport
        assert not transport.recv_buffer
        assert not transport.reconnect_task
        assert not transport.reconnect_delay_current
        transport.cb_connection_made.assert_not_called()
        transport.cb_handle_data.assert_not_called()
        transport.cb_connection_lost.assert_called_once()

        transport.transport = mock.Mock()
        transport.connection_lost(RuntimeError("not implemented"))
        assert not transport.transport
        assert transport.reconnect_task
        transport.close()
        assert not transport.reconnect_task

    async def test_close(self, transport):
        """Test close()."""
        socket = DummyTransport()
        socket.abort = mock.Mock()
        socket.close = mock.Mock()
        transport.connection_made(socket)
        transport.cb_connection_made.reset_mock()
        transport.cb_connection_lost.reset_mock()
        transport.cb_handle_data.reset_mock()
        transport.recv_buffer = b"abc"
        transport.reconnect_task = mock.MagicMock()
        transport.close()
        socket.abort.assert_called_once()
        socket.close.assert_called_once()
        transport.cb_connection_made.assert_not_called()
        transport.cb_connection_lost.assert_not_called()
        transport.cb_handle_data.assert_not_called()
        assert not transport.recv_buffer
        assert not transport.reconnect_task

    async def test_reset_delay(self, transport, commparams):
        """Test reset_delay()."""
        transport.reconnect_delay_current += 5.17
        transport.reset_delay()
        assert transport.reconnect_delay_current == commparams.reconnect_delay

    async def test_datagram(self, transport):
        """Test datagram_received()."""
        transport.data_received = mock.MagicMock()
        transport.datagram_received(b"abc", "127.0.0.1")
        transport.data_received.assert_called_once()

    async def test_data(self, transport):
        """Test data_received."""
        transport.cb_handle_data = mock.MagicMock(return_value=2)
        transport.data_received(b"123456")
        transport.cb_handle_data.assert_called_once()
        assert transport.recv_buffer == b"3456"
        transport.data_received(b"789")
        assert transport.recv_buffer == b"56789"

    async def test_eof_received(self, transport):
        """Test eof_received."""
        transport.eof_received()

    async def test_error_received(self, transport):
        """Test error_received."""
        with pytest.raises(RuntimeError):
            transport.error_received(Exception("test call"))

    async def test_send(self, transport, params):
        """Test send()."""
        transport.transport = mock.AsyncMock()
        await transport.send(b"abc")

        transport.setup_udp(False, params.host, params.port)
        await transport.send(b"abc")
        transport.close()

    async def test_handle_listen(self, transport):
        """Test handle_listen()."""
        assert transport == transport.handle_listen()

    async def test_no_loop(self, transport):
        """Test properties."""
        transport.loop = None
        transport.call_connect_listen = mock.AsyncMock(return_value=(117, 118))
        await transport.transport_connect()
        assert transport.loop

    async def test_reconnect_connect(self, transport):
        """Test handle_listen()."""
        transport.comm_params.reconnect_delay = 0.01
        transport.transport_connect = mock.AsyncMock(side_effect=[False, True])
        await transport.reconnect_connect()
        assert (
            transport.reconnect_delay_current
            == transport.comm_params.reconnect_delay * 2
        )
        assert not transport.reconnect_task
        transport.transport_connect = mock.AsyncMock(
            side_effect=asyncio.CancelledError("stop loop")
        )
        await transport.reconnect_connect()
        assert (
            transport.reconnect_delay_current == transport.comm_params.reconnect_delay
        )
        assert not transport.reconnect_task


@pytest.mark.skipif(pytest.IS_WINDOWS, reason="not implemented")
class TestBasicUnixTransport:
    """Test transport module, unix part."""

    @pytest.mark.xdist_group(name="server_serialize")
    @pytest.mark.parametrize("setup_server", [True, False])
    def test_properties(self, params, setup_server, transport, commparams):
        """Test properties."""
        transport.setup_unix(setup_server, params.host)
        commparams.host = params.host
        assert transport.comm_params == commparams
        assert transport.call_connect_listen
        transport.close()

    @pytest.mark.xdist_group(name="server_serialize")
    @pytest.mark.parametrize("setup_server", [True, False])
    def test_properties_windows(self, params, setup_server, transport):
        """Test properties."""
        with mock.patch(
            "pymodbus.transport.transport.sys.platform", return_value="windows"
        ), pytest.raises(RuntimeError):
            transport.setup_unix(setup_server, params.host)

    @pytest.mark.xdist_group(name="server_serialize")
    async def test_connect(self, params, transport):
        """Test connect_unix()."""
        transport.setup_unix(False, params.host)
        mocker = mock.AsyncMock()
        transport.loop.create_unix_connection = mocker
        mocker.side_effect = FileNotFoundError("testing")
        assert not await transport.transport_connect()
        mocker.side_effect = None

        mocker.return_value = (mock.Mock(), mock.Mock())
        assert await transport.transport_connect()
        transport.close()

    @pytest.mark.xdist_group(name="server_serialize")
    async def test_listen(self, params, transport):
        """Test listen_unix()."""
        transport.setup_unix(True, params.host)
        mocker = mock.AsyncMock()
        transport.loop.create_unix_server = mocker
        mocker.side_effect = OSError("testing")
        assert await transport.transport_listen() is None
        mocker.side_effect = None

        mocker.return_value = mock.Mock()
        assert mocker.return_value == await transport.transport_listen()
        transport.close()


class TestBasicTcpTransport:
    """Test transport module, tcp part."""

    @pytest.mark.xdist_group(name="server_serialize")
    @pytest.mark.parametrize("setup_server", [True, False])
    def test_properties(self, params, setup_server, transport, commparams):
        """Test properties."""
        transport.setup_tcp(setup_server, params.host, params.port)
        commparams.host = params.host
        commparams.port = params.port
        assert transport.comm_params == commparams
        assert transport.call_connect_listen
        transport.close()

    @pytest.mark.xdist_group(name="server_serialize")
    async def test_connect(self, params, transport):
        """Test connect_tcp()."""
        transport.setup_tcp(False, params.host, params.port)
        mocker = mock.AsyncMock()
        transport.loop.create_connection = mocker
        mocker.side_effect = asyncio.TimeoutError("testing")
        assert not await transport.transport_connect()
        mocker.side_effect = None

        mocker.return_value = (mock.Mock(), mock.Mock())
        assert await transport.transport_connect()
        transport.close()

    @pytest.mark.xdist_group(name="server_serialize")
    async def test_listen(self, params, transport):
        """Test listen_tcp()."""
        transport.setup_tcp(True, params.host, params.port)
        mocker = mock.AsyncMock()
        transport.loop.create_server = mocker
        mocker.side_effect = OSError("testing")
        assert await transport.transport_listen() is None
        mocker.side_effect = None

        mocker.return_value = mock.Mock()
        assert mocker.return_value == await transport.transport_listen()
        transport.close()

    @pytest.mark.xdist_group(name="server_serialize")
    async def test_is_active(self, params, transport):
        """Test properties."""
        transport.setup_tcp(False, params.host, params.port)
        assert not transport.is_active()
        transport.connection_made(mock.AsyncMock())
        assert transport.is_active()
        transport.close()


class TestBasicTlsTransport:
    """Test transport module, tls part."""

    @pytest.mark.xdist_group(name="server_serialize")
    @pytest.mark.parametrize("setup_server", [True, False])
    @pytest.mark.parametrize("sslctx", [None, "test ctx"])
    def test_properties(self, setup_server, sslctx, params, transport, commparams):
        """Test properties."""
        with mock.patch("pymodbus.transport.transport.ssl.SSLContext"):
            transport.setup_tls(
                setup_server,
                params.host,
                params.port,
                sslctx,
                "certfile dummy",
                None,
                None,
                params.server_hostname,
            )
            commparams.host = params.host
            commparams.port = params.port
            commparams.server_hostname = params.server_hostname
            commparams.ssl = sslctx if sslctx else transport.comm_params.ssl
            assert transport.comm_params == commparams
            assert transport.call_connect_listen
        transport.close()

    @pytest.mark.xdist_group(name="server_serialize")
    async def test_connect(self, params, transport):
        """Test connect_tcls()."""
        transport.setup_tls(
            False,
            params.host,
            params.port,
            "no ssl",
            None,
            None,
            None,
            params.server_hostname,
        )
        mocker = mock.AsyncMock()
        transport.loop.create_connection = mocker
        mocker.side_effect = asyncio.TimeoutError("testing")
        assert not await transport.transport_connect()
        mocker.side_effect = None

        mocker.return_value = (mock.Mock(), mock.Mock())
        assert await transport.transport_connect()
        transport.close()

    @pytest.mark.xdist_group(name="server_serialize")
    async def test_listen(self, params, transport):
        """Test listen_tls()."""
        transport.setup_tls(
            True,
            params.host,
            params.port,
            "no ssl",
            None,
            None,
            None,
            params.server_hostname,
        )
        mocker = mock.AsyncMock()
        transport.loop.create_server = mocker
        mocker.side_effect = OSError("testing")
        assert await transport.transport_listen() is None
        mocker.side_effect = None

        mocker.return_value = mock.Mock()
        assert mocker.return_value == await transport.transport_listen()
        transport.close()


class TestBasicUdpTransport:
    """Test transport module, udp part."""

    @pytest.mark.xdist_group(name="server_serialize")
    @pytest.mark.parametrize("setup_server", [True, False])
    def test_properties(self, params, setup_server, transport, commparams):
        """Test properties."""
        transport.setup_udp(setup_server, params.host, params.port)
        commparams.host = params.host
        commparams.port = params.port
        assert transport.comm_params == commparams
        assert transport.call_connect_listen
        transport.close()

    @pytest.mark.xdist_group(name="server_serialize")
    async def test_connect(self, params, transport):
        """Test connect_udp()."""
        transport.setup_udp(False, params.host, params.port)
        mocker = mock.AsyncMock()
        transport.loop.create_datagram_endpoint = mocker
        mocker.side_effect = asyncio.TimeoutError("testing")
        assert not await transport.transport_connect()
        mocker.side_effect = None

        mocker.return_value = (mock.Mock(), mock.Mock())
        assert await transport.transport_connect()
        transport.close()

    @pytest.mark.xdist_group(name="server_serialize")
    async def test_listen(self, params, transport):
        """Test listen_udp()."""
        transport.setup_udp(True, params.host, params.port)
        mocker = mock.AsyncMock()
        transport.loop.create_datagram_endpoint = mocker
        mocker.side_effect = OSError("testing")
        assert await transport.transport_listen() is None
        mocker.side_effect = None

        mocker.return_value = (mock.Mock(), mock.Mock())
        assert await transport.transport_listen() == mocker.return_value[0]
        transport.close()


class TestBasicSerialTransport:
    """Test transport module, serial part."""

    @pytest.mark.xdist_group(name="server_serialize")
    @pytest.mark.parametrize("setup_server", [True, False])
    def test_properties(self, params, setup_server, transport, commparams):
        """Test properties."""
        transport.setup_serial(
            setup_server,
            params.host,
            params.baudrate,
            params.bytesize,
            params.parity,
            params.stopbits,
        )
        commparams.host = params.host
        commparams.baudrate = params.baudrate
        commparams.bytesize = params.bytesize
        commparams.parity = params.parity
        commparams.stopbits = params.stopbits
        assert transport.comm_params == commparams
        assert transport.call_connect_listen
        transport.close()

    @pytest.mark.xdist_group(name="server_serialize")
    async def test_connect(self, params, transport):
        """Test connect_serial()."""
        transport.setup_serial(
            False,
            params.host,
            params.baudrate,
            params.bytesize,
            params.parity,
            params.stopbits,
        )
        mocker = mock.AsyncMock()
        with mock.patch(
            "pymodbus.transport.transport.create_serial_connection", new=mocker
        ):
            mocker.side_effect = asyncio.TimeoutError("testing")
            assert not await transport.transport_connect()
            mocker.side_effect = None

            mocker.return_value = (mock.Mock(), mock.Mock())
            assert await transport.transport_connect()
            transport.close()

    @pytest.mark.xdist_group(name="server_serialize")
    async def test_listen(self, params, transport):
        """Test listen_serial()."""
        transport.setup_serial(
            True,
            params.host,
            params.baudrate,
            params.bytesize,
            params.parity,
            params.stopbits,
        )
        mocker = mock.AsyncMock()
        with mock.patch(
            "pymodbus.transport.transport.create_serial_connection", new=mocker
        ):
            mocker.side_effect = SerialException("testing")
            assert await transport.transport_listen() is None
            mocker.side_effect = None

            mocker.return_value = mock.Mock()
            assert await transport.transport_listen() == mocker.return_value
            transport.close()
