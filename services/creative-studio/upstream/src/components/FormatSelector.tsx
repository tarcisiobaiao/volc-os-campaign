import { useState, useMemo } from "react";
import { Monitor, Smartphone, Square, Columns2, Search } from "lucide-react";

interface Format {
  id: string;
  label: string;
  ratio: string;
  dimensions: string; // exact target pixels, e.g. "1080x1350"
  width: number;      // aspect width (for the preview shape)
  height: number;     // aspect height (for the preview shape)
  description: string;
}

type Category = "all" | "portrait" | "landscape" | "square";

// Tamanhos exatos suportados pelo gpt-image — cada card carrega o pixel de saída.
// Vários compartilham o mesmo aspect ratio (ex.: 1080x1920 e 2160x3840 = 9:16),
// por isso o que é propagado para o backend é a DIMENSÃO exata, não só o ratio.
const allFormats: Format[] = [
  { id: "post-1080x1080",  label: "Post Quadrado",   ratio: "1:1",    dimensions: "1080x1080", width: 1080, height: 1080, description: "Post quadrado, feed" },
  { id: "feed-1080x1350",  label: "Feed Instagram",  ratio: "4:5",    dimensions: "1080x1350", width: 1080, height: 1350, description: "Feed Instagram retrato 4:5" },
  { id: "story-1080x1920", label: "Stories / Reels", ratio: "9:16",   dimensions: "1080x1920", width: 1080, height: 1920, description: "Stories, Reels, TikTok 9:16" },
  { id: "yt-1920x1080",    label: "YouTube / Thumb", ratio: "16:9",   dimensions: "1920x1080", width: 1920, height: 1080, description: "YouTube, thumbnail 16:9" },
  { id: "ads-1200x628",    label: "Ads / Preview",   ratio: "1.91:1", dimensions: "1200x628",  width: 1200, height: 628,  description: "Ads, social link preview" },
  { id: "wide-1600x900",   label: "Widescreen",      ratio: "16:9",   dimensions: "1600x900",  width: 1600, height: 900,  description: "Widescreen, apresentação" },
  { id: "v4k-2160x3840",   label: "Vertical 4K",     ratio: "9:16",   dimensions: "2160x3840", width: 2160, height: 3840, description: "Vertical 4K 9:16" },
  { id: "h4k-3840x2160",   label: "Horizontal 4K",   ratio: "16:9",   dimensions: "3840x2160", width: 3840, height: 2160, description: "Horizontal 4K 16:9" },
];

const categories: { id: Category; label: string; icon: typeof Square }[] = [
  { id: "all",       label: "Todos",    icon: Columns2 },
  { id: "portrait",  label: "Vertical", icon: Smartphone },
  { id: "landscape", label: "Horizontal", icon: Monitor },
  { id: "square",    label: "Quadrado", icon: Square },
];

function getCategory(f: Format): Category {
  if (f.width === f.height) return "square";
  return f.width < f.height ? "portrait" : "landscape";
}

interface FormatSelectorProps {
  selected: string;
  onSelect: (id: string, ratio: string, label: string, dimensions: string) => void;
}

function FormatCard({
  format,
  isSelected,
  onClick,
  index,
}: {
  format: Format;
  isSelected: boolean;
  onClick: () => void;
  index: number;
}) {
  const maxDim = 44;
  const aspectW = format.width;
  const aspectH = format.height;
  const scale = Math.min(maxDim / aspectW, maxDim / aspectH);
  const w = Math.max(6, Math.round(aspectW * scale));
  const h = Math.max(6, Math.round(aspectH * scale));

  return (
    <button
      onClick={onClick}
      className="animate-scale-in"
      style={{ animationDelay: `${index * 30}ms` }}
    >
      <div
        className={`group relative flex flex-col items-center gap-2 p-3 rounded-xl border transition-all duration-300 cursor-pointer
          ${isSelected
            ? "border-primary bg-primary/[0.06] card-glow-selected"
            : "border-border/60 bg-card/50 hover:border-primary/40 hover:bg-card hover:shadow-md"
          }`}
      >
        {/* Shape preview */}
        <div className="flex items-center justify-center w-full" style={{ height: `${maxDim + 4}px` }}>
          <div
            className={`rounded-md border-2 transition-all duration-300
              ${isSelected
                ? "border-primary bg-gradient-to-br from-primary/20 to-primary/5"
                : "border-muted-foreground/15 bg-muted/40 group-hover:border-primary/30 group-hover:bg-primary/5"
              }`}
            style={{ width: `${w}px`, height: `${h}px` }}
          />
        </div>

        {/* Label */}
        <div className="text-center w-full min-w-0">
          <p className={`text-xs font-semibold truncate transition-colors ${isSelected ? "text-primary" : "text-foreground/80"}`}>
            {format.label}
          </p>
          <p className={`text-[10px] font-mono transition-colors ${isSelected ? "text-primary/80" : "text-muted-foreground/70"}`}>
            {format.dimensions.replace("x", "×")}
          </p>
          <p className={`text-[9px] font-mono transition-colors ${isSelected ? "text-primary/50" : "text-muted-foreground/45"}`}>
            {format.ratio}
          </p>
        </div>

        {/* Selected indicator */}
        {isSelected && (
          <div className="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-primary border-2 border-background animate-scale-in" />
        )}
      </div>
    </button>
  );
}

export default function FormatSelector({ selected, onSelect }: FormatSelectorProps) {
  const [activeCategory, setActiveCategory] = useState<Category>("all");
  const [search, setSearch] = useState("");

  const filteredFormats = useMemo(() => {
    return allFormats.filter((f) => {
      const matchCategory = activeCategory === "all" || getCategory(f) === activeCategory;
      const matchSearch =
        !search ||
        f.label.toLowerCase().includes(search.toLowerCase()) ||
        f.ratio.includes(search) ||
        f.description.toLowerCase().includes(search.toLowerCase());
      return matchCategory && matchSearch;
    });
  }, [activeCategory, search]);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-bold text-foreground/80 uppercase tracking-wider">
          Formato
        </h3>
        <span className="text-xs text-muted-foreground font-medium tabular-nums">
          {allFormats.length} formatos
        </span>
      </div>

      {/* Category tabs */}
      <div className="flex gap-1 p-1 bg-muted/50 rounded-xl">
        {categories.map((cat) => {
          const Icon = cat.icon;
          const isActive = activeCategory === cat.id;
          return (
            <button
              key={cat.id}
              onClick={() => setActiveCategory(cat.id)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 flex-1 justify-center
                ${isActive
                  ? "bg-card text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
                }`}
            >
              <Icon className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">{cat.label}</span>
            </button>
          );
        })}
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground/50" />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Buscar formato..."
          className="w-full pl-8 pr-3 py-2 rounded-xl bg-muted/30 border border-border/40 text-sm text-foreground placeholder:text-muted-foreground/40 focus:outline-none focus:border-primary/40 focus:ring-1 focus:ring-primary/10 transition-all"
        />
      </div>

      {/* Format grid */}
      <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 gap-2">
        {filteredFormats.map((f, i) => (
          <FormatCard
            key={f.id}
            format={f}
            isSelected={selected === f.id}
            onClick={() => onSelect(f.id, f.ratio, f.label, f.dimensions)}
            index={i}
          />
        ))}
      </div>

      {filteredFormats.length === 0 && (
        <div className="text-center py-6 text-sm text-muted-foreground">
          Nenhum formato encontrado
        </div>
      )}
    </div>
  );
}
