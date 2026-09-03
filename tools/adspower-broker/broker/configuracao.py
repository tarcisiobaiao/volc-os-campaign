"""Preflight do broker: o que ele se RECUSA a fazer, decidido antes de escutar.

Toda recusa aqui acontece na subida do processo, não na primeira requisição. A
diferença importa: um broker que aceita bind público e só falha quando alguém
de fora chama já esteve exposto pelo tempo entre as duas coisas.

## As seis recusas de preflight

1. **bind fora de loopback** — sem exceção e sem variável de escape. Um broker
   que fala com a rede é um broker que a rede pode fazer falar.
2. **token de autenticação ausente, curto ou de exemplo** — a alternativa é o
   defeito de `deps.require_api_key` que `seguranca/identidade.py` documenta:
   `if not expected: return`, um portão que some quando a configuração falta.
3. **verificação de API desligada** — o guia oficial de MCP do AdsPower
   (consultado em 02/09/2026, https://help.adspower.com/docs/MCP) instrui
   literalmente a "disable 'API verification'". O ADR VOLC recusa esse modo, e
   a recusa mora aqui para não depender de alguém lembrar.
4. **endpoint do AdsPower fora da fronteira** — loopback, literal de IP, porta
   declarada. Ver `dominio.exigir_endpoint_do_adspower`.
5. **allowlist legível por outros** — o arquivo carrega `op://` e `user_id` de
   perfil. Modo 0600 ou o processo não sobe.
6. **`--no-masking` em qualquer argumento do resolvedor** — é a flag que
   desliga o mascaramento do `op run`. O smoke de P03-T09 já a trata como
   proibida no preflight; aqui vale a mesma regra.
"""
from __future__ import annotations

import ipaddress
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from app.visual_proof import dominio as dom


class PreflightRecusado(RuntimeError):
    """O broker não sobe. A mensagem diz o que corrigir, sem citar segredo."""


#: Um token de 32 caracteres é o piso, não o alvo. Abaixo disso a força bruta
#: local vira viável, e o broker é justamente o processo que já tem a chave.
TAMANHO_MINIMO_DO_TOKEN = 32

#: Valores que aparecem em tutorial e nunca podem virar autenticação real.
TOKENS_PROIBIDOS: frozenset[str] = frozenset({
    "changeme", "trocar", "example", "exemplo", "token", "secret", "password",
    "xxxxxx", "your-token-here", "0" * 32, "a" * 32,
})

FLAGS_PROIBIDAS: tuple[str, ...] = ("--no-masking",)


@dataclass(frozen=True)
class PerfilAutorizado:
    """A tradução `nome lógico -> user_id`, e ela mora SÓ aqui.

    `user_id` e `localizador` são os dois campos que nunca saem deste processo:
    não entram em recibo, em log, em resposta HTTP nem em exceção. O restante do
    sistema conhece o perfil apenas por `perfil_logico`.
    """

    perfil_logico: str
    user_id: str
    owner_sub: str
    ativo_id: str
    operacoes: frozenset[str]
    credencial_nome_logico: str
    localizador: str
    dominios_permitidos: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        dom.exigir_perfil_logico(self.perfil_logico)
        if not (self.user_id or "").strip():
            raise PreflightRecusado(
                f"o perfil {self.perfil_logico} não declara user_id do AdsPower.")
        if not (self.owner_sub or "").strip():
            raise PreflightRecusado(f"o perfil {self.perfil_logico} não declara owner.")
        if not (self.ativo_id or "").strip():
            raise PreflightRecusado(
                f"o perfil {self.perfil_logico} não declara o ativo do Cofre a que pertence.")
        desconhecidas = set(self.operacoes) - set(dom.OPERACOES_DO_BROKER)
        if desconhecidas:
            raise PreflightRecusado(
                f"o perfil {self.perfil_logico} declara operação fora da allowlist: "
                f"{sorted(desconhecidas)}")
        if not self.operacoes:
            raise PreflightRecusado(
                f"o perfil {self.perfil_logico} não declara operação nenhuma. Um perfil "
                "sem allowlist não é um perfil aberto: é um perfil inútil, e declarar "
                "isso é melhor do que herdar a lista inteira em silêncio.")
        if not dom.NOME_LOGICO.match(self.credencial_nome_logico or ""):
            raise PreflightRecusado(
                f"o perfil {self.perfil_logico} não declara nome lógico de credencial.")
        if not (self.localizador or "").startswith(("op://", "bw://", "bwv://",
                                                    "passbolt://", "infisical://")):
            raise PreflightRecusado(
                f"o perfil {self.perfil_logico} não declara uma referência de cofre "
                "reconhecível. O valor recebido não é repetido aqui de propósito.")

    def publico(self) -> dict[str, Any]:
        """A projeção que pode sair do processo. Sem `user_id`, sem localizador."""
        return {
            "perfil_logico": self.perfil_logico,
            "owner_sub": self.owner_sub,
            "ativo_id": self.ativo_id,
            "operacoes": sorted(self.operacoes),
            "credencial_nome_logico": self.credencial_nome_logico,
            "dominios_permitidos": list(self.dominios_permitidos),
        }


