import { useState } from "react";
import { Settings, Loader2, Eye, EyeOff } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { getConfig, saveConfig, testConfig, type ConfigStatus, type KeyStatus } from "@/lib/api";

const SOURCE_LABEL: Record<KeyStatus["source"], string> = {
  runtime: "salva aqui",
  env: "do ambiente (.env / Vercel)",
  missing: "não configurada",
};

// Module-scope so the input keeps focus across keystrokes (an inner component
// would be a new type each render and remount the input).
function KeyField({
  id,
  label,
  value,
  onChange,
  info,
  placeholder,
  show,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  info?: KeyStatus;
  placeholder: string;
  show: boolean;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <Label htmlFor={id} className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          {label}
        </Label>
        {info && (
          <span
            className={`text-[10px] font-medium px-2 py-0.5 rounded-full truncate max-w-[60%] ${
              info.source === "missing"
                ? "bg-destructive/10 text-destructive"
                : "bg-primary/10 text-primary"
            }`}
          >
            {info.configured ? `${info.masked} · ${SOURCE_LABEL[info.source]}` : SOURCE_LABEL.missing}
          </span>
        )}
      </div>
      <Input
        id={id}
        type={show ? "text" : "password"}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoComplete="off"
        className="h-10 rounded-xl bg-muted/30 border-border/50 font-mono text-sm"
      />
    </div>
  );
}

export default function SettingsModal() {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<ConfigStatus | null>(null);
  const [openaiKey, setOpenaiKey] = useState("");
  const [geminiKey, setGeminiKey] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState<"" | "load" | "save" | "test">("");

  const refresh = async () => {
    setBusy("load");
    try {
      setStatus(await getConfig());
    } catch (e) {
      toast.error("Falha ao carregar configuração: " + (e instanceof Error ? e.message : ""));
    } finally {
      setBusy("");
    }
  };

  const onOpenChange = (o: boolean) => {
    setOpen(o);
    if (o) {
      setOpenaiKey("");
      setGeminiKey("");
      refresh();
    }
  };

  const buildUpdate = () => {
    const u: { openai_api_key?: string; gemini_api_key?: string } = {};
    if (openaiKey.trim()) u.openai_api_key = openaiKey.trim();
    if (geminiKey.trim()) u.gemini_api_key = geminiKey.trim();
    return u;
  };

  const handleTest = async () => {
    setBusy("test");
    try {
      const r = await testConfig(buildUpdate());
      (r.openai.ok ? toast.success : toast.error)("OpenAI — " + r.openai.message);
      (r.gemini.ok ? toast.success : toast.error)("Gemini — " + r.gemini.message);
    } catch (e) {
      toast.error("Falha no teste: " + (e instanceof Error ? e.message : ""));
    } finally {
      setBusy("");
    }
  };

  const handleSave = async () => {
    const u = buildUpdate();
    if (!Object.keys(u).length) {
      toast.info("Preencha ao menos uma chave para salvar.");
      return;
    }
    setBusy("save");
    try {
      setStatus(await saveConfig(u));
      setOpenaiKey("");
      setGeminiKey("");
      toast.success("Chaves salvas — o backend já está usando as novas.");
    } catch (e) {
      toast.error("Falha ao salvar: " + (e instanceof Error ? e.message : ""));
    } finally {
      setBusy("");
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="rounded-xl text-muted-foreground hover:text-foreground"
          title="Configurações (chaves de API)"
        >
          <Settings className="w-5 h-5" />
        </Button>
      </DialogTrigger>

      <DialogContent className="sm:max-w-md rounded-2xl">
        <DialogHeader>
          <DialogTitle>Chaves de API</DialogTitle>
          <DialogDescription>
            Cole uma nova chave para sobrescrever a do ambiente. Deixe em branco para manter a atual.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          <KeyField
            id="openai-key"
            label="OpenAI API Key"
            value={openaiKey}
            onChange={setOpenaiKey}
            info={status?.openai}
            placeholder="sk-..."
            show={show}
          />
          <KeyField
            id="gemini-key"
            label="Gemini API Key"
            value={geminiKey}
            onChange={setGeminiKey}
            info={status?.gemini}
            placeholder="AIza..."
            show={show}
          />

          <button
            type="button"
            onClick={() => setShow((s) => !s)}
            className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            {show ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
            {show ? "Ocultar chaves" : "Mostrar chaves"}
          </button>
        </div>

        <DialogFooter className="gap-2 sm:gap-2">
          <Button variant="outline" onClick={handleTest} disabled={busy !== ""} className="rounded-xl gap-2">
            {busy === "test" && <Loader2 className="w-4 h-4 animate-spin" />}
            Testar
          </Button>
          <Button onClick={handleSave} disabled={busy !== ""} className="rounded-xl gap-2">
            {busy === "save" && <Loader2 className="w-4 h-4 animate-spin" />}
            Salvar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
