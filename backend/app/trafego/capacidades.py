"""Capacidades do operador — separadas porque não são a mesma coisa.

## O problema que este módulo resolve

Ser ADMIN no VOLC O.S. e poder gastar dinheiro na conta do cliente eram, até
aqui, a mesma pergunta feita a lugares diferentes: `exigir_admin` guarda
`POST /subir` e `POST /remover`, e `volc_ads/gads/modo.py` guarda a saída da
requisição. As duas travas existem e funcionam — o que não existia era um lugar
que dissesse, para a TELA, quais delas estão abertas e por quê.

Sem isso a interface tem duas saídas ruins:

* **derivar tudo de `role === 'ADMIN'`** — e aí um administrador de produto vê
  botões de gasto que a trava do servidor vai recusar no clique, depois de todo
  o trabalho de montar o pedido;
* **não oferecer nada** — e aí a capacidade real fica escondida atrás de um
  cinza mudo, que é o defeito que `plataforma.py` já descreve para canal.

## Os cinco degraus gerais e a porta estreita

    is_admin               papel de PRODUTO. Administra usuários, contas, projeto.
    lab_mode               pode navegar a jornada inteira com fixture declarada.
    google_read            pode ver o que já foi lido da conta.
    google_validate_only   pode mandar o Google CONFERIR um pedido sem criar nada.
    google_mutate          pode criar ou alterar campanha de verdade.
    google_demand_gen_validate_only
                           porta experimental mais estreita; não herda a geral.

Elas formam degraus, e o degrau que importa é o último: `is_admin` NÃO implica
`google_mutate`. A implicação inversa vale — quem pode mutar é necessariamente
admin —, e é isso que a invariante `_coerente()` cobra.

⚠️ `google_validate_only` é deliberadamente concedido sem a trava de escrita.
`validate_only` é leitura para todos os efeitos: a API confere o payload e o
descarta (`volc_ads/gads/client.py:validar_mutacoes`, que não chama
`exigir_leitura_apenas`). Tratá-lo como escrita faria a prova — a única etapa
que separa "montei um pedido" de "tenho o direito de gastar" — ficar do lado
errado da porta, e o operador subiria sem provar por ser o caminho aberto.

## O que este módulo NÃO faz

Não decide autorização. Quem recusa continua sendo `exigir_admin` na rota e
`modo.exigir_leitura_apenas` na saída da requisição — as duas continuam valendo
mesmo que este módulo minta. Aqui só se PROJETA, para a tela, o que aquelas duas
já decidiram. Uma capacidade calculada aqui e não cobrada lá seria uma promessa
de tela, não uma permissão.

⚠️ E nada aqui vira claim de JWT. O token viaja para o navegador e tem vida
longa; um `google_mutate=true` gravado nele continuaria valendo depois de a
permissão ser revogada. É o mesmo argumento que `seguranca/identidade.py` já usa
para nunca ler papel do token — a resposta desta rota é um retrato do instante,
pedido a cada carregamento, e não uma credencial.
"""
from __future__ import annotations

import os
import pathlib
import sys
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, Optional

#: Quando o servidor oferece o laboratório. `auto` é o padrão e amarra a oferta
#: à trava de escrita: o laboratório existe exatamente enquanto NADA pode ser
#: escrito na conta do Google.
#:
#: ⚠️ Essa amarração é o ponto. Um laboratório que continuasse ligado no dia em
#: que a escrita abrisse seria a pior combinação possível — uma tela que convida
#: a explorar sem consequência, sobre um sistema que passou a ter consequência.
#: Em `auto`, abrir a escrita FECHA o laboratório, e ninguém precisa lembrar.
ENV_LABORATORIO = "VOLC_LABORATORIO"

# Porta experimental e SOMENTE de prova de Demand Gen. Diferente do
# laboratório, não existe modo `auto`: ausência, erro de grafia ou qualquer
# valor diferente de `on` mantêm a superfície fechada.
ENV_DEMAND_GEN_VALIDATE_ONLY = "VOLC_DEMAND_GEN_VALIDATE_ONLY"

AUTO = "auto"
LIGADO = "on"
DESLIGADO = "off"

