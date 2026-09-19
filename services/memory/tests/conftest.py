from __future__ import annotations

import ipaddress
import socket

import pytest

from app.backends import StubBackend
from app.main import app


LOCAL_NAMES = {"localhost", "127.0.0.1", "::1", "testserver"}


def _is_local(host: object) -> bool:
    if not isinstance(host, str):
        return True
    if host in LOCAL_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@pytest.fixture(autouse=True)
def isolated_stub_and_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    app.state.backend = StubBackend()
    original_connect = socket.socket.connect
    original_getaddrinfo = socket.getaddrinfo

    def guarded_connect(instance: socket.socket, address: object) -> object:
        host = address[0] if isinstance(address, tuple) and address else address
        if not _is_local(host):
            raise AssertionError(f"test tried to open a non-local socket to {host}")
        return original_connect(instance, address)

    def guarded_getaddrinfo(host: object, *args: object, **kwargs: object) -> object:
        if not _is_local(host):
            raise AssertionError(f"test tried to resolve non-local host {host}")
        return original_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)

