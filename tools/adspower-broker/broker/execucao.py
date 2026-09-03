"""O ato do broker: autorizar, resolver, executar, limpar, recibar.

## A ordem das guardas não é estilo

    allowlist de perfil  →  dono  →  ativo  →  operação  →  destino  →  lease
    →  idempotência  →  resolução do segredo  →  AdsPower  →  captura  →  recibo

O segredo é resolvido **por último entre as guardas**, e essa posição é a
decisão mais importante deste arquivo. Um broker que resolve primeiro e valida
depois já pediu o segredo ao cofre para todo pedido que chega — inclusive para
os que ele vai recusar. Cada recusa passaria a custar uma leitura no 1Password,
o que transforma uma varredura em ruído de auditoria e desgasta a aprovação do
operador até ele aprovar por reflexo.

## O que sempre acontece, mesmo com exceção

`finally` descarta o segredo e fecha o perfil que ESTA operação abriu. Um
perfil deixado aberto é uma sessão autenticada disponível para o próximo
processo do host; um segredo não descartado é o `bytearray` vivo pelo resto do
processo.

## A última peneira

Antes de o recibo virar resposta, ele é varrido atrás do valor que acabou de
ser resolvido — enquanto esse valor ainda está em escopo. Se aparecer, o recibo
é DESCARTADO e vira recusa `vazamento_contido`. É a única checagem do sistema
que consegue comparar o recibo com o segredo real; depois deste ponto o valor
não existe mais para comparar.
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from app.visual_proof import dominio as dom
from broker import adspower as ads
from broker.configuracao import ConfiguracaoDoBroker, PerfilAutorizado, PerfilNaoAutorizado
from broker import segredo as seg


class ConflitoDeIdempotencia(RuntimeError):
    """Mesma chave, entrada diferente. Nunca vira execução nova.

    É a semântica que a v13_01 já implementa para o Cofre e que o contrato de
    handoff manda copiar: mesma chave + mesma entrada devolve o recibo guardado;
    mesma chave + entrada diferente FALHA. Escolher uma das duas entradas em
    silêncio seria executar a intenção que ninguém confirmou.
    """


class LeaseIndisponivel(RuntimeError):
    """Outro consumidor já está executando esta chave e o prazo não venceu."""


def agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class _Entrada:
    impressao: str
    consumidor: str
    expira_em: float
    recibo: Optional[dom.AdsPowerBrokerReceipt] = None


class RegistroDeIdempotencia:
    """Chave → (impressão, dono do lease, recibo). Em memória, com trava.

    ⚠️ **Alcance honesto:** isto coordena consumidores dentro de UM processo.
    Dois brokers no mesmo host, ou um broker reiniciado, não compartilham este
    registro. Para produção com mais de um executor, a sede do lease tem de ser
    o banco (`UPDATE … WHERE reivindicado_por IS NULL` ou advisory lock), e essa
    troca está declarada como pendência no handoff. Um dicionário com `Lock`
    prova a semântica; ele não prova durabilidade.
    """

    def __init__(self, *, relogio: Callable[[], float] = time.monotonic):
        self._entradas: dict[str, _Entrada] = {}
        self._trava = threading.Lock()
        self._relogio = relogio

    def reivindicar(self, chave: str, impressao: str, consumidor: str,
                    lease_s: float) -> Optional[dom.AdsPowerBrokerReceipt]:
        with self._trava:
            entrada = self._entradas.get(chave)
            if entrada is None:
                self._entradas[chave] = _Entrada(
                    impressao=impressao, consumidor=consumidor,
                    expira_em=self._relogio() + lease_s)
                return None
            if entrada.impressao != impressao:
                raise ConflitoDeIdempotencia(
                    "esta chave de idempotência já foi usada com uma entrada diferente. "
                    "O broker recusa em vez de escolher qual das duas executar.")
            if entrada.recibo is not None:
                return entrada.recibo
            if self._relogio() < entrada.expira_em:
                raise LeaseIndisponivel(
                    "outro consumidor está executando esta chave neste momento.")
            # Lease vencido: o dono anterior morreu sem concluir. Reivindica.
            entrada.consumidor = consumidor
            entrada.expira_em = self._relogio() + lease_s
            return None

    def concluir(self, chave: str, recibo: dom.AdsPowerBrokerReceipt) -> None:
        with self._trava:
            entrada = self._entradas.get(chave)
            if entrada is not None:
                entrada.recibo = recibo
                entrada.expira_em = 0.0

    def liberar(self, chave: str) -> None:
        """Solta o lease SEM guardar recibo — para falha que pode ser retentada."""
        with self._trava:
            entrada = self._entradas.get(chave)
            if entrada is not None and entrada.recibo is None:
                self._entradas.pop(chave, None)


class ArmazenamentoDeArtefatos:
    """Grava a imagem em disco privado e devolve REFERÊNCIA + hash.

    O recibo carrega `vpartifact://…`, nunca o caminho absoluto: um caminho
    absoluto contém o usuário do host, e já houve o precedente do
    `canonical_path` dos manifestos de engine (que carregava o e-mail do
    operador na string).
    """

    ESQUEMA = "vpartifact"

    def __init__(self, raiz: Path):
        self._raiz = Path(raiz)

    def guardar(self, *, perfil_logico: str, recibo_id: str, dados: bytes,
                mime: str = "image/png") -> dom.VisualProofArtifact:
        sha = dom.sha256_de_bytes(dados)
        destino = self._raiz / perfil_logico / recibo_id
        destino.mkdir(parents=True, exist_ok=True, mode=0o700)
        arquivo = destino / "captura.png"
        # 0600 desde a criação: escrever e depois `chmod` deixa uma janela em que
        # o arquivo existe legível.
        descritor = os.open(arquivo, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.write(descritor, dados)
        finally:
            os.close(descritor)
        return dom.VisualProofArtifact(
            referencia=f"{self.ESQUEMA}://{perfil_logico}/{recibo_id}/captura.png",
            sha256=sha, bytes_=len(dados), mime=mime, criado_em=agora_iso())

    def caminho(self, referencia: str) -> Path:
        """Resolve a referência de volta para disco. Só quem tem o disco resolve."""
        prefixo = f"{self.ESQUEMA}://"
        if not referencia.startswith(prefixo):
            raise ValueError("referência de artefato desconhecida.")
        relativo = referencia[len(prefixo):]
        if ".." in relativo.split("/"):
            raise ValueError("referência de artefato com travessia de caminho.")
        return self._raiz / relativo


class ExecutorDoBroker:
    """Um pedido entra, um recibo sai. Nenhum caminho devolve valor resolvido."""

    def __init__(
        self, *,
        config: ConfiguracaoDoBroker,
        resolvedor: seg.ResolvedorDeSegredo,
        cliente: ads.ClienteDoAdsPower,
        navegador: ads.Navegador,
        artefatos: Optional[ArmazenamentoDeArtefatos] = None,
        registro: Optional[RegistroDeIdempotencia] = None,
        relogio: Callable[[], float] = time.monotonic,
        agora: Callable[[], str] = agora_iso,
        resolvedor_de_dns: Optional[Callable[[str], list[str]]] = None,
    ) -> None:
        self._config = config
        self._resolvedor = resolvedor
        self._cliente = cliente
        self._navegador = navegador
        self._artefatos = artefatos or ArmazenamentoDeArtefatos(config.artefatos_dir)
        self._registro = registro or RegistroDeIdempotencia(relogio=relogio)
        self._relogio = relogio
        self._agora = agora
        self._dns = resolvedor_de_dns
        #: Perfis que ESTE processo abriu. Fechar o que não abrimos derrubaria a
        #: sessão de quem estava usando o navegador manualmente.
        self._abertos_por_nos: set[str] = set()
        #: Falhas de limpeza. Instância, nunca classe: um `avisos: list = []` no
        #: corpo da classe seria compartilhado por todos os executores do
        #: processo, e o aviso de um pedido apareceria no diagnóstico de outro.
        self.avisos: list[str] = []

    # ── porta pública ────────────────────────────────────────────────────────

    def executar(self, pedido: dom.AdsPowerBrokerRequest, *,
                 consumidor: str = "desconhecido") -> dom.AdsPowerBrokerReceipt:
        inicio_iso = self._agora()
        inicio = self._relogio()
        recibo_id = f"rcp_{uuid.uuid4().hex[:16]}"

        try:
            perfil = self._autorizar(pedido)
        except (PerfilNaoAutorizado, PermissionError, dom.PayloadRecusado) as exc:
            return self._recusa(pedido, recibo_id, "nao_autorizado", str(exc),
                                inicio_iso, inicio)

        try:
            replay = self._registro.reivindicar(
                pedido.chave_idempotencia, pedido.impressao(), consumidor,
                float(self._config.lease_s))
        except ConflitoDeIdempotencia as exc:
            return self._recusa(pedido, recibo_id, "idempotencia_divergente", str(exc),
                                inicio_iso, inicio)
        except LeaseIndisponivel as exc:
            return self._recusa(pedido, recibo_id, "em_execucao", str(exc),
                                inicio_iso, inicio)
        if replay is not None:
            # Mesma chave, mesma entrada: devolve o recibo guardado, com o estado
            # trocado para `replay`. Quem chamou sabe que nada novo aconteceu —
            # e o `recibo_id` continua sendo o da execução ORIGINAL, porque é
            # dela que o artefato veio.
            return replace(replay, estado="replay", pedido_id=pedido.pedido_id)

        concluido = False
        try:
            recibo = self._executar_autorizado(pedido, perfil, recibo_id, inicio_iso, inicio)
            self._registro.concluir(pedido.chave_idempotencia, recibo)
            concluido = True
            return recibo
        finally:
            if not concluido:
                # Exceção não prevista: solta o lease para que um retry honesto
                # possa acontecer, em vez de travar a chave para sempre.
                self._registro.liberar(pedido.chave_idempotencia)

    # ── autorização ──────────────────────────────────────────────────────────

    def _autorizar(self, pedido: dom.AdsPowerBrokerRequest) -> PerfilAutorizado:
        perfil = self._config.perfil(pedido.perfil.perfil_logico)
        if perfil.owner_sub != pedido.owner_sub:
            raise PermissionError(
                "o dono do pedido não é o dono do perfil na allowlist do broker.")
        if perfil.ativo_id != pedido.ativo_id:
            raise PermissionError(
                "o perfil autorizado pertence a outro ativo do Cofre.")
        if pedido.operacao not in perfil.operacoes:
            raise PermissionError(
                f"a operação {pedido.operacao} não está na allowlist deste perfil.")
        if perfil.credencial_nome_logico != pedido.perfil.credencial_nome_logico:
            raise PermissionError(
                "o nome lógico de credencial não é o declarado para este perfil.")
        if pedido.operacao == "capturar_superficie":
            dominio = pedido.dominio_esperado
            if perfil.dominios_permitidos:
                if not dominio:
                    raise PermissionError(
                        "este perfil só captura dentro de domínios declarados: informe "
                        "o domínio esperado.")
                if not any(dom.dominio_casa(dominio, permitido)
                           for permitido in perfil.dominios_permitidos):
                    raise PermissionError(
                        "o domínio pedido está fora da allowlist deste perfil.")
            dom.exigir_url_de_superficie(
                pedido.url_alvo or "", dominio_esperado=dominio, resolver=self._dns)
        return perfil

    # ── execução ─────────────────────────────────────────────────────────────

    def _executar_autorizado(
        self, pedido: dom.AdsPowerBrokerRequest, perfil: PerfilAutorizado,
        recibo_id: str, inicio_iso: str, inicio: float,
    ) -> dom.AdsPowerBrokerReceipt:
        prazo = inicio + pedido.timeout_s
        segredo: Optional[seg.SegredoEfemero] = None
        #: ⚠️ Lista, e não booleano de retorno. Um `abrimos_agora` devolvido por
        #: `_operar` nunca chega a ser atribuído quando `_operar` levanta — e é
        #: exatamente aí, no meio da captura, que o perfil já está aberto. O
        #: registro por efeito colateral é o que faz a limpeza alcançar o caminho
        #: de exceção, que é o único caminho em que ela importa.
        abertos_nesta_operacao: list[PerfilAutorizado] = []
        deixar_aberto = False
        try:
            try:
                segredo = self._resolvedor.resolver(
                    nome_logico=perfil.credencial_nome_logico,
                    localizador=perfil.localizador)
            except seg.SegredoIndisponivel as exc:
                return self._falha(pedido, recibo_id, "resolucao_de_segredo_falhou",
                                   str(exc), inicio_iso, inicio)

            with segredo.usar() as chave:
                try:
                    recibo = self._operar(pedido, perfil, chave, recibo_id, inicio_iso,
                                          inicio, prazo, abertos_nesta_operacao)
                    deixar_aberto = (
                        pedido.operacao == "abrir_perfil" and recibo.estado == "executado")
                except ads.AdsPowerRecusou as exc:
                    recibo = self._falha(pedido, recibo_id, "autenticacao_recusada",
                                         str(exc), inicio_iso, inicio,
                                         adspower_code=exc.codigo)
                except ads.AdsPowerTempoEsgotado as exc:
                    recibo = self._falha(pedido, recibo_id, "timeout", str(exc),
                                         inicio_iso, inicio)
                except ads.AdsPowerIndisponivel as exc:
                    recibo = self._falha(pedido, recibo_id, "adspower_indisponivel",
                                         str(exc), inicio_iso, inicio)
                except ads.CheckpointExterno as exc:
                    recibo = self._falha(pedido, recibo_id, "checkpoint_externo",
                                         str(exc), inicio_iso, inicio)
                except dom.UrlRecusada as exc:
                    # Redirect para endereço privado cai aqui: a navegação já
                    # aconteceu, e o que se recusa é ACEITAR o destino final.
                    recibo = self._recusa(pedido, recibo_id, "destino_recusado",
                                          str(exc), inicio_iso, inicio)
                except TimeoutError as exc:
                    recibo = self._falha(pedido, recibo_id, "timeout", str(exc),
                                         inicio_iso, inicio)

                # ⚠️ A última peneira, e ela só é possível AQUI: `chave` ainda
                # existe. Depois deste bloco não há mais com o que comparar.
                projecao = recibo.para_dicionario()
                if len(chave) >= dom.TAMANHO_MINIMO_DE_SENTINELA:
                    try:
                        dom.recusar_valor_sensivel(projecao, sentinelas=(chave,))
                    except dom.VazamentoDetectado:
                        recibo = self._recusa(
                            pedido, recibo_id, "vazamento_contido",
                            "o recibo continha o valor resolvido e foi descartado antes "
                            "de sair do broker.", inicio_iso, inicio)
                return recibo
        finally:
            if not deixar_aberto:
                for aberto in abertos_nesta_operacao:
                    self._fechar_silenciosamente(aberto, segredo)
            if segredo is not None:
                segredo.descartar()

    def _operar(
        self, pedido: dom.AdsPowerBrokerRequest, perfil: PerfilAutorizado, chave: str,
        recibo_id: str, inicio_iso: str, inicio: float, prazo: float,
        abertos: list[PerfilAutorizado],
    ) -> dom.AdsPowerBrokerReceipt:
        restante = self._restante(prazo)

        if pedido.operacao == "estado_do_perfil":
            resposta = self._cliente.estado_do_perfil(
                chave, user_id=perfil.user_id, timeout_s=restante)
            estado = str(resposta.data.get("status") or "Desconhecido")
            return self._sucesso(pedido, recibo_id, f"perfil {estado}", inicio_iso,
                                 inicio, adspower_code=resposta.code)

        if pedido.operacao == "fechar_perfil":
            resposta = self._cliente.fechar_perfil(
                chave, user_id=perfil.user_id, timeout_s=restante)
            self._abertos_por_nos.discard(perfil.perfil_logico)
            return self._sucesso(pedido, recibo_id, "perfil fechado", inicio_iso,
                                 inicio, adspower_code=resposta.code)

        ws = self._garantir_perfil_aberto(perfil, chave, prazo, abertos)

        if pedido.operacao == "abrir_perfil":
            return self._sucesso(pedido, recibo_id, "perfil aberto", inicio_iso,
                                 inicio, adspower_code=0)

        # capturar_superficie
        alvo = dom.exigir_url_de_superficie(
            pedido.url_alvo or "", dominio_esperado=pedido.dominio_esperado,
            resolver=self._dns)
        captura = self._navegador.capturar(
            ws_endpoint=ws, url=alvo,
            viewport=pedido.viewport or dom.Viewport(largura=1366, altura=768),
            timezone=pedido.timezone, timeout_s=self._restante(prazo))

        # ⚠️ O endereço FINAL passa pela mesma política do inicial. Um redirect
        # para 169.254.169.254 é exatamente o caminho que a validação de entrada
        # não alcança, porque ele acontece depois dela.
        url_final = dom.exigir_url_de_superficie(
            captura.url_final, dominio_esperado=pedido.dominio_esperado, resolver=self._dns)
        for salto in captura.redirecionamentos:
            dom.exigir_url_de_superficie(
                salto, dominio_esperado=pedido.dominio_esperado, resolver=self._dns)

        artefato = self._artefatos.guardar(
            perfil_logico=perfil.perfil_logico, recibo_id=recibo_id,
            dados=captura.imagem, mime=captura.mime)

        return dom.AdsPowerBrokerReceipt(
            recibo_id=recibo_id, pedido_id=pedido.pedido_id,
            chave_idempotencia=pedido.chave_idempotencia, operacao=pedido.operacao,
            perfil_logico=perfil.perfil_logico, owner_sub=pedido.owner_sub,
            ativo_id=pedido.ativo_id, estado="executado",
            motivo_codigo="ok", motivo="captura concluída",
            iniciado_em=inicio_iso, concluido_em=self._agora(),
            duracao_ms=self._duracao(inicio), adspower_code=0,
            url_final=url_final, status_http=captura.status_http,
            redirecionamentos=tuple(captura.redirecionamentos),
            artefato=artefato,
            console_resumo=_resumir_console(captura.console),
            rede_resumo=_resumir_rede(captura.rede),
        )

    def _garantir_perfil_aberto(self, perfil: PerfilAutorizado, chave: str,
                                prazo: float, abertos: list[PerfilAutorizado]) -> str:
        """Abre só se não estiver aberto. `start` duas vezes é sessão duplicada.

        A checagem custa uma chamada a mais e evita a classe de defeito em que
        um retry legítimo abre um segundo navegador com o mesmo perfil — que o
        AdsPower não impede, e que produz duas sessões disputando os mesmos
        cookies.
        """
        try:
            atual = self._cliente.estado_do_perfil(
                chave, user_id=perfil.user_id, timeout_s=self._restante(prazo))
            if str(atual.data.get("status")) == "Active":
                ws = atual.ws_puppeteer()
                if ws:
                    return ws
        except ads.AdsPowerRecusou:
            # Perfil desconhecido para `active` não é motivo para não abrir.
            pass
        aberto = self._cliente.abrir_perfil(
            chave, user_id=perfil.user_id, timeout_s=self._restante(prazo))
        ws = aberto.ws_puppeteer()
        self._abertos_por_nos.add(perfil.perfil_logico)
        abertos.append(perfil)
        if not ws:
            raise ads.AdsPowerIndisponivel(
                "a Local API abriu o perfil sem devolver endpoint de depuração.")
        return ws

    def _fechar_silenciosamente(self, perfil: PerfilAutorizado,
                                segredo: Optional[seg.SegredoEfemero]) -> None:
        """Limpeza do `finally`. Ela não pode derrubar o recibo já produzido.

        Se o fechamento falhar, o fato entra em `avisos` e o recibo do que JÁ
        aconteceu continua valendo. Trocar um recibo bom por uma exceção de
        limpeza apagaria a evidência da operação que deu certo.

        Reusa o segredo do pedido em vez de pedir outro ao cofre: uma segunda
        resolução por limpeza dobraria as leituras no 1Password e faria toda
        falha custar uma aprovação a mais ao operador.
        """
        if segredo is None or segredo.descartado:
            self.avisos.append(
                f"não foi possível fechar {perfil.perfil_logico}: credencial já descartada")
            return
        try:
            with segredo.usar() as chave:
                self._cliente.fechar_perfil(chave, user_id=perfil.user_id, timeout_s=10.0)
            self._abertos_por_nos.discard(perfil.perfil_logico)
        except (ads.AdsPowerRecusou, ads.AdsPowerIndisponivel, seg.SegredoJaDescartado) as exc:
            self.avisos.append(
                f"não foi possível fechar {perfil.perfil_logico}: {type(exc).__name__}")

    # ── fábricas de recibo ───────────────────────────────────────────────────

    def _restante(self, prazo: float) -> float:
        restante = prazo - self._relogio()
        if restante <= 0:
            raise TimeoutError("o prazo da operação acabou antes de ela terminar.")
        return restante

    def _duracao(self, inicio: float) -> int:
        return max(0, int((self._relogio() - inicio) * 1000))

    def _base(self, pedido: dom.AdsPowerBrokerRequest, recibo_id: str, estado: str,
              codigo: str, motivo: str, inicio_iso: str, inicio: float,
              adspower_code: Optional[int] = None) -> dom.AdsPowerBrokerReceipt:
        return dom.AdsPowerBrokerReceipt(
            recibo_id=recibo_id, pedido_id=pedido.pedido_id,
            chave_idempotencia=pedido.chave_idempotencia, operacao=pedido.operacao,
            perfil_logico=pedido.perfil.perfil_logico, owner_sub=pedido.owner_sub,
            ativo_id=pedido.ativo_id, estado=estado, motivo_codigo=codigo,
            motivo=dom.sanitizar_texto(motivo), iniciado_em=inicio_iso,
            concluido_em=self._agora(), duracao_ms=self._duracao(inicio),
            adspower_code=adspower_code)

    def _sucesso(self, pedido, recibo_id, motivo, inicio_iso, inicio,
                 adspower_code=None) -> dom.AdsPowerBrokerReceipt:
        return self._base(pedido, recibo_id, "executado", "ok", motivo,
                          inicio_iso, inicio, adspower_code)

    def _recusa(self, pedido, recibo_id, codigo, motivo, inicio_iso,
                inicio) -> dom.AdsPowerBrokerReceipt:
        return self._base(pedido, recibo_id, "recusado", codigo, motivo, inicio_iso, inicio)

    def _falha(self, pedido, recibo_id, codigo, motivo, inicio_iso, inicio,
               adspower_code=None) -> dom.AdsPowerBrokerReceipt:
        return self._base(pedido, recibo_id, "falhou", codigo, motivo, inicio_iso,
                          inicio, adspower_code)


def _resumir_console(entradas) -> dict[str, Any]:
    """Contagem por nível e as primeiras mensagens SANITIZADAS.

    Guardar o console cru é guardar tudo que a página imprimiu — o que inclui
    token de sessão que alguma biblioteca resolveu logar. O resumo conta e
    mostra pouco, já limpo.
    """
    niveis: dict[str, int] = {}
    amostras: list[str] = []
    for entrada in entradas:
        nivel = str(entrada.get("nivel") or entrada.get("level") or "log").lower()
        niveis[nivel] = niveis.get(nivel, 0) + 1
        if nivel in ("error", "erro") and len(amostras) < 5:
            amostras.append(dom.sanitizar_texto(str(entrada.get("texto") or entrada.get("text") or ""), 200))
    return {
        "total": sum(niveis.values()),
        "erros": niveis.get("error", 0) + niveis.get("erro", 0),
        "avisos": niveis.get("warning", 0) + niveis.get("aviso", 0),
        "por_nivel": niveis,
        "amostras_de_erro": amostras,
    }


def _resumir_rede(entradas) -> dict[str, Any]:
    """Contagem e domínios de TERCEIRO, sem URL completa nem query.

    Um QA visual precisa saber "12 requisições, 2 falharam, e uma delas foi para
    um domínio de anúncio". Não precisa da URL inteira, que carrega parâmetros.
    """
    total = 0
    falhas = 0
    dominios: dict[str, int] = {}
    for entrada in entradas:
        total += 1
        status = entrada.get("status")
        if entrada.get("falhou") or (isinstance(status, int) and status >= 400):
            falhas += 1
        host = str(entrada.get("host") or "")
        if host:
            dominios[host] = dominios.get(host, 0) + 1
    return {
        "requisicoes": total,
        "falhas": falhas,
        "hosts": dict(sorted(dominios.items(), key=lambda kv: -kv[1])[:15]),
    }


__all__ = [
    "ArmazenamentoDeArtefatos", "ConflitoDeIdempotencia", "ExecutorDoBroker",
    "LeaseIndisponivel", "RegistroDeIdempotencia", "agora_iso",
]
