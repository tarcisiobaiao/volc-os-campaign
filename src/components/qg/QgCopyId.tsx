import * as React from "react";
import { Check, Copy } from "lucide-react";
import { cn } from "@/lib/utils";
import { copyText } from "@/features/work-road/copy-id";

export function QgCopyId({
  value,
  className,
}: {
  value: string;
  className?: string;
}) {
  const [copied, setCopied] = React.useState(false);
  const [failed, setFailed] = React.useState(false);

  const onCopy = async () => {
    const ok = await copyText(value);
    setCopied(ok);
    setFailed(!ok);
    window.setTimeout(() => {
      setCopied(false);
      setFailed(false);
    }, 1800);
  };

  return (
    <button
      type="button"
      onClick={() => { void onCopy(); }}
      aria-label={`Copiar ID ${value}`}
      className={cn(
        "inline-flex min-h-10 items-center gap-2 rounded-md border border-input bg-background px-3 text-sm font-medium text-foreground",
        "transition-transform duration-150 ease-out active:scale-[0.96]",
        "hover:bg-muted/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
        "motion-reduce:transition-none motion-reduce:active:scale-100",
        className,
      )}
    >
      {copied ? <Check aria-hidden="true" className="h-4 w-4 text-success" /> : <Copy aria-hidden="true" className="h-4 w-4" />}
      {copied ? "ID copiado" : failed ? "Não copiou" : "Copiar ID"}
    </button>
  );
}
