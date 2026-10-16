import socket

import pytest


def test_pacote_importa():
    import volc_dil

    assert volc_dil.__version__


def test_rede_bloqueada_contraprova():
    with pytest.raises(RuntimeError):
        socket.create_connection(("example.com", 443), timeout=1)
