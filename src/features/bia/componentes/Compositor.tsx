/**
 * Compositor da Bia: texto, anexos, comandos `/` e contexto de campanha.
 *
 * - Enter envia, Shift+Enter quebra a linha; durante composição de IME
 *   (acentos, japonês…) Enter é do IME, não do envio.
 * - O rascunho fica no `sessionStorage` por usuário e conversa, e só é limpo
 *   depois que o servidor aceitou a mensagem: erro de rede não apaga nada.
 * - Texto que começa com `/` NUNCA é enviado à Bia: é um comando, resolvido
 *   aqui (local) ou por rota tipada do servidor (`/status`). Comando
 *   indisponível mostra o motivo e não sai do navegador.
 */
import React, { useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Icone } from '@/components/ui/icone';
import { cn } from '@/lib/utils';

import { ICONES_BIA } from '../icones';
import type { ComandoDoCatalogo, ContextoPedido, JanelaDeContexto } from '../tipos';
import { ACCEPT, type useAnexos } from '../useAnexos';
import type { EstadoDoChat } from '../useBia';
import { consultaDeComando, separarComando, type useComandos } from '../useComandos';

import { FilaDeAnexos } from './FilaDeAnexos';
import { PaletaDeComandos, type OpcaoDaPaleta } from './PaletaDeComandos';

const PADRAO_REF = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,119}$/;
const ALTURA_MAXIMA = 200;

export const chaveDoRascunho = (userId: string, conversaId: string | null) =>
  `volc.bia.rascunho.${userId}.${conversaId ?? 'nova'}`;

function lerRascunho(chave: string): string {
  try {
    return window.sessionStorage.getItem(chave) ?? '';
  } catch {
    return '';
  }
}

function gravarRascunho(chave: string, texto: string): void {
  try {
    if (texto) window.sessionStorage.setItem(chave, texto);
    else window.sessionStorage.removeItem(chave);
  } catch {
    /* sem armazenamento: o rascunho vive só na tela */
  }
}

interface Props {
  userId: string;
  bia: EstadoDoChat;
  anexos: ReturnType<typeof useAnexos>;
  comandos: ReturnType<typeof useComandos>;
  campo: React.RefObject<HTMLTextAreaElement>;
  /** Texto posto no campo por sugestão/reaproveitamento (`n` muda a cada pedido). */
  preenchimento?: { texto: string; n: number } | null;
  onAbrirConversas: () => void;
}

