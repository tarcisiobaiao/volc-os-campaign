import { useCallback, useState } from "react";
import { Upload, Check, X, ImageIcon } from "lucide-react";

interface LogoSelectorProps {
  selectedLogo: string | null;
  uploadedFile: File | null;
  onSelectPreset: (id: string) => void;
  onUpload: (file: File) => void;
  onClearUpload: () => void;
}

const presetLogos = [
  {
    id: "aprova-main",
    label: "Aprova Concursos",
    src: "/aprova-logo.png",
  },
];

export default function LogoSelector({ selectedLogo, uploadedFile, onSelectPreset, onUpload, onClearUpload }: LogoSelectorProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  const handleFile = useCallback((file: File) => {
    onUpload(file);
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
  }, [onUpload]);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith("image/")) handleFile(file);
  }, [handleFile]);

  const handleClear = () => {
    onClearUpload();
    setPreviewUrl(null);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <ImageIcon className="w-4 h-4 text-muted-foreground/70" />
        <h3 className="text-sm font-bold text-foreground/80 uppercase tracking-wider">Logo da Marca</h3>
      </div>

      <div className="flex gap-3 flex-wrap">
        {presetLogos.map((logo) => {
          const isActive = selectedLogo === logo.id && !uploadedFile;
          return (
            <button
              key={logo.id}
              onClick={() => onSelectPreset(logo.id)}
              className={`relative flex items-center gap-3 px-4 py-3 rounded-xl border transition-all duration-300 ${
                isActive
                  ? "border-primary bg-primary/[0.06] card-glow-selected"
                  : "border-border/60 bg-card/50 hover:border-primary/30 hover:shadow-md hover:bg-card"
              }`}
            >
              <div className="w-10 h-10 rounded-lg bg-white flex items-center justify-center p-1 shadow-sm border border-border/30">
                <img
                  src={logo.src}
                  alt={logo.label}
                  className="w-full h-full object-contain"
                />
              </div>
              <span className="text-sm font-medium text-foreground">{logo.label}</span>
              {isActive && (
                <Check className="w-4 h-4 text-primary" />
              )}
            </button>
          );
        })}
      </div>

      {/* Upload zone */}
      {uploadedFile && previewUrl ? (
        <div className="relative inline-flex items-center gap-3 p-3 rounded-xl border border-primary bg-primary/[0.06] card-glow-selected animate-scale-in">
          <img src={previewUrl} alt="Logo" className="w-10 h-10 object-contain rounded-lg bg-white p-0.5" />
          <span className="text-sm font-medium text-foreground">{uploadedFile.name}</span>
          <button
            onClick={handleClear}
            className="p-1.5 rounded-full hover:bg-destructive/10 transition-colors group"
          >
            <X className="w-4 h-4 text-muted-foreground group-hover:text-destructive transition-colors" />
          </button>
        </div>
      ) : (
        <div
          onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          className={`relative flex flex-col items-center justify-center gap-2.5 p-7 rounded-xl border-2 border-dashed transition-all duration-300 cursor-pointer ${
            isDragging
              ? "border-primary bg-primary/5 scale-[1.01]"
              : "border-border/40 hover:border-primary/30 hover:bg-muted/20"
          }`}
        >
          <div className="w-10 h-10 rounded-xl bg-muted/50 flex items-center justify-center">
            <Upload className="w-5 h-5 text-muted-foreground/60" />
          </div>
          <div className="text-center">
            <p className="text-sm text-muted-foreground font-medium">Arraste ou clique para enviar outro logo</p>
            <p className="text-xs text-muted-foreground/40 mt-0.5">PNG com fundo transparente recomendado</p>
          </div>
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="absolute inset-0 opacity-0 cursor-pointer"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleFile(file);
            }}
          />
        </div>
      )}
    </div>
  );
}
