/**
 * Fila de anexos do compositor: escolhe, sobe com progresso, repete, remove.
 *
 * A conferência aqui é só cortesia (resposta imediata ao operador). Quem decide
 * é o servidor, pelos BYTES: tipo, tamanho, cota, dono. Um arquivo só conta como
 * pronto depois do 201 do servidor; nada é anexado à mensagem antes disso.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

import { biaApi, type BiaApi } from './api';
import type { AnexoDaBia } from './tipos';
import { mensagemDe } from './useBia';

const MB = 1024 * 1024;

/** Espelho do backend (anexos/dominio.py). Divergência só deixa o servidor recusar. */
export const TIPOS_ACEITOS: Record<string, { rotulo: string; max: number; familia: 'imagem' | 'documento' }> = {
  '.png': { rotulo: 'PNG', max: 3 * MB, familia: 'imagem' },
  '.jpg': { rotulo: 'JPEG', max: 3 * MB, familia: 'imagem' },
  '.jpeg': { rotulo: 'JPEG', max: 3 * MB, familia: 'imagem' },
  '.webp': { rotulo: 'WebP', max: 3 * MB, familia: 'imagem' },
  '.pdf': { rotulo: 'PDF', max: 10 * MB, familia: 'documento' },
  '.txt': { rotulo: 'TXT', max: 2 * MB, familia: 'documento' },
  '.md': { rotulo: 'TXT', max: 2 * MB, familia: 'documento' },
  '.csv': { rotulo: 'CSV', max: 2 * MB, familia: 'documento' },
  '.docx': { rotulo: 'DOCX', max: 10 * MB, familia: 'documento' },
};
export const ACCEPT = Object.keys(TIPOS_ACEITOS).join(',');
export const MAX_ANEXOS = 4;
export const MAX_IMAGENS = 3;

export type EstadoDoAnexo = 'enviando' | 'pronto' | 'falhou';

export interface ItemDeAnexo {
  chave: string;
  arquivo: File;
  nome: string;
  tamanho: number;
  rotulo: string;
  familia: 'imagem' | 'documento';
  previa: string | null; // blob: local, só para imagem
  estado: EstadoDoAnexo;
  progresso: number;
  anexo: AnexoDaBia | null;
  erro: string | null;
}

export function formatarTamanho(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < MB) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / MB).toFixed(1).replace('.', ',')} MB`;
}

const extensao = (nome: string) => (nome.match(/\.[A-Za-z0-9]{1,8}$/)?.[0] ?? '').toLowerCase();

export function useAnexos(api: BiaApi = biaApi) {
  const [itens, setItens] = useState<ItemDeAnexo[]>([]);
  const [aviso, setAviso] = useState<string | null>(null);
  const cancelamentos = useRef(new Map<string, () => void>());
  const vivo = useRef(true);
  const itensRef = useRef<ItemDeAnexo[]>([]);
  itensRef.current = itens;

  useEffect(() => {
    vivo.current = true;
    const canc = cancelamentos.current;
    return () => {
      vivo.current = false;
      canc.forEach((c) => c());
      itensRef.current.forEach((i) => i.previa && URL.revokeObjectURL(i.previa));
    };
  }, []);

  const mudar = (chave: string, parcial: Partial<ItemDeAnexo>) =>
    setItens((lista) => lista.map((i) => (i.chave === chave ? { ...i, ...parcial } : i)));

  const subir = useCallback(
    (item: ItemDeAnexo) => {
      const envio = api.enviarAnexo(item.arquivo, (f) => vivo.current && mudar(item.chave, { progresso: f }));
      cancelamentos.current.set(item.chave, envio.cancelar);
      envio.promessa
        .then((anexo) => vivo.current && mudar(item.chave, { estado: 'pronto', anexo, progresso: 1, erro: null }))
        .catch((e) => vivo.current && mudar(item.chave, { estado: 'falhou', erro: mensagemDe(e) }))
        .finally(() => cancelamentos.current.delete(item.chave));
    },
    [api],
  );

  const adicionar = useCallback(
    (arquivos: Iterable<File>) => {
      setAviso(null);
      const atuais = itensRef.current;
      const novos: ItemDeAnexo[] = [];
      const recusas: string[] = [];
      for (const arquivo of arquivos) {
        const tipo = TIPOS_ACEITOS[extensao(arquivo.name)];
        if (!tipo) {
          recusas.push(`${arquivo.name}: tipo não aceito. Use PNG, JPEG, WebP, PDF, TXT, CSV ou DOCX.`);
          continue;
        }
        if (arquivo.size > tipo.max) {
          recusas.push(`${arquivo.name}: ${tipo.rotulo} acima de ${tipo.max / MB} MB.`);
          continue;
        }
        if (atuais.length + novos.length >= MAX_ANEXOS) {
          recusas.push(`Até ${MAX_ANEXOS} anexos por mensagem.`);
          break;
        }
        const imagens = [...atuais, ...novos].filter((i) => i.familia === 'imagem').length;
        if (tipo.familia === 'imagem' && imagens >= MAX_IMAGENS) {
          recusas.push(`Até ${MAX_IMAGENS} imagens por mensagem.`);
          continue;
        }
        novos.push({
          chave: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
          arquivo,
          nome: arquivo.name,
          tamanho: arquivo.size,
          rotulo: tipo.rotulo,
          familia: tipo.familia,
          previa: tipo.familia === 'imagem' && typeof URL.createObjectURL === 'function'
            ? URL.createObjectURL(arquivo) : null,
          estado: 'enviando',
          progresso: 0,
          anexo: null,
          erro: null,
        });
      }
      if (recusas.length) setAviso(recusas.join(' '));
      if (novos.length) {
        setItens((lista) => [...lista, ...novos]);
        novos.forEach(subir);
      }
    },
    [subir],
  );

  const tentarDeNovo = useCallback(
    (chave: string) => {
      const item = itensRef.current.find((i) => i.chave === chave);
      if (!item || item.estado !== 'falhou') return;
      mudar(chave, { estado: 'enviando', progresso: 0, erro: null });
      subir({ ...item, estado: 'enviando', progresso: 0, erro: null });
    },
    [subir],
  );

  const remover = useCallback(
    (chave: string) => {
      const item = itensRef.current.find((i) => i.chave === chave);
      cancelamentos.current.get(chave)?.();
      if (item?.previa) URL.revokeObjectURL(item.previa);
      if (item?.anexo) void api.removerAnexo(item.anexo.id).catch(() => undefined);
      setItens((lista) => lista.filter((i) => i.chave !== chave));
    },
    [api],
  );

  /** Depois que o servidor ACEITOU a mensagem: some da fila (o arquivo fica no servidor). */
  const esvaziar = useCallback(() => {
    itensRef.current.forEach((i) => i.previa && URL.revokeObjectURL(i.previa));
    setItens([]);
    setAviso(null);
  }, []);

  return {
    itens,
    aviso,
    limparAviso: () => setAviso(null),
    adicionar,
    tentarDeNovo,
    remover,
    esvaziar,
    prontos: itens.filter((i) => i.estado === 'pronto' && i.anexo).map((i) => i.anexo!.id),
    enviandoAlgum: itens.some((i) => i.estado === 'enviando'),
    falhouAlgum: itens.some((i) => i.estado === 'falhou'),
  };
}
