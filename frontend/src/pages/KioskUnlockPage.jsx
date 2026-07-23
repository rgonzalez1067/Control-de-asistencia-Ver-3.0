import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatApiErrorDetail } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { toast } from "sonner";
import {
  ScanFace, LockKeyhole, ArrowRight, ArrowLeft, KeyRound, Loader2, RefreshCw,
} from "lucide-react";

const KIOSK_KEY = "megasoft.kiosk.unlocked";
const FACEAPI_URL = "https://cdn.jsdelivr.net/npm/face-api.js@0.22.2/dist/face-api.min.js";
const MODELS_URL = "https://cdn.jsdelivr.net/gh/justadudewhohacks/face-api.js@master/weights";

export function isKioskUnlocked() {
  try { return sessionStorage.getItem(KIOSK_KEY) === "1"; }
  catch (_) { return false; }
}
export function setKioskUnlocked(v) {
  try {
    if (v) sessionStorage.setItem(KIOSK_KEY, "1");
    else sessionStorage.removeItem(KIOSK_KEY);
  } catch (_) { /* noop */ }
}

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

export default function KioskUnlockPage() {
  const nav = useNavigate();

  function handleSuccess(msg = "Kiosco desbloqueado") {
    setKioskUnlocked(true);
    toast.success(msg);
    nav("/kiosk/scan", { replace: true });
  }

  return (
    <div className="min-h-screen bg-primary text-primary-foreground grid place-items-center px-4 py-10 relative overflow-hidden">
      <div className="pointer-events-none absolute -top-40 -left-40 h-[520px] w-[520px] rounded-full border border-white/5" />
      <div className="pointer-events-none absolute -bottom-32 -right-32 h-[420px] w-[420px] rounded-full bg-accent/10 blur-3xl" />

      <Card className="relative w-full max-w-md border-white/10 bg-white/5 backdrop-blur-xl text-primary-foreground shadow-2xl">
        <CardContent className="pt-8 pb-6 space-y-5">
          <div className="flex flex-col items-center text-center">
            <div className="h-16 w-16 rounded-2xl bg-accent grid place-items-center shadow-lg shadow-accent/30 mb-4">
              <ScanFace className="h-8 w-8 text-foreground" />
            </div>
            <p className="text-xs uppercase tracking-[0.3em] text-white/50">MegaSoft · Modo</p>
            <h1 className="text-3xl font-bold mt-1">Kiosco compartido</h1>
            <p className="font-serif-display text-accent/80 text-xl mt-1">desbloquéalo con tu rostro o clave.</p>
          </div>

          <Tabs defaultValue="face" className="w-full">
            <TabsList className="grid grid-cols-2 bg-white/5 border border-white/10 rounded-full h-11 p-1">
              <TabsTrigger
                value="face"
                data-testid="tab-face-unlock"
                className="rounded-full data-[state=active]:bg-accent data-[state=active]:text-foreground text-white/70 gap-2"
              >
                <ScanFace className="h-4 w-4" /> Rostro
              </TabsTrigger>
              <TabsTrigger
                value="credentials"
                data-testid="tab-credentials-unlock"
                className="rounded-full data-[state=active]:bg-accent data-[state=active]:text-foreground text-white/70 gap-2"
              >
                <KeyRound className="h-4 w-4" /> Credenciales
              </TabsTrigger>
            </TabsList>

            <TabsContent value="face" className="mt-5">
              <FaceUnlockPanel onSuccess={handleSuccess} />
            </TabsContent>

            <TabsContent value="credentials" className="mt-5">
              <CredentialsUnlockPanel onSuccess={handleSuccess} />
            </TabsContent>
          </Tabs>

          <div className="pt-4 border-t border-white/10 text-center">
            <button
              type="button"
              onClick={() => nav("/", { replace: true })}
              className="text-xs text-white/60 hover:text-accent inline-flex items-center gap-1.5 transition-colors"
              data-testid="kiosk-back-to-admin"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              Regresar al panel administrativo
            </button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

/** Formulario clásico email + contraseña */
function CredentialsUnlockPanel({ onSuccess }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e) {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/kiosk/unlock", { email: email.trim(), password });
      onSuccess("Kiosco desbloqueado");
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally { setBusy(false); }
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4" data-testid="kiosk-unlock-form">
      <div className="space-y-1.5">
        <Label className="text-xs text-white/70">Correo del administrador</Label>
        <Input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="admin@empresa.com"
          required
          className="h-11 bg-white/10 border-white/10 text-white placeholder:text-white/40 focus-visible:ring-accent"
          data-testid="kiosk-email"
        />
      </div>
      <div className="space-y-1.5">
        <Label className="text-xs text-white/70">Contraseña</Label>
        <Input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••"
          required
          className="h-11 bg-white/10 border-white/10 text-white placeholder:text-white/40 focus-visible:ring-accent"
          data-testid="kiosk-password"
        />
      </div>
      <Button
        type="submit"
        disabled={busy}
        className="w-full h-12 rounded-full bg-accent hover:bg-accent/90 text-foreground font-semibold shadow-lg shadow-accent/20"
        data-testid="kiosk-unlock-btn"
      >
        {busy
          ? (<><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Desbloqueando…</>)
          : (<><LockKeyhole className="h-4 w-4 mr-2" /> Desbloquear kiosco <ArrowRight className="h-4 w-4 ml-2" /></>)}
      </Button>
      <p className="text-[11px] text-white/50 text-center pt-1">
        Al desbloquear, la pantalla mostrará la cámara y aceptará marcas de cualquier empleado.
      </p>
    </form>
  );
}

/** Panel biométrico — reconoce a un administrador con face-api.js */
function FaceUnlockPanel({ onSuccess }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [status, setStatus] = useState("Enciende la cámara para comenzar");

  async function startCamera() {
    setError(null);
    setStatus("Cargando modelos…");
    try {
      loadFaceApi().then((fa) => loadFaceModels(fa)).catch(() => null);
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 640 }, height: { ideal: 640 } },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => null);
      }
      setReady(true);
      setStatus("Mira directo a la cámara y toca “Reconocer”");
    } catch (_) {
      setError("No pudimos acceder a la cámara. Autoriza el permiso o usa el panel de credenciales.");
    }
  }

  useEffect(() => {
    startCamera();
    return () => {
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function scanAndUnlock() {
    if (!videoRef.current) return;
    setBusy(true);
    setStatus("Analizando rostro…");
    try {
      const faceapi = await loadFaceApi();
      await loadFaceModels(faceapi);
      const opts = new faceapi.TinyFaceDetectorOptions({ inputSize: 320, scoreThreshold: 0.5 });
      const det = await faceapi
        .detectSingleFace(videoRef.current, opts)
        .withFaceLandmarks()
        .withFaceDescriptor();
      if (!det?.descriptor) {
        setStatus("Sin rostro claro. Ilumina bien y vuelve a intentar.");
        toast.error("No se detectó un rostro. Intenta con mejor luz.");
        return;
      }
      const descriptor = Array.from(det.descriptor);
      setStatus("Verificando administrador…");
      const { data } = await api.post("/kiosk/unlock-face", { face_descriptor: descriptor });
      streamRef.current?.getTracks().forEach((t) => t.stop());
      onSuccess(`Bienvenido, ${(data?.admin_name || "").split(" ")[0] || "admin"}`);
    } catch (e) {
      const msg = formatApiErrorDetail(e.response?.data?.detail) || e.message;
      setStatus(msg);
      toast.error(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4" data-testid="kiosk-face-unlock">
      <div className="relative aspect-square w-full max-w-[280px] mx-auto rounded-2xl overflow-hidden border border-white/10 bg-black/40">
        {!ready && !error && (
          <div className="absolute inset-0 grid place-items-center text-white/60 text-xs">
            <Loader2 className="h-6 w-6 animate-spin" />
          </div>
        )}
        <video
          ref={videoRef}
          autoPlay muted playsInline
          className="absolute inset-0 h-full w-full object-cover [transform:scaleX(-1)]"
          data-testid="kiosk-face-video"
        />
        <div className="pointer-events-none absolute inset-6 rounded-full border-2 border-accent/60 shadow-[0_0_0_9999px_rgba(0,0,0,0.35)]" />
      </div>

      <p className={
        "text-center text-xs " + (error ? "text-red-300" : "text-white/70")
      } data-testid="kiosk-face-status">
        {error || status}
      </p>

      <div className="flex gap-2">
        {error && (
          <Button
            type="button"
            variant="outline"
            onClick={startCamera}
            className="flex-1 h-12 rounded-full bg-white/5 border-white/20 text-white hover:bg-white/10"
            data-testid="kiosk-face-retry"
          >
            <RefreshCw className="h-4 w-4 mr-1.5" /> Reintentar
          </Button>
        )}
        <Button
          type="button"
          onClick={scanAndUnlock}
          disabled={!ready || busy}
          className="flex-1 h-12 rounded-full bg-accent hover:bg-accent/90 text-foreground font-semibold shadow-lg shadow-accent/20"
          data-testid="kiosk-face-unlock-btn"
        >
          {busy
            ? (<><Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> Verificando…</>)
            : (<><ScanFace className="h-4 w-4 mr-1.5" /> Reconocer <ArrowRight className="h-4 w-4 ml-1.5" /></>)}
        </Button>
      </div>

      <p className="text-[11px] text-white/50 text-center">
        Sólo se aceptan administradores con selfie previamente registrada.
      </p>
    </div>
  );
}
