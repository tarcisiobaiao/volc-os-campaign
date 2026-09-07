# Probes herméticos da base

Diagnósticos de leitura executados no código `d54e10012c34aeaae2e2089945178bc20353e145`. Não são testes adicionados ao produto. Usam somente mocks/objetos sintéticos, sem token, arquivo de credencial ou conexão com banco.

Resultados observados:

| Probe | Resultado da base | Interpretação |
| --- | --- | --- |
| P01 | Filtro de conta ausente em conjuntos/anúncios/mensuração | F07 reproduzido no adapter de consulta. |
| P02 | `NOT_AN_IMAGE` aceito como `AUTHORIZED`, `READY_FOR_PAID_MEDIA` | F01: sem decode técnico dos bytes. |
| P03 | Confirmação de duas horas recusada com `META_ASSET_POLICY_RECEIPT_EXPIRED` | Expiração é esperada para nova aprovação. F02 é sua ligação indevida ao caminho de recuperação, confirmada por fonte; não houve execução do ledger real. |
| P04 | LPV 4 + ViewContent 7 retorna 11; LPV NULL retorna 0 | F09 reproduzido. |

Executar o bloco Python abaixo a partir da worktree com `PYTHONPATH=backend backend/.venv/bin/python -B`. É código de diagnóstico, não um script a implantar. Após as correções, a saída deve mudar; não transformar o comportamento defeituoso em expectativa de regressão.

```python
import asyncio
import json
import socket
from datetime import date, datetime, timedelta, timezone

def deny_network(*args, **kwargs):
    raise RuntimeError('HERMETIC_PROBE_NETWORK_FORBIDDEN')

socket.socket.connect = deny_network
socket.socket.connect_ex = deny_network
socket.create_connection = deny_network

import httpx
from app.trafego.meta.read_model import RepositorioMetaReadModelSupabase
from app.trafego.meta.adaptador import _landing_page_views
from app.trafego.meta.dominio import AcaoInsightMeta
from app.trafego.meta_execucao.ativos import (
    AtivoDeCriacaoMeta, _AtivoResolvido, ResolvedorAtivosMeta,
)
from app.trafego.meta_execucao.contrato import (
    DeclaracaoPoliticaAtivoMeta, ErroDeNascimentoMeta,
)

class SelectSpy:
    enabled = True
    def __init__(self):
        self.calls = []
    async def select(self, table, params):
        self.calls.append({'table': table, 'params': dict(params)})
        return []

async def run():
    spy = SelectSpy()
    repo = RepositorioMetaReadModelSupabase(spy)
    for entity in ('campanhas', 'conjuntos', 'anuncios', 'criativos', 'insights', 'mensuracao'):
        await repo.listar(entity, 'metaacct_probe')
    print(json.dumps({'probe': 'P01', 'calls': spy.calls}, ensure_ascii=False))

    transport = httpx.MockTransport(lambda request: httpx.Response(
        200, content=b'NOT_AN_IMAGE', headers={'content-type': 'image/png'},
    ))
    asset = _AtivoResolvido(
        publico=AtivoDeCriacaoMeta(
            referencia_opaca='metaasset_probe', nome='Imagem sintética de teste',
            tipo='image', largura=1200, altura=628, preview_disponivel=True,
        ),
        id_externo='probe_image_hash',
        preview_url='https://fixture.fbcdn.net/image.png',
    )
    async with httpx.AsyncClient(transport=transport) as client:
        resolver = ResolvedorAtivosMeta(client)
        for probe, age in (('P02', timedelta()), ('P03', timedelta(hours=2))):
            declaration = DeclaracaoPoliticaAtivoMeta(
                direitos_confirmados=True, identidade_de_terceiro_liberada=True,
                confirmada_em=datetime.now(timezone.utc) - age,
            )
            try:
                manifest = await resolver._manifestar_imagem(asset, declaration)
                result = {'accepted': True, 'policy_state': manifest.policy_state,
                          'lifecycle': manifest.lifecycle}
            except ErroDeNascimentoMeta as exc:
                result = {'accepted': False, 'code': exc.codigo}
            print(json.dumps({'probe': probe, 'result': result}))

    day = date(2026, 9, 1)
    def action(kind, value):
        return AcaoInsightMeta(kind, value, 'default', 'account', day, day)
    result = {
        'lpv_4_plus_view_content_7': _landing_page_views((
            action('landing_page_view', 4),
            action('offsite_conversion.fb_pixel_view_content', 7),
        )),
        'lpv_null': _landing_page_views((action('landing_page_view', None),)),
    }
    print(json.dumps({'probe': 'P04', 'result': result}))

asyncio.run(run())
```

A ligação de F02 está em `backend/app/routers/trafego_meta_criacao.py`, função `reconciliar`: recompila `plan_request` por `_compilar` antes de `ReconciliadorMetaSomenteLeitura.conciliar`. F03 é a seleção exclusiva de `AMBIGUOUS` na mesma rota, confrontada com `prepare_step` e as guardas de expiração no SQL.

Esses probes não substituem a matriz de crashes/concorrência em Postgres de T03, as provas autorizadas de conta nem a inspeção visual autenticada.
