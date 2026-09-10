import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { isKioskUnlocked, setKioskUnlocked, getKioskSite, clearKioskSite } from "@/pages/KioskUnlockPage";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import {
  ScanFace, LogIn, LogOut as LogOutIcon, Loader2, LockKeyhole,
  KeyRound, X, CheckCircle2, UserCircle2, Search, ArrowRight, RefreshCcw, DoorOpen, Camera, MapPin,
  Building2, Clock3,
} from "lucide-react";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import SelfieCaptureDialog from "@/components/SelfieCaptureDialog";

const FACEAPI_URL = "/vendor/face-api/face-api.min.js";
const MODELS_URL = "/vendor/face-api/weights";

// ── Validación de rostro (endurecida para reducir falsos positivos) ──
// Distancia euclidiana; menor = más parecido. En face-api el máximo es ~1.
const MATCH_THRESHOLD = 0.48;       // Antes 0.55 — rechaza matches débiles
const MATCH_MARGIN = 0.06;          // El 2do candidato debe estar ≥ 0.06 más lejos que el 1ro
const REQUIRED_CONSECUTIVE = 3;     // Mismo usuario detectado en N frames seguidos
const DETECT_INTERVAL_MS = 500;     // Un poco más rápido para acumular frames sin frustrar al usuario

/** Carga face-api.js una sola vez desde CDN. */
function loadFaceApi() {
  if (window.faceapi) return Promise.resolve(window.faceapi);
  if (window.__faceApiLoading) return window.__faceApiLoading;
  window.__faceApiLoading = new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = FACEAPI_URL;
    s.async = true;
    s.onload = () => resolve(window.faceapi);
    s.onerror = () => {
      window.__faceApiLoading = null;
      reject(new Error("No se pudo cargar face-api.js"));
    };
    document.head.appendChild(s);
  });
  return window.__faceApiLoading;
}

async function loadModels(faceapi) {
  // Idempotente: si ya se cargaron (p. ej. desde KioskUnlockPage) no reintenta.
  if (window.__faceModelsReady) return;
  await Promise.all([
    faceapi.nets.tinyFaceDetector.loadFromUri(MODELS_URL),
    faceapi.nets.faceLandmark68Net.loadFromUri(MODELS_URL),
    faceapi.nets.faceRecognitionNet.loadFromUri(MODELS_URL),
  ]);
  window.__faceModelsReady = true;
}

/** Envuelve una promesa con un timeout. Si expira, se rechaza con `message`. */
function withTimeout(promise, ms, message) {
  return Promise.race([
    promise,
    new Promise((_, reject) => setTimeout(() => reject(new Error(message)), ms)),
  ]);
}

