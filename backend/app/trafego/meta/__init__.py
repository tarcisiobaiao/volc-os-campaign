"""Meta Ads read model, deliberately isolated from the Google-shaped v9 core.

Nothing in this package registers routes or enables the Meta capability.  The
first slice is hermetic by design: callers must inject both an HTTP client and
a secret resolver, and the production application does neither yet.
"""

from . import adaptador, credenciais, dominio, persistencia, sincronizador

__all__ = ("adaptador", "credenciais", "dominio", "persistencia", "sincronizador")
