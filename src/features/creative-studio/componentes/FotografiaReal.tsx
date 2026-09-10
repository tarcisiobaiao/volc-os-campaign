/**
 * A fotografia real do operador — opcional, e opcional de verdade.
 *
 * ## O que esta tela promete, e o que ela se recusa a prometer
 *
 * O modo híbrido cola os PIXELS da fotografia na peça: o modelo compõe o
 * entorno e um compositor determinístico junta os dois. Isso é verificável, e o
 * texto abaixo pode afirmá-lo.
 *
 * O modo "Reinterpretar com IA" manda a foto como referência e o modelo
 * redesenha a cena. Semelhança, rosto e detalhes MUDAM. Ele existe porque às
 * vezes é o que se quer, mas não é o padrão e o texto não finge que preserva
 * nada.
 *
 * ## Por que a prévia não é a fotografia enviada
 *
 * A prévia usa `URL.createObjectURL` sobre o arquivo LOCAL, e o URL é revogado
 * quando o componente desmonta. O que o servidor guardou é uma versão
 * normalizada — EXIF removido, orientação aplicada — e a tela diz isso em vez
 * de sugerir que os dois arquivos são o mesmo.
 */
import { useEffect, useRef, useState } from 'react';
import { AlertCircle, Camera, Image as IconeImagem, Loader2, X } from 'lucide-react';

import { Button } from '@/components/ui/button';

import type { Anexo, ModoDeComposicao } from '../tipos';

export interface FotografiaRealProps {
  anexo: Anexo | null;
  modos: readonly ModoDeComposicao[];
  modo: string;
  enviando: boolean;
  erro?: string | null;
  onEnviar: (arquivo: File) => void;
  onRemover: () => void;
  onModo: (id: string) => void;
}

function tamanho(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function FotografiaReal({
  anexo,
  modos,
  modo,
  enviando,
  erro,
  onEnviar,
  onRemover,
  onModo,
}: FotografiaRealProps) {
  const entrada = useRef<HTMLInputElement>(null);
  const [previa, setPrevia] = useState<string | null>(null);

  // O objeto de URL é revogado no desmonte e a cada troca: sem isso, cada
  // arquivo escolhido deixa um blob vivo até a aba fechar.
  useEffect(() => () => { if (previa) URL.revokeObjectURL(previa); }, [previa]);
  useEffect(() => {
    if (!anexo && previa) {
      URL.revokeObjectURL(previa);
      setPrevia(null);
    }
  }, [anexo, previa]);

  function escolher(arquivo: File | undefined) {
    if (!arquivo) return;
    if (previa) URL.revokeObjectURL(previa);
    setPrevia(URL.createObjectURL(arquivo));
    onEnviar(arquivo);
  }

  const comFoto = Boolean(anexo);
  const modosComFoto = modos.filter((m) => m.id !== 'sem_foto');

  return (
    <section className="studio-surface">
      <div className="studio-section-label">
        <Camera aria-hidden className="h-4 w-4" />
        <h2>Imagem de referência ou fotografia</h2>
        <span className="ml-auto normal-case tracking-normal text-muted-foreground">
          opcional
        </span>
      </div>

      <p className="mt-3 max-w-[70ch] text-sm text-muted-foreground">
        Tem um criativo que quer usar como inspiração? Envie a imagem e escolha
        como usá-la. Você também pode preservar uma fotografia na arte final.
        Sem anexo, o briefing é suficiente para gerar.
      </p>

      {!comFoto && (
        <div className="mt-4">
          <input
            ref={entrada}
            id="ac-fotografia"
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="sr-only"
            onChange={(e) => escolher(e.target.files?.[0])}
          />
          <Button
            type="button"
            variant="outline"
            disabled={enviando}
            onClick={() => entrada.current?.click()}
          >
            {enviando ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
            ) : (
              <IconeImagem className="h-4 w-4" aria-hidden />
            )}
            {enviando ? 'Enviando…' : 'Escolher imagem'}
          </Button>
          <p className="mt-2 max-w-[70ch] text-xs text-muted-foreground">
            PNG, JPEG ou WebP, até 25 MB e no mínimo 320 px no menor lado. Ao
            enviar, você declara que tem autorização para usar esta imagem. Os
            dados de câmera e localização são removidos no servidor.
          </p>
        </div>
      )}

      {erro && (
        <p
          role="alert"
          className="mt-4 flex items-start gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive"
        >
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          {erro}
        </p>
      )}

      {anexo && (
        <div className="mt-4 rounded-lg border border-border bg-muted/20 p-3">
          <div className="flex flex-wrap items-start gap-4">
            <div className="flex h-24 w-24 shrink-0 items-center justify-center overflow-hidden rounded-md border border-border bg-card">
              {previa ? (
                <img
                  src={previa}
                  alt="Prévia da fotografia escolhida"
                  className="h-full w-full object-cover"
                />
              ) : (
                <IconeImagem className="h-6 w-6 text-muted-foreground" aria-hidden />
              )}
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-foreground">
                Imagem recebida
              </p>
              <p className="mt-1 text-xs tabular-nums text-muted-foreground">
                {anexo.largura} × {anexo.altura} px · {tamanho(anexo.bytes_totais)}
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                {anexo.exif_removido
                  ? 'Dados de câmera e localização removidos.'
                  : 'A imagem não trazia dados de câmera.'}
              </p>
              <p className="mt-1 font-mono text-[11px] text-muted-foreground">
                {anexo.content_sha256.slice(0, 16)}…
              </p>
            </div>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={onRemover}
              aria-label="Remover a fotografia"
            >
              <X className="h-4 w-4" aria-hidden />
              Remover
            </Button>
          </div>

          <fieldset className="mt-4">
            <legend className="studio-field-label">Como usar esta imagem?</legend>
            {!modo && <p role="status" className="mt-2 text-sm text-primary">Escolha uma opção antes de conferir a geração. Nada foi selecionado automaticamente.</p>}
            <div className="mt-2 space-y-2">
              {modosComFoto.map((m) => (
                <label
                  key={m.id}
                  className="flex cursor-pointer items-start gap-3 rounded-md border border-border bg-card p-3"
                >
                  <input
                    type="radio"
                    name="modo-de-composicao"
                    className="mt-1 h-4 w-4 accent-primary"
                    checked={modo === m.id}
                    onChange={() => onModo(m.id)}
                  />
                  <span className="min-w-0">
                    <span className="block text-sm font-medium text-foreground">
                      {m.rotulo}
                    </span>
                    <span className="mt-0.5 block text-xs leading-relaxed text-muted-foreground">
                      {m.descricao}
                    </span>
                    {!m.preserva_pixels_da_foto && m.id !== 'referencia_visual' && (
                      <span className="mt-1 flex items-center gap-1.5 text-xs font-medium text-warning">
                        <AlertCircle className="h-3.5 w-3.5" aria-hidden />
                        A pessoa e os detalhes da foto podem mudar.
                      </span>
                    )}
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
        </div>
      )}
    </section>
  );
}