MODOS = (AUTO, LIGADO, DESLIGADO)


def _modo_configurado() -> str:
    bruto = str(os.environ.get(ENV_LABORATORIO) or AUTO).strip().lower()
    # Valor desconhecido cai em `auto`, e não em `on`: um erro de digitação na
    # configuração não pode ser o que liga uma superfície.
    return bruto if bruto in MODOS else AUTO


def servidor_oferece_laboratorio(*, escrita_permitida: bool) -> bool:
    """O SERVIDOR oferece laboratório? Independe de quem está pedindo.

    Separado de `de_identidade` de propósito: isto é propriedade do ambiente, e
    misturá-lo com o papel da pessoa produziria o defeito de um ADMIN em
    produção herdar laboratório por ser admin.
    """
    modo = _modo_configurado()
    if modo == DESLIGADO:
        return False
    # ⚠️ Nem `on` abre laboratório sobre um servidor que pode escrever.
    #
    # `on` responde "eu QUERO o laboratório", e não "eu aceito o laboratório
    # sobre consequência real". A combinação — tela que convida a explorar sem
    # custo, sobre um sistema que passou a ter custo — é a que este módulo
    # declara ser a pior possível, e deixá-la depender de alguém lembrar de
    # trocar a variável no dia do deploy é deixá-la acontecer.
    if escrita_permitida:
        return False
    return modo == LIGADO or modo == AUTO


@lru_cache(maxsize=1)
def _sdk_demand_gen_disponivel() -> bool:
    """Os protos v25 usados pela prova existem e serializam neste processo?

    A flag declara intenção operacional; ela não consegue instalar namespace,
    enum ou campo no SDK. A sonda é local, não cria cliente autenticado e não
    chama a API. Importação, campo ou serialização ausente rebaixam a capacidade
    inteira — nunca há fallback silencioso para outra versão.
    """
    raiz = pathlib.Path(__file__).resolve().parents[3]
    if str(raiz) not in sys.path:
        sys.path.insert(0, str(raiz))
    try:
        from volc_ads.campanha.demand_gen import sondar_proto_v25

        return sondar_proto_v25().disponivel
    except Exception:  # noqa: BLE001 — ausência do SDK é estado de capacidade
        return False


def servidor_oferece_demand_gen_validate_only() -> bool:
    """Flag durável + SDK v25 real; desligada por padrão e fail-closed."""
    ligado = (
        str(os.environ.get(ENV_DEMAND_GEN_VALIDATE_ONLY) or "").strip().lower()
        == LIGADO
    )
    return ligado and _sdk_demand_gen_disponivel()


