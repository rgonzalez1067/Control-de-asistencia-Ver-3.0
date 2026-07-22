import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatApiErrorDetail } from "@/lib/api";
import { isKioskUnlocked, setKioskUnlocked } from "@/pages/KioskUnlockPage";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import {
  ScanFace, LogIn, LogOut as LogOutIcon, Loader2, LockKeyhole,
  KeyRound, X, CheckCircle2, UserCircle2, Search, ArrowRight, RefreshCcw,
} from "lucide-react";
import SelfieCaptureDialog from "@/components/SelfieCaptureDialog";

const FACEAPI_URL = "https://cdn.jsdelivr.net/npm/face-api.js@0.22.2/dist/face-api.min.js";
const MODELS_URL = "https://cdn.jsdelivr.net/gh/justadudewhohacks/face-api.js@master/weights";
const MATCH_THRESHOLD = 0.55;
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
  const [phase, setPhase] = useState("boot");
  const [status, setStatus] = useState("Cargando reconocimiento facial…");
  const [roster, setRoster] = useState([]);
  const [matcher, setMatcher] = useState(null);
  const [current, setCurrent] = useState(null);   // {user, nextType, distance, marked?}
  const [pinFor, setPinFor] = useState(null);
  const [showPinList, setShowPinList] = useState(false);
  // Re-enroll flow: usuario intenta reemplazar su selfie tras no ser reconocido
  const [reenrollPick, setReenrollPick] = useState(false);       // muestra picker
  const [reenrollTarget, setReenrollTarget] = useState(null);    // usuario elegido (para PIN)
  const [reenrollCapture, setReenrollCapture] = useState(null);  // {user_id, name, pin} lista para capturar
  const [reenrollSaving, setReenrollSaving] = useState(false);
  const [clock, setClock] = useState(new Date());
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const intervalRef = useRef(null);
  const clockRef = useRef(null);
  const busyRef = useRef(false);
  const phaseRef = useRef(phase);
  const matcherRef = useRef(matcher);
  const rosterRef = useRef(roster);

  useEffect(() => { phaseRef.current = phase; }, [phase]);
  useEffect(() => { matcherRef.current = matcher; }, [matcher]);
  useEffect(() => { rosterRef.current = roster; }, [roster]);

  useEffect(() => {
    if (!isKioskUnlocked()) { nav("/kiosk", { replace: true }); return; }
    let cancelled = false;

    clockRef.current = setInterval(() => setClock(new Date()), 1000);

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
          video: { facingMode: "user", width: { ideal: 720 }, height: { ideal: 960 } },
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
          ? "Sin rostros registrados — usa PIN"
          : "Mira a la cámara para marcar");

        intervalRef.current = setInterval(scan, DETECT_INTERVAL_MS);
      } catch (e) {
        console.error(e);
        setPhase("faceUnavailable");
        setStatus("Reconocimiento facial no disponible — usa PIN");
      }
    }

    async function scan() {
      if (busyRef.current || !videoRef.current || !window.faceapi) return;
      if (phaseRef.current !== "ready" || !matcherRef.current) return;
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
        // Consultar próximo tipo (in/out) al backend
        try {
          const { data: nt } = await api.get(`/kiosk/next-type/${matched.user_id}`);
          setCurrent({ ...matched, nextType: nt.next_type, distance: best.distance });
          setPhase("matched");
        } catch (_) {
          setCurrent({ ...matched, nextType: "in", distance: best.distance });
          setPhase("matched");
        }
      } catch (e) { /* ignore transient */ }
      finally { busyRef.current = false; }
    }

    boot();
    return () => {
      cancelled = true;
      if (intervalRef.current) clearInterval(intervalRef.current);
      if (clockRef.current) clearInterval(clockRef.current);
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  async function confirmMark(user, expectedType) {
    try {
      const { data } = await api.post("/kiosk/attendance/check", {
        user_id: user.user_id,
        type: "auto",  // backend decide para evitar races
      });
      const marked = data?.type || expectedType || "in";
      toast.success(`${user.name.split(" ")[0]} · ${marked === "in" ? "Entrada" : "Salida"} registrada`);
      setPhase("success");
      setCurrent({ ...user, marked });
      setTimeout(() => { setCurrent(null); setPhase("ready"); }, 2200);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    }
  }

  function lockKiosk() {
    setKioskUnlocked(false);
    streamRef.current?.getTracks().forEach((t) => t.stop());
    nav("/kiosk", { replace: true });
  }

  async function saveReenroll(dataUrl) {
    if (!reenrollCapture) return;
    setReenrollSaving(true);
    try {
      const fd = new FormData();
      fd.append("user_id", reenrollCapture.user_id);
      fd.append("pin", reenrollCapture.pin);
      fd.append("selfie_base64", dataUrl);
      await api.post("/kiosk/reenroll-face", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success(`Rostro de ${reenrollCapture.name.split(" ")[0]} actualizado`);
      // recargar roster para actualizar el matcher
      try {
        const { data } = await api.get("/kiosk/roster");
        setRoster(data);
      } catch (_) { /* noop */ }
      setReenrollCapture(null);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally { setReenrollSaving(false); }
  }

  // Formato "Miércoles, 22 de julio" (weekday y mes capitalizados, "de" en minúscula).
  const wk = clock.toLocaleDateString("es-VE", { weekday: "long" });
  const mo = clock.toLocaleDateString("es-VE", { month: "long" });
  const dateStr = `${wk.charAt(0).toUpperCase()}${wk.slice(1)}, ${clock.getDate()} de ${mo}`;
  const timeStr = clock.toLocaleTimeString("es-VE", {
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });

  return (
    <div className="min-h-screen bg-primary text-primary-foreground relative overflow-hidden flex flex-col" data-testid="kiosk-scan-page">
      <div className="pointer-events-none absolute -top-40 -left-40 h-[520px] w-[520px] rounded-full border border-white/5" />
      <div className="pointer-events-none absolute -bottom-32 -right-32 h-[420px] w-[420px] rounded-full bg-accent/10 blur-3xl" />

      {/* Header */}
      <header className="relative flex items-center justify-between px-4 py-4 border-b border-white/5">
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-xl bg-accent grid place-items-center">
            <ScanFace className="h-5 w-5 text-primary" />
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-[0.3em] text-white/50 leading-none">MegaSoft</p>
            <p className="text-sm font-semibold leading-tight mt-0.5">Kiosco de asistencia</p>
          </div>
        </div>
        <div className="text-right hidden sm:block">
          <p className="text-[10px] uppercase tracking-widest text-white/40 leading-none">Hoy</p>
          <p className="text-sm font-mono font-semibold leading-tight mt-0.5">{timeStr}</p>
        </div>
      </header>

      {/* Portrait main */}
      <main className="relative flex-1 flex flex-col items-center px-4 pt-6 pb-4">
        {phase === "faceUnavailable" ? (
          <div className="w-full max-w-md rounded-3xl border border-white/10 bg-white/5 backdrop-blur p-10 text-center mt-8" data-testid="kiosk-face-unavailable">
            <div className="h-16 w-16 rounded-2xl bg-accent/20 grid place-items-center mx-auto mb-4">
              <KeyRound className="h-8 w-8 text-accent" />
            </div>
            <h2 className="text-2xl font-bold">Reconocimiento facial no disponible</h2>
            <p className="text-white/60 text-sm mt-2 max-w-md mx-auto">
              Los empleados pueden marcar con PIN mientras se resuelve.
            </p>
            <Button onClick={() => setShowPinList(true)}
              className="mt-6 h-14 rounded-full bg-accent hover:bg-accent/90 text-primary font-semibold px-8 text-base"
              data-testid="kiosk-face-unavailable-pin-btn">
              <KeyRound className="h-5 w-5 mr-2" /> Marcar con PIN
            </Button>
          </div>
        ) : (
          <>
            {/* Video vertical */}
            <div
              className="relative w-full max-w-md aspect-[3/4] rounded-[36px] overflow-hidden bg-black shadow-2xl shadow-black/50"
              data-testid="kiosk-video-wrap"
            >
              <video ref={videoRef} muted playsInline
                     className="absolute inset-0 h-full w-full object-cover scale-x-[-1]" />

              {phase === "ready" && (
                <div className="pointer-events-none absolute inset-0">
                  <div className="absolute inset-6 border-2 border-dashed border-accent/70 rounded-[28px]" />
                  <div className="absolute left-0 right-0 h-1 bg-gradient-to-r from-transparent via-accent to-transparent animate-[kiosk-scan_2.4s_ease-in-out_infinite]" />
                </div>
              )}

              {/* Corner brackets — mejora percepción de "cámara profesional" */}
              <div className="pointer-events-none absolute inset-6">
                <span className="absolute -top-1 -left-1 h-6 w-6 border-t-2 border-l-2 border-accent rounded-tl-2xl" />
                <span className="absolute -top-1 -right-1 h-6 w-6 border-t-2 border-r-2 border-accent rounded-tr-2xl" />
                <span className="absolute -bottom-1 -left-1 h-6 w-6 border-b-2 border-l-2 border-accent rounded-bl-2xl" />
                <span className="absolute -bottom-1 -right-1 h-6 w-6 border-b-2 border-r-2 border-accent rounded-br-2xl" />
              </div>

              {/* Status pill */}
              <div className="absolute bottom-4 left-1/2 -translate-x-1/2 rounded-full bg-black/60 backdrop-blur border border-white/10 px-4 py-2 text-xs text-white/85 flex items-center gap-2" data-testid="kiosk-status">
                {phase === "boot" && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                {phase === "ready" && <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />}
                <span>{status}</span>
              </div>
            </div>

            {/* Info */}
            <div className="w-full max-w-md mt-6 text-center">
              <p className="font-serif-display text-3xl text-accent leading-none">{dateStr}</p>
              <p className="text-white/60 text-sm mt-2 max-w-xs mx-auto">
                Colócate frente a la cámara. Marcaremos automáticamente entrada o salida.
              </p>
              <button
                type="button"
                onClick={() => setReenrollPick(true)}
                className="mt-4 text-xs text-white/50 hover:text-accent underline underline-offset-4 decoration-dotted transition-colors inline-flex items-center gap-1.5"
                data-testid="kiosk-reenroll-btn"
              >
                <RefreshCcw className="h-3 w-3" />
                No me reconoció · Reemplazar mi rostro con PIN
              </button>
            </div>
          </>
        )}
      </main>

      {/* Bottom actions */}
      <div className="relative px-4 pb-6 pt-2 border-t border-white/5 flex items-center gap-2">
        <Button variant="ghost" onClick={lockKiosk}
          className="rounded-full h-12 text-white/70 hover:bg-white/10 hover:text-white flex-1"
          data-testid="kiosk-lock-btn">
          <LockKeyhole className="h-4 w-4 mr-1.5" /> Bloquear
        </Button>
        <Button onClick={() => setShowPinList(true)}
          className="rounded-full h-12 flex-1 bg-accent hover:bg-accent/90 text-primary font-semibold"
          data-testid="kiosk-pin-mode-btn">
          <KeyRound className="h-4 w-4 mr-1.5" /> Marcar con PIN
        </Button>
      </div>

      <style>{`
        @keyframes kiosk-scan {
          0%, 100% { top: 10%; opacity: 0.6; }
          50% { top: 90%; opacity: 1; }
        }
      `}</style>

      {/* Match confirmation — vertical, un solo botón */}
      <Dialog open={phase === "matched"} onOpenChange={(v) => !v && (setPhase("ready"), setCurrent(null))}>
        <DialogContent className="max-w-sm" data-testid="kiosk-match-dialog">
          <DialogHeader className="items-center text-center">
            <DialogTitle>¿Confirmas tu marca?</DialogTitle>
            <DialogDescription>
              Registraremos tu {current?.nextType === "in" ? "entrada" : "salida"} automáticamente.
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col items-center text-center py-2">
            <div className="h-36 w-36 rounded-full overflow-hidden border-4 border-primary/20 mb-3 shadow-lg">
              {current?.selfie_base64
                ? <img alt="user" src={current.selfie_base64} className="h-full w-full object-cover" data-testid="kiosk-match-photo" />
                : <div className="h-full w-full bg-muted grid place-items-center"><UserCircle2 className="h-16 w-16 text-muted-foreground" /></div>}
            </div>
            <p className="text-2xl font-semibold text-primary dark:text-foreground" data-testid="kiosk-match-name">{current?.name}</p>
            <p className="text-xs text-muted-foreground mt-0.5">{current?.position || "—"}</p>
            <div
              className={
                "mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm font-semibold " +
                (current?.nextType === "in"
                  ? "bg-emerald-100 text-emerald-800"
                  : "bg-slate-200 text-slate-700")
              }
              data-testid="kiosk-match-type-badge"
            >
              {current?.nextType === "in" ? <LogIn className="h-4 w-4" /> : <LogOutIcon className="h-4 w-4" />}
              {current?.nextType === "in" ? "Registrar ENTRADA" : "Registrar SALIDA"}
            </div>
            <p className="text-[10px] text-muted-foreground/70 mt-3">
              Confianza · {((1 - (current?.distance ?? 0)) * 100 | 0)}%
            </p>
          </div>
          <DialogFooter className="flex-row gap-2 sm:justify-center">
            <Button variant="outline" className="flex-1 h-14 rounded-full text-base"
              onClick={() => { setPhase("ready"); setCurrent(null); }}
              data-testid="kiosk-match-cancel">
              <X className="h-4 w-4 mr-1.5" /> No soy yo
            </Button>
            <Button
              onClick={() => confirmMark(current, current?.nextType)}
              className={
                "flex-1 h-14 rounded-full text-base font-semibold " +
                (current?.nextType === "in"
                  ? "bg-emerald-600 hover:bg-emerald-700"
                  : "bg-primary hover:bg-primary/90")
              }
              data-testid="kiosk-match-confirm"
            >
              Sí, soy yo <ArrowRight className="h-4 w-4 ml-1.5" />
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Success overlay */}
      {phase === "success" && current && (
        <div className="fixed inset-0 grid place-items-center bg-primary/95 z-50 animate-in fade-in" data-testid="kiosk-success">
          <div className="text-center px-6">
            <CheckCircle2 className="h-28 w-28 text-emerald-400 mx-auto mb-4 animate-bounce" />
            <p className="text-3xl font-bold text-primary-foreground">¡Listo, {current.name.split(" ")[0]}!</p>
            <p className="font-serif-display text-accent text-2xl mt-1">
              {current.marked === "in" ? "entrada registrada" : "salida registrada"}
            </p>
            <p className="text-white/60 text-sm mt-3 font-mono">{timeStr}</p>
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
        onSuccess={(u) => { setPinFor(null); confirmMark(u); }}
      />

      {/* Re-enroll: paso 1 — selección de usuario */}
      <PinPickerDialog
        open={reenrollPick}
        roster={roster}
        title="¿Quién eres?"
        description="Selecciónate para reemplazar tu foto."
        testId="kiosk-reenroll-picker"
        onCancel={() => setReenrollPick(false)}
        onPick={(u) => { setReenrollPick(false); setReenrollTarget(u); }}
      />

      {/* Re-enroll: paso 2 — PIN */}
      <ReenrollPinDialog
        target={reenrollTarget}
        onCancel={() => setReenrollTarget(null)}
        onSuccess={(u, pin) => { setReenrollTarget(null); setReenrollCapture({ ...u, pin }); }}
      />

      {/* Re-enroll: paso 3 — captura + POST */}
      <SelfieCaptureDialog
        open={!!reenrollCapture}
        onOpenChange={(v) => !v && setReenrollCapture(null)}
        title={`Nuevo rostro de ${reenrollCapture?.name || ""}`}
        description="Mira directo a la cámara con buena luz. Reemplazará tu foto anterior."
        onConfirm={saveReenroll}
        saving={reenrollSaving}
      />
    </div>
  );
}

/** Dialog especializado para el re-enroll — pide el PIN sin la opción de marcar */
function ReenrollPinDialog({ target, onCancel, onSuccess }) {
  const [pin, setPin] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { setPin(""); }, [target]);

  async function verify() {
    if (!pin || pin.length < 4) { toast.error("Ingresa tu PIN"); return; }
    setBusy(true);
    try {
      await api.post("/kiosk/verify-pin", { user_id: target.user_id, pin });
      onSuccess(target, pin);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || "PIN incorrecto");
    } finally { setBusy(false); }
  }

  return (
    <Dialog open={!!target} onOpenChange={(v) => !v && onCancel()}>
      <DialogContent className="max-w-sm" data-testid="kiosk-reenroll-pin">
        <DialogHeader className="items-center text-center">
          <DialogTitle>Confirma con tu PIN</DialogTitle>
          <DialogDescription>
            {target?.name?.split(" ")[0]}, ingresa tu PIN para reemplazar tu rostro registrado.
          </DialogDescription>
        </DialogHeader>
        <Input
          type="password"
          inputMode="numeric"
          pattern="[0-9]*"
          value={pin}
          onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 8))}
          placeholder="••••"
          className="text-3xl text-center h-16 tracking-widest font-mono"
          data-testid="kiosk-reenroll-pin-input"
          autoFocus
        />
        <DialogFooter className="flex-row gap-2 sm:justify-stretch">
          <Button variant="outline" onClick={onCancel} className="h-14 rounded-full flex-1 text-base">
            <X className="h-4 w-4 mr-1.5" /> Cancelar
          </Button>
          <Button onClick={verify} disabled={busy}
            className="h-14 rounded-full flex-1 text-base font-semibold bg-primary hover:bg-primary/90"
            data-testid="kiosk-reenroll-pin-confirm">
            Continuar <ArrowRight className="h-4 w-4 ml-1.5" />
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PinPickerDialog({ open, roster, onCancel, onPick, title, description, testId }) {
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
      <DialogContent className="max-w-md sm:max-w-lg" data-testid={testId || "kiosk-pin-picker"}>
        <DialogHeader>
          <DialogTitle>{title || "Selecciona tu nombre"}</DialogTitle>
          <DialogDescription>{description || "Después te pediremos el PIN."}</DialogDescription>
        </DialogHeader>
        <div className="relative mb-3">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)}
                 placeholder="Nombre o cédula"
                 className="pl-9 h-12 text-base" data-testid="kiosk-pin-search" autoFocus />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-[460px] overflow-y-auto">
          {filtered.map((u) => (
            <button
              key={u.user_id}
              onClick={() => onPick(u)}
              className="flex items-center gap-3 p-3 rounded-xl border border-border/60 hover:border-primary/40 hover:bg-muted/40 transition-colors text-left"
              data-testid={`kiosk-pin-user-${u.user_id}`}
            >
              <div className="h-11 w-11 rounded-full overflow-hidden bg-muted grid place-items-center shrink-0">
                {u.selfie_base64
                  ? <img src={u.selfie_base64} alt="" className="h-full w-full object-cover" />
                  : <UserCircle2 className="h-6 w-6 text-muted-foreground" />}
              </div>
              <div className="min-w-0">
                <p className="text-sm font-medium text-primary dark:text-foreground truncate">{u.name}</p>
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
  const [nextType, setNextType] = useState("in");

  useEffect(() => {
    setPin("");
    if (target?.user_id) {
      api.get(`/kiosk/next-type/${target.user_id}`)
        .then(({ data }) => setNextType(data.next_type || "in"))
        .catch(() => setNextType("in"));
    }
  }, [target]);

  async function verify() {
    if (!pin || pin.length < 4) { toast.error("Ingresa tu PIN"); return; }
    setBusy(true);
    try {
      await api.post("/kiosk/verify-pin", { user_id: target.user_id, pin });
      onSuccess(target);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || "PIN incorrecto");
    } finally { setBusy(false); }
  }

  const isIn = nextType === "in";

  return (
    <Dialog open={!!target} onOpenChange={(v) => !v && onCancel()}>
      <DialogContent className="max-w-sm" data-testid="kiosk-pin-enter">
        <DialogHeader className="items-center text-center">
          <DialogTitle>Hola, {target?.name?.split(" ")[0]}</DialogTitle>
          <DialogDescription>
            Ingresa tu PIN para registrar tu {isIn ? "entrada" : "salida"}.
          </DialogDescription>
        </DialogHeader>

        <div className={
          "mx-auto inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-semibold " +
          (isIn ? "bg-emerald-100 text-emerald-800" : "bg-slate-200 text-slate-700")
        } data-testid="kiosk-pin-type-badge">
          {isIn ? <LogIn className="h-3.5 w-3.5" /> : <LogOutIcon className="h-3.5 w-3.5" />}
          {isIn ? "Próxima: ENTRADA" : "Próxima: SALIDA"}
        </div>

        <Input
          type="password"
          inputMode="numeric"
          pattern="[0-9]*"
          value={pin}
          onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 8))}
          placeholder="••••"
          className="text-3xl text-center h-16 tracking-widest font-mono mt-2"
          data-testid="kiosk-pin-input"
          autoFocus
        />
        <DialogFooter className="flex-row gap-2 sm:justify-stretch">
          <Button variant="outline" onClick={onCancel} className="h-14 rounded-full flex-1 text-base" data-testid="kiosk-pin-cancel">
            <X className="h-4 w-4 mr-1.5" /> Cancelar
          </Button>
          <Button onClick={verify} disabled={busy}
            className={
              "h-14 rounded-full flex-1 text-base font-semibold " +
              (isIn ? "bg-emerald-600 hover:bg-emerald-700" : "bg-primary hover:bg-primary/90")
            }
            data-testid="kiosk-pin-confirm">
            Marcar <ArrowRight className="h-4 w-4 ml-1.5" />
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
