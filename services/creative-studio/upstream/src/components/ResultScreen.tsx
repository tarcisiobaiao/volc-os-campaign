import { useState } from "react";
import { Download, Package, ZoomIn, X, Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { downloadBlob, downloadFromUrl } from "@/lib/api";
import type { GeneratedImage } from "@/lib/api";

interface ResultScreenProps {
  images: GeneratedImage[];
  zipBlob: Blob | null;
  aspectRatio: string;
  onBack: () => void;
}

export default function ResultScreen({
  images,
  zipBlob,
  aspectRatio,
  onBack,
}: ResultScreenProps) {
  const [lightbox, setLightbox] = useState<string | null>(null);

  const handleDownloadAll = () => {
    if (!zipBlob) return;
    const ts = new Date().toISOString().slice(0, 16).replace(/[T:]/g, "-");
    downloadBlob(zipBlob, `criativos-aprova-${ts}.zip`);
  };

  const handleDownloadOne = (img: GeneratedImage) => {
    downloadFromUrl(img.url, img.name);
  };

  const hasImages = images.length > 0;

  return (
    <div className="space-y-8 animate-float-up">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div />
        {zipBlob && zipBlob.size > 0 && (
          <Button
            onClick={handleDownloadAll}
            className="gap-2 rounded-xl shadow-lg shadow-primary/20 hover:shadow-xl hover:shadow-primary/30 hover:scale-[1.02] active:scale-[0.98] transition-all"
          >
            <Package className="w-4 h-4" />
            Baixar tudo (.zip)
          </Button>
        )}
      </div>

      {/* Hero */}
      <div className="text-center space-y-3">
        <img
          src="/aprova-logo.png"
          alt=""
          className="h-10 mx-auto object-contain opacity-50"
        />
        <div className="inline-flex items-center gap-3 px-5 py-2.5 rounded-2xl bg-primary/[0.06] border border-primary/15">
          <span className="text-3xl font-black text-primary tabular-nums">
            {hasImages ? images.length : "0"}
          </span>
          <div className="text-left">
            <p className="text-sm font-bold text-foreground leading-tight">
              {hasImages
                ? images.length === 1
                  ? "Criativo pronto"
                  : "Criativos prontos"
                : "Geração concluída"}
            </p>
            <p className="text-xs text-muted-foreground">Formato {aspectRatio}</p>
          </div>
        </div>
      </div>

      {/* Image grid */}
      {hasImages ? (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          {images.map((img, i) => (
            <div
              key={img.name}
              className="group relative rounded-2xl overflow-hidden border border-border/50 bg-card shadow-sm hover:shadow-xl hover:border-primary/20 transition-all duration-300 animate-scale-in"
              style={{ animationDelay: `${i * 70}ms` }}
            >
              <img
                src={img.url}
                alt={`Criativo ${i + 1}`}
                className="w-full aspect-[4/5] object-cover"
                loading="lazy"
              />

              {/* Number badge */}
              <div className="absolute top-2.5 left-2.5 w-7 h-7 rounded-lg bg-black/40 backdrop-blur-md flex items-center justify-center">
                <span className="text-[11px] font-bold text-white tabular-nums">
                  {i + 1}
                </span>
              </div>

              {/* Hover overlay */}
              <div className="absolute inset-0 bg-gradient-to-t from-black/50 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-all duration-300 flex items-end justify-center pb-4 gap-2">
                <button
                  onClick={() => setLightbox(img.url)}
                  className="p-2.5 rounded-xl bg-white/90 backdrop-blur-sm shadow-lg hover:bg-white transition-all scale-90 group-hover:scale-100"
                >
                  <ZoomIn className="w-4 h-4 text-foreground" />
                </button>
                <button
                  onClick={() => handleDownloadOne(img)}
                  className="p-2.5 rounded-xl bg-white/90 backdrop-blur-sm shadow-lg hover:bg-white transition-all scale-90 group-hover:scale-100"
                >
                  <Download className="w-4 h-4 text-foreground" />
                </button>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-center py-12 space-y-4">
          <p className="text-sm text-muted-foreground">
            {zipBlob && zipBlob.size > 0
              ? "Criativos gerados. Baixe o arquivo .zip para visualizar."
              : "Nenhum criativo retornado. Verifique a configuração do backend."}
          </p>
          {zipBlob && zipBlob.size > 0 && (
            <Button
              onClick={handleDownloadAll}
              size="lg"
              className="gap-2 rounded-2xl shadow-xl shadow-primary/20"
            >
              <Package className="w-5 h-5" />
              Baixar criativos (.zip)
            </Button>
          )}
        </div>
      )}

      {/* Gerar mais — botão principal */}
      <div className="pt-2 flex flex-col items-center gap-3">
        <Button
          onClick={onBack}
          size="lg"
          className="gap-2.5 px-12 py-6 text-base font-bold rounded-2xl shadow-xl shadow-primary/20 hover:shadow-2xl hover:shadow-primary/30 hover:scale-[1.02] active:scale-[0.98] transition-all duration-300 w-full max-w-sm"
        >
          <Zap className="w-5 h-5" />
          Gerar Mais Criativos
        </Button>
        <p className="text-xs text-muted-foreground/50">
          Volta ao início com formulário limpo
        </p>
      </div>

      {/* Lightbox */}
      {lightbox && (
        <div
          className="fixed inset-0 z-50 bg-black/85 backdrop-blur-md flex items-center justify-center p-6 animate-fade-in cursor-pointer"
          onClick={() => setLightbox(null)}
        >
          <button
            className="absolute top-5 right-5 p-2 rounded-full bg-white/10 hover:bg-white/20 transition-colors"
            onClick={() => setLightbox(null)}
          >
            <X className="w-5 h-5 text-white" />
          </button>
          <img
            src={lightbox}
            alt="Preview"
            className="max-w-full max-h-[90vh] object-contain rounded-2xl shadow-2xl animate-scale-in"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </div>
  );
}
