/**
 * A completude dos canais visuais — os booleanos que a projeção das paradas
 * lê (`FatosDaBancada.multicanal`).
 *
 * Moraram dentro de `NovaCampanhaPage.tsx` até 08/10/2026; regra de negócio
 * dentro de componente é o que o CLAUDE.md proíbe, e o formato de vídeo de
 * Demand Gen mudou a régua do kit (exatamente um logo quadrado, nada mais), o
 * que exigia testá-la fora da página.
 *
 * ⚠️ Cada booleano é calculado dos MESMOS campos que compõem o pedido. Não é
 * um segundo contrato: é "o operador já preencheu o que o pedido carrega?".
 */
import type { AssetDemandGen, CopyGerada } from '@/types/trafego';
import type { FormDemandGen } from './formularios';
import { linhas, numeroDoTexto } from './montagem';

export interface CompletudeMulticanal {
  displayCriativo: boolean;
  displayEconomia: boolean;
  demandSuperficies: boolean;
  demandAudiencia: boolean;
  demandKit: boolean;
  demandMensagem: boolean;
  demandEconomia: boolean;
  pmaxObjetivo: boolean;
  pmaxAssetGroup: boolean;
  pmaxSinais: boolean;
  pmaxMarca: boolean;
  pmaxEconomia: boolean;
}

export interface EntradaDaCompletude {
  orcamento: number | null;
  copyDisplay: CopyGerada;
  assetsDisplay: AssetDemandGen[];
  displayTcpa: string;
  copyDemand: CopyGerada;
  assetsDemand: AssetDemandGen[];
  formDemand: FormDemandGen;
  demandEstrategiaCanais: string | null;
  demandCanaisSelecionados: string[];
  demandUpgradedTargeting: boolean | null;
  demandAudienciasConfirmadas: boolean;
  temMetaPrimaria: boolean;
  pmaxNomeAssetGroup: string;
  pmaxTitulos: string;
  pmaxTitulosLongos: string;
  pmaxDescricoes: string;
  pmaxNomeEmpresa: string;
  assetsPMax: AssetDemandGen[];
  pmaxSinaisConfirmados: boolean;
  pmaxNegativasConfirmadas: boolean;
  pmaxBrandGuidelines: boolean | null;
  pmaxMeta: string;
}

const valido = (itens: string[], min: number, max: number, chars: number) =>
  itens.length >= min && itens.length <= max && itens.every((item) => item.length <= chars);

const metaOpcionalValida = (bruto: string) => bruto.trim() === '' || (numeroDoTexto(bruto) ?? 0) > 0;

export function completudeMulticanal(e: EntradaDaCompletude): CompletudeMulticanal {
  const orcamentoOk = e.orcamento != null && e.orcamento > 0;
  const demandSelecionadosOk = e.demandEstrategiaCanais !== 'SELECTED_CHANNELS'
    || e.demandCanaisSelecionados.length > 0;
  const pmaxTitulos = linhas(e.pmaxTitulos);
  const pmaxLongos = linhas(e.pmaxTitulosLongos);
  const pmaxDescricoes = linhas(e.pmaxDescricoes);
  const formato = e.formDemand.formato;
  // Vídeo e carrossel têm régua própria, dita com as palavras certas em
  // `faltasDeDemandGen`; aqui o kit de imagens só vale para multi-asset.
  const kitMultiAsset = e.assetsDemand.some((a) => a.tipo.startsWith('imagem_marketing'))
    && e.assetsDemand.some((a) => a.tipo === 'logo_quadrado');
  return {
    displayCriativo:
      valido(e.copyDisplay.headlines, 1, 5, 30)
      && valido(e.copyDisplay.descriptions, 1, 5, 90)
      && Boolean(e.copyDisplay.long_headlines?.[0])
      && (e.copyDisplay.long_headlines?.[0]?.length ?? 0) <= 90
      && Boolean(e.copyDisplay.business_name) && (e.copyDisplay.business_name?.length ?? 0) <= 25
      && e.assetsDisplay.some((a) => a.tipo === 'imagem_marketing')
      && e.assetsDisplay.some((a) => a.tipo === 'imagem_marketing_quadrada'),
    displayEconomia: orcamentoOk && metaOpcionalValida(e.displayTcpa),
    demandSuperficies: Boolean(e.demandEstrategiaCanais) && demandSelecionadosOk,
    demandAudiencia: e.demandUpgradedTargeting != null && e.demandAudienciasConfirmadas,
    demandKit: formato === 'MULTI_ASSET' ? kitMultiAsset : true,
    demandMensagem: valido(e.copyDemand.headlines, 1, 5, 30)
      && valido(e.copyDemand.descriptions, 1, 5, 90)
      && Boolean(e.copyDemand.business_name) && (e.copyDemand.business_name?.length ?? 0) <= 25,
    demandEconomia: orcamentoOk,
    pmaxObjetivo: e.temMetaPrimaria,
    pmaxAssetGroup: e.pmaxNomeAssetGroup.length <= 128
      && valido(pmaxTitulos, 3, 15, 30)
      && valido(pmaxLongos, 1, 5, 90)
      && valido(pmaxDescricoes, 2, 5, 90)
      && pmaxDescricoes.some((item) => item.length <= 60)
      && Boolean(e.pmaxNomeEmpresa.trim()) && e.pmaxNomeEmpresa.trim().length <= 25
      && e.assetsPMax.some((a) => a.tipo === 'imagem_marketing')
      && e.assetsPMax.some((a) => a.tipo === 'imagem_marketing_quadrada')
      && e.assetsPMax.some((a) => a.tipo === 'logo_quadrado'),
    pmaxSinais: e.pmaxSinaisConfirmados && e.pmaxNegativasConfirmadas,
    pmaxMarca: e.pmaxBrandGuidelines != null,
    pmaxEconomia: orcamentoOk && metaOpcionalValida(e.pmaxMeta),
  };
}
