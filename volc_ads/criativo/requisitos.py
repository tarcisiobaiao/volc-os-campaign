"""As exigências de asset por canal — leitura de `requisitos.yaml`, não `if`.

## Por que os números não estão neste arquivo

Pela mesma razão que `campanha/validacao.py` lê `limites.yaml`: número mágico
espalhado em código não sobrevive à primeira mudança de versão da API. Quando a
matriz oficial em `docs/growth-engine/matriz-api/` for corrigida ou completada,
a troca é de um arquivo de dados, e nenhum `if` precisa ser reescrito — foi
exatamente assim que os provisórios desta camada saíram, sem tocar em lógica.

## De onde vem cada número — e por que são três fontes

  a matriz oficial      →  `docs/growth-engine/matriz-api/`, transcrita em
                           `requisitos.yaml` com a página citada por canal.
  caractere e contagem  →  `volc_ads/campanha/limites.yaml`, quando existe
                           chave semanticamente correta lá. Aqueles números
                           vieram do proto do SDK instalado e, na parte de
                           texto, de `validate_only` contra conta real.
  este arquivo          →  só o que as duas acima não cobrem, e aí sim provisório.

## Ausência é resposta, e é a resposta certa

A tabela completa que o Google publica — com os 5120 KB de peso máximo — é a de
Performance Max. Para o Display, o proto declara dimensão, proporção e contagem
e NÃO declara peso nem spec de vídeo. Onde a matriz diz `[NÃO CONFIRMADO]`, o
YAML traz `null` e o validador simplesmente não checa aquilo.

Número emprestado de outro canal é pior que campo vazio: um lote que valida
contra o teto errado passa localmente e é recusado pela API depois, com o erro
apontando para o asset e não para a regra que o reprovou.

Cada `EspecificacaoDeAsset` sai daqui com `fonte_dos_numeros` preenchido. Isso
não é enfeite: é o que permite, na revisão, separar num relance o que é verdade
medida do que ainda é leitura de documentação. Quando a chave do outro dono
desaparece, o fallback local entra e a fonte DIZ que entrou — o silêncio seria
pior que o número errado.

## O que este módulo NÃO faz

Não valida nada — quem valida é `validacao.py`. Não sabe o que é um canal
válido do ponto de vista do Google: a taxonomia canônica tem dono em
`campanha/taxonomia.py`, e um segundo enum de canal aqui divergiria do primeiro.
"""

from __future__ import annotations

import pathlib

import yaml

from .contrato import (
    TIPOS_BINARIOS,
    EspecificacaoDeAsset,
    ExigenciaDeCanal,
    TetoCombinado,
    TipoDeAsset,
)

_AQUI = pathlib.Path(__file__).parent
_RAIZ = _AQUI.parents[1]
_ARQUIVO = _AQUI / "requisitos.yaml"
_LIMITES_DA_CAMPANHA = _AQUI.parent / "campanha" / "limites.yaml"

_DADOS = yaml.safe_load(_ARQUIVO.read_text(encoding="utf-8"))

# A constante única que o cabeçalho promete. Enquanto ela for True, todo
# relatório desta camada deve dizer em voz alta que os números binários não
# foram medidos.
NUMEROS_SAO_PROVISORIOS: bool = bool(_DADOS.get("provisorio", True))
FONTE_OFICIAL: str = str(_DADOS.get("fonte_oficial", ""))
DONO_DOS_CARACTERES: str = str(_DADOS.get("dono_dos_caracteres", ""))

CANAIS_SEM_EXIGENCIA_DE_CRIATIVO: dict[str, str] = dict(
    _DADOS.get("sem_exigencia_de_criativo") or {}
)

_ROTULO_PROVISORIO = f"PROVISÓRIO — não coberto por {FONTE_OFICIAL}"


