import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatApiErrorDetail } from "@/lib/api";
import { isKioskUnlocked, setKioskUnlocked } from "@/pages/KioskUnlockPage";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import {
  ScanFace, LogIn, LogOut as LogOutIcon, Loader2, LockKeyhole,
  KeyRound, X, CheckCircle2, UserCircle2, Search,
} from "lucide-react";

const FACEAPI_URL = "https://cdn.jsdelivr.net/npm/face-api.js@0.22.2/dist/face-api.min.js";
const MODELS_URL = "https://cdn.jsdelivr.net/gh/justadudewhohacks/face-api.js@master/weights";
const MATCH_THRESHOLD = 0.55; // <-- distance; menor = más estricto
const DETECT_INTERVAL_MS = 700;

/** Carga face-api.js una sola vez desde CDN. */
function loadFaceApi() {
  if (window.faceapi) return Promise.resolve(window.faceapi);
  if (window.__faceApiLoading) return window.__faceApiLoading;
  window.__faceApiLoading = new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = FACEAPI_URL;
    s.async = true;
    s.onload = () => resolve(window.faceapi);
    s.onerror = () => reject(new Error("No se pudo cargar face-api.js"));
    document.head.appendChild(s);
  });
  return window.__faceApiLoading;
}

async function loadModels(faceapi) {
  await Promise.all([
    faceapi.nets.tinyFaceDetector.loadFromUri(MODELS_URL),
    faceapi.nets.faceLandmark68Net.loadFromUri(MODELS_URL),
    faceapi.nets.faceRecognitionNet.loadFromUri(MODELS_URL),
  ]);
}

