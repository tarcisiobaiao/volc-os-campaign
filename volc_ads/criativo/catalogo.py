"""O catálogo de criativos — quem já existe, de quem veio e a quem serve.

## O problema que ele resolve, e que já custou caro em outro lugar

Sem catálogo, o mesmo banner é gerado de novo a cada campanha porque ninguém
sabe que ele existe. Gerar de novo custa dinheiro no motor, custa revisão de
política no Google e — o pior — produz dois assets diferentes com o MESMO
conteúdo, cada um com sua métrica, de modo que a pergunta "qual criativo
funcionou?" fica sem resposta porque a resposta está dividida em dois.

A regra é a mesma que o Hub de Tráfego aprendeu com as campanhas de dois donos:
identidade primeiro, e identidade derivada do conteúdo, não do nome.

## Duplicata devolve o existente — não levanta

Uma tentativa de catalogar algo que já está lá **devolve o asset existente**,
com `novo=False`. Levantar exceção obrigaria todo chamador a envolver o
registro num `try`, e o caminho normal (o motor gerou de novo a mesma coisa)
não é excepcional: é o comportamento esperado de um motor determinístico.

## O mesmo arquivo em dois papéis não é conflito

Uma imagem 1:1 pode ser LOGO_QUADRADO numa campanha e
IMAGEM_MARKETING_QUADRADA em outra: para a API é um `ImageAsset` só, usado em
dois lugares. O catálogo deduplica pelo CONTEÚDO e anota os papéis; o `tipo` do
asset registrado é o do primeiro registro, e o segundo papel entra em
`papeis()` com a observação. Recusar seria criar duas cópias do mesmo arquivo
para satisfazer o modelo — exatamente o que a deduplicação existe para evitar.

## Procedência é do arquivo, e o arquivo é o mesmo

Quando o mesmo conteúdo chega com procedência diferente, vale a PRIMEIRA. O
segundo registro não é uma criação: é um reencontro. Sobrescrever apagaria o
prompt que de fato produziu aquele arquivo — que é a única coisa que permite
repetir um acerto.

Este módulo não persiste nada. Guardar em banco é do domínio de Tráfego
(`backend/app/trafego/`), e a linhagem em Supabase tem outro dono nesta missão.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .contrato import (
    Asset,
    Falha,
    LoteDeAssets,
    Origem,
    Procedencia,
    TipoDeAsset,
    hash_de_conteudo,
)
from .porta import PedidoDeGeracao, RespostaDoMotor


@dataclass(frozen=True)
class Registro:
    """O que aconteceu ao tentar catalogar um asset."""

    asset: Asset
    novo: bool
    observacao: str = ""


# ── da resposta do motor para assets ────────────────────────────────────────


def assets_da_resposta(
    resposta: RespostaDoMotor,
    pedido: PedidoDeGeracao,
    *,
    motor: str,
    versao: str,
    quando: datetime,
    origem: Origem = Origem.GERADO,
) -> tuple[tuple[Asset, ...], tuple[Falha, ...]]:
    """Converte o cru do motor em assets medidos e com procedência.

    Um arquivo que não vira asset (medida impossível, zero disfarçado de
    medida, texto vazio) vira `Falha` e os outros seguem. É a fronteira onde a
    regra "falha não corrompe o lote" precisa ser cumprida de verdade: aqui é o
    único lugar que sabe que existiam cinco arquivos quando só quatro deram.
    """
    assets: list[Asset] = []
    falhas: list[Falha] = list(resposta.falhas)

    for i, arquivo in enumerate(resposta.arquivos):
        referencia = f"{resposta.pedido}#{i}"
        conteudo = arquivo.conteudo if arquivo.conteudo is not None else arquivo.texto
        try:
            assets.append(Asset(
                tipo=pedido.tipo,
                procedencia=Procedencia(
                    motor=motor,
                    versao_do_motor=versao,
                    insumo=pedido.insumo,
                    quando=quando,
                    pedido=resposta.pedido,
                    custo_usd=arquivo.custo_usd,
                ),
                conteudo_hash=hash_de_conteudo(conteudo),
                origem=origem,
                texto=arquivo.texto,
                bytes_totais=(
                    len(arquivo.conteudo) if arquivo.conteudo is not None
                    else len((arquivo.texto or "").encode("utf-8")) or None
                ),
                mime=arquivo.mime,
                largura=arquivo.largura,
                altura=arquivo.altura,
                duracao_s=arquivo.duracao_s,
                rotulo=arquivo.metadados.get("rotulo", ""),
            ))
        except ValueError as e:
            falhas.append(Falha(
                referencia=referencia,
                motivo=f"arquivo não virou asset: {e}",
                codigo="F1.arquivo_invalido",
                tipo=pedido.tipo,
                permanente=True,
            ))

    return tuple(assets), tuple(falhas)


# ── o catálogo ──────────────────────────────────────────────────────────────


class Catalogo:
    """Banco de criativos em memória, com deduplicação por conteúdo."""

    def __init__(self) -> None:
        self._por_hash: dict[str, Asset] = {}
        self._papeis: dict[str, set[TipoDeAsset]] = {}
        self._intencoes: dict[str, list[str]] = {}   # identidade -> intenções
        self._por_intencao: dict[str, list[str]] = {}  # intenção -> identidades
        self._falhas: list[tuple[str, Falha]] = []

    # -- escrita --

    def registrar(self, asset: Asset) -> Registro:
        """Cataloga, ou devolve o que já estava lá."""
        existente = self._por_hash.get(asset.conteudo_hash)
        if existente is None:
            self._por_hash[asset.conteudo_hash] = asset
            self._papeis[asset.identidade] = {asset.tipo}
            self._intencoes.setdefault(asset.identidade, [])
            return Registro(asset, novo=True)

        observacoes: list[str] = []
        if asset.tipo not in self._papeis[existente.identidade]:
            self._papeis[existente.identidade].add(asset.tipo)
            observacoes.append(
                f"mesmo conteúdo já catalogado como {existente.tipo.value}; "
                f"papel {asset.tipo.value} anotado"
            )
        if asset.procedencia != existente.procedencia:
            observacoes.append(
                f"procedência divergente ignorada — vale a primeira "
                f"({existente.procedencia.motor} em {existente.procedencia.quando:%Y-%m-%d})"
            )
        return Registro(existente, novo=False, observacao=" · ".join(observacoes))

    def registrar_falha(self, falha: Falha, intencao: str = "") -> None:
        self._falhas.append((intencao, falha))

    def absorver(
        self,
        assets: tuple[Asset, ...],
        falhas: tuple[Falha, ...] = (),
        *,
        intencao: str = "",
    ) -> tuple[Registro, ...]:
        """Cataloga um lote inteiro e amarra tudo à intenção, se houver."""
        registros = []
        for asset in assets:
            registro = self.registrar(asset)
            if intencao:
                self.associar(registro.asset.identidade, intencao)
            registros.append(registro)
        for falha in falhas:
            self.registrar_falha(falha, intencao)
        return tuple(registros)

    def associar(self, identidade: str, intencao: str) -> bool:
        """Liga um asset a uma intenção de campanha. Devolve False se já estava."""
        if identidade not in self._papeis:
            raise KeyError(f"asset {identidade!r} não está no catálogo")
        if not intencao.strip():
            raise ValueError("intenção vazia não é intenção")
        vinculos = self._intencoes.setdefault(identidade, [])
        if intencao in vinculos:
            return False
        vinculos.append(intencao)
        self._por_intencao.setdefault(intencao, []).append(identidade)
        return True

    def carimbar_id_externo(self, identidade: str, id_externo: str) -> Asset:
        """Guarda o id do Google sem tocar na identidade interna."""
        asset = self.por_identidade(identidade)
        carimbado = asset.com_id_externo(id_externo)
        self._por_hash[asset.conteudo_hash] = carimbado
        return carimbado

    # -- leitura --

    def por_identidade(self, identidade: str) -> Asset:
        for asset in self._por_hash.values():
            if asset.identidade == identidade:
                return asset
        raise KeyError(f"asset {identidade!r} não está no catálogo")

    def por_hash(self, conteudo_hash: str) -> Asset | None:
        return self._por_hash.get(conteudo_hash)

    def papeis(self, identidade: str) -> frozenset[TipoDeAsset]:
        return frozenset(self._papeis.get(identidade, ()))

    def intencoes_de(self, identidade: str) -> tuple[str, ...]:
        return tuple(self._intencoes.get(identidade, ()))

    def assets_de(
        self, intencao: str, tipo: TipoDeAsset | None = None
    ) -> tuple[Asset, ...]:
        saida = [
            self.por_identidade(i) for i in self._por_intencao.get(intencao, [])
        ]
        if tipo is not None:
            saida = [a for a in saida if tipo in self.papeis(a.identidade)]
        return tuple(saida)

    def variantes(self, identidade: str) -> tuple[Asset, ...]:
        """Os assets que declaram este como pai — recortes, resizes, regerações."""
        return tuple(
            a for a in self._por_hash.values() if a.derivado_de == identidade
        )

    def falhas(self, intencao: str | None = None) -> tuple[Falha, ...]:
        if intencao is None:
            return tuple(f for _, f in self._falhas)
        return tuple(f for i, f in self._falhas if i == intencao)

    def lote(self, intencao: str, canal: str) -> LoteDeAssets:
        """O que existe hoje para esta intenção, pronto para validar."""
        return LoteDeAssets(
            canal=canal,
            assets=self.assets_de(intencao),
            falhas=self.falhas(intencao),
            intencao=intencao,
        )

    def todos(self) -> tuple[Asset, ...]:
        return tuple(self._por_hash.values())

    def __len__(self) -> int:
        return len(self._por_hash)

    def __contains__(self, item: object) -> bool:
        if isinstance(item, Asset):
            return item.conteudo_hash in self._por_hash
        return item in self._por_hash