def _carregar_limites() -> dict:
    """Lê o dono vizinho dos limites, tolerando a ausência dele.

    `campanha/` tem outro dono e pode se mover. Explodir o import inteiro do
    pacote de criativo porque um arquivo vizinho mudou de lugar transformaria
    uma refatoração alheia numa quebra desta camada; cair para o número
    provisório e DIZER isso na `fonte_dos_numeros` é o comportamento honesto.
    """
    try:
        return yaml.safe_load(_LIMITES_DA_CAMPANHA.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}


_LIMITES = _carregar_limites()


def _do_vizinho(caminho: str | None):
    """Busca por caminho pontuado em `limites.yaml`. `None` quando não existe."""
    if not caminho:
        return None
    no = _LIMITES
    for parte in caminho.split("."):
        if not isinstance(no, dict) or parte not in no:
            return None
        no = no[parte]
    return no


def _inteiro(valor) -> int | None:
    return valor if isinstance(valor, int) and not isinstance(valor, bool) else None


# ── resolução de cada número, com a fonte colada ────────────────────────────


def _caracteres(chave: str | None, fallback: int | None) -> tuple[int | None, str]:
    valor = _inteiro(_do_vizinho(f"texto.{chave}.max_chars") if chave else None)
    if valor is not None:
        return valor, f"{DONO_DOS_CARACTERES}:texto.{chave}"
    return fallback, _ROTULO_PROVISORIO


def _quantidade(bruto: dict, limites_chave: str | None) -> tuple[int, int | None, str]:
    """Mínimo, máximo e fonte.

    Três origens possíveis, nesta ordem de autoridade: a chave explícita de
    `quantidade_chave`, a contagem que acompanha a chave de texto
    (`min_itens`/`max_itens` moram na MESMA entrada que o `max_chars`), e o
    fallback local.
    """
    q = bruto.get("quantidade") or {}
    minimo_local = int(q.get("min", 0))
    maximo_local = None if q.get("max") is None else int(q["max"])

    chaves = bruto.get("quantidade_chave") or {}
    minimo = _inteiro(_do_vizinho(chaves.get("min")))
    maximo = _inteiro(_do_vizinho(chaves.get("max")))
    fonte = ""
    if minimo is not None or maximo is not None:
        fonte = DONO_DOS_CARACTERES

    if limites_chave and minimo is None and maximo is None:
        minimo = _inteiro(_do_vizinho(f"texto.{limites_chave}.min_itens"))
        maximo = _inteiro(_do_vizinho(f"texto.{limites_chave}.max_itens"))
        if minimo is not None or maximo is not None:
            fonte = f"{DONO_DOS_CARACTERES}:texto.{limites_chave}"

    if minimo is None:
        minimo, fonte = minimo_local, fonte or _ROTULO_PROVISORIO
    if maximo is None and chaves.get("max") is not None:
        maximo = maximo_local
    elif maximo is None and not chaves:
        maximo = maximo_local
    return minimo, maximo, fonte or _ROTULO_PROVISORIO


def _par(valor) -> tuple[int, int] | None:
    if not valor:
        return None
    largura, altura = valor
    return int(largura), int(altura)