export const Compositor: React.FC<Props> = ({ userId, bia, anexos, comandos, campo, preenchimento, onAbrirConversas }) => {
  const chave = chaveDoRascunho(userId, bia.conversaId);
  const [texto, setTexto] = useState(() => lerRascunho(chave));
  const [contexto, setContexto] = useState<ContextoPedido | null>(null);
  const [ativa, setAtiva] = useState(0);
  const [paletaDispensada, setPaletaDispensada] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);
  const seletor = useRef<HTMLInputElement>(null);
  const base = useId();
  const ids = { campo: `${base}-campo`, paleta: `${base}-paleta`, dica: `${base}-dica`, aviso: `${base}-aviso`, contador: `${base}-contador` };

  // Troca de conversa: carrega o rascunho daquela conversa.
  const chaveAnterior = useRef(chave);
  useEffect(() => {
    if (chaveAnterior.current === chave) return;
    chaveAnterior.current = chave;
    setTexto(lerRascunho(chave));
    setAviso(null);
  }, [chave]);

  useEffect(() => gravarRascunho(chave, texto), [chave, texto]);

  useEffect(() => {
    if (!preenchimento) return;
    setTexto(preenchimento.texto);
    requestAnimationFrame(() => campo.current?.focus());
  }, [preenchimento, campo]);

  // Altura automática até o limite; depois rola dentro do campo.
  useLayoutEffect(() => {
    const el = campo.current;
    if (!el) return;
    el.style.height = 'auto';
    // scrollHeight não inclui a borda; com border-box, sem somá-la sobra 1px de rolagem.
    const borda = el.offsetHeight - el.clientHeight;
    el.style.height = `${Math.min(el.scrollHeight + borda, ALTURA_MAXIMA)}px`;
  }, [texto, campo]);

  const consulta = paletaDispensada ? null : consultaDeComando(texto);
  const paletaAberta = consulta !== null;
  const { web, telegram } = useMemo(() => {
    const r = comandos.filtrar(consulta ?? '');
    const op = (c: ComandoDoCatalogo, grupo: string): OpcaoDaPaleta => ({ comando: c, idDom: `${base}-op-${grupo}-${c.nome}` });
    return { web: r.web.map((c) => op(c, 'w')), telegram: r.telegram.map((c) => op(c, 't')) };
  }, [comandos, consulta, base]);
  const opcoes = [...web, ...telegram];
  const ativaSegura = Math.min(ativa, Math.max(0, opcoes.length - 1));

  useEffect(() => setAtiva(0), [consulta]);

  const limite = bia.servico?.limites.max_caracteres ?? 4000;
  const motorDesligado = bia.servico ? !bia.servico.motor_configurado : false;
  const bloqueioDeEnvio = motorDesligado
    ? 'O Hermes ainda não está configurado neste servidor.'
    : bia.bloqueada
      ? 'Há um envio de resultado incerto nesta conversa. Verifique a resposta ou abra uma nova conversa.'
      : bia.emAndamento
        ? 'Aguarde a resposta da Bia para enviar a próxima mensagem.'
        : anexos.enviandoAlgum
          ? 'Aguarde os arquivos terminarem de subir.'
          : anexos.falhouAlgum
            ? 'Remova os arquivos recusados (ou envie de novo os que falharam por rede) para enviar.'
            : !bia.online
              ? 'Sem conexão com a internet.'
              : null;
  const temConteudo = texto.trim().length > 0 || anexos.prontos.length > 0;
  const motivoSemRascunho = !bia.execucoes.some((x) => x.estado === 'succeeded' && !x.contexto?.intencao)
    ? 'Ainda não há conversa para salvar: converse com a Bia primeiro.'
    : bloqueioDeEnvio && bloqueioDeEnvio !== 'Aguarde os arquivos terminarem de subir.'
      ? bloqueioDeEnvio
      : null;
  const podeEnviar = !bia.enviando && !bloqueioDeEnvio && temConteudo && texto.length <= limite;

  const focar = () => requestAnimationFrame(() => campo.current?.focus());

  const nota = (titulo: string, mensagem: string) => bia.adicionarNota({ tipo: 'recusa', titulo, texto: mensagem });

  const rodarComando = (nome: string, argumentos: string) => {
    const c = comandos.procurar(nome);
    setPaletaDispensada(false);
    if (!c) {
      nota(`/${nome}`, 'Comando desconhecido. Digite / para ver a lista. Nada foi enviado à Bia.');
      setTexto('');
      return;
    }
    if (!c.disponivel) {
      nota(`/${c.nome}`, `${c.motivo}${c.equivalente_web ? ` Na web, use /${c.equivalente_web}.` : ''} Nada foi enviado à Bia.`);
      setTexto('');
      return;
    }
    setTexto('');
    switch (c.nome) {
      case 'nova':
        void bia.novaConversa();
        break;
      case 'conversas':
        onAbrirConversas();
        return;
      case 'anexar':
        seletor.current?.click();
        break;
      case 'copiar':
        if (!bia.ultimaResposta) {
          nota('/copiar', 'Ainda não há resposta da Bia nesta conversa.');
        } else {
          void navigator.clipboard?.writeText(bia.ultimaResposta).then(
            () => bia.adicionarNota({ tipo: 'info', texto: 'Última resposta copiada.' }),
            () => nota('/copiar', 'O navegador não permitiu copiar. Use o botão Copiar da resposta.'),
          );
        }
        break;
      case 'contexto': {
        const ref = argumentos.trim();
        if (!ref) {
          setTexto('/contexto ');
          setPaletaDispensada(true);
          setAviso('Escreva o id VOLC da campanha depois de /contexto e tecle Enter.');
          break;
        }
        if (!PADRAO_REF.test(ref)) {
          nota('/contexto', 'Id inválido: use o id VOLC da campanha (letras, números, ponto, hífen, dois-pontos).');
          break;
        }
        setContexto({ campaign_ref: ref, janela: 'ultimos_7_dias' });
        break;
      }
      case 'status':
        void bia.executarStatus();
        break;
      case 'ajuda':
        bia.adicionarNota({ tipo: 'ajuda' });
        break;
      case 'cerebro':
        void bia.statusDoCerebro();
        break;
      case 'salvar':
        if (motivoSemRascunho) {
          nota('/salvar', motivoSemRascunho);
          break;
        }
        void bia.pedirRascunho(argumentos);
        break;
      default:
        nota(`/${c.nome}`, 'Este comando ainda não tem ação nesta tela. Nada foi enviado à Bia.');
    }
    focar();
  };

  const escolher = (c: ComandoDoCatalogo) => {
    if (c.disponivel && c.args) {
      // Completa e espera o argumento.
      setTexto(`/${c.nome} `);
      setPaletaDispensada(true);
      focar();
      return;
    }
    rodarComando(c.nome, '');
  };

  const enviar = async () => {
    setAviso(null);
    const cmd = separarComando(texto);
    if (cmd) {
      rodarComando(cmd.nome, cmd.argumentos);
      return;
    }
    if (bloqueioDeEnvio) {
      setAviso(bloqueioDeEnvio);
      return;
    }
    if (!podeEnviar) return;
    const ok = await bia.enviar(texto.trim(), { anexos: anexos.prontos, contexto: contexto ?? undefined });
    if (ok) {
      // Só agora: o servidor aceitou.
      setTexto('');
      gravarRascunho(chave, '');
      anexos.esvaziar();
    }
    focar();
  };

  const aoTeclar = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.nativeEvent.isComposing || e.keyCode === 229) return;
    if (paletaAberta && opcoes.length) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setAtiva((ativaSegura + 1) % opcoes.length);
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setAtiva((ativaSegura - 1 + opcoes.length) % opcoes.length);
        return;
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault();
        escolher(opcoes[ativaSegura].comando);
        return;
      }
    }
    if (paletaAberta && e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation();
      setPaletaDispensada(true);
      return;
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void enviar();
    }
  };

  const aoColar = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const arquivos = Array.from(e.clipboardData?.files ?? []);
    if (!arquivos.length) return;
    if (!e.clipboardData.getData('text/plain')) e.preventDefault();
    anexos.adicionar(arquivos);
  };

  const pertoDoLimite = texto.length >= limite * 0.8;
  const avisoVisivel = aviso ?? anexos.aviso;

  return (
    <div className="relative border-t border-border bg-card">
      {paletaAberta ? (
        <PaletaDeComandos
          id={ids.paleta}
          web={web}
          telegram={telegram}
          ativa={ativaSegura}
          carregando={!comandos.catalogo && !comandos.erro}
          falhou={comandos.erro}
          onEscolher={escolher}
          onApontar={setAtiva}
        />
      ) : null}

      {anexos.itens.length ? (
        <FilaDeAnexos itens={anexos.itens} onRemover={anexos.remover} onRepetir={anexos.tentarDeNovo} />
      ) : null}

      {contexto ? (
        <div className="flex flex-wrap items-center gap-2 px-3 pt-3">
          <span className="kicker">Contexto</span>
          <span className="inline-flex min-w-0 items-center gap-1.5 rounded-full border border-border bg-muted py-0.5 pl-2.5 pr-0.5 text-denso text-foreground">
            <span className="truncate">Campanha {contexto.campaign_ref}</span>
            <label className="sr-only" htmlFor={`${base}-janela`}>Janela do contexto</label>
            <select
              id={`${base}-janela`}
              value={contexto.janela}
              onChange={(e) => setContexto({ ...contexto, janela: e.target.value as JanelaDeContexto })}
              className="h-7 rounded-full border-0 bg-transparent px-1 text-denso text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/70"
            >
              <option value="ultimos_7_dias">7 dias</option>
              <option value="ultimos_14_dias">14 dias</option>
              <option value="ultimos_30_dias">30 dias</option>
            </select>
            <Button type="button" variant="ghost" size="icon" className="touch-target h-7 w-7 rounded-full" onClick={() => setContexto(null)}>
              <Icone icon={ICONES_BIA.remover} tamanho="sm" rotulo="Remover contexto da campanha" />
            </Button>
          </span>
        </div>
      ) : null}

      <form
        className="px-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-2.5"
        onSubmit={(e) => {
          e.preventDefault();
          void enviar();
        }}
      >
        <label htmlFor={ids.campo} className="sr-only">Mensagem para a Bia</label>
        <textarea
          id={ids.campo}
          ref={campo}
          value={texto}
          rows={1}
          maxLength={limite + 500}
          onChange={(e) => {
            setTexto(e.target.value);
            setPaletaDispensada(false);
            if (aviso) setAviso(null);
          }}
          onKeyDown={aoTeclar}
          onPaste={aoColar}
          placeholder="Pergunte à Bia, ou digite / para comandos"
          role="combobox"
          aria-expanded={paletaAberta}
          aria-haspopup="listbox"
          aria-controls={paletaAberta ? ids.paleta : undefined}
          aria-autocomplete="list"
          aria-activedescendant={paletaAberta && opcoes.length ? opcoes[ativaSegura].idDom : undefined}
          aria-describedby={[ids.dica, avisoVisivel ? ids.aviso : null, pertoDoLimite ? ids.contador : null].filter(Boolean).join(' ')}
          aria-invalid={texto.length > limite || undefined}
          className="block max-h-[200px] min-h-[44px] w-full resize-none rounded-md border border-input bg-card px-3 py-2.5 text-sm leading-relaxed text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/70 focus-visible:ring-offset-1 focus-visible:ring-offset-card"
        />

        {avisoVisivel ? (
          <p id={ids.aviso} role="alert" className="mt-1.5 text-denso text-foreground">
            {avisoVisivel}
          </p>
        ) : bloqueioDeEnvio && !bia.emAndamento && !anexos.enviandoAlgum ? (
          <p className="mt-1.5 text-denso text-muted-foreground">{bloqueioDeEnvio}</p>
        ) : null}

        <div className="mt-2 flex items-center gap-1">
          <input
            ref={seletor}
            type="file"
            multiple
            accept={ACCEPT}
            tabIndex={-1}
            aria-hidden="true"
            className="sr-only"
            onChange={(e) => {
              if (e.target.files?.length) anexos.adicionar(Array.from(e.target.files));
              e.target.value = '';
            }}
          />
          <Button type="button" variant="ghost" size="icon" className="touch-target h-10 w-10" onClick={() => seletor.current?.click()}>
            <Icone icon={ICONES_BIA.anexar} rotulo="Anexar arquivos (PNG, JPEG, WebP, PDF, TXT, CSV, DOCX)" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="touch-target h-10 w-10"
            aria-expanded={paletaAberta}
            aria-controls={paletaAberta ? ids.paleta : undefined}
            onClick={() => {
              setPaletaDispensada(false);
              setTexto((t) => (t.startsWith('/') ? t : '/'));
              focar();
            }}
          >
            <Icone icon={ICONES_BIA.comandos} rotulo="Comandos" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="touch-target h-10 gap-1.5 px-2.5 text-muted-foreground"
            onClick={() => void bia.statusDoCerebro()}
          >
            <Icone icon={ICONES_BIA.cerebro} rotulo="Cérebro: status dos três (só leitura)" />
            <span aria-hidden="true" className="hidden text-micro font-medium tracking-normal lg:inline">Cérebro</span>
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="touch-target h-10 gap-1.5 px-2.5 text-muted-foreground"
            aria-disabled={!!motivoSemRascunho || bia.enviando}
            title={motivoSemRascunho ?? 'A Bia redige; você revisa e confirma antes de gravar'}
            onClick={() => (motivoSemRascunho ? setAviso(motivoSemRascunho) : void bia.pedirRascunho())}
          >
            <Icone icon={ICONES_BIA.salvar} rotulo="Salvar no cérebro: preparar captura desta conversa" />
            <span aria-hidden="true" className="hidden text-micro font-medium tracking-normal lg:inline">Salvar no cérebro</span>
          </Button>
          <p id={ids.dica} className="ml-1 hidden min-w-0 flex-1 truncate text-micro font-normal tracking-normal text-muted-foreground md:block lg:sr-only">
            Enter envia · Shift+Enter quebra a linha
          </p>
          <span className="flex-1 md:hidden lg:block" />
          {pertoDoLimite ? (
            <span
              id={ids.contador}
              className={cn('numero mr-1 shrink-0 text-micro', texto.length > limite ? 'text-destructive' : 'text-muted-foreground')}
            >
              {texto.length.toLocaleString('pt-BR')}/{limite.toLocaleString('pt-BR')}
            </span>
          ) : null}
          <Button
            type="submit"
            size="icon"
            className="touch-target h-10 w-10 shrink-0 rounded-full"
            disabled={!separarComando(texto) && !podeEnviar}
            aria-label={bia.enviando ? 'Enviando…' : 'Enviar mensagem'}
          >
            <Icone
              icon={bia.enviando ? ICONES_BIA.enviando : ICONES_BIA.enviar}
              className={bia.enviando ? 'motion-safe:animate-spin' : undefined}
            />
          </Button>
        </div>
      </form>
    </div>
  );
};