@dataclass(frozen=True)
class ConfiguracaoDoBroker:
    bind_host: str
    bind_porta: int
    token_de_autenticacao: str
    adspower_base: str
    perfis: Mapping[str, PerfilAutorizado]
    artefatos_dir: Path
    timeout_padrao_s: int = 45
    intervalo_minimo_entre_chamadas_s: float = 1.0
    lease_s: int = 120

    def perfil(self, perfil_logico: str) -> PerfilAutorizado:
        try:
            return self.perfis[perfil_logico]
        except KeyError:
            raise PerfilNaoAutorizado(perfil_logico) from None

    def saude(self) -> dict[str, Any]:
        """Retrato para `GET /v1/saude`. Nenhum campo carrega segredo."""
        return {
            "bind": f"{self.bind_host}:{self.bind_porta}",
            "adspower_base": self.adspower_base,
            "autenticacao": "ativa",
            "verificacao_de_api": "exigida",
            "operacoes_permitidas": list(dom.OPERACOES_DO_BROKER),
            "perfis": [p.publico() for p in self.perfis.values()],
            "artefatos": "diretorio_privado_configurado",
        }


class PerfilNaoAutorizado(PermissionError):
    def __init__(self, perfil_logico: str):
        super().__init__(
            f"perfil {perfil_logico} não está na allowlist deste broker.")
        self.perfil_logico = perfil_logico


def _exigir_loopback(host: str) -> str:
    bruto = (host or "").strip().strip("[]")
    if not bruto:
        raise PreflightRecusado("bind host ausente.")
    try:
        ip = ipaddress.ip_address(bruto)
    except ValueError:
        raise PreflightRecusado(
            f"bind host {bruto!r} não é um literal de IP. O broker só escuta em "
            "127.0.0.1 ou ::1 — um nome pode ser reapontado para 0.0.0.0.") from None
    if not ip.is_loopback:
        raise PreflightRecusado(
            f"bind em {bruto} é bind público. O broker só escuta em loopback, e não "
            "existe variável de ambiente que afrouxe isto.")
    return str(ip)


def _exigir_token(token: str) -> str:
    limpo = (token or "").strip()
    if not limpo:
        raise PreflightRecusado(
            "token de autenticação ausente: o broker não sobe sem portão. Um portão "
            "que some quando a configuração falta é pior que nenhum, porque parece "
            "que existe.")
    if len(limpo) < TAMANHO_MINIMO_DO_TOKEN:
        raise PreflightRecusado(
            f"token de autenticação curto demais: use ao menos "
            f"{TAMANHO_MINIMO_DO_TOKEN} caracteres. O valor não é repetido aqui.")
    if limpo.lower() in TOKENS_PROIBIDOS:
        raise PreflightRecusado(
            "token de autenticação é um valor de exemplo. Gere um novo.")
    return limpo


def _exigir_arquivo_privado(caminho: Path) -> None:
    if not caminho.is_file():
        raise PreflightRecusado(f"allowlist de perfis não encontrada em {caminho}.")
    modo = caminho.stat().st_mode
    if modo & (stat.S_IRWXG | stat.S_IRWXO):
        raise PreflightRecusado(
            f"a allowlist {caminho} é legível por grupo ou por outros. Ela carrega "
            "referência de cofre e id de perfil: exija modo 0600.")


def _exigir_diretorio_privado(caminho: Path) -> Path:
    caminho.mkdir(parents=True, exist_ok=True, mode=0o700)
    modo = caminho.stat().st_mode
    if modo & (stat.S_IRWXG | stat.S_IRWXO):
        raise PreflightRecusado(
            f"o diretório de artefatos {caminho} é acessível por grupo ou por outros. "
            "Screenshots de superfície autenticada não são arquivos públicos.")
    return caminho