def _montar(
    tipo: TipoDeAsset, bruto: dict, padroes: dict, fonte_do_canal: str
) -> EspecificacaoDeAsset:
    duracao = bruto.get("duracao") or {}
    minima = _par(bruto.get("dimensao_minima"))
    recomendada = _par(bruto.get("dimensao_recomendada"))
    e_texto = "caracteres_maximos" in bruto or "limites_chave" in bruto

    # `"chave" in bruto` e não `bruto.get(...)`: `null` EXPLÍCITO significa
    # "a matriz diz [NÃO CONFIRMADO]" e tem de vencer o padrão do canal.
    # Tratar os dois como ausência devolveria o número emprestado pela porta
    # dos fundos, que é exatamente o defeito que este arquivo evita.
    if e_texto:
        mimes, bytes_maximos = (), None
    else:
        familia = "video" if tipo is TipoDeAsset.VIDEO else "imagem"
        padrao = padroes.get(familia) or {}
        mimes = tuple(
            bruto["mimes"] if "mimes" in bruto else (padrao.get("mimes") or ())
        )
        bytes_maximos = (
            bruto["bytes_maximos"] if "bytes_maximos" in bruto
            else padrao.get("bytes_maximos")
        )

    limites_chave = bruto.get("limites_chave")
    caracteres, fonte = (None, fonte_do_canal)
    if e_texto:
        caracteres, fonte = _caracteres(limites_chave, bruto.get("caracteres_maximos"))
        if fonte == _ROTULO_PROVISORIO:
            fonte = fonte_do_canal

    minimo, maximo, fonte_quantidade = _quantidade(bruto, limites_chave)
    if not e_texto and fonte_quantidade != _ROTULO_PROVISORIO:
        fonte = fonte_quantidade
    # A especificação pode citar uma fonte mais precisa que a do canal (o logo
    # de Demand Gen vem do Help Center, não do proto).
    fonte = bruto.get("fonte") or fonte

    return EspecificacaoDeAsset(
        tipo=tipo,
        quantidade_minima=minimo,
        quantidade_maxima=maximo,
        quantidade_recomendada=_inteiro((bruto.get("quantidade") or {}).get("recomendada")),
        proporcao_alvo=_par(bruto.get("proporcao")),
        tolerancia_proporcao=float(bruto.get("tolerancia_proporcao", 0.01)),
        largura_minima=minima[0] if minima else None,
        altura_minima=minima[1] if minima else None,
        largura_recomendada=recomendada[0] if recomendada else None,
        altura_recomendada=recomendada[1] if recomendada else None,
        bytes_maximos=bytes_maximos,
        mimes_aceitos=mimes,
        duracao_minima_s=duracao.get("min_s"),
        duracao_maxima_s=duracao.get("max_s"),
        caracteres_maximos=caracteres,
        caracteres_de_pelo_menos_um=_inteiro(bruto.get("caracteres_de_pelo_menos_um")),
        fonte_dos_numeros=fonte,
    )


def _combinados_de(canal: str) -> tuple[TetoCombinado, ...]:
    saida: list[TetoCombinado] = []
    for bruto in (_DADOS.get("combinados") or {}).get(canal, []):
        maximo = _inteiro(_do_vizinho(bruto.get("maximo_chave")))
        minimo = _inteiro(_do_vizinho(bruto.get("minimo_chave")))
        fonte = (
            DONO_DOS_CARACTERES
            if maximo is not None or minimo is not None
            else _ROTULO_PROVISORIO
        )
        if maximo is None:
            maximo = _inteiro(bruto.get("maximo"))
        if minimo is None:
            minimo = int(bruto.get("minimo", 0))
        saida.append(TetoCombinado(
            rotulo=str(bruto.get("rotulo", "")),
            tipos=tuple(TipoDeAsset(t) for t in bruto.get("tipos") or ()),
            maximo=maximo,
            minimo=minimo,
            fonte_dos_numeros=fonte,
        ))
    return tuple(saida)


def _construir() -> dict[str, ExigenciaDeCanal]:
    padroes = _DADOS.get("padroes") or {}
    saida: dict[str, ExigenciaDeCanal] = {}
    for canal, bloco in (_DADOS.get("canais") or {}).items():
        fonte_do_canal = str(bloco.get("fonte") or _ROTULO_PROVISORIO)
        saida[canal] = ExigenciaDeCanal(
            canal=canal,
            especificacoes=tuple(
                _montar(TipoDeAsset(nome), bruto or {}, padroes, fonte_do_canal)
                for nome, bruto in (bloco.get("assets") or {}).items()
            ),
            combinados=_combinados_de(canal),
            provisorio=bool(bloco.get("provisorio", True)),
            fonte=fonte_do_canal,
        )
    return saida


_POR_CANAL = _construir()

CANAIS: tuple[str, ...] = tuple(_POR_CANAL)


