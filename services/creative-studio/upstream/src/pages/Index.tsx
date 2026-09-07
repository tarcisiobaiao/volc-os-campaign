import { useState, useCallback, useRef, useEffect } from "react";
import { Zap } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import ContentTypeSelector from "@/components/ContentTypeSelector";
import type { ContentType } from "@/components/ContentTypeSelector";
import FormatSelector from "@/components/FormatSelector";
import CampaignInput from "@/components/CampaignInput";
import QuantitySlider from "@/components/QuantitySlider";
import LoadingScreen from "@/components/LoadingScreen";
import type { LoadPhase, SlotState, SlotStatus } from "@/components/LoadingScreen";
import ResultScreen from "@/components/ResultScreen";
import ErrorScreen from "@/components/ErrorScreen";
import SettingsModal from "@/components/SettingsModal";
import {
  streamCreatives,
  generateCreatives,
  isStreamingSupported,
  isWebhookConfigured,
  isConfigSupported,
  getConfig,
  dataUrlToBlob,
  buildZip,
} from "@/lib/api";
import type { GeneratedImage } from "@/lib/api";

type AppState = "form" | "loading" | "results" | "error";

const APROVA_LOGO = {
  data: "",
  mimeType: "image/png",
  variant: "aprova-main" as const,
  assetLabel: "Aprova Concursos — marca principal",
};

const FIXED_RATIOS: Record<ContentType, { ratio: string; id: string; label: string; dimensions: string } | null> = {
  "meta-ads": null,
  "news": { ratio: "4:5", id: "feed-1080x1350", label: "Feed Instagram", dimensions: "1080x1350" },
  "pinterest": { ratio: "9:16", id: "story-1080x1920", label: "Stories / Reels", dimensions: "1080x1920" },
};

