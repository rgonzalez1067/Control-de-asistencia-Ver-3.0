import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Download, X, Smartphone } from "lucide-react";

const DISMISSED_KEY = "megasoft.pwa.dismissed";

/** Prompt discreto para instalar la PWA. Aparece cuando el navegador dispara
 * `beforeinstallprompt` y el usuario no lo cerró antes. */
export default function InstallPWAPrompt() {
  const [deferred, setDeferred] = useState(null);
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (localStorage.getItem(DISMISSED_KEY) === "1") return;
    // ya instalada
    if (window.matchMedia?.("(display-mode: standalone)").matches) return;

    function onPrompt(e) {
      e.preventDefault();
      setDeferred(e);
      setShow(true);
    }
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", () => setShow(false));
    return () => window.removeEventListener("beforeinstallprompt", onPrompt);
  }, []);

  if (!show || !deferred) return null;

  async function install() {
    try {
      deferred.prompt();
      const choice = await deferred.userChoice;
      if (choice?.outcome === "accepted") {
        setShow(false);
      }
    } catch (_) { /* noop */ }
  }

  function dismiss() {
    localStorage.setItem(DISMISSED_KEY, "1");
    setShow(false);
  }

  return (
    <div
      data-testid="pwa-install-prompt"
      className="fixed bottom-4 right-4 z-40 max-w-sm rounded-2xl border border-primary/20 bg-card/95 backdrop-blur shadow-2xl px-4 py-3 pr-3 flex items-start gap-3 animate-in slide-in-from-bottom-4"
    >
      <div className="h-10 w-10 rounded-xl bg-primary text-primary-foreground grid place-items-center shrink-0">
        <Smartphone className="h-5 w-5 text-accent" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-foreground">Instala MegaSoft</p>
        <p className="text-xs text-muted-foreground mt-0.5">
          Añádela a tu inicio para abrirla como app y marcar más rápido.
        </p>
        <div className="mt-2 flex gap-2">
          <Button size="sm" onClick={install}
            className="rounded-full h-8 bg-primary hover:bg-primary/90 text-primary-foreground"
            data-testid="pwa-install-btn">
            <Download className="h-3.5 w-3.5 mr-1" /> Instalar
          </Button>
          <Button size="sm" variant="ghost" onClick={dismiss} className="rounded-full h-8" data-testid="pwa-dismiss-btn">
            Ahora no
          </Button>
        </div>
      </div>
      <button
        onClick={dismiss}
        aria-label="Cerrar"
        className="text-muted-foreground hover:text-primary transition-colors"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}
