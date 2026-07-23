import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Camera, Check, RefreshCw, X, Loader2 } from "lucide-react";
import { toast } from "sonner";

const FACEAPI_URL = "https://cdn.jsdelivr.net/npm/face-api.js@0.22.2/dist/face-api.min.js";
const MODELS_URL = "https://cdn.jsdelivr.net/gh/justadudewhohacks/face-api.js@master/weights";

function loadFaceApi() {
  if (window.faceapi) return Promise.resolve(window.faceapi);
  if (window.__faceApiLoading) return window.__faceApiLoading;
  window.__faceApiLoading = new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = FACEAPI_URL; s.async = true;
    s.onload = () => resolve(window.faceapi);
    s.onerror = () => reject(new Error("No se pudo cargar face-api.js"));
    document.head.appendChild(s);
  });
  return window.__faceApiLoading;
}

async function loadFaceModels(faceapi) {
  if (window.__faceModelsReady) return;
  await Promise.all([
    faceapi.nets.tinyFaceDetector.loadFromUri(MODELS_URL),
    faceapi.nets.faceLandmark68Net.loadFromUri(MODELS_URL),
    faceapi.nets.faceRecognitionNet.loadFromUri(MODELS_URL),
  ]);
  window.__faceModelsReady = true;
}

/**
 * Reusable selfie capture dialog. Opens getUserMedia, shows preview,
 * computes a face-api descriptor and returns (base64, descriptor[]) to the parent.
 *
 * Props:
 *   open, onOpenChange, title, description
 *   onConfirm(dataUrl, descriptor)  — called when user confirms the captured selfie
 *   saving                           — external saving flag (disables buttons)
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
  const [descriptor, setDescriptor] = useState(null);
  const [analyzing, setAnalyzing] = useState(false);

  useEffect(() => {
    if (!open) return;
    let stopped = false;
    setReady(false); setError(null); setPreview(null); setDescriptor(null);
    (async () => {
      try {
        // Kick off models loading in parallel with camera warm-up
        loadFaceApi().then((fa) => loadFaceModels(fa)).catch(() => null);
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

  async function capture() {
    const v = videoRef.current;
    if (!v) return;
    setAnalyzing(true);
    try {
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
      const dataUrl = c.toDataURL("image/jpeg", 0.85);

      // Compute face descriptor from the LIVE video (mejor detección que del canvas espejado)
      let desc = null;
      try {
        const faceapi = await loadFaceApi();
        await loadFaceModels(faceapi);
        const opts = new faceapi.TinyFaceDetectorOptions({ inputSize: 320, scoreThreshold: 0.5 });
        const det = await faceapi
          .detectSingleFace(v, opts)
          .withFaceLandmarks()
          .withFaceDescriptor();
        if (det?.descriptor) desc = Array.from(det.descriptor);
      } catch (e) {
        // ignore — permitimos guardar sólo la foto si el modelo no cargó
      }

      if (!desc) {
        toast.warning("No se detectó un rostro claro. Repite con mejor luz y de frente.");
      }
      setDescriptor(desc);
      setPreview(dataUrl);
    } finally {
      setAnalyzing(false);
    }
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
          {preview && (
            <div className={
              "absolute bottom-3 left-1/2 -translate-x-1/2 rounded-full px-3 py-1 text-[11px] font-medium backdrop-blur border " +
              (descriptor
                ? "bg-emerald-500/90 border-emerald-300/40 text-white"
                : "bg-amber-500/90 border-amber-300/40 text-white")
            } data-testid="selfie-descriptor-status">
              {descriptor ? "✓ Rostro detectado" : "⚠ Sin rostro claro — repetir"}
            </div>
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
              <Button onClick={capture} disabled={!ready || analyzing}
                className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground"
                data-testid="selfie-capture-btn">
                {analyzing
                  ? (<><Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> Analizando rostro…</>)
                  : (<><Camera className="h-4 w-4 mr-1.5" /> Capturar</>)}
              </Button>
            </>
          ) : (
            <>
              <Button variant="outline" onClick={() => { setPreview(null); setDescriptor(null); }} className="rounded-full" data-testid="selfie-retake">
                <RefreshCw className="h-4 w-4 mr-1.5" /> Repetir
              </Button>
              <Button onClick={() => onConfirm(preview, descriptor)} disabled={saving}
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