export default function KioskScanPage() {
  const nav = useNavigate();
  const { user: currentUser, logout } = useAuth();
  const kioskSite = useMemo(() => getKioskSite(), []);
  const [phase, setPhase] = useState("boot");
  const [status, setStatus] = useState("Cargando reconocimiento facial…");
  const [roster, setRoster] = useState([]);
  const [labeled, setLabeled] = useState([]);      // [{user_id, descriptor: Float32Array}]
  const [current, setCurrent] = useState(null);   // {user, nextType, distance, marked?}
  const [pinFor, setPinFor] = useState(null);
  const [showPinList, setShowPinList] = useState(false);
  // Re-enroll flow: usuario intenta reemplazar su selfie tras no ser reconocido
  const [reenrollPick, setReenrollPick] = useState(false);       // muestra picker
  const [reenrollTarget, setReenrollTarget] = useState(null);    // usuario elegido (para PIN)
  const [reenrollCapture, setReenrollCapture] = useState(null);  // {user_id, name, pin} lista para capturar
  const [reenrollSaving, setReenrollSaving] = useState(false);
  const [showExit, setShowExit] = useState(false);
  const [showLock, setShowLock] = useState(false);
  const [clock, setClock] = useState(new Date());
  const [idle, setIdle] = useState(false);
  const [pendingVisits, setPendingVisits] = useState([]);
  const [activeVisit, setActiveVisit] = useState(null);
  const [visitVisitorIdx, setVisitVisitorIdx] = useState(0);
  // Nuevo flujo: acceso directo a las visitas del día desde el Kiosco (independiente
  // del marcaje del anfitrión). Se navega listado → PIN → selfies → cierre.
  const [visitsBrowserOpen, setVisitsBrowserOpen] = useState(false);
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const intervalRef = useRef(null);
  const clockRef = useRef(null);
  const busyRef = useRef(false);
  const phaseRef = useRef(phase);
  const labeledRef = useRef(labeled);
  const rosterRef = useRef(roster);
  const idleRef = useRef(false);
  const lastFaceAtRef = useRef(Date.now());
  // Contador de frames consecutivos para el mismo user (evita falsos positivos)
  const consecutiveRef = useRef({ userId: null, count: 0 });

  const IDLE_AFTER_MS = 15000; // 15s sin rostro → reposo

  useEffect(() => { phaseRef.current = phase; }, [phase]);
  useEffect(() => { labeledRef.current = labeled; }, [labeled]);
  useEffect(() => { rosterRef.current = roster; }, [roster]);
  useEffect(() => { idleRef.current = idle; }, [idle]);

  function wakeUp() {
    lastFaceAtRef.current = Date.now();
    if (idleRef.current) setIdle(false);
  }

  useEffect(() => {
    if (!isKioskUnlocked()) { nav("/kiosk", { replace: true }); return; }
    if (!kioskSite.site_id || !kioskSite.session_id) {
      // Falta la asociación de sede — regresa al desbloqueo para elegirla.
      clearKioskSite();
      setKioskUnlocked(false);
      nav("/kiosk", { replace: true });
      return;
    }
    let cancelled = false;

    clockRef.current = setInterval(() => setClock(new Date()), 1000);

    // Heartbeat cada 2 min para mantener la sesión activa (TTL backend: 5 min).
    const heartbeatId = setInterval(() => {
      api.post("/kiosk/session/heartbeat", { session_id: kioskSite.session_id })
        .catch(() => null);
    }, 120_000);

    // Bloqueo de navegación mientras el kiosco esté activo.
    function onBeforeUnload(e) {
      e.preventDefault();
      e.returnValue = "";
      return "";
    }
    function onKeyDown(e) {
      // Bloquea F5, Ctrl+R, Ctrl+W, Alt+F4 (silencioso — el navegador respeta lo que puede).
      const k = (e.key || "").toLowerCase();
      if (k === "f5" || (e.ctrlKey && (k === "r" || k === "w")) || (e.altKey && k === "f4")) {
        e.preventDefault();
        e.stopPropagation();
      }
    }
    function onContextMenu(e) { e.preventDefault(); }
    window.addEventListener("beforeunload", onBeforeUnload);
    window.addEventListener("keydown", onKeyDown, true);
    window.addEventListener("contextmenu", onContextMenu);

    async function boot() {
      try {
        setStatus("Descargando modelos de rostro…");
        const faceapi = await withTimeout(
          loadFaceApi(),
          25000,
          "Tiempo agotado al descargar face-api.js. Verifica la conexión a Internet.",
        );
        await withTimeout(
          loadModels(faceapi),
          40000,
          "Tiempo agotado al cargar los modelos de rostro. Verifica la conexión a Internet o intenta de nuevo.",
        );
        if (cancelled) return;

        setStatus("Cargando personal…");
        const { data } = await api.get("/kiosk/roster");
        if (cancelled) return;
        setRoster(data);

        const labeledList = [];
        for (const u of data) {
          if (Array.isArray(u.face_descriptor) && u.face_descriptor.length > 0) {
            labeledList.push({
              user_id: u.user_id,
              descriptor: Float32Array.from(u.face_descriptor),
            });
          }
        }
        setLabeled(labeledList);

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
        setStatus(labeledList.length === 0
          ? "Sin rostros registrados — usa PIN"
          : "Mira a la cámara para marcar");

        intervalRef.current = setInterval(scan, DETECT_INTERVAL_MS);
      } catch (e) {
        console.error(e);
        setPhase("faceUnavailable");
        setStatus(e?.message || "Reconocimiento facial no disponible — usa PIN");
      }
    }

    async function scan() {
      if (busyRef.current || !videoRef.current || !window.faceapi) return;
      if (phaseRef.current !== "ready") return;
      const labeledArr = labeledRef.current;
      if (!labeledArr || labeledArr.length === 0) return;
      busyRef.current = true;
      try {
        const faceapi = window.faceapi;
        const opts = new faceapi.TinyFaceDetectorOptions({ inputSize: 320, scoreThreshold: 0.5 });

        // Modo reposo: solo detectamos presencia (rápido, sin descriptor).
        // Si hay un rostro nuevo, despertamos y en el siguiente tick se hace el matching completo.
        if (idleRef.current) {
          const face = await faceapi.detectSingleFace(videoRef.current, opts);
          if (face) {
            wakeUp();
          }
          busyRef.current = false;
          return;
        }

        const det = await faceapi
          .detectSingleFace(videoRef.current, opts)
          .withFaceLandmarks()
          .withFaceDescriptor();
        if (!det) {
          // no cara visible: reinicia contador
          consecutiveRef.current = { userId: null, count: 0 };
          // Si llevamos suficiente tiempo sin rostro → entrar en reposo
          if (Date.now() - lastFaceAtRef.current > IDLE_AFTER_MS) {
            setIdle(true);
          }
          busyRef.current = false;
          return;
        }

        // Hay rostro: actualiza timestamp para reset del temporizador
        lastFaceAtRef.current = Date.now();

        // Distancia euclidiana contra TODOS los descriptores + top-2
        const distances = labeledArr.map((ld) => ({
          user_id: ld.user_id,
          distance: faceapi.euclideanDistance(det.descriptor, ld.descriptor),
        }));
        distances.sort((a, b) => a.distance - b.distance);
        const best = distances[0];
        const second = distances[1];

        // Regla 1: umbral estricto
        if (!best || best.distance >= MATCH_THRESHOLD) {
          consecutiveRef.current = { userId: null, count: 0 };
          busyRef.current = false;
          return;
        }

        // Regla 2: margen entre 1º y 2º candidato — evita gemelos/parecidos
        if (second && (second.distance - best.distance) < MATCH_MARGIN) {
          consecutiveRef.current = { userId: null, count: 0 };
          setStatus("Rostro ambiguo — acércate un poco o usa PIN");
          busyRef.current = false;
          return;
        }

        // Regla 3: mismo usuario en N frames consecutivos
        if (consecutiveRef.current.userId === best.user_id) {
          consecutiveRef.current.count += 1;
        } else {
          consecutiveRef.current = { userId: best.user_id, count: 1 };
        }
        if (consecutiveRef.current.count < REQUIRED_CONSECUTIVE) {
          const conf = Math.max(0, Math.round((1 - best.distance) * 100));
          setStatus(`Verificando… ${consecutiveRef.current.count}/${REQUIRED_CONSECUTIVE}  (${conf}%)`);
          busyRef.current = false;
          return;
        }

        // ¡Match confirmado!
        const matched = rosterRef.current.find((u) => u.user_id === best.user_id);
        if (!matched) { busyRef.current = false; return; }
        consecutiveRef.current = { userId: null, count: 0 };
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
      clearInterval(heartbeatId);
      window.removeEventListener("beforeunload", onBeforeUnload);
      window.removeEventListener("keydown", onKeyDown, true);
      window.removeEventListener("contextmenu", onContextMenu);
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  async function confirmMark(user, expectedType) {
    try {
      const { data } = await api.post("/kiosk/attendance/check", {
        user_id: user.user_id,
        type: "auto",  // backend decide para evitar races
        site_id: kioskSite.site_id || null,
      });
      const marked = data?.type || expectedType || "in";
      toast.success(`${user.name.split(" ")[0]} · ${marked === "in" ? "Entrada" : "Salida"} registrada`);
      setPhase("success");
      setCurrent({ ...user, marked });
      // Detectar visitas pendientes del anfitrión.
      // Consultamos SIEMPRE (tanto en entrada como en salida) porque una visita
      // puede haberse agendado justo antes/después de una marca de asistencia.
      let visits = [];
      try {
        const r = await api.get(`/kiosk/pending-visits/${user.user_id}`);
        visits = r.data || [];
      } catch (_) { visits = []; }
      if (visits.length > 0) {
        setPendingVisits(visits);
        // No auto-cierre — el usuario decide si atiende la visita
      } else {
        setTimeout(() => { setCurrent(null); setPhase("ready"); }, 2200);
      }
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    }
  }

  function lockKiosk() {
    // Cierra sesión y devuelve el kiosco al desbloqueo (donde se pedirá auth admin + sede).
    const sid = kioskSite.session_id;
    if (sid) api.post("/kiosk/session/close", { session_id: sid }).catch(() => null);
    clearKioskSite();
    setKioskUnlocked(false);
    streamRef.current?.getTracks().forEach((t) => t.stop());
    if (intervalRef.current) clearInterval(intervalRef.current);
    // Si estamos como usuario `kiosk`, también cerramos la sesión de auth
    // para que "Regresar al panel administrativo" no rebote a /kiosk/auto.
    if (currentUser?.role === "kiosk") {
      logout().finally(() => nav("/kiosk", { replace: true }));
      return;
    }
    nav("/kiosk", { replace: true });
  }

  function exitToAdmin() {
    const sid = kioskSite.session_id;
    if (sid) api.post("/kiosk/session/close", { session_id: sid }).catch(() => null);
    clearKioskSite();
    setKioskUnlocked(false);
    streamRef.current?.getTracks().forEach((t) => t.stop());
    if (intervalRef.current) clearInterval(intervalRef.current);
    // Si la sesión actual pertenece a un usuario `kiosk` (Kiosco TBP / LCH),
    // hay que cerrarla; de lo contrario HomeRedirect nos rebotaría a
    // `/kiosk/auto`. Así el admin que desbloqueó vuelve a la pantalla de login
    // para entrar con sus propias credenciales.
    if (currentUser?.role === "kiosk") {
      logout().finally(() => nav("/login", { replace: true }));
      return;
    }
    nav("/", { replace: true });
  }

  async function saveReenroll(dataUrl, descriptor) {
    if (!reenrollCapture) return;
    setReenrollSaving(true);
    try {
      const fd = new FormData();
      fd.append("user_id", reenrollCapture.user_id);
      fd.append("pin", reenrollCapture.pin);
      fd.append("selfie_base64", dataUrl);
      if (Array.isArray(descriptor) && descriptor.length > 0) {
        fd.append("face_descriptor", JSON.stringify(descriptor));
      }
      await api.post("/kiosk/reenroll-face", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success(`Rostro de ${reenrollCapture.name.split(" ")[0]} actualizado`);
      // recargar roster + reconstruir descriptores para el matcher endurecido
      try {
        const { data } = await api.get("/kiosk/roster");
        setRoster(data);
        const rebuilt = [];
        for (const u of data) {
          if (Array.isArray(u.face_descriptor) && u.face_descriptor.length > 0) {
            rebuilt.push({ user_id: u.user_id, descriptor: Float32Array.from(u.face_descriptor) });
          }
        }
        setLabeled(rebuilt);
      } catch (_) { /* noop */ }
      setReenrollCapture(null);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally { setReenrollSaving(false); }
  }

  // Formato "Miércoles, 22 de julio" (weekday y mes capitalizados, "de" en minúscula).
  const TZ_CARACAS = "America/Caracas";
  const wk = clock.toLocaleDateString("es-VE", { weekday: "long", timeZone: TZ_CARACAS });
  const mo = clock.toLocaleDateString("es-VE", { month: "long", timeZone: TZ_CARACAS });
  const dayNum = clock.toLocaleDateString("es-VE", { day: "numeric", timeZone: TZ_CARACAS });
  const dateStr = `${wk.charAt(0).toUpperCase()}${wk.slice(1)}, ${dayNum} de ${mo}`;
  const timeStr = clock.toLocaleTimeString("es-VE", {
    hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: TZ_CARACAS,
  });

  return (
    <div
      className="min-h-screen bg-primary text-primary-foreground relative overflow-hidden flex flex-col"
      data-testid="kiosk-scan-page"
      onPointerDown={wakeUp}
    >
      <div className="pointer-events-none absolute -top-40 -left-40 h-[520px] w-[520px] rounded-full border border-white/5" />
      <div className="pointer-events-none absolute -bottom-32 -right-32 h-[420px] w-[420px] rounded-full bg-accent/10 blur-3xl" />

      {/* Contenedor atenuable — todo el contenido se oscurece en modo reposo */}
      <div className={"flex-1 flex flex-col transition-[filter,opacity] duration-[1200ms] ease-out " + (idle ? "brightness-[0.06] opacity-70" : "brightness-100 opacity-100")}>

      {/* Header */}
      <header className="relative flex items-center justify-between gap-3 px-4 py-4 border-b border-white/5">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <div className="h-10 w-10 rounded-xl bg-accent grid place-items-center shrink-0">
            <ScanFace className="h-5 w-5 text-primary" />
          </div>
          <div className="min-w-0">
            <p className="text-[10px] uppercase tracking-[0.3em] text-white/50 leading-none">Mega Soft · Kiosco</p>
            {kioskSite.site_name ? (
              <p
                className="mt-1 flex items-center gap-2 text-2xl sm:text-3xl md:text-4xl font-extrabold tracking-tight text-accent leading-tight truncate drop-shadow-[0_0_12px_rgba(250,204,21,0.25)]"
                data-testid="kiosk-site-badge"
                title={kioskSite.site_name}
              >
                <MapPin className="h-6 w-6 sm:h-7 sm:w-7 shrink-0" />
                <span className="truncate">{kioskSite.site_name}</span>
              </p>
            ) : (
              <p className="text-sm font-semibold leading-tight mt-0.5">Kiosco de asistencia</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="text-right hidden sm:block">
            <p className="text-[10px] uppercase tracking-widest text-white/40 leading-none">Hoy</p>
            <p className="text-sm font-mono font-semibold leading-tight mt-0.5">{timeStr}</p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowExit(true)}
            className="rounded-full h-9 px-3 text-white/70 hover:bg-white/10 hover:text-white text-xs"
            data-testid="kiosk-exit-btn"
          >
            <DoorOpen className="h-4 w-4 mr-1.5" />
            Salir
          </Button>
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
            <p className="text-white/60 text-sm mt-2 max-w-md mx-auto whitespace-pre-line">
              {status || "Los empleados pueden marcar con PIN mientras se resuelve."}
            </p>
            <div className="mt-6 flex flex-col sm:flex-row items-center justify-center gap-3">
              <Button onClick={() => setShowPinList(true)}
                className="h-14 rounded-full bg-accent hover:bg-accent/90 text-primary font-semibold px-8 text-base"
                data-testid="kiosk-face-unavailable-pin-btn">
                <KeyRound className="h-5 w-5 mr-2" /> Marcar con PIN
              </Button>
              <Button
                variant="outline"
                onClick={() => window.location.reload()}
                className="h-14 rounded-full border-2 border-white/30 bg-white/5 text-white hover:bg-white/10 px-6 text-base"
                data-testid="kiosk-face-retry-btn"
              >
                <RefreshCcw className="h-4 w-4 mr-2" /> Reintentar carga
              </Button>
            </div>
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

              {phase === "ready" && !idle && (
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

      {/* Botón fijo "Visitas" — esquina inferior izquierda del kiosco.
          Permite acceder al listado de citas del día sin depender del marcaje del anfitrión. */}
      <button
        type="button"
        onClick={() => setVisitsBrowserOpen(true)}
        className="absolute left-4 bottom-24 md:bottom-6 z-30 rounded-2xl bg-white/10 hover:bg-white/20 active:bg-white/25 backdrop-blur-md border border-white/15 text-white px-4 py-3 flex items-center gap-2 shadow-xl transition-all"
        data-testid="kiosk-visits-fab"
      >
        <div className="h-9 w-9 rounded-xl bg-accent grid place-items-center">
          <UserCircle2 className="h-5 w-5 text-primary" />
        </div>
        <div className="text-left">
          <p className="text-[10px] uppercase tracking-[0.25em] text-white/60 leading-none">Recepción</p>
          <p className="text-sm font-semibold leading-tight mt-0.5">Visitas del día</p>
        </div>
      </button>

      {/* Bottom actions */}
      <div className="relative px-4 pb-6 pt-2 border-t border-white/5 flex items-center gap-2">
        <Button variant="ghost" onClick={() => setShowLock(true)}
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

      </div>{/* /contenedor atenuable */}

      {/* Badge sutil "En reposo" — visible aún con la pantalla atenuada */}
      {idle && (
        <div className="pointer-events-none absolute bottom-6 left-1/2 -translate-x-1/2 z-20 flex items-center gap-2 text-[10px] tracking-[0.35em] uppercase text-white/40" data-testid="kiosk-idle-badge">
          <span className="h-1.5 w-1.5 rounded-full bg-white/40 animate-pulse" />
          En reposo · acércate para activar
        </div>
      )}

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
          <DialogFooter className="flex-row gap-3 sm:justify-center">
            <Button variant="outline"
              className="flex-1 h-16 rounded-full text-lg font-semibold border-2 border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-100 dark:hover:bg-slate-800"
              onClick={() => { setPhase("ready"); setCurrent(null); }}
              data-testid="kiosk-match-cancel">
              <X className="h-5 w-5 mr-2" /> No soy yo
            </Button>
            <Button
              onClick={() => confirmMark(current, current?.nextType)}
              className={
                "flex-1 h-16 rounded-full text-lg font-bold text-white shadow-lg " +
                (current?.nextType === "in"
                  ? "bg-emerald-600 hover:bg-emerald-700 focus-visible:ring-2 focus-visible:ring-emerald-400"
                  : "bg-blue-600 hover:bg-blue-700 focus-visible:ring-2 focus-visible:ring-blue-400")
              }
              data-testid="kiosk-match-confirm"
            >
              Sí, soy yo <ArrowRight className="h-5 w-5 ml-2" />
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Success overlay */}
      {phase === "success" && current && (
        <div className="fixed inset-0 grid place-items-center bg-primary/95 z-50 animate-in fade-in" data-testid="kiosk-success">
          <div className="text-center px-6 max-w-md">
            <CheckCircle2 className="h-28 w-28 text-emerald-400 mx-auto mb-4 animate-bounce" />
            <p className="text-3xl font-bold text-primary-foreground">¡Listo, {current.name.split(" ")[0]}!</p>
            <p className="font-serif-display text-accent text-2xl mt-1">
              {current.marked === "in" ? "entrada registrada" : "salida registrada"}
            </p>
            <p className="text-white/60 text-sm mt-3 font-mono">{timeStr}</p>

            {pendingVisits.length > 0 && (
              <div className="mt-6 space-y-2">
                <p className="text-white/70 text-sm">Tienes {pendingVisits.length} visita{pendingVisits.length > 1 ? "s" : ""} pendiente{pendingVisits.length > 1 ? "s" : ""}</p>
                <Button
                  onClick={() => { setActiveVisit(pendingVisits[0]); setVisitVisitorIdx(0); }}
                  className="rounded-full h-14 px-8 bg-accent hover:bg-accent/90 text-primary font-bold text-lg shadow-lg"
                  data-testid="kiosk-visit-btn"
                >
                  <UserCircle2 className="h-5 w-5 mr-2" /> Visita
                </Button>
                <button
                  type="button"
                  onClick={() => { setPendingVisits([]); setCurrent(null); setPhase("ready"); }}
                  className="block w-full text-xs text-white/40 hover:text-white/70 mt-2"
                >
                  Omitir por ahora
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      <VisitSelfieDialog
        visit={activeVisit}
        visitorIdx={visitVisitorIdx}
        onCaptured={async (dataUrl) => {
          try {
            const { data } = await api.post(`/visits/${activeVisit.visit_id}/capture-selfie`, {
              visitor_index: visitVisitorIdx,
              selfie_base64: dataUrl,
            });
            if (data.status === "completed") {
              toast.success("Visita completada");
              // Pasar a la siguiente visita pendiente o cerrar
              const remaining = pendingVisits.filter((v) => v.visit_id !== activeVisit.visit_id);
              setPendingVisits(remaining);
              setActiveVisit(null);
              setVisitVisitorIdx(0);
              if (remaining.length === 0) {
                setTimeout(() => { setCurrent(null); setPhase("ready"); }, 800);
              }
            } else {
              setVisitVisitorIdx((i) => i + 1);
            }
          } catch (e) {
            toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
          }
        }}
        onCancel={() => { setActiveVisit(null); setVisitVisitorIdx(0); }}
      />

      {/* Nuevo flujo: navegador de visitas del día en el Kiosco (recepción) */}
      <VisitsBrowserDialog
        open={visitsBrowserOpen}
        onClose={() => setVisitsBrowserOpen(false)}
        onVisitSelected={(visit) => {
          // Ya no verificamos un PIN global — cada visitante se autentica por
          // separado con los últimos 3 dígitos de su cédula dentro del flujo de selfies.
          setVisitsBrowserOpen(false);
          setActiveVisit(visit);
          setVisitVisitorIdx(0);
        }}
      />

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

      {/* Salir del kiosco — requiere credenciales admin */}
      <ExitKioskDialog
        open={showExit}
        onCancel={() => setShowExit(false)}
        onSuccess={() => { setShowExit(false); exitToAdmin(); }}
      />

      {/* Bloquear kiosco — también requiere credenciales admin */}
      <ExitKioskDialog
        open={showLock}
        title="Bloquear kiosco"
        description="Confirma con tus credenciales de administrador para liberar la sede y bloquear este dispositivo."
        confirmLabel="Bloquear"
        icon="lock"
        onCancel={() => setShowLock(false)}
        onSuccess={() => { setShowLock(false); lockKiosk(); }}
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
        <PasswordInput
          inputMode="numeric"
          pattern="[0-9]*"
          value={pin}
          onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 8))}
          placeholder="••••"
          className="text-3xl text-center h-16 tracking-widest font-mono"
          data-testid="kiosk-reenroll-pin-input"
          toggleTestId="kiosk-reenroll-pin-toggle"
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
    const removeAccents = (str) => str ? str.normalize("NFD").replace(/[\u0300-\u036f]/g, "") : "";
    const n = removeAccents(q.toLowerCase()).trim();
    
    return (roster || [])
      .filter((u) => !n
        || removeAccents(u.name.toLowerCase()).includes(n)
        || (u.cedula || "").includes(n))
      .slice(0, 500);
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
              type="button"
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

        <PasswordInput
          inputMode="numeric"
          pattern="[0-9]*"
          value={pin}
          onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 8))}
          placeholder="••••"
          className="text-3xl text-center h-16 tracking-widest font-mono mt-2"
          data-testid="kiosk-pin-input"
          toggleTestId="kiosk-pin-input-toggle"
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

/** Dialog para salir del kiosco — pide credenciales de administrador */
function ExitKioskDialog({ open, onCancel, onSuccess, title, description, confirmLabel, icon }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) { setEmail(""); setPassword(""); }
  }, [open]);

  async function verify(e) {
    e?.preventDefault?.();
    if (!email || !password) { toast.error("Ingresa correo y contraseña"); return; }
    setBusy(true);
    try {
      await api.post("/kiosk/unlock", { email: email.trim(), password });
      toast.success("Credenciales válidas");
      onSuccess();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Credenciales inválidas");
    } finally { setBusy(false); }
  }

  const Icon = icon === "lock" ? LockKeyhole : DoorOpen;

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onCancel()}>
      <DialogContent className="max-w-sm" data-testid="kiosk-exit-dialog">
        <DialogHeader className="items-center text-center">
          <div className="h-14 w-14 rounded-2xl bg-primary/10 grid place-items-center mb-2">
            <Icon className="h-7 w-7 text-primary dark:text-foreground" />
          </div>
          <DialogTitle>{title || "Salir del kiosco"}</DialogTitle>
          <DialogDescription>
            {description || "Confirma con tus credenciales de administrador para regresar al panel."}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={verify} className="space-y-3">
          <div className="space-y-1.5">
            <Label className="text-xs">Correo del administrador</Label>
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="admin@empresa.com"
              className="h-11"
              autoFocus
              data-testid="kiosk-exit-email"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Contraseña</Label>
            <PasswordInput
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="h-11"
              data-testid="kiosk-exit-password"
              toggleTestId="kiosk-exit-password-toggle"
            />
          </div>
          <DialogFooter className="flex-row gap-2 sm:justify-stretch pt-2">
            <Button type="button" variant="outline" onClick={onCancel}
              className="h-12 rounded-full flex-1" data-testid="kiosk-exit-cancel">
              <X className="h-4 w-4 mr-1.5" /> Cancelar
            </Button>
            <Button type="submit" disabled={busy}
              className="h-12 rounded-full flex-1 bg-primary hover:bg-primary/90 font-semibold"
              data-testid="kiosk-exit-confirm">
              {busy ? "Verificando…" : (<>{confirmLabel || "Salir"} <ArrowRight className="h-4 w-4 ml-1.5" /></>)}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}



/** Modal de captura de selfie del visitante N. Cámara + botón "Capturar". */
function VisitSelfieDialog({ visit, visitorIdx, onCaptured, onCancel }) {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [subStep, setSubStep] = useState("pin"); // "pin" → "camera"
  const [pin, setPin] = useState("");
  const [pinError, setPinError] = useState(null);
  const [verifying, setVerifying] = useState(false);
  const visitor = visit?.visitors?.[visitorIdx];

  // Cada vez que cambia el visitante activo se vuelve al paso de PIN.
  useEffect(() => {
    setSubStep("pin"); setPin(""); setPinError(null);
  }, [visit?.visit_id, visitorIdx]);

  // Cámara — sólo se enciende una vez el PIN individual está validado.
  useEffect(() => {
    if (!visit || subStep !== "camera") return;
    let stopped = false;
    (async () => {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: "user", width: { ideal: 720 }, height: { ideal: 720 } },
          audio: false,
        });
        if (stopped) { stream.getTracks().forEach((t) => t.stop()); return; }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play().catch(() => null);
        }
        setReady(true);
      } catch (_) { /* ignore */ }
    })();
    return () => {
      stopped = true;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      setReady(false);
    };
  }, [visit, subStep]);

  async function submitPin() {
    if (!visit || !visitor) return;
    const clean = (pin || "").trim();
    if (!/^\d{3}$/.test(clean)) {
      setPinError("Debes ingresar 3 dígitos");
      return;
    }
    setVerifying(true); setPinError(null);
    try {
      await api.post(`/kiosk/visits/${visit.visit_id}/verify-visitor`, {
        visitor_index: visitorIdx, pin: clean,
      });
      setSubStep("camera");
    } catch (e) {
      const code = e.response?.status;
      if (code === 403) setPinError("Los 3 dígitos no coinciden con tu cédula. Intenta de nuevo.");
      else setPinError(formatApiErrorDetail(e.response?.data?.detail) || e.message);
      setPin("");
    } finally { setVerifying(false); }
  }

  async function capture() {
    if (!videoRef.current) return;
    setBusy(true);
    try {
      const v = videoRef.current;
      const size = Math.min(v.videoWidth, v.videoHeight);
      const c = document.createElement("canvas");
      c.width = 480; c.height = 480;
      const ctx = c.getContext("2d");
      const sx = (v.videoWidth - size) / 2;
      const sy = (v.videoHeight - size) / 2;
      ctx.save(); ctx.translate(c.width, 0); ctx.scale(-1, 1);
      ctx.drawImage(v, sx, sy, size, size, 0, 0, c.width, c.height);
      ctx.restore();
      const dataUrl = c.toDataURL("image/jpeg", 0.85);
      await onCaptured(dataUrl);
    } finally { setBusy(false); }
  }

  if (!visit || !visitor) return null;
  const total = visit.visitors.length;

  return (
    <Dialog open onOpenChange={(v) => !v && onCancel()}>
      <DialogContent className="max-w-md bg-primary text-primary-foreground border-white/10" data-testid="kiosk-visit-selfie">
        <DialogHeader className="items-center text-center">
          <DialogTitle className="text-2xl">
            Visitante {visitorIdx + 1} / {total}
          </DialogTitle>
          <DialogDescription className="text-white/70">
            <span className="block text-lg font-semibold text-white">{visitor.name}</span>
            {subStep === "pin"
              ? (<span className="text-sm">Introduce los últimos <b>3 dígitos</b> de tu Cédula de Identidad</span>)
              : (<span className="text-sm">Mira a la cámara y toca <b>Capturar</b></span>)}
          </DialogDescription>
        </DialogHeader>

        {subStep === "pin" ? (
          <>
            <div className="grid place-items-center py-2">
              <PinPad3
                value={pin}
                onChange={(v) => { setPin(v); setPinError(null); }}
                disabled={verifying}
              />
            </div>
            {pinError && (
              <p className="text-center text-sm text-red-300" data-testid="kiosk-visitor-pin-error">
                {pinError}
              </p>
            )}
            <DialogFooter className="flex-row gap-2 sm:justify-stretch pt-2">
              <Button variant="outline" onClick={onCancel} disabled={verifying}
                className="rounded-full h-12 flex-1 bg-white/5 border-white/20 text-white hover:bg-white/10"
                data-testid="kiosk-visitor-pin-cancel">
                Cancelar
              </Button>
              <Button onClick={submitPin} disabled={verifying || pin.length !== 3}
                className="rounded-full h-12 flex-[1.4] bg-accent hover:bg-accent/90 text-primary font-bold"
                data-testid="kiosk-visitor-pin-submit">
                {verifying ? "Validando…" : (<>Validar <ArrowRight className="h-4 w-4 ml-1.5" /></>)}
              </Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <div className="relative aspect-square w-full max-w-[320px] mx-auto rounded-2xl overflow-hidden border-2 border-accent/50 bg-black/40">
              <video ref={videoRef} autoPlay muted playsInline
                className="absolute inset-0 h-full w-full object-cover [transform:scaleX(-1)]" />
              <div className="pointer-events-none absolute inset-6 rounded-full border-2 border-accent/70" />
            </div>
            <DialogFooter className="flex-row gap-2 sm:justify-stretch">
              <Button variant="outline" onClick={onCancel} disabled={busy}
                className="rounded-full h-12 flex-1 bg-white/5 border-white/20 text-white hover:bg-white/10"
                data-testid="kiosk-visit-selfie-cancel">
                Cancelar
              </Button>
              <Button onClick={capture} disabled={!ready || busy}
                className="rounded-full h-12 flex-1 bg-accent hover:bg-accent/90 text-primary font-bold"
                data-testid="kiosk-visit-selfie-capture">
                {busy ? "Guardando…" : (<><Camera className="h-4 w-4 mr-1.5" /> Capturar</>)}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}


/** VisitsBrowserDialog — listado de visitas del día + vista "Visita Seleccionada".
 *  El PIN individual por cédula se pide más adelante, en el flujo de selfies. */
function VisitsBrowserDialog({ open, onClose, onVisitSelected }) {
  const [step, setStep] = useState("list");  // "list" | "confirm"
  const [visits, setVisits] = useState([]);
  const [loading, setLoading] = useState(false);
  const [target, setTarget] = useState(null);

  async function load() {
    setLoading(true);
    try {
      const { data } = await api.get("/kiosk/visits/today");
      setVisits(Array.isArray(data) ? data : []);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
      setVisits([]);
    } finally { setLoading(false); }
  }

  useEffect(() => {
    if (!open) return;
    setStep("list"); setTarget(null);
    load();
  }, [open]);

  function pickVisit(v) { setTarget(v); setStep("confirm"); }

  function fmtHora(iso) {
    if (!iso) return "";
    try {
      return new Date(iso).toLocaleTimeString("es-VE", { hour: "2-digit", minute: "2-digit" });
    } catch (_) { return ""; }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent
        className="max-w-lg text-primary-foreground bg-primary border-white/10"
        data-testid="kiosk-visits-browser"
      >
        {step === "list" && (
          <>
            <DialogHeader className="text-center items-center">
              <div className="h-14 w-14 rounded-2xl bg-accent grid place-items-center mb-2">
                <UserCircle2 className="h-7 w-7 text-primary" />
              </div>
              <DialogTitle className="text-primary-foreground">Visitas del día</DialogTitle>
              <DialogDescription className="text-white/70">
                Selecciona una visita para autorizarla con el PIN de 3 dígitos.
              </DialogDescription>
            </DialogHeader>

            {loading ? (
              <div className="py-10 grid place-items-center text-white/60 text-sm">
                <Loader2 className="h-6 w-6 animate-spin" />
                <p className="mt-2">Cargando visitas…</p>
              </div>
            ) : visits.length === 0 ? (
              <div className="py-10 text-center text-white/70" data-testid="kiosk-visits-empty">
                <UserCircle2 className="h-8 w-8 text-white/40 mx-auto mb-2" />
                <p className="text-sm">No hay visitas agendadas para hoy.</p>
              </div>
            ) : (
              <div className="space-y-2 max-h-[420px] overflow-y-auto pr-1" data-testid="kiosk-visits-list">
                {visits.map((v) => (
                  <button
                    key={v.visit_id}
                    type="button"
                    onClick={() => pickVisit(v)}
                    className="w-full text-left rounded-xl border border-white/15 bg-white/5 hover:bg-white/10 hover:border-accent/50 transition-all p-3 flex items-center gap-3"
                    data-testid={`kiosk-visit-item-${v.visit_id}`}
                  >
                    <div className="h-10 w-10 rounded-xl bg-accent/20 grid place-items-center shrink-0">
                      <Building2 className="h-5 w-5 text-accent" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-white truncate">
                        {v.company_name || v.primary_visitor_name || "Visitante"}
                      </p>
                      <p className="text-[11px] text-white/60 leading-tight">
                        Anfitrión: <b className="text-white/90">{v.host_name}</b>
                      </p>
                      <p className="text-[11px] text-white/60 leading-tight mt-0.5 flex items-center gap-1">
                        <Clock3 className="h-3 w-3" /> {fmtHora(v.scheduled_at)} · {v.visitors_count} visitante{v.visitors_count === 1 ? "" : "s"}
                        {v.purpose_label && <span className="ml-1">· {v.purpose_label}</span>}
                      </p>
                    </div>
                    <ArrowRight className="h-4 w-4 text-white/40 shrink-0" />
                  </button>
                ))}
              </div>
            )}

            <DialogFooter className="pt-2">
              <Button
                variant="outline"
                onClick={onClose}
                className="h-11 rounded-full w-full bg-white/5 border-white/20 text-white hover:bg-white/10"
                data-testid="kiosk-visits-close"
              >
                Cerrar
              </Button>
            </DialogFooter>
          </>
        )}

        {step === "confirm" && target && (
          <>
            <DialogHeader className="text-center items-center">
              <div className="h-14 w-14 rounded-2xl bg-accent grid place-items-center mb-2">
                <UserCircle2 className="h-7 w-7 text-primary" />
              </div>
              <DialogTitle className="text-primary-foreground">Visita seleccionada</DialogTitle>
              <DialogDescription className="text-white/70">
                Verifica los datos y toca <b>Comenzar</b> para iniciar el registro.
              </DialogDescription>
            </DialogHeader>

            <div className="rounded-xl bg-white/5 border border-white/10 p-4 space-y-2.5">
              <div>
                <p className="text-[10px] uppercase tracking-[0.3em] text-white/50">Anfitrión</p>
                <p className="text-lg font-semibold text-white leading-tight">{target.host_name || "—"}</p>
              </div>
              {(target.company_name || target.purpose_label) && (
                <div>
                  <p className="text-[10px] uppercase tracking-[0.3em] text-white/50">
                    {target.company_name ? "Empresa representada" : "Motivo"}
                  </p>
                  <p className="text-sm font-medium text-white leading-tight">
                    {target.company_name || target.purpose_label || target.purpose_other || "—"}
                    {target.company_name && target.purpose_label && (
                      <span className="text-white/60 text-xs"> · {target.purpose_label}</span>
                    )}
                  </p>
                </div>
              )}
              <div>
                <p className="text-[10px] uppercase tracking-[0.3em] text-white/50">
                  Primer visitante ({target.visitors_count} en total)
                </p>
                <p className="text-lg font-semibold text-accent leading-tight" data-testid="kiosk-visit-first-visitor">
                  {target.visitors?.[0]?.name || target.primary_visitor_name || "—"}
                </p>
              </div>
              <div className="flex items-center gap-2 text-[11px] text-white/60 pt-1 border-t border-white/10">
                <Clock3 className="h-3 w-3" />
                <span>Programada para las {fmtHora(target.scheduled_at)}</span>
              </div>
            </div>

            <DialogFooter className="flex-row gap-2 sm:justify-stretch pt-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setStep("list")}
                className="h-11 rounded-full flex-1 bg-white/5 border-white/20 text-white hover:bg-white/10"
                data-testid="kiosk-visit-confirm-back"
              >
                Atrás
              </Button>
              <Button
                type="button"
                onClick={() => onVisitSelected(target)}
                className="h-11 rounded-full flex-[1.4] bg-accent hover:bg-accent/90 text-primary font-bold"
                data-testid="kiosk-visit-confirm-start"
              >
                Comenzar <ArrowRight className="h-4 w-4 ml-1.5" />
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

/** Teclado numérico de 3 dígitos para el PIN de visitas. */
function PinPad3({ value, onChange, disabled }) {
  function press(d) {
    if (disabled) return;
    if ((value || "").length >= 3) return;
    onChange((value || "") + d);
  }
  function back() {
    if (disabled) return;
    onChange((value || "").slice(0, -1));
  }
  function clear() {
    if (disabled) return;
    onChange("");
  }
  const digits = (value || "").padEnd(3, "·").split("");
  return (
    <div className="w-full max-w-[280px] space-y-3">
      <div className="flex justify-center gap-3">
        {digits.map((d, i) => (
          <div
            key={i}
            className={
              "h-14 w-14 rounded-xl border grid place-items-center text-3xl font-mono font-bold " +
              (d === "·" ? "text-white/25 border-white/10" : "text-white border-accent/60 bg-white/5")
            }
            data-testid={`kiosk-visit-pin-slot-${i}`}
          >
            {d === "·" ? "•" : "•"}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-3 gap-2">
        {["1","2","3","4","5","6","7","8","9"].map((d) => (
          <button
            key={d}
            type="button"
            onClick={() => press(d)}
            disabled={disabled}
            className="h-14 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-white text-2xl font-semibold transition-colors disabled:opacity-40"
            data-testid={`kiosk-visit-pin-key-${d}`}
          >
            {d}
          </button>
        ))}
        <button
          type="button"
          onClick={clear}
          disabled={disabled}
          className="h-14 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-xs text-white/70 uppercase tracking-widest disabled:opacity-40"
          data-testid="kiosk-visit-pin-clear"
        >
          Borrar
        </button>
        <button
          type="button"
          onClick={() => press("0")}
          disabled={disabled}
          className="h-14 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-white text-2xl font-semibold disabled:opacity-40"
          data-testid="kiosk-visit-pin-key-0"
        >
          0
        </button>
        <button
          type="button"
          onClick={back}
          disabled={disabled}
          className="h-14 rounded-xl bg-white/5 hover:bg-white/10 border border-white/10 text-white grid place-items-center disabled:opacity-40"
          data-testid="kiosk-visit-pin-backspace"
        >
          <X className="h-5 w-5" />
        </button>
      </div>
    </div>
  );
}

