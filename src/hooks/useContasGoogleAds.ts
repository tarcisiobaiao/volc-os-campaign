/**
 * O estado da aba Google Ads: o escopo da casa e a conta de cada projeto.
 *
 * ## Por que as duas leituras andam juntas
 *
 * A tela é uma única pergunta — "cada projeto anuncia em qual conta?" — e ela
 * só se responde cruzando as duas listas. Carregar em momentos diferentes
 * produziria um estado intermediário em que um projeto vinculado aparece com
 * "conta desconhecida" só porque o escopo ainda não chegou.
 *
 * ## Este hook NÃO é a guarda
 *
 * Ele mostra apenas contas da casa porque é o que o servidor devolve. Quem
 * recusa conta de terceiro é `app/trafego/escopo.py`, com 403, inclusive em
 * `/provar` e `/subir` — onde `customer_id` viaja no corpo e nenhuma tela
 * alcança. Se este arquivo sumir amanhã, o limite continua de pé.
 */
import { useCallback, useEffect, useState } from 'react';

import { pautadorApi } from '@/lib/pautadorApi';
import { useToast } from '@/hooks/use-toast';
import type { EscopoDeContas, EstadoDaTrava, ProjetoComConta } from '@/types/trafego';

export function useContasGoogleAds() {
  const { toast } = useToast();
  const [escopo, setEscopo] = useState<EscopoDeContas | null>(null);
  const [projetos, setProjetos] = useState<ProjetoComConta[]>([]);
  const [trava, setTrava] = useState<EstadoDaTrava | null>(null);
  // ⚠️ TRÊS estados, não dois. `trava === null` era a mesma coisa para "ainda
  // não perguntei" e para "perguntei e a resposta não veio", e o painel
  // renderizava o selo com `{trava && …}` — a falha de leitura sumia o selo, e
  // um cartão sem selo é indistinguível de um cartão saudável.
  const [travaLida, setTravaLida] = useState<'nao_coletado' | 'com_dados' | 'falhou'>(
    'nao_coletado',
  );
  const [carregando, setCarregando] = useState(true);
  const [salvando, setSalvando] = useState<number | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const carregar = useCallback(async () => {
    setCarregando(true);
    try {
      // `/escopo` faz duas chamadas à API do Google por dentro (~2,3 s medido
      // em 18/08/2026). As três em paralelo para a tela não somar as esperas.
      const [e, p, t] = await Promise.all([
        pautadorApi.escopoDeContas(),
        pautadorApi.projetosComConta(),
        // A falha da trava não derruba a tela inteira — as contas continuam
        // legíveis —, mas ela é REGISTRADA, e quem renderiza tem de dizê-la.
        pautadorApi.estadoDaTrava().then(
          (v) => ({ ok: true as const, v }),
          () => ({ ok: false as const, v: null }),
        ),
      ]);
      setEscopo(e);
      setProjetos(p.projetos);
      setTrava(t.v);
      setTravaLida(t.ok ? 'com_dados' : 'falhou');
      setErro(null);
    } catch (e) {
      setErro(e instanceof Error ? e.message : 'Falhei ao ler as contas.');
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    void carregar();
  }, [carregar]);

  const vincular = useCallback(
    async (projectId: number, customerId: string) => {
      if (!escopo) return false;
      setSalvando(projectId);
      try {
        await pautadorApi.vincularConta(projectId, customerId, escopo.mcc);
        // Relê em vez de remendar o estado local: o servidor normaliza os ids
        // (o painel do Google mostra `801-785-1692`) e é o que ele gravou que
        // o cockpit vai ler depois.
        await carregar();
        return true;
      } catch (e) {
        toast({
          variant: 'destructive',
          title: 'Não foi possível vincular',
          description: e instanceof Error ? e.message : 'Erro desconhecido.',
        });
        return false;
      } finally {
        setSalvando(null);
      }
    },
    [escopo, carregar, toast],
  );

  const desvincular = useCallback(
    async (projectId: number) => {
      setSalvando(projectId);
      try {
        await pautadorApi.desvincularConta(projectId);
        await carregar();
        return true;
      } catch (e) {
        toast({
          variant: 'destructive',
          title: 'Não foi possível desvincular',
          description: e instanceof Error ? e.message : 'Erro desconhecido.',
        });
        return false;
      } finally {
        setSalvando(null);
      }
    },
    [carregar, toast],
  );

  return {
    escopo, projetos, trava, travaLida,
    carregando, salvando, erro, carregar, vincular, desvincular,
  };
}
