from pathlib import Path

from app.config import Settings, _RAIZ_REPOSITORIO


def test_fastapi_le_env_server_da_raiz_do_repositorio() -> None:
    """O QG não pode subir em 8010 sem a configuração que o launcher validou."""

    arquivos = tuple(Settings.model_config["env_file"])

    assert Path(arquivos[0]) == _RAIZ_REPOSITORIO / ".env.server"
    assert arquivos[1:] == (".env", ".env.local")
    assert _RAIZ_REPOSITORIO == Path(__file__).resolve().parents[2]
