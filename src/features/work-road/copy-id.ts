export async function copyText(value: string): Promise<boolean> {
  try {
    if (navigator?.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return true;
    }
  } catch {
    /* plano B */
  }
  try {
    if (typeof document === "undefined" || typeof document.execCommand !== "function") {
      return false;
    }
    const box = document.createElement("textarea");
    box.value = value;
    box.setAttribute("aria-hidden", "true");
    box.style.position = "fixed";
    box.style.opacity = "0";
    box.style.pointerEvents = "none";
    document.body.appendChild(box);
    box.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(box);
    return ok;
  } catch {
    return false;
  }
}
