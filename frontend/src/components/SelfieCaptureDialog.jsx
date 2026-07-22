import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Camera, Check, RefreshCw, X } from "lucide-react";

/**
 * Reusable selfie capture dialog. Opens getUserMedia, shows preview,
 * and returns a base64 JPEG to the parent via onConfirm(dataUrl).
 *
 * Props:
 *   open, onOpenChange, title, description
 *   onConfirm(dataUrl)  — called when user confirms the captured selfie
 *   saving              — external saving flag (disables buttons)
 */
export default function SelfieCaptureDialog({
  open, onOpenChange, title = "Registrar rostro",
  description = "Captura una foto frontal con buena luz.",
  onConfirm, saving = false,
}) {
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState(null);
  const [preview, setPreview] = useState(null);

  useEffect(() => {
    if (!open) return;
    let stopped = false;
    setReady(false); setError(null); setPreview(null);
    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 640 } },
          audio: false,
        });
        if (stopped) { stream.getTracks().forEach((t) => t.stop()); return; }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play().catch(() => null);
        }
        setReady(true);
      } catch (_) {
        setError("No pudimos acceder a la cámara. Autoriza el permiso o usa otro navegador.");
      }
    })();
    return () => {
      stopped = true;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    };
  }, [open]);

  function capture() {
    const v = videoRef.current;
    if (!v) return;
    const size = Math.min(v.videoWidth, v.videoHeight);
    const c = canvasRef.current;
    c.width = 480; c.height = 480;
    const ctx = c.getContext("2d");
    const sx = (v.videoWidth - size) / 2;
    const sy = (v.videoHeight - size) / 2;
    ctx.save();
    ctx.translate(c.width, 0); ctx.scale(-1, 1);
    ctx.drawImage(v, sx, sy, size, size, 0, 0, c.width, c.height);
    ctx.restore();
    setPreview(c.toDataURL("image/jpeg", 0.85));
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="selfie-capture-dialog">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        <div className="relative aspect-square w-full rounded-2xl overflow-hidden bg-primary/95 shadow-lg">
          {!preview && (
            <>
              <video ref={videoRef} muted playsInline
                     className="absolute inset-0 h-full w-full object-cover scale-x-[-1]"
                     data-testid="selfie-video" />
              <div className="pointer-events-none absolute inset-6 border-2 border-dashed border-accent/70 rounded-2xl" />
            </>
          )}
          {preview && (
            <img src={preview} alt="preview" className="absolute inset-0 h-full w-full object-cover"
                 data-testid="selfie-preview" />
          )}
          {!ready && !preview && (
            <div className="absolute inset-0 grid place-items-center text-white text-sm text-center px-6">
              {error
                ? <div><p className="text-red-200 font-medium">Cámara bloqueada</p>
                       <p className="text-xs text-white/70 mt-2">{error}</p></div>
                : "Iniciando cámara…"}
            </div>
          )}
        </div>
        <canvas ref={canvasRef} className="hidden" />

        <DialogFooter className="flex-row gap-2 sm:justify-center">
          {!preview ? (
            <>
              <Button variant="outline" onClick={() => onOpenChange(false)} className="rounded-full" data-testid="selfie-cancel">
                <X className="h-4 w-4 mr-1.5" /> Cancelar
              </Button>
              <Button onClick={capture} disabled={!ready}
                className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground"
                data-testid="selfie-capture-btn">
                <Camera className="h-4 w-4 mr-1.5" /> Capturar
              </Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={() => setPreview(null)} className="rounded-full" data-testid="selfie-retake">
                <RefreshCw className="h-4 w-4 mr-1.5" /> Repetir
              </Button>
              <Button onClick={() => onConfirm(preview)} disabled={saving}
                className="rounded-full bg-emerald-600 hover:bg-emerald-700 text-white"
                data-testid="selfie-confirm">
                <Check className="h-4 w-4 mr-1.5" /> {saving ? "Guardando…" : "Confirmar rostro"}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