def exigencia_de(canal: str) -> ExigenciaDeCanal:
    """As exigências de criativo de um canal.

    Canal sem exigência de asset binário (Search) levanta com o dono no texto,
    em vez de devolver um lote vazio que o chamador leria como "não precisa de
    nada" — que é verdade para imagem e mentira para a copy.
    """
    canal = canal.upper()
    if canal in _POR_CANAL:
        return _POR_CANAL[canal]
    if canal in CANAIS_SEM_EXIGENCIA_DE_CRIATIVO:
        raise ValueError(
            f"{canal} não tem exigência de criativo nesta camada — "
            f"o dono é {CANAIS_SEM_EXIGENCIA_DE_CRIATIVO[canal]}"
        )
    raise ValueError(f"canal {canal!r} fora de {sorted(_POR_CANAL)}")


def exigencia_binaria_de(canal: str) -> ExigenciaDeCanal:
    """Só a parte de ARQUIVO da exigência — imagem e vídeo, sem texto.

    ## Por que esta projeção precisa existir

    `exigencia_de("DISPLAY")` inclui `headline`, `headline_longa`, `descricao`
    e `nome_da_empresa`, todas com `quantidade.min ≥ 1`. Isso está certo: são
    exigências reais do canal. Mas validar um lote de IMAGENS contra ela
    produziria um `Q1.faltam` de severidade `erro` para cada um desses quatro
    tipos, e `ResultadoDeValidacao.ok` seria `False` **sempre** — reprovando o
    lote de imagem por falta de texto cujo dono é `campanha/conteudo.py`, que
    já valida a copy pelo `limites.yaml` no mesmo `construir()`.

    Um portão que reprova 100% das vezes por um motivo que não é dele é um
    portão que alguém desliga na primeira semana.

    ## Por que mora aqui, e não na ponte

    Porque quem projeta uma exigência é o dono dela. Se a ponte filtrasse, ela
    precisaria conhecer `TIPOS_BINARIOS` e reler a estrutura do YAML — uma
    segunda leitura da mesma fonte, que é a armadilha dos dois medidores.

    Os `combinados` são filtrados junto, e a regra é conservadora: um teto só
    entra se **todos** os seus tipos forem binários. Um teto que mistura texto e
    arquivo mediria uma soma da qual metade das parcelas não está no lote, e
    diria que faltam itens que não deveriam estar ali.
    """
    inteira = exigencia_de(canal)
    binarias = tuple(
        s for s in inteira.especificacoes if s.tipo in TIPOS_BINARIOS
    )
    combinados = tuple(
        t for t in inteira.combinados
        if t.tipos and all(tipo in TIPOS_BINARIOS for tipo in t.tipos)
    )
    if not binarias:
        # Não devolvo uma exigência vazia: o chamador a leria como "este canal
        # não pede arquivo nenhum", que é uma afirmação bem diferente de "este
        # canal não está descrito nesta camada".
        raise ValueError(
            f"{inteira.canal} não declara nenhum asset binário em "
            f"{_ARQUIVO.name} — não há o que validar num lote de arquivos aqui"
        )
    return ExigenciaDeCanal(
        canal=inteira.canal,
        especificacoes=binarias,
        combinados=combinados,
        provisorio=inteira.provisorio,
        fonte=inteira.fonte,
    )


def aviso_de_procedencia(canal: str | None = None) -> str:
    """Uma linha para colar em qualquer relatório desta camada."""
    if canal is not None:
        exigencia = exigencia_de(canal)
        if not exigencia.provisorio:
            return f"requisitos de {exigencia.canal}: {exigencia.fonte}"
        return f"⚠️ requisitos de {exigencia.canal} PROVISÓRIOS — {exigencia.fonte}"
    pendentes = [c for c in _POR_CANAL if _POR_CANAL[c].provisorio]
    if not pendentes:
        return f"requisitos de asset: números oficiais de {FONTE_OFICIAL}"
    return (
        f"⚠️ canais ainda sem número oficial: {', '.join(pendentes)}. "
        f"Os demais vêm de {FONTE_OFICIAL}"
    )