export default function KioskScanPage() {
  const nav = useNavigate();
  const [phase, setPhase] = useState("boot");   // boot | ready | matched | success | error
  const [status, setStatus] = useState("Cargando reconocimiento facial…");
  const [roster, setRoster] = useState([]);
  const [matcher, setMatcher] = useState(null);
  const [current, setCurrent] = useState(null); // matched user
  const [pinFor, setPinFor] = useState(null);   // user chosen for PIN fallback
  const [showPinList, setShowPinList] = useState(false);
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const intervalRef = useRef(null);
  const busyRef = useRef(false);

  useEffect(() => {
    if (!isKioskUnlocked()) { nav("/kiosk", { replace: true }); return; }
    let cancelled = false;

    async function boot() {
      try {
        setStatus("Descargando modelos de rostro…");
        const faceapi = await loadFaceApi();
        await loadModels(faceapi);
        if (cancelled) return;

        setStatus("Cargando personal…");
        const { data } = await api.get("/kiosk/roster");
        if (cancelled) return;
        setRoster(data);

        // Construir descriptores para el matcher (los que ya vinieron de mobile)
        const labeled = [];
        for (const u of data) {
          if (Array.isArray(u.face_descriptor) && u.face_descriptor.length > 0) {
            const d = Float32Array.from(u.face_descriptor);
            labeled.push(new faceapi.LabeledFaceDescriptors(u.user_id, [d]));
          }
        }
        if (labeled.length > 0) {
          setMatcher(new faceapi.FaceMatcher(labeled, MATCH_THRESHOLD));
        }

        setStatus("Iniciando cámara…");
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
          audio: false,
        });
        if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return; }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play().catch(() => null);
        }
        setPhase("ready");
        setStatus(labeled.length === 0
          ? "Ningún empleado tiene rostro registrado — usa PIN"
          : "Acércate a la cámara para marcar");

        // start loop
        intervalRef.current = setInterval(scan, DETECT_INTERVAL_MS);
      } catch (e) {
        console.error(e);
        setPhase("error");
        setStatus(e.message || "No se pudo iniciar el kiosco");
      }
    }

    async function scan() {
      if (busyRef.current || !videoRef.current || !window.faceapi) return;
      if (phaseRef.current !== "ready") return;
      if (!matcherRef.current) return;
      busyRef.current = true;
      try {
        const faceapi = window.faceapi;
        const opts = new faceapi.TinyFaceDetectorOptions({ inputSize: 320, scoreThreshold: 0.5 });
        const det = await faceapi
          .detectSingleFace(videoRef.current, opts)
          .withFaceLandmarks()
          .withFaceDescriptor();
        if (!det) { busyRef.current = false; return; }

        const best = matcherRef.current.findBestMatch(det.descriptor);
        if (best.label === "unknown") { busyRef.current = false; return; }

        const matched = rosterRef.current.find((u) => u.user_id === best.label);
        if (!matched) { busyRef.current = false; return; }
        setCurrent({ ...matched, distance: best.distance });
        setPhase("matched");
      } catch (e) {
        // ignore transient
      } finally {
        busyRef.current = false;
      }
    }

    boot();
    return () => {
      cancelled = true;
      if (intervalRef.current) clearInterval(intervalRef.current);
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  // refs que el loop necesita ver siempre actualizados
  const phaseRef = useRef(phase);
  const matcherRef = useRef(matcher);
  const rosterRef = useRef(roster);
  useEffect(() => { phaseRef.current = phase; }, [phase]);
  useEffect(() => { matcherRef.current = matcher; }, [matcher]);
  useEffect(() => { rosterRef.current = roster; }, [roster]);

  async function registerAttendance(user, type) {
    try {
      await api.post("/kiosk/attendance/check", {
        user_id: user.user_id,
        type,
      });
      toast.success(`${user.name.split(" ")[0]} · ${type === "in" ? "Entrada" : "Salida"} registrada`);
      setPhase("success");
      setCurrent({ ...user, marked: type });
      setTimeout(() => {
        setCurrent(null); setPhase("ready");
      }, 2500);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    }
  }

  function lockKiosk() {
    setKioskUnlocked(false);
    streamRef.current?.getTracks().forEach((t) => t.stop());
    nav("/kiosk", { replace: true });
  }

  return (
    <div className="min-h-screen bg-primary text-primary-foreground relative overflow-hidden" data-testid="kiosk-scan-page">
      <div className="pointer-events-none absolute -top-40 -left-40 h-[520px] w-[520px] rounded-full border border-white/5" />
      <div className="pointer-events-none absolute -bottom-32 -right-32 h-[420px] w-[420px] rounded-full bg-accent/10 blur-3xl" />

      <header className="relative flex items-center justify-between px-6 py-4 border-b border-white/5">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-accent grid place-items-center">
            <ScanFace className="h-5 w-5 text-primary" />
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-[0.3em] text-white/50">MegaSoft · Kiosco</p>
            <p className="text-sm font-semibold">Marca tu asistencia</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" onClick={() => setShowPinList(true)}
            className="rounded-full text-white/80 hover:bg-white/10 hover:text-white" data-testid="kiosk-pin-mode-btn">
            <KeyRound className="h-4 w-4 mr-1.5" /> Marcar con PIN
          </Button>
          <Button variant="ghost" onClick={lockKiosk}
            className="rounded-full text-white/70 hover:bg-white/10 hover:text-white" data-testid="kiosk-lock-btn">
            <LockKeyhole className="h-4 w-4 mr-1.5" /> Bloquear
          </Button>
        </div>
      </header>

      <main className="relative grid place-items-center px-6 py-10">
        <div className="relative w-full max-w-[720px] aspect-video rounded-3xl overflow-hidden bg-black shadow-2xl" data-testid="kiosk-video-wrap">
          <video ref={videoRef} muted playsInline className="absolute inset-0 h-full w-full object-cover scale-x-[-1]" />

          {/* Overlay scan animation */}
          {phase === "ready" && (
            <div className="pointer-events-none absolute inset-0">
              <div className="absolute inset-10 border-2 border-dashed border-accent/70 rounded-3xl" />
              <div className="absolute left-0 right-0 h-1 bg-gradient-to-r from-transparent via-accent to-transparent animate-[kiosk-scan_2.4s_ease-in-out_infinite]" />
            </div>
          )}

          {/* Status pill */}
          <div className="absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full bg-black/60 backdrop-blur border border-white/10 px-4 py-2 text-xs text-white/80 flex items-center gap-2" data-testid="kiosk-status">
            {phase === "boot" && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            {phase === "ready" && <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />}
            {phase === "error" && <span className="h-2 w-2 rounded-full bg-red-400" />}
            <span>{status}</span>
          </div>
        </div>

        <p className="mt-6 text-center text-white/60 text-sm max-w-xl">
          Mira directo a la cámara. Cuando el sistema te reconozca, confirma tu <b className="text-accent">entrada</b> o <b className="text-accent">salida</b>.
          Si el rostro no funciona, usa el botón <b>Marcar con PIN</b>.
        </p>
      </main>

      {/* Style keyframes */}
      <style>{`
        @keyframes kiosk-scan {
          0%, 100% { top: 12%; opacity: 0.6; }
          50% { top: 88%; opacity: 1; }
        }
      `}</style>

      {/* Match confirmation dialog */}
      <Dialog open={phase === "matched"} onOpenChange={(v) => !v && (setPhase("ready"), setCurrent(null))}>
        <DialogContent className="max-w-md" data-testid="kiosk-match-dialog">
          <DialogHeader>
            <DialogTitle>¿Eres tú?</DialogTitle>
            <DialogDescription>Confirmá tu marca de asistencia.</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col items-center text-center py-2">
            <div className="h-32 w-32 rounded-full overflow-hidden border-4 border-primary/20 mb-3">
              {current?.selfie_base64
                ? <img alt="user" src={current.selfie_base64} className="h-full w-full object-cover" data-testid="kiosk-match-photo" />
                : <div className="h-full w-full bg-muted grid place-items-center"><UserCircle2 className="h-16 w-16 text-muted-foreground" /></div>}
            </div>
            <p className="text-xl font-semibold text-primary" data-testid="kiosk-match-name">{current?.name}</p>
            <p className="text-xs text-muted-foreground mt-0.5">{current?.position || "—"}</p>
            <p className="text-[10px] text-muted-foreground/70 mt-2">
              Confianza: {(1 - (current?.distance ?? 0)) * 100 | 0}%
            </p>
          </div>
          <DialogFooter className="flex-row gap-2 sm:justify-center">
            <Button variant="outline" className="flex-1 h-12 rounded-full" onClick={() => { setPhase("ready"); setCurrent(null); }} data-testid="kiosk-match-cancel">
              <X className="h-4 w-4 mr-1.5" /> No soy yo
            </Button>
            <Button onClick={() => registerAttendance(current, "in")} className="flex-1 h-12 rounded-full bg-emerald-600 hover:bg-emerald-700" data-testid="kiosk-match-in">
              <LogIn className="h-4 w-4 mr-1.5" /> Entrada
            </Button>
            <Button onClick={() => registerAttendance(current, "out")} className="flex-1 h-12 rounded-full bg-primary hover:bg-primary/90" data-testid="kiosk-match-out">
              <LogOutIcon className="h-4 w-4 mr-1.5" /> Salida
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Success overlay */}
      {phase === "success" && current && (
        <div className="fixed inset-0 grid place-items-center bg-primary/95 z-50 animate-in fade-in" data-testid="kiosk-success">
          <div className="text-center">
            <CheckCircle2 className="h-24 w-24 text-emerald-400 mx-auto mb-4 animate-bounce" />
            <p className="text-3xl font-bold text-primary-foreground">¡Listo, {current.name.split(" ")[0]}!</p>
            <p className="text-accent mt-1">{current.marked === "in" ? "Entrada registrada" : "Salida registrada"}</p>
          </div>
        </div>
      )}

      <PinPickerDialog
        open={showPinList}
        roster={roster}
        onCancel={() => setShowPinList(false)}
        onPick={(u) => { setShowPinList(false); setPinFor(u); }}
      />
      <PinEnterDialog
        target={pinFor}
        onCancel={() => setPinFor(null)}
        onSuccess={(u, type) => { setPinFor(null); registerAttendance(u, type); }}
      />
    </div>
  );
}

