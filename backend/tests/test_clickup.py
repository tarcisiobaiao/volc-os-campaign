"""O ClickUp está DESLIGADO no VOLC O.S., e este arquivo é o que o mantém assim.

Era uma integração herdada do webgo: ao mover o card para "Pronto", o sistema
gerava o `.docx` do briefing, abria uma task no ClickUp, anexava o arquivo e
comentava.

Duas decisões do operador a desmontaram, nesta ordem:

1. **O anexo saiu.** Documentação em cópia nasce desatualizada no instante em
   que o funil muda, e passam a existir duas versões sem ninguém saber qual
   vale.

2. **A task saiu junto.** O VOLC O.S. concentra o log e o trabalho. Um
   gerenciador externo dividiria a verdade em dois lugares.

Medido ANTES de cortar: **0 de 20 cards** tinham `clickup_task_id`. A
integração nunca chegou a ser usada nesta instância — nenhum dado se perdeu.

O que sobreviveu, de propósito:
  · as COLUNAS `clickup_task_id` / `clickup_task_url` no banco (vazias, e
    derrubar coluna é destrutivo por um ganho de nada);
  · `services/clickup_service.py`, sem chamadores — se um dia voltar, volta
    inteiro em vez de ser reescrito de memória;
  · o briefing, que virou página no próprio sistema (`/briefing.html`) com o
    `.docx` sob demanda (`/briefing.docx`).
"""
import asyncio
import os
import sys

for _k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "CLICKUP_API_TOKEN", "CLICKUP_LIST_ID"):
    os.environ[_k] = ""
os.environ["PAUTADOR_ENGINE"] = "mock"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings
from app.routers import entities as R

get_settings.cache_clear()


def test_dispatch_e_no_op_e_nunca_chama_o_clickup():
    """Mesmo com credencial e card completo, nada é criado."""
    res = asyncio.run(R._dispatch_clickup_briefing(get_settings(), object(), {"id": 1}))
    assert res["dispatched"] is False
    assert res["reason"] == "clickup_desligado_no_volc_os"


def test_nao_existe_mais_rota_nem_gatilho_de_clickup():
    """A rota manual e o disparo automático saíram. Se alguém religar por
    engano, este teste cai antes de a task aparecer na conta de alguém."""
    assert not hasattr(R, "create_clickup_task")
    assert not hasattr(R, "_clickup_task_name")
    assert not hasattr(R, "_clickup_description")

    rotas = {getattr(r, "path", "") for r in R.router.routes}
    assert not [p for p in rotas if "clickup" in p]


def test_o_briefing_continua_existindo_no_sistema():
    """A documentação não sumiu — mudou de casa."""
    rotas = {getattr(r, "path", "") for r in R.router.routes}
    assert any(p.endswith("/briefing.html") for p in rotas)
    assert any(p.endswith("/briefing.docx") for p in rotas)
