import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatApiErrorDetail } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { PasswordInput } from "@/components/ui/password-input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import {
  ScanFace, LockKeyhole, ArrowRight, ArrowLeft, KeyRound, Loader2, RefreshCw,
  MapPin, Play,
} from "lucide-react";

const KIOSK_KEY = "megasoft.kiosk.unlocked";
const KIOSK_SITE_KEY = "megasoft.kiosk.site_id";
const KIOSK_SITE_NAME_KEY = "megasoft.kiosk.site_name";
const KIOSK_SESSION_KEY = "megasoft.kiosk.session_id";
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
export function getKioskSite() {
  try {
    return {
      site_id: sessionStorage.getItem(KIOSK_SITE_KEY) || null,
      site_name: sessionStorage.getItem(KIOSK_SITE_NAME_KEY) || null,
      session_id: sessionStorage.getItem(KIOSK_SESSION_KEY) || null,
    };
  } catch (_) { return { site_id: null, site_name: null, session_id: null }; }
}
export function clearKioskSite() {
  try {
    sessionStorage.removeItem(KIOSK_SITE_KEY);
    sessionStorage.removeItem(KIOSK_SITE_NAME_KEY);
    sessionStorage.removeItem(KIOSK_SESSION_KEY);
  } catch (_) { /* noop */ }
}
function setKioskSite({ site_id, site_name, session_id }) {
  try {
    sessionStorage.setItem(KIOSK_SITE_KEY, site_id);
    sessionStorage.setItem(KIOSK_SITE_NAME_KEY, site_name || "");
    sessionStorage.setItem(KIOSK_SESSION_KEY, session_id);
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
  // Pasos: 'auth' → 'site'
  const [step, setStep] = useState("auth");

  function handleAuthSuccess() {
    // No marcamos unlocked=1 aún; pedimos la sede antes de entrar al kiosco.
    setStep("site");
  }

  function handleSiteConfirmed({ site_id, site_name, session_id }) {
    setKioskSite({ site_id, site_name, session_id });
    setKioskUnlocked(true);
    toast.success(`Kiosco activo en “${site_name || "sede"}”`);
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
              {step === "site" ? <MapPin className="h-8 w-8 text-foreground" /> : <ScanFace className="h-8 w-8 text-foreground" />}
            </div>
            <p className="text-xs uppercase tracking-[0.3em] text-white/50">Mega Soft · Modo</p>
            <h1 className="text-3xl font-bold mt-1">
              {step === "site" ? "Elige la sede" : "Kiosco compartido"}
            </h1>
            <p className="font-serif-display text-accent/80 text-xl mt-1">
              {step === "site" ? "asócialo al lugar físico." : "desbloquéalo con tu rostro o clave."}
            </p>
          </div>

          {step === "auth" ? (
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
                <FaceUnlockPanel onSuccess={handleAuthSuccess} />
              </TabsContent>

              <TabsContent value="credentials" className="mt-5">
                <CredentialsUnlockPanel onSuccess={handleAuthSuccess} />
              </TabsContent>
            </Tabs>
          ) : (
            <SiteSelectionPanel
              onBack={() => setStep("auth")}
              onSuccess={handleSiteConfirmed}
            />
          )}

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

/** Selector de sede — asocia el kiosco a un lugar físico antes de activarlo. */
function SiteSelectionPanel({ onBack, onSuccess }) {
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [siteId, setSiteId] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const { data } = await api.get("/kiosk/sites");
        if (cancel) return;
        setSites(Array.isArray(data) ? data : []);
      } catch (e) {
        setErr(formatApiErrorDetail(e.response?.data?.detail) || "No se pudieron cargar las sedes");
      } finally {
        if (!cancel) setLoading(false);
      }
    })();
    return () => { cancel = true; };
  }, []);

  async function activate() {
    if (!siteId) { toast.error("Selecciona una sede"); return; }
    setBusy(true);
    setErr(null);
    try {
      const { data } = await api.post("/kiosk/session/open", { site_id: siteId });
      onSuccess({
        site_id: data.site_id,
        site_name: data.site_name,
        session_id: data.session_id,
      });
    } catch (e) {
      const msg = formatApiErrorDetail(e.response?.data?.detail) || e.message;
      setErr(msg);
      toast.error(msg);
    } finally { setBusy(false); }
  }

  const chosen = sites.find((s) => s.site_id === siteId);

  return (
    <div className="space-y-4" data-testid="kiosk-site-selector">
      <div className="space-y-1.5">
        <Label className="text-xs text-white/70">Sede física de este kiosco</Label>
        {loading ? (
          <div className="h-11 rounded-md bg-white/10 border border-white/10 flex items-center justify-center">
            <Loader2 className="h-4 w-4 animate-spin text-white/60" />
          </div>
        ) : (
          <Select value={siteId} onValueChange={setSiteId}>
            <SelectTrigger
              className="h-12 bg-white/10 border-white/10 text-white focus:ring-accent"
              data-testid="kiosk-site-select"
            >
              <SelectValue placeholder="— Selecciona la sede —" />
            </SelectTrigger>
            <SelectContent>
              {sites.length === 0 && (
                <div className="px-3 py-2 text-sm text-muted-foreground">
                  No hay sedes registradas.
                </div>
              )}
              {sites.map((s) => (
                <SelectItem key={s.site_id} value={s.site_id} data-testid={`kiosk-site-opt-${s.site_id}`}>
                  {s.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
        {chosen?.address && (
          <p className="text-[11px] text-white/50 mt-1">{chosen.address}</p>
        )}
      </div>

      {err && (
        <div className="rounded-md border border-red-400/30 bg-red-500/10 p-3 text-xs text-red-200" data-testid="kiosk-site-error">
          {err}
        </div>
      )}

      <div className="flex gap-2">
        <Button
          type="button"
          variant="outline"
          onClick={onBack}
          disabled={busy}
          className="h-12 rounded-full bg-white/5 border-white/20 text-white hover:bg-white/10 flex-1"
          data-testid="kiosk-site-back"
        >
          <ArrowLeft className="h-4 w-4 mr-1.5" /> Atrás
        </Button>
        <Button
          type="button"
          onClick={activate}
          disabled={busy || !siteId || loading}
          className="h-12 rounded-full bg-accent hover:bg-accent/90 text-foreground font-semibold flex-[1.4] shadow-lg shadow-accent/20"
          data-testid="kiosk-site-activate"
        >
          {busy
            ? (<><Loader2 className="h-4 w-4 mr-1.5 animate-spin" /> Activando…</>)
            : (<><Play className="h-4 w-4 mr-1.5" /> Activar kiosco <ArrowRight className="h-4 w-4 ml-1.5" /></>)}
        </Button>
      </div>

      <p className="text-[11px] text-white/50 text-center">
        Sólo puede haber un kiosco activo por sede. Si otro dispositivo ya está en esa sede, deberás cerrarlo primero.
      </p>
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
        <PasswordInput
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••"
          required
          className="h-11 bg-white/10 border-white/10 text-white placeholder:text-white/40 focus-visible:ring-accent"
          toggleClassName="text-white/60 hover:text-accent hover:bg-white/10"
          data-testid="kiosk-password"
          toggleTestId="kiosk-password-toggle"
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
          : (<><LockKeyhole className="h-4 w-4 mr-2" /> Continuar <ArrowRight className="h-4 w-4 ml-2" /></>)}
      </Button>
      <p className="text-[11px] text-white/50 text-center pt-1">
        Luego elegirás la sede física a la que se asociará este kiosco.
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
  }, []);

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
