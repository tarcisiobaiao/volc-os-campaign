"""A porta para o control plane externo — e nada do Postiz atravessa por ela.

## O que esta porta e, e o que ela recusa ser

O Postiz e um SERVICO SEPARAVEL, integrado por API oficial. Ele tem licenca
AGPL-3.0 (https://github.com/gitroomhq/postiz-app/blob/main/LICENSE, consultado
em 02/09/2026), e por isso nenhuma linha do codigo dele entra no core do VOLC.
Esta porta e a fronteira: de um lado, tipos do VOLC; do outro, HTTP.

Ela tambem NAO fala com o banco interno do Postiz. O Postiz tem Postgres proprio
(`DATABASE_URL`, via Prisma) e nunca recebe a `service_role` do Supabase — o
adaptador desta casa so conhece um segredo, o token da API do control plane.

## As capacidades, medidas contra a API oficial em 02/09/2026

| operacao VOLC          | endpoint oficial                | observacao                        |
|------------------------|---------------------------------|-----------------------------------|
| `criar_rascunho`       | `POST /posts` com `type=draft`  |                                   |
| `agendar`              | `POST /posts` com `type=schedule` e `date` em UTC ISO |          |
| `publicar_agora`       | `POST /posts` com `type=now`    | so com consentimento humano       |
| `consultar`            | `GET /posts?startDate&endDate`  | ⚠️ NAO existe `GET /posts/{id}`   |
| `cancelar`             | `DELETE /posts/{id}`            | apaga todos do mesmo grupo        |
| `prontidao`            | `GET /integrations`             | ⚠️ NAO ha health oficial          |
| `listar_canais`        | `GET /integrations`             |                                   |

⚠️ DUAS AUSENCIAS REAIS, E NENHUMA FOI CONTORNADA COM ENDPOINT INVENTADO:

1. **Nao ha busca de um post por id.** A consulta e por JANELA DE DATA e devolve
   uma lista; a reconciliacao FILTRA pela referencia externa que ja temos. Uma
   implementacao que fingisse `GET /posts/{id}` produziria 404 em producao.
2. **Nao ha endpoint de health publico.** `prontidao()` usa `GET /integrations`
   como PROXY e diz isso no proprio resultado (`fonte='proxy:/integrations'`).
   Chamar isso de "health check" seria afirmar uma capacidade que a API nao
   documenta.

E uma ausencia que decide o desenho do nosso lado:

3. **A API publica nao documenta idempotencia.** Nao ha campo de request-id no
   schema de `POST /posts`. Logo a idempotencia NAO pode ser delegada: ela vive
   no ledger da v14_01, e a porta e chamada no maximo uma vez por job.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


class FalhaDoControlPlane(Exception):
    """O control plane recusou de forma DETERMINADA. Nao adianta reenviar igual.

    `permanente=True` significa: o pedido, como esta, nunca vai passar (400, 401,
    403, 422). `permanente=False` e recusa que pode mudar (429, 503) — mas ainda
    assim e uma resposta CONHECIDA, e por isso e falha e nao incerteza.
    """

    def __init__(self, mensagem: str, *, status: int | None = None,
                 permanente: bool = True) -> None:
        super().__init__(mensagem)
        self.status = status
        self.permanente = permanente


class DesfechoIncerto(Exception):
    """Nao sabemos o que aconteceu: timeout, conexao cortada, corpo ilegivel.

    ⚠️ ESTA EXCECAO E O CORACAO DA HONESTIDADE DESTA PORTA. Quando ela sobe, o
    pedido PODE ter chegado ao destino. Tratar como falha e convidar o operador
    a reenviar e duplicar o post; tratar como sucesso e inventar um recibo. O
    unico desfecho correto e `indeterminado`, que so sai pela reconciliacao.
    """


@dataclass(frozen=True)
class Canal:
    """Uma integracao do control plane, sem nada sensivel."""

    referencia_externa: str
    nome: str
    plataforma: str
    perfil: str | None = None
    desativado: bool = False


@dataclass(frozen=True)
class ReciboExterno:
    """A resposta do control plane, ja sanitizada e traduzida.

    `bruto` guarda o corpo do provedor DEPOIS de sanitizado, e existe porque
    "o provedor disse X" e a unica prova que temos quando alguem pergunta seis
    meses depois. Ele nunca contem token: o adaptador aplica
    `dominio.recusar_chave_sensivel` antes de construir este objeto.
    """

    referencia_externa: str
    estado_externo: str
    url_publicada: str | None = None
    publicado_em: str | None = None
    bruto: dict[str, Any] = field(default_factory=dict)

    def como_recibo(self) -> dict[str, Any]:
        """A forma que a funcao governada `concluir_despacho` espera."""
        recibo: dict[str, Any] = {
            "referencia_externa": self.referencia_externa,
            "estado_externo": self.estado_externo,
            "bruto": self.bruto,
        }
        if self.url_publicada:
            recibo["url_publicada"] = self.url_publicada
        if self.publicado_em:
            recibo["publicado_em"] = self.publicado_em
        return recibo


@dataclass(frozen=True)
class Prontidao:
    """O que sabemos sobre a saude do control plane, e de onde sabemos."""

    pronto: bool
    fonte: str
    detalhe: str
    canais_visiveis: int | None = None


@dataclass(frozen=True)
class SolicitacaoExterna:
    """O que sai daqui para o control plane. Montado a partir do SNAPSHOT.

    ⚠️ `snapshot` e o jsonb imutavel gravado na criacao do job. O despachante
    NUNCA rele a peca: se a peca ganhou versao nova depois da aprovacao, o que
    sai continua sendo o que foi aprovado. Essa e a contraprova I.
    """

    referencia_do_canal: str
    modo: str                      # draft | schedule | now
    texto: str
    instante_utc: str | None       # ISO 8601 UTC; obrigatorio em schedule
    imagens: tuple[str, ...] = ()
    plataforma: str = ""


@runtime_checkable
class PortaDePublicacao(Protocol):
    """O contrato que o nucleo conhece. Duas implementacoes o satisfazem:

    - `adaptadores.postiz.AdaptadorPostiz` — HTTP real contra a API oficial;
    - `adaptadores.fake.ControlPlaneFake` — servidor HTTP hermetico para E2E.

    O nucleo NAO precisa de nenhuma chamada real para ser provado. Essa e a
    razao de a porta existir como Protocol e nao como classe base: o fake nao
    herda comportamento nenhum do real, e por isso nao herda defeito nenhum.
    """

    async def criar_rascunho(self, pedido: SolicitacaoExterna) -> ReciboExterno: ...

    async def agendar(self, pedido: SolicitacaoExterna) -> ReciboExterno: ...

    async def publicar_agora(self, pedido: SolicitacaoExterna) -> ReciboExterno: ...

    async def consultar(self, referencia_externa: str, *,
                        janela_horas: int = 168) -> ReciboExterno | None: ...

    async def cancelar(self, referencia_externa: str) -> bool: ...

    async def listar_canais(self) -> list[Canal]: ...

    async def prontidao(self) -> Prontidao: ...


#: Operacoes que a API oficial do Postiz oferece e que esta v1 NAO exercita.
#: Declaradas aqui para que "nao implementamos" nao vire "nao existe".
CAPACIDADES_NAO_EXERCITADAS: dict[str, str] = {
    "promover_rascunho_para_agendado":
        "PUT /posts/{id}/status com body {status:'schedule'} — existe na API "
        "oficial (docs.postiz.com/public-api/posts/change-status, 02/09/2026) e "
        "nao foi implementada: promover mudaria o `modo`, que faz parte do "
        "snapshot imutavel. Um job novo com modo 'schedule' e o caminho desta v1.",
    "upload_de_midia":
        "POST /upload e POST /upload-from-url — nao exercitados. Esta v1 envia "
        "texto; imagem exige decidir onde o arquivo do Asset Vault e servido, e "
        "essa decisao e de infraestrutura.",
    "analytics":
        "GET /analytics/* — fora do escopo de publicacao.",
    "webhook_de_confirmacao":
        "Nao encontrado na documentacao publica consultada em 02/09/2026. A "
        "reconciliacao desta v1 e por consulta (pull), nao por notificacao.",
}