@dataclass(frozen=True)
class Capacidades:
    """O que ESTA pessoa pode, neste servidor, neste instante."""

    is_admin: bool
    lab_mode: bool
    google_read: bool
    google_validate_only: bool
    google_mutate: bool
    #: Capacidade mais estreita: permite somente `/provar` Demand Gen. Nunca
    #: autoriza `/subir`, mesmo quando `google_mutate` está aberta para Search.
    google_demand_gen_validate_only: bool = False
    #: Por que `google_mutate` está fechada, em uma frase que a tela pode
    #: mostrar. `None` quando ela está aberta.
    #:
    #: ⚠️ A frase é escrita para o OPERADOR, não para quem administra o
    #: servidor: ela não cita variável de ambiente, função nem arquivo. Uma
    #: instrução que a pessoa não tem como executar faz ela concluir que o
    #: sistema está quebrado — é a mesma correção que a rota `/trava` já levou.
    porque_sem_mutacao: Optional[str] = None

    def __post_init__(self) -> None:
        self._coerente()

    def _coerente(self) -> None:
        """As invariantes que separam papel de produto de poder de gasto."""
        if self.google_mutate and not self.is_admin:
            raise ValueError(
                "mutar sem ser admin: a porta de escrita exige papel "
                "administrativo, e uma capacidade que discorde dela promete "
                "à tela o que a rota vai recusar.")
        if self.google_mutate and not self.google_validate_only:
            raise ValueError(
                "mutar sem poder provar: a escada é montar → provar → subir, e "
                "pular a prova é o que ela existe para impedir.")
        if self.google_validate_only and not self.google_read:
            raise ValueError(
                "provar sem poder ler: provar um pedido contra uma conta que "
                "não se pode observar é decidir no escuro.")
        if self.google_demand_gen_validate_only and not self.google_validate_only:
            raise ValueError(
                "prova Demand Gen sem capacidade geral de validate_only"
            )
        if self.google_mutate and self.porque_sem_mutacao:
            raise ValueError(
                "mutação liberada com motivo de recusa preenchido — a tela "
                "mostraria as duas coisas ao mesmo tempo.")
        if self.lab_mode and self.google_mutate:
            raise ValueError(
                "laboratório aberto num servidor que escreve: a tela diria que "
                "nada tem consequência sobre um sistema que passou a ter.")
        if self.lab_mode and not self.is_admin:
            raise ValueError(
                "laboratório sem papel administrativo: ele mostra jornadas que "
                "ainda não existem, e ensiná-las a quem opera todo dia é "
                "prometer uma interface que o sistema não cumpre.")
        if not self.google_mutate and not self.porque_sem_mutacao:
            raise ValueError(
                "mutação fechada sem dizer por quê. Botão cinza sem explicação "
                "é o que faz o operador procurar contorno em vez de permissão.")

    def json(self) -> Dict[str, Any]:
        return {
            "is_admin": self.is_admin,
            "lab_mode": self.lab_mode,
            "google_read": self.google_read,
            "google_validate_only": self.google_validate_only,
            "google_mutate": self.google_mutate,
            "google_demand_gen_validate_only": self.google_demand_gen_validate_only,
            "porque_sem_mutacao": self.porque_sem_mutacao,
        }


#: Ditas para o operador, uma vez, e não montadas por concatenação na tela.
_SEM_PAPEL = (
    "sua sessão não tem papel ativo agora. Leitura continua valendo; criar ou "
    "alterar campanha exige papel, e ele é concedido por quem administra o "
    "sistema.")
_SEM_ADMIN = (
    "criar ou alterar campanha na conta do cliente exige papel administrativo. "
    "Você continua podendo montar o pedido e mandar o Google conferi-lo — a "
    "conferência não cria nada.")
_TRAVA_FECHADA = (
    "a permissão operacional para escrever nas contas está fechada neste "
    "servidor. Montar e conferir seguem liberados; publicar não. Quem "
    "administra o sistema é que a abre, e é uma decisão declarada.")


def de_identidade(*, papel: str, escrita_permitida: bool) -> Capacidades:
    """As capacidades de quem chegou com este papel, neste servidor.

    `papel` vem de `volc_role_of` — string vazia quando foi revogado, e a
    revogação vale no ato. `escrita_permitida` vem de `volc_ads.gads.modo`, que
    é a mesma função que a saída da requisição consulta; ler de outro lugar
    faria a tela e a porta discordarem.
    """
    papel_limpo = str(papel or "").strip().upper()
    tem_papel = bool(papel_limpo)
    admin = papel_limpo == "ADMIN"

    # Ler é o degrau de quem tem sessão com papel. Sem papel, nem ler: é o mesmo
    # corte que `POST /vinculos` já faz — papel revogado vale desde já.
    ler = tem_papel
    # Provar bate na conta real e gasta quota dela, então acompanha o papel
    # administrativo. Não gasta verba, e por isso não espera a trava.
    provar = admin
    mutar = admin and escrita_permitida

    if mutar:
        porque = None
    elif not tem_papel:
        porque = _SEM_PAPEL
    elif not admin:
        porque = _SEM_ADMIN
    else:
        porque = _TRAVA_FECHADA

    return Capacidades(
        is_admin=admin,
        # Laboratório é para quem administra: ele mostra jornadas que ainda não
        # existem, e mostrá-las a quem opera todo dia ensinaria uma interface
        # que o sistema não cumpre.
        lab_mode=admin and servidor_oferece_laboratorio(
            escrita_permitida=escrita_permitida),
        google_read=ler,
        google_validate_only=provar,
        google_mutate=mutar,
        google_demand_gen_validate_only=(
            provar and servidor_oferece_demand_gen_validate_only()
        ),
        porque_sem_mutacao=porque,
    )
