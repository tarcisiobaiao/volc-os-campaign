import { AlertTriangle, RotateCcw, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ErrorScreenProps {
  code: string;
  message: string;
  onRetry: () => void;
  onBack: () => void;
}

// Friendly hints per error code — actionable next step beyond the cause.
const HINTS: Record<string, string> = {
  insufficient_quota: "Adicione créditos em platform.openai.com → Billing.",
  invalid_api_key: "Atualize a OPENAI_API_KEY no backend/.env e reinicie o backend.",
  rate_limit: "Aguarde alguns segundos antes de tentar de novo.",
  no_access: "Verifique o projeto/organização da chave na OpenAI.",
  content_policy: "Reescreva o objetivo evitando termos sensíveis.",
  connection: "Confira sua conexão com a internet.",
};

export default function ErrorScreen({
  code,
  message,
  onRetry,
  onBack,
}: ErrorScreenProps) {
  const hint = HINTS[code];

  return (
    <div className="flex flex-col items-center justify-center min-h-[80vh] px-4 animate-float-up">
      <div className="glass-card-elevated p-8 w-full max-w-md space-y-6 text-center">
        <div className="mx-auto w-16 h-16 rounded-2xl bg-destructive/10 border border-destructive/20 flex items-center justify-center">
          <AlertTriangle className="w-8 h-8 text-destructive" />
        </div>

        <div className="space-y-2">
          <h2 className="text-lg font-bold text-foreground">
            Não foi possível gerar os criativos
          </h2>
          <p className="text-sm text-muted-foreground leading-relaxed">{message}</p>
          {hint && (
            <p className="text-xs text-muted-foreground/70 leading-relaxed">{hint}</p>
          )}
          {code && (
            <p className="text-[10px] font-mono text-muted-foreground/40 pt-1">
              código: {code}
            </p>
          )}
        </div>

        <div className="flex flex-col gap-2 pt-1">
          <Button
            onClick={onRetry}
            className="w-full h-11 gap-2 rounded-xl font-semibold shadow-lg shadow-primary/20 hover:shadow-xl hover:shadow-primary/25 transition-all"
          >
            <RotateCcw className="w-4 h-4" />
            Tentar novamente
          </Button>
          <Button
            onClick={onBack}
            variant="ghost"
            className="w-full h-11 gap-2 rounded-xl font-medium text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft className="w-4 h-4" />
            Voltar ao formulário
          </Button>
        </div>
      </div>
    </div>
  );
}
