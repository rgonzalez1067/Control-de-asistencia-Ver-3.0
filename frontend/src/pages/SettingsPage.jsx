import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatApiErrorDetail } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { Settings2, Save, Image as ImageIcon, RefreshCw, ShieldCheck, ScanFace, ExternalLink } from "lucide-react";

const TIMEZONES = [
  "America/Caracas", "America/Bogota", "America/Mexico_City", "America/Buenos_Aires",
  "America/Santiago", "America/Lima", "America/Panama", "UTC",
];

export default function SettingsPage() {
  const nav = useNavigate();
  const [form, setForm] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const logoRef = useRef(null);

  async function load() {
    setLoading(true);
    try {
      const { data } = await api.get("/settings");
      setForm({
        name: data.name || "",
        identification_method: data.identification_method || "face",
        kiosk_enabled: !!data.kiosk_enabled,
        logo_base64: data.logo_base64 || "",
        timezone: data.timezone || "America/Caracas",
      });
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);

  async function save() {
    setSaving(true);
    try {
      await api.put("/settings", form);
      toast.success("Ajustes actualizados");
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally { setSaving(false); }
  }

  function handleLogo(file) {
    if (!file) return;
    if (file.size > 1024 * 1024) {
      toast.error("El logo no debe superar 1 MB");
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => setForm((f) => ({ ...f, logo_base64: e.target.result }));
    reader.readAsDataURL(file);
  }

  if (loading) return <div className="p-8 text-sm text-muted-foreground">Cargando ajustes…</div>;

  return (
    <div className="p-4 sm:p-8 max-w-4xl mx-auto space-y-6" data-testid="settings-page">
      <div>
        <Badge variant="secondary" className="rounded-full mb-3">Configuración</Badge>
        <h1 className="text-3xl sm:text-4xl font-bold text-foreground flex items-center gap-3">
          <Settings2 className="h-8 w-8 text-primary/70" /> Ajustes de la empresa
        </h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Datos generales, método de identificación en el kiosco y logo corporativo.
        </p>
      </div>

      <Card className="border-border/70 bg-card/80 backdrop-blur">
        <CardHeader>
          <CardTitle className="text-base text-foreground">Identidad corporativa</CardTitle>
          <CardDescription>Se muestra en el login, el kiosco y el carnet digital.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-6 sm:grid-cols-[1fr_180px]">
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>Nombre de la empresa</Label>
              <Input value={form.name || ""} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} data-testid="settings-name" />
            </div>
            <div className="space-y-1.5">
              <Label>Zona horaria</Label>
              <Select value={form.timezone || "America/Caracas"} onValueChange={(v) => setForm((f) => ({ ...f, timezone: v }))}>
                <SelectTrigger data-testid="settings-tz"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {TIMEZONES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                </SelectContent>
              </Select>
              <p className="text-[11px] text-muted-foreground">Afecta tardanzas y el rango de &ldquo;hoy&rdquo; en reportes.</p>
            </div>
          </div>

          <div className="space-y-2">
            <Label>Logo</Label>
            <div className="aspect-square w-full rounded-2xl border-2 border-dashed border-border/70 bg-muted/30 grid place-items-center overflow-hidden">
              {form.logo_base64 ? (
                <img src={form.logo_base64} alt="logo" className="object-contain w-full h-full" data-testid="settings-logo-preview" />
              ) : (
                <ImageIcon className="h-8 w-8 text-muted-foreground/60" />
              )}
            </div>
            <input ref={logoRef} type="file" accept="image/*" className="hidden" onChange={(e) => handleLogo(e.target.files?.[0])} data-testid="settings-logo-input" />
            <div className="flex gap-2">
              <Button variant="outline" size="sm" className="flex-1 rounded-full" onClick={() => logoRef.current?.click()} data-testid="settings-logo-btn">
                {form.logo_base64 ? "Cambiar" : "Subir"}
              </Button>
              {form.logo_base64 && (
                <Button variant="ghost" size="sm" className="rounded-full" onClick={() => setForm((f) => ({ ...f, logo_base64: "" }))}>
                  Quitar
                </Button>
              )}
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="border-border/70 bg-card/80 backdrop-blur">
        <CardHeader>
          <CardTitle className="text-base text-foreground flex items-center gap-2">
            <ShieldCheck className="h-4 w-4" /> Identificación en el kiosco
          </CardTitle>
          <CardDescription>Define cómo los empleados se identifican al marcar asistencia en el kiosco compartido.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <div className="grid grid-cols-3 gap-2" data-testid="settings-method">
            {[
              { v: "face", label: "Rostro", hint: "Solo reconocimiento facial" },
              { v: "pin",  label: "PIN", hint: "Solo código numérico" },
              { v: "both", label: "Rostro + PIN", hint: "Rostro como primario, PIN como respaldo" },
            ].map((opt) => {
              const active = form.identification_method === opt.v;
              return (
                <button
                  key={opt.v}
                  type="button"
                  onClick={() => setForm((f) => ({ ...f, identification_method: opt.v }))}
                  data-testid={`settings-method-${opt.v}`}
                  className={
                    "text-left rounded-2xl border-2 px-4 py-3 transition-all " +
                    (active
                      ? "border-primary bg-primary/5 shadow-sm"
                      : "border-border/60 bg-card/40 hover:border-primary/40")
                  }
                >
                  <p className="text-sm font-semibold text-foreground">{opt.label}</p>
                  <p className="text-[11px] text-muted-foreground mt-0.5">{opt.hint}</p>
                </button>
              );
            })}
          </div>

          <div className="flex items-center justify-between rounded-xl bg-muted/30 px-4 py-3">
            <div>
              <p className="text-sm font-medium text-foreground">Modo kiosco habilitado</p>
              <p className="text-xs text-muted-foreground">Permite la ruta pública <code>/kiosk</code> con desbloqueo por admin.</p>
            </div>
            <Switch checked={!!form.kiosk_enabled} onCheckedChange={(v) => setForm((f) => ({ ...f, kiosk_enabled: v }))} data-testid="settings-kiosk-switch" />
          </div>

          {form.kiosk_enabled && (
            <button
              type="button"
              onClick={() => nav("/kiosk")}
              data-testid="settings-kiosk-launch"
              className="w-full text-left rounded-2xl bg-primary text-primary-foreground p-5 hover:bg-primary/90 transition-all group flex items-center gap-4 shadow-lg shadow-primary/20"
            >
              <div className="h-14 w-14 rounded-2xl bg-accent grid place-items-center shrink-0">
                <ScanFace className="h-7 w-7 text-primary" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold flex items-center gap-2">
                  Activar el modo kiosco ahora
                  <ExternalLink className="h-3.5 w-3.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                </p>
                <p className="text-xs opacity-80 mt-0.5">
                  Abre la pantalla compartida donde los empleados marcan asistencia con rostro o PIN.
                </p>
              </div>
            </button>
          )}
        </CardContent>
      </Card>

      <div className="flex items-center gap-2 justify-end sticky bottom-4 rounded-2xl bg-card/90 backdrop-blur border border-border/60 shadow-xl shadow-primary/10 px-3 py-2">
        <Button variant="outline" onClick={load} className="rounded-full" data-testid="settings-reset">
          <RefreshCw className="h-4 w-4 mr-1.5" /> Descartar
        </Button>
        <Button onClick={save} disabled={saving} className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground shadow-lg shadow-primary/20" data-testid="settings-save">
          <Save className="h-4 w-4 mr-1.5" /> {saving ? "Guardando…" : "Guardar cambios"}
        </Button>
      </div>
      {/* Spacer para que el sticky no tape la última tarjeta */}
      <div className="h-4" />
    </div>
  );
}
