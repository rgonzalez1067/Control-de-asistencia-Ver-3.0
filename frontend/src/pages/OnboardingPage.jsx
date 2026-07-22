import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Camera, Check, RefreshCw, ArrowLeft, ShieldCheck, Sparkles } from "lucide-react";
import { toast } from "sonner";

/**
 * OnboardingPage — captura una selfie con getUserMedia y la envía a
 * `/api/onboarding/selfie`. El descriptor facial (face-api.js) se
 * incorporará en la Fase 3 desde CDN; por ahora enviamos solo la foto.
 */
export default function OnboardingPage() {
  const { user, refresh } = useAuth();
  const nav = useNavigate();
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const streamRef = useRef(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState(null);
  const [preview, setPreview] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let stopped = false;
    async function start() {
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
      } catch (e) {
        setError("No pudimos acceder a tu cámara. Autoriza el permiso o usa otro navegador.");
      }
    }
    start();
    return () => {
      stopped = true;
      streamRef.current?.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    };
  }, []);

  function capture() {
    if (!videoRef.current) return;
    const v = videoRef.current;
    const size = Math.min(v.videoWidth, v.videoHeight);
    const c = canvasRef.current;
    c.width = 480; c.height = 480;
    const ctx = c.getContext("2d");
    const sx = (v.videoWidth - size) / 2;
    const sy = (v.videoHeight - size) / 2;
    // mirror horizontally so it matches the on-screen preview
    ctx.save();
    ctx.translate(c.width, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(v, sx, sy, size, size, 0, 0, c.width, c.height);
    ctx.restore();
    setPreview(c.toDataURL("image/jpeg", 0.85));
  }

  async function save() {
    if (!preview) return;
    setSaving(true);
    try {
      await api.post("/onboarding/selfie", { selfie_base64: preview });
      toast.success("¡Rostro registrado! Ya puedes usar el kiosco.");
      await refresh();
      nav("/", { replace: true });
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="p-4 sm:p-8 max-w-4xl mx-auto" data-testid="onboarding-page">
      <button
        onClick={() => nav(-1)}
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary mb-6 transition-colors"
        data-testid="onboarding-back"
      >
        <ArrowLeft className="h-4 w-4" /> Volver
      </button>

      <div className="grid lg:grid-cols-[1.1fr_1fr] gap-8">
        <div>
          <Badge variant="secondary" className="rounded-full mb-3">
            Registro biométrico
          </Badge>
          <h1 className="text-3xl sm:text-4xl font-bold text-foreground">
            Registra tu rostro
            <span className="block font-serif-display text-primary/60 text-2xl mt-1">
              en menos de 15 segundos.
            </span>
          </h1>
          <p className="text-muted-foreground mt-3 text-sm max-w-md">
            La selfie se usará para verificar tu identidad en el kiosco compartido.
            Se guarda cifrada en el servidor y nunca se comparte.
          </p>

          <ul className="mt-6 space-y-3 max-w-md">
            {[
              { icon: Sparkles, t: "Luz frontal y natural", d: "Evita luces detrás de ti." },
              { icon: ShieldCheck, t: "Solo tu rostro en cuadro", d: "Sin gorra, lentes oscuros ni mascarilla." },
              { icon: Camera, t: "Mira directo a la cámara", d: "Neutral, sin expresiones exageradas." },
            ].map((it) => (
              <li key={it.t} className="flex items-start gap-3">
                <div className="h-9 w-9 rounded-xl bg-primary/10 text-foreground grid place-items-center shrink-0">
                  <it.icon className="h-4 w-4" />
                </div>
                <div>
                  <p className="text-sm font-medium text-foreground">{it.t}</p>
                  <p className="text-xs text-muted-foreground">{it.d}</p>
                </div>
              </li>
            ))}
          </ul>

          <div className="mt-6 rounded-xl border border-border/70 bg-card/60 backdrop-blur px-4 py-3 text-xs text-muted-foreground max-w-md">
            Sesión de: <b className="text-foreground">{user?.name}</b> · {user?.email}
          </div>
        </div>

        <Card className="border-border/70 bg-card/80 backdrop-blur">
          <CardContent className="p-4 sm:p-6">
            <div className="relative aspect-square w-full max-w-[420px] mx-auto rounded-3xl overflow-hidden bg-primary/95 shadow-xl shadow-primary/20">
              {/* video preview */}
              {!preview && (
                <>
                  <video
                    ref={videoRef}
                    muted
                    playsInline
                    className="absolute inset-0 h-full w-full object-cover scale-x-[-1]"
                    data-testid="onboarding-video"
                  />
                  <div className="absolute inset-0 pointer-events-none">
                    <div className="absolute inset-6 border-2 border-dashed border-accent/70 rounded-3xl" />
                  </div>
                </>
              )}
              {preview && (
                <img src={preview} alt="preview" className="absolute inset-0 h-full w-full object-cover" data-testid="onboarding-preview" />
              )}
              {!ready && !preview && (
                <div className="absolute inset-0 grid place-items-center text-white text-sm">
                  {error ? (
                    <div className="text-center px-4">
                      <p className="text-red-200 font-medium">Cámara bloqueada</p>
                      <p className="text-xs text-white/70 mt-2">{error}</p>
                    </div>
                  ) : "Iniciando cámara…"}
                </div>
              )}
            </div>
            <canvas ref={canvasRef} className="hidden" />

            <div className="mt-6 flex items-center justify-center gap-3">
              {!preview ? (
                <Button
                  onClick={capture}
                  disabled={!ready}
                  className="rounded-full h-12 px-6 bg-primary hover:bg-primary/90 text-primary-foreground shadow-lg shadow-primary/20"
                  data-testid="onboarding-capture"
                >
                  <Camera className="h-4 w-4 mr-2" /> Capturar
                </Button>
              ) : (
                <>
                  <Button
                    variant="outline"
                    onClick={() => setPreview(null)}
                    className="rounded-full h-12 px-5"
                    data-testid="onboarding-retake"
                  >
                    <RefreshCw className="h-4 w-4 mr-1.5" /> Repetir
                  </Button>
                  <Button
                    onClick={save}
                    disabled={saving}
                    className="rounded-full h-12 px-6 bg-emerald-600 hover:bg-emerald-700 text-white"
                    data-testid="onboarding-save"
                  >
                    <Check className="h-4 w-4 mr-1.5" /> {saving ? "Guardando…" : "Confirmar rostro"}
                  </Button>
                </>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
