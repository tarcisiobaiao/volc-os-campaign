/**
 * Catálogo de comandos `/` (inventário real do Hermes + comandos da web) e filtro.
 *
 * O catálogo vem do servidor. Um comando só aparece como executável se o
 * servidor disser `disponivel`; os demais aparecem com o motivo, para quem já
 * usa no Telegram entender por que não roda aqui.
 */
import { useEffect, useMemo, useState } from 'react';

import { biaApi, type BiaApi } from './api';
import type { ComandoDoCatalogo } from './tipos';

/** Texto do compositor que está pedindo a paleta: "/" + nome, sem espaço ainda. */
export function consultaDeComando(texto: string): string | null {
  const m = texto.match(/^\/([\w-]*)$/);
  return m ? m[1].toLowerCase() : null;
}

/** "/nome argumentos" → { nome, argumentos }. */
export function separarComando(texto: string): { nome: string; argumentos: string } | null {
  const m = texto.trim().match(/^\/([\w-]+)(?:\s+([\s\S]*))?$/);
  return m ? { nome: m[1].toLowerCase(), argumentos: (m[2] ?? '').trim() } : null;
}

export function useComandos(api: BiaApi = biaApi) {
  const [catalogo, setCatalogo] = useState<ComandoDoCatalogo[] | null>(null);
  const [erro, setErro] = useState(false);

  useEffect(() => {
    let ativo = true;
    api.comandos()
      .then((r) => ativo && setCatalogo(r.comandos))
      .catch(() => ativo && setErro(true));
    return () => {
      ativo = false;
    };
  }, [api]);

  const procurar = useMemo(() => {
    const porNome = new Map<string, ComandoDoCatalogo>();
    for (const c of catalogo ?? []) if (!porNome.has(c.nome)) porNome.set(c.nome, c);
    return (nome: string) => porNome.get(nome.toLowerCase()) ?? null;
  }, [catalogo]);

  /** Disponíveis primeiro; do Hermes, só os que casam com a busca (até 8). */
  const filtrar = useMemo(
    () => (consulta: string) => {
      const lista = catalogo ?? [];
      const casa = (c: ComandoDoCatalogo) =>
        c.nome.startsWith(consulta) || c.aliases.some((a) => a.replace('/', '').startsWith(consulta));
      const web = lista.filter((c) => c.origem === 'volc' && casa(c));
      const nomesWeb = new Set(web.map((c) => c.nome));
      const telegram = consulta
        ? lista.filter((c) => c.origem !== 'volc' && !c.disponivel && c.nome.startsWith(consulta) && !nomesWeb.has(c.nome)).slice(0, 8)
        : [];
      return { web, telegram };
    },
    [catalogo],
  );

  return { catalogo, erro, procurar, filtrar };
}