def exigir_argumentos_do_resolvedor(argumentos: Iterable[str]) -> tuple[str, ...]:
    itens = tuple(str(a) for a in argumentos)
    for proibida in FLAGS_PROIBIDAS:
        if any(proibida in item for item in itens):
            raise PreflightRecusado(
                f"a flag {proibida} desliga o mascaramento do 1Password e está "
                "proibida no preflight do broker.")
    return itens


def carregar(
    *,
    allowlist: Path,
    token: Optional[str] = None,
    bind_host: Optional[str] = None,
    bind_porta: Optional[int] = None,
    adspower_base: Optional[str] = None,
    artefatos_dir: Optional[Path] = None,
    verificacao_de_api_ativa: Optional[bool] = None,
    portas_do_adspower: Iterable[int] = (50325,),
    ambiente: Optional[Mapping[str, str]] = None,
) -> ConfiguracaoDoBroker:
    """Lê a allowlist e o ambiente, e recusa antes de abrir socket nenhum."""
    env = dict(ambiente if ambiente is not None else os.environ)

    verificacao = (
        verificacao_de_api_ativa
        if verificacao_de_api_ativa is not None
        else env.get("VOLC_BROKER_VERIFICACAO_DE_API", "1").strip() not in ("0", "false", "off")
    )
    if not verificacao:
        raise PreflightRecusado(
            "o modo com verificação de API desligada não é aceito. O guia oficial de "
            "MCP do AdsPower ensina a desligá-la; o ADR VOLC recusa esse modo porque "
            "ele deixa qualquer processo local abrir perfis autenticados.")

    _exigir_arquivo_privado(allowlist)
    try:
        bruto = json.loads(allowlist.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PreflightRecusado(f"allowlist não é JSON válido: linha {exc.lineno}.") from None
    if not isinstance(bruto, dict) or not isinstance(bruto.get("perfis"), list):
        raise PreflightRecusado("allowlist precisa ser um objeto com a lista `perfis`.")

    perfis: dict[str, PerfilAutorizado] = {}
    for entrada in bruto["perfis"]:
        if not isinstance(entrada, dict):
            raise PreflightRecusado("cada perfil da allowlist precisa ser um objeto.")
        perfil = PerfilAutorizado(
            perfil_logico=str(entrada.get("perfil_logico", "")),
            user_id=str(entrada.get("user_id", "")),
            owner_sub=str(entrada.get("owner_sub", "")),
            ativo_id=str(entrada.get("ativo_id", "")),
            operacoes=frozenset(entrada.get("operacoes") or ()),
            credencial_nome_logico=str(entrada.get("credencial_nome_logico", "")),
            localizador=str(entrada.get("localizador", "")),
            dominios_permitidos=tuple(entrada.get("dominios_permitidos") or ()),
        )
        if perfil.perfil_logico in perfis:
            raise PreflightRecusado(
                f"perfil {perfil.perfil_logico} declarado duas vezes na allowlist.")
        perfis[perfil.perfil_logico] = perfil
    if not perfis:
        raise PreflightRecusado("a allowlist não declara perfil nenhum.")

    base = dom.exigir_endpoint_do_adspower(
        adspower_base or env.get("VOLC_BROKER_ADSPOWER_BASE", "http://127.0.0.1:50325"),
        portas_permitidas=portas_do_adspower,
    )

    return ConfiguracaoDoBroker(
        bind_host=_exigir_loopback(bind_host or env.get("VOLC_BROKER_BIND", "127.0.0.1")),
        bind_porta=int(bind_porta if bind_porta is not None else env.get("VOLC_BROKER_PORTA", "0")),
        token_de_autenticacao=_exigir_token(token or env.get("VOLC_BROKER_TOKEN", "")),
        adspower_base=base,
        perfis=perfis,
        artefatos_dir=_exigir_diretorio_privado(
            Path(artefatos_dir or env.get("VOLC_BROKER_ARTEFATOS", "./.artefatos-visuais"))),
        timeout_padrao_s=int(env.get("VOLC_BROKER_TIMEOUT_S", "45")),
        intervalo_minimo_entre_chamadas_s=float(
            env.get("VOLC_BROKER_INTERVALO_S", "1.0")),
        lease_s=int(env.get("VOLC_BROKER_LEASE_S", "120")),
    )


__all__ = [
    "ConfiguracaoDoBroker", "PerfilAutorizado", "PerfilNaoAutorizado",
    "PreflightRecusado", "carregar", "exigir_argumentos_do_resolvedor",
]