const Index = () => {
  const [state, setState] = useState<AppState>("form");
  const [contentType, setContentType] = useState<ContentType>("meta-ads");
  const [formatId, setFormatId] = useState("feed-1080x1350");
  const [formatRatio, setFormatRatio] = useState("4:5");
  const [formatLabel, setFormatLabel] = useState("Feed Instagram");
  const [formatDimensions, setFormatDimensions] = useState("1080x1350");
  const [objective, setObjective] = useState("");
  const [quantity, setQuantity] = useState(4);

  // ── Real-time generation state ───────────────────────
  const [phase, setPhase] = useState<LoadPhase>("research");
  const [slots, setSlots] = useState<SlotState[]>([]);
  const [error, setError] = useState<{ code: string; message: string } | null>(null);
  const [resultImages, setResultImages] = useState<GeneratedImage[]>([]);
  const [resultZip, setResultZip] = useState<Blob | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  // n -> {name, blob, url} collected from the stream; source for the client-side zip.
  const collectedRef = useRef<Map<number, { name: string; blob: Blob; url: string }>>(
    new Map()
  );

  // Preflight: notify if the OpenAI key isn't configured yet (so they fix it before generating).
  useEffect(() => {
    if (!isConfigSupported()) return;
    getConfig()
      .then((cfg) => {
        if (!cfg.openai.configured) {
          toast.warning(
            "Nenhuma chave OpenAI configurada — abra as configurações (⚙) para adicionar."
          );
        }
      })
      .catch(() => {
        /* backend offline / unreachable — stay quiet */
      });
  }, []);

  const handleContentTypeChange = useCallback((type: ContentType) => {
    setContentType(type);
    setObjective("");
    const fixed = FIXED_RATIOS[type];
    if (fixed) {
      setFormatId(fixed.id);
      setFormatRatio(fixed.ratio);
      setFormatLabel(fixed.label);
      setFormatDimensions(fixed.dimensions);
    }
  }, []);

  const handleFormatSelect = useCallback(
    (id: string, ratio: string, label: string, dimensions: string) => {
      setFormatId(id);
      setFormatRatio(ratio);
      setFormatLabel(label);
      setFormatDimensions(dimensions);
    },
    []
  );

  const activeRatio = FIXED_RATIOS[contentType]?.ratio ?? formatRatio;
  const activeLabel = FIXED_RATIOS[contentType]?.label ?? formatLabel;
  const activeDimensions = FIXED_RATIOS[contentType]?.dimensions ?? formatDimensions;

  const revokeCollected = useCallback(() => {
    collectedRef.current.forEach((v) => URL.revokeObjectURL(v.url));
    collectedRef.current.clear();
  }, []);

  const setSlot = useCallback((n: number, next: SlotState) => {
    setSlots((prev) => prev.map((s, i) => (i === n - 1 ? next : s)));
  }, []);

  const handleGenerate = useCallback(async () => {
    // Reset for a fresh run.
    revokeCollected();
    setError(null);
    setPhase("research");
    setSlots(Array.from({ length: quantity }, () => ({ status: "pending" as SlotStatus })));
    setResultImages([]);
    setResultZip(null);
    setState("loading");

    if (!isWebhookConfigured()) {
      toast.warning("Backend não configurado. Defina VITE_API_URL no .env");
    }

    const controller = new AbortController();
    abortRef.current = controller;

    const request = {
      aspect_ratio: activeRatio,
      dimensions: activeDimensions,
      objective,
      quantity,
      logo: APROVA_LOGO,
      content_type: contentType,
    };

    try {
      if (isStreamingSupported()) {
        await streamCreatives(
          request,
          {
            onPhase: (p) => {
              if (p === "research" || p === "blueprints" || p === "packaging") {
                setPhase(p);
              }
            },
            onImageStart: (n) => {
              setPhase("images");
              setSlot(n, { status: "active" });
            },
            onImageDone: async (img) => {
              const blob = await dataUrlToBlob(img.dataUrl);
              const url = URL.createObjectURL(blob);
              collectedRef.current.set(img.n, { name: img.name, blob, url });
              setSlot(img.n, { status: "done", url });
            },
            onImageFailed: (info) => {
              setSlot(info.n, { status: "failed" });
            },
            onDone: async () => {
              setPhase("done");
              const entries = [...collectedRef.current.entries()].sort(
                (a, b) => a[0] - b[0]
              );
              const images = entries.map(([, v]) => ({ name: v.name, url: v.url }));
              const zip = await buildZip(
                entries.map(([, v]) => ({ name: v.name, blob: v.blob }))
              );
              setResultImages(images);
              setResultZip(zip);
              setTimeout(() => setState("results"), 700);
            },
            onError: (err) => {
              revokeCollected();
              toast.error(err.message);
              setError(err);
              setState("error");
            },
          },
          controller.signal
        );
      } else {
        // Fallback (e.g. n8n webhook): single-shot, no real per-image progress.
        setPhase("images");
        setSlots((prev) => prev.map(() => ({ status: "active" })));
        const { images, zipBlob } = await generateCreatives(request, controller.signal);
        setResultImages(images);
        setResultZip(zipBlob);
        setPhase("done");
        setTimeout(() => setState("results"), 500);
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        revokeCollected();
        toast.info("Geração cancelada.");
        setState("form");
        return;
      }
      console.error("Generate error:", err);
      revokeCollected();
      const message = err instanceof Error ? err.message : "Erro ao gerar criativos.";
      toast.error(message);
      setError({ code: "error", message });
      setState("error");
    } finally {
      abortRef.current = null;
    }
  }, [activeRatio, activeDimensions, objective, quantity, contentType, revokeCollected, setSlot]);

  const handleBack = useCallback(() => {
    resultImages.forEach((img) => URL.revokeObjectURL(img.url));
    collectedRef.current.clear();
    setResultImages([]);
    setResultZip(null);
    setState("form");
  }, [resultImages]);

  const handleErrorBack = useCallback(() => {
    setError(null);
    setState("form");
  }, []);

  const canGenerate = objective.trim().length > 0;

  // ── Loading ──────────────────────────────────────

  if (state === "loading") {
    return (
      <div className="min-h-screen bg-background relative">
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          <div className="absolute top-1/4 left-1/3 w-[500px] h-[500px] bg-primary/[0.04] rounded-full blur-3xl animate-pulse" />
          <div className="absolute bottom-1/4 right-1/4 w-[400px] h-[400px] bg-accent/[0.04] rounded-full blur-3xl animate-pulse" />
        </div>
        <div className="relative max-w-2xl mx-auto px-4 py-12">
          <LoadingScreen total={quantity} phase={phase} slots={slots} />
        </div>
      </div>
    );
  }

  // ── Error ────────────────────────────────────────

  if (state === "error" && error) {
    return (
      <div className="min-h-screen bg-background">
        <div className="max-w-2xl mx-auto px-4 py-12">
          <ErrorScreen
            code={error.code}
            message={error.message}
            onRetry={handleGenerate}
            onBack={handleErrorBack}
          />
        </div>
      </div>
    );
  }

  // ── Results ──────────────────────────────────────

  if (state === "results") {
    return (
      <div className="min-h-screen bg-background">
        <div className="max-w-3xl mx-auto px-4 py-12">
          <ResultScreen
            images={resultImages}
            zipBlob={resultZip}
            aspectRatio={activeRatio}
            onBack={handleBack}
          />
        </div>
      </div>
    );
  }

  // ── Form ─────────────────────────────────────────

  return (
    <div className="min-h-screen bg-background relative">
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute -top-20 left-1/4 w-[600px] h-[400px] bg-primary/[0.05] rounded-full blur-3xl" />
        <div className="absolute top-1/2 right-0 w-[400px] h-[400px] bg-accent/[0.05] rounded-full blur-3xl" />
      </div>

      <div className="relative max-w-2xl mx-auto px-4 py-12 space-y-10">
        <div className="absolute top-4 right-4 z-10">
          <SettingsModal />
        </div>
        <div className="flex justify-center animate-float-up">
          <img
            src="/aprova-logo.png"
            alt="Aprova Concursos"
            className="h-20 md:h-24 object-contain"
          />
        </div>

        <div className="space-y-6">
          {/* Tipo de postagem */}
          <section
            className="glass-card-elevated p-6 animate-float-up"
            style={{ animationDelay: "50ms" }}
          >
            <ContentTypeSelector selected={contentType} onSelect={handleContentTypeChange} />
          </section>

          {/* Formato — só para Meta Ads */}
          {contentType === "meta-ads" && (
            <section
              className="glass-card-elevated p-6 animate-float-up"
              style={{ animationDelay: "100ms" }}
            >
              <FormatSelector selected={formatId} onSelect={handleFormatSelect} />
            </section>
          )}

          {/* Objetivo / Contexto / Ideia */}
          <section
            className="glass-card-elevated p-6 animate-float-up"
            style={{ animationDelay: "150ms" }}
          >
            <CampaignInput
              value={objective}
              onChange={setObjective}
              contentType={contentType}
            />
          </section>

          {/* Quantidade */}
          <section
            className="glass-card-elevated p-6 animate-float-up"
            style={{ animationDelay: "200ms" }}
          >
            <QuantitySlider value={quantity} onChange={setQuantity} />
          </section>

          <div
            className="flex justify-center pt-4 animate-float-up"
            style={{ animationDelay: "250ms" }}
          >
            <Button
              onClick={handleGenerate}
              disabled={!canGenerate}
              size="lg"
              className="gap-2.5 px-12 py-6 text-base font-bold rounded-2xl shadow-xl shadow-primary/20 hover:shadow-2xl hover:shadow-primary/30 hover:scale-[1.02] active:scale-[0.98] transition-all duration-300 disabled:opacity-30 disabled:shadow-none disabled:scale-100"
            >
              <Zap className="w-5 h-5" />
              Gerar Criativos
            </Button>
          </div>

          {canGenerate && (
            <p className="text-center text-xs text-muted-foreground/60 animate-fade-in">
              {quantity} {quantity === 1 ? "criativo" : "criativos"} ·{" "}
              {activeLabel} · {activeDimensions.replace("x", "×")}
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

export default Index;