function PinPickerDialog({ open, roster, onCancel, onPick }) {
  const [q, setQ] = useState("");
  const filtered = useMemo(() => {
    const n = q.toLowerCase().trim();
    return (roster || [])
      .filter((u) => !n
        || u.name.toLowerCase().includes(n)
        || (u.cedula || "").includes(n))
      .slice(0, 60);
  }, [roster, q]);

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onCancel()}>
      <DialogContent className="max-w-3xl" data-testid="kiosk-pin-picker">
        <DialogHeader>
          <DialogTitle>Selecciona tu nombre</DialogTitle>
          <DialogDescription>Luego te pediremos el PIN.</DialogDescription>
        </DialogHeader>
        <div className="relative mb-3">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Nombre o cédula" className="pl-9" data-testid="kiosk-pin-search" autoFocus />
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 max-h-[420px] overflow-y-auto">
          {filtered.map((u) => (
            <button
              key={u.user_id}
              onClick={() => onPick(u)}
              className="flex items-center gap-3 p-3 rounded-xl border border-border/60 hover:border-primary/40 hover:bg-muted/40 transition-colors text-left"
              data-testid={`kiosk-pin-user-${u.user_id}`}
            >
              <div className="h-10 w-10 rounded-full overflow-hidden bg-muted grid place-items-center shrink-0">
                {u.selfie_base64 ? <img src={u.selfie_base64} alt="" className="h-full w-full object-cover" /> : <UserCircle2 className="h-6 w-6 text-muted-foreground" />}
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium text-primary truncate">{u.name}</p>
                <p className="text-[11px] text-muted-foreground">{u.cedula || "—"}</p>
              </div>
            </button>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

function PinEnterDialog({ target, onCancel, onSuccess }) {
  const [pin, setPin] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { setPin(""); }, [target]);

  async function verify(type) {
    if (!pin || pin.length < 4) { toast.error("Ingresa tu PIN"); return; }
    setBusy(true);
    try {
      await api.post("/kiosk/verify-pin", { user_id: target.user_id, pin });
      onSuccess(target, type);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || "PIN incorrecto");
    } finally { setBusy(false); }
  }

  return (
    <Dialog open={!!target} onOpenChange={(v) => !v && onCancel()}>
      <DialogContent className="max-w-sm" data-testid="kiosk-pin-enter">
        <DialogHeader>
          <DialogTitle>Hola, {target?.name?.split(" ")[0]}</DialogTitle>
          <DialogDescription>Ingresa tu PIN y elige entrada o salida.</DialogDescription>
        </DialogHeader>
        <Input
          type="password"
          inputMode="numeric"
          pattern="[0-9]*"
          value={pin}
          onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 8))}
          placeholder="••••"
          className="text-2xl text-center h-14 tracking-widest font-mono"
          data-testid="kiosk-pin-input"
          autoFocus
        />
        <DialogFooter className="flex-row gap-2 sm:justify-stretch">
          <Button onClick={() => verify("in")} disabled={busy} className="flex-1 h-12 rounded-full bg-emerald-600 hover:bg-emerald-700" data-testid="kiosk-pin-in">
            <LogIn className="h-4 w-4 mr-1.5" /> Entrada
          </Button>
          <Button onClick={() => verify("out")} disabled={busy} className="flex-1 h-12 rounded-full bg-primary hover:bg-primary/90" data-testid="kiosk-pin-out">
            <LogOutIcon className="h-4 w-4 mr-1.5" /> Salida
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
