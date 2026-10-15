import { type IconSvgElement } from "@hugeicons/react";
import { ICONES } from "@/lib/icones";

/**
 * O mapa de destinos do shell: um lugar só para o menu lateral e para a trilha
 * do cabeçalho.
 *
 * Antes, o menu era duas listas ("Principal" e "Configurações"), e "Principal"
 * misturava portfólio, produção e mídia. Os grupos agora seguem o fluxo do
 * PRODUCT.md §3 (ver o portfólio → operar mídia → produzir → configurar) e os
 * domínios que o Mapa Vivo já reconhece. Rotas, `href` e regras de papel são
 * as mesmas de antes: só a arrumação mudou.
 */
export interface Destino {
  title: string;
  href: string;
  icon: IconSvgElement;
  /** Vira dica (title) no menu. Não ocupa mais uma segunda linha em cada item. */
  description: string;
  adminOnly?: boolean;
}

export interface GrupoDeDestinos {
  id: string;
  titulo: string;
  itens: Destino[];
}

export const GRUPOS_DE_DESTINOS: GrupoDeDestinos[] = [
  {
    id: "visao",
    titulo: "Visão",
    itens: [
      { title: "Dashboard Geral", href: "/", icon: ICONES.visaoGeral, description: "Visão geral de todas as campanhas", adminOnly: true },
      { title: "Projetos", href: "/dashboard/projects", icon: ICONES.projetos, description: "Gerenciar projetos", adminOnly: true },
      { title: "Relatórios", href: "/reports", icon: ICONES.relatorios, description: "Relatórios e análises avançadas", adminOnly: true },
    ],
  },
  {
    id: "midia",
    titulo: "Mídia",
    itens: [
      // ⚠️ A descrição antiga dizia "Subir campanhas de Search no Google Ads" —
      // uma ação de um canal no rótulo de um Hub que responde três perguntas.
      { title: "Tráfego", href: "/trafego", icon: ICONES.trafego, description: "Campanhas, preparar e atenção", adminOnly: true },
      // Único destino sem `adminOnly`: é a sala do operador.
      { title: "Campanhas", href: "/settings/campaigns", icon: ICONES.campanhas, description: "Ver e configurar campanhas" },
    ],
  },
  {
    id: "producao",
    titulo: "Produção",
    itens: [
      { title: "Pautador Pro", href: "/pautador-pro", icon: ICONES.pautador, description: "Arbitragem de atenção por país", adminOnly: true },
      { title: "Redator", href: "/redator", icon: ICONES.redator, description: "O funil sendo escrito, etapa por etapa", adminOnly: true },
      // O Estúdio é área de PRODUÇÃO transversal (SPEC §6), não subaba de Tráfego.
      { title: "Criativos", href: "/criativos", icon: ICONES.criativos, description: "Estúdio Criativo, produção e aprovação", adminOnly: true },
      { title: "Incubadora", href: "/incubator", icon: ICONES.incubadora, description: "Pipeline de sites para AdSense", adminOnly: true },
    ],
  },
  {
    id: "sistema",
    titulo: "Sistema",
    itens: [
      { title: "Custos", href: "/settings/costs", icon: ICONES.custos, description: "Custos, impostos e divisão por mês", adminOnly: true },
      { title: "Integrações", href: "/settings/integrations", icon: ICONES.integracoes, description: "Google Ads, Meta Ads e Meta CAPI", adminOnly: true },
      { title: "Usuários", href: "/settings/users", icon: ICONES.usuarios, description: "Cadastros, acessos e comissões", adminOnly: true },
      { title: "Cofre de Ativos", href: "/settings/cofre-ativos", icon: ICONES.cofreDeAtivos, description: "Patrimônio, custódia e relações", adminOnly: true },
      { title: "QG Agêntico", href: "/settings/qg-agentico", icon: ICONES.qgAgentico, description: "Roadmap vivo e execução", adminOnly: true },
    ],
  },
];

/**
 * "Você está aqui" sobrevive à rota filha.
 *
 * O casamento é por SEGMENTO, não por prefixo de string: `/settings/costs` não
 * pode acender `/settings/co`, e `/` só casa com `/`.
 */
export const estaNaSecao = (pathname: string, href: string) => {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(href + "/");
};

/** Destinos que este papel enxerga, sem grupos vazios. */
export function gruposVisiveis(role: string | undefined): GrupoDeDestinos[] {
  return GRUPOS_DE_DESTINOS.map((g) => ({
    ...g,
    itens: g.itens.filter((d) => !d.adminOnly || role === "ADMIN"),
  })).filter((g) => g.itens.length > 0);
}

/**
 * Onde a rota atual mora no mapa, para a trilha do cabeçalho.
 *
 * `/settings/projects` é a mesma página de `/dashboard/projects` e mora no
 * mesmo lugar. Rota fora do mapa devolve `null`: a trilha some, em vez de
 * inventar um pai.
 */
export function localizar(pathname: string): { grupo: GrupoDeDestinos; destino: Destino; profundo: boolean } | null {
  const caminho = pathname === "/settings/projects" ? "/dashboard/projects" : pathname;
  for (const grupo of GRUPOS_DE_DESTINOS) {
    for (const destino of grupo.itens) {
      if (estaNaSecao(caminho, destino.href)) {
        return { grupo, destino, profundo: caminho !== destino.href };
      }
    }
  }
  return null;
}
