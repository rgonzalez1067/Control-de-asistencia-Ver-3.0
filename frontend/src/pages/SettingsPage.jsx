import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, API, getToken, formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
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
import { Settings2, Save, Image as ImageIcon, RefreshCw, ShieldCheck, ScanFace, ExternalLink, Database, Download, Upload, AlertTriangle, KeyRound, MonitorSmartphone, Unlock, MapPin, Clock } from "lucide-react";

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

      <BackupCard />
      <KioskSessionsCard />
      <ResetAllPasswordsCard />

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


// =====================================================================
// Backup / Restore card — solo admin
// =====================================================================
function BackupCard() {
  const { user } = useAuth();
  const [collections, setCollections] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);
  const [mode, setMode] = useState("upsert");
  const fileRef = useRef(null);

  useEffect(() => {
    if (user?.role !== "admin") return;
    (async () => {
      try {
        const { data } = await api.get("/admin/collections");
        setCollections(data);
        setSelected(new Set(data.map((c) => c.name))); // por defecto todas
      } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message); }
      finally { setLoading(false); }
    })();
  }, [user?.role]);

  if (user?.role !== "admin") return null;

  const toggleAll = () => {
    setSelected((s) => s.size === collections.length ? new Set() : new Set(collections.map((c) => c.name)));
  };
  const toggleOne = (name) => {
    setSelected((s) => {
      const n = new Set(s);
      n.has(name) ? n.delete(name) : n.add(name);
      return n;
    });
  };

  async function doExport() {
    if (!selected.size) { toast.error("Selecciona al menos una colección"); return; }
    setExporting(true);
    try {
      const resp = await fetch(`${API}/admin/export`, {
        method: "POST",
        headers: {
          "Authorization": `Bearer ${getToken()}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ collections: Array.from(selected) }),
      });
      if (!resp.ok) throw new Error("Error al exportar");
      const blob = await resp.blob();
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `megasoft-backup-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      toast.success(`Backup generado (${selected.size} colección/es)`);
    } catch (e) { toast.error(e.message); }
    finally { setExporting(false); }
  }

  async function doImport(file) {
    if (!file) return;
    const warn = mode === "replace"
      ? "⚠️ MODO REEMPLAZO: se BORRARÁN los datos actuales de las colecciones seleccionadas antes de restaurar. ¿Continuar?"
      : "Se importarán los datos del archivo (upsert por llave natural). ¿Continuar?";
    if (!window.confirm(warn)) return;
    setImporting(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const qs = new URLSearchParams({
        mode,
        collections: Array.from(selected).join(","),
      });
      const resp = await fetch(`${API}/admin/import?${qs}`, {
        method: "POST",
        headers: { "Authorization": `Bearer ${getToken()}` },
        body: fd,
      });
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.detail || "Error al importar");
      const restoredTotal = Object.values(data.restored || {}).reduce((a, b) => a + b, 0);
      toast.success(`Restauración OK — ${restoredTotal} documento(s) en ${Object.keys(data.restored || {}).length} colección(es)`);
    } catch (e) { toast.error(e.message); }
    finally {
      setImporting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  const allSelected = selected.size === collections.length;

  return (
    <Card className="border-amber-200 bg-amber-50/40" data-testid="backup-card">
      <CardHeader>
        <div className="flex items-center gap-2">
          <Database className="h-5 w-5 text-amber-700" />
          <CardTitle className="text-amber-900">Copia de seguridad — Backup & restauración</CardTitle>
        </div>
        <CardDescription className="text-amber-900/80">
          Exporta o restaura configuraciones y catálogos (usuarios, sedes, departamentos, horarios, novedades, visitas, ajustes).
          El registro de <b>asistencia (entradas/salidas) queda excluido</b> por regla del producto.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium text-foreground">Colecciones ({selected.size}/{collections.length})</p>
          <button
            type="button"
            onClick={toggleAll}
            className="text-xs font-semibold text-amber-700 hover:underline"
            data-testid="backup-toggle-all"
          >
            {allSelected ? "Deseleccionar todas" : "Seleccionar todas"}
          </button>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
          {collections.map((c) => (
            <label
              key={c.name}
              className={`flex items-center gap-2 rounded-lg border px-3 py-2 cursor-pointer text-sm transition ${
                selected.has(c.name)
                  ? "border-amber-400 bg-amber-100/50 text-amber-900"
                  : "border-border/60 bg-card hover:border-amber-300"
              }`}
              data-testid={`backup-col-${c.name}`}
            >
              <input
                type="checkbox"
                className="accent-amber-600"
                checked={selected.has(c.name)}
                onChange={() => toggleOne(c.name)}
              />
              <span className="flex-1 capitalize">{c.name}</span>
              <span className="text-[11px] text-muted-foreground">{c.count}</span>
            </label>
          ))}
        </div>

        <div className="flex items-center gap-3 pt-2">
          <Label className="text-xs text-muted-foreground">Modo importación:</Label>
          <Select value={mode} onValueChange={setMode}>
            <SelectTrigger className="w-56 h-8 text-xs" data-testid="backup-mode">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="upsert">Upsert (mezcla sin borrar)</SelectItem>
              <SelectItem value="replace">Reemplazo total (peligroso)</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {mode === "replace" && (
          <div className="flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-800">
            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
            <div>
              Modo <b>Reemplazo total</b>: se eliminarán todos los documentos existentes en las colecciones seleccionadas
              antes de restaurar. Úsalo solo para migrar a un servidor nuevo o revertir después de una prueba controlada.
            </div>
          </div>
        )}

        <div className="flex flex-wrap gap-2 pt-2">
          <Button
            onClick={doExport}
            disabled={exporting || !selected.size || loading}
            className="rounded-full bg-amber-600 hover:bg-amber-700 text-white"
            data-testid="backup-export"
          >
            <Download className="h-4 w-4 mr-1.5" />
            {exporting ? "Exportando…" : `Exportar backup (${selected.size})`}
          </Button>

          <input
            type="file"
            accept="application/json,.json"
            ref={fileRef}
            className="hidden"
            onChange={(e) => doImport(e.target.files?.[0])}
            data-testid="backup-file-input"
          />
          <Button
            variant="outline"
            onClick={() => fileRef.current?.click()}
            disabled={importing}
            className="rounded-full border-amber-300 text-amber-800 hover:bg-amber-100"
            data-testid="backup-import"
          >
            <Upload className="h-4 w-4 mr-1.5" />
            {importing ? "Importando…" : "Importar backup…"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}


// =====================================================================
// Reset masivo de contraseñas — solo admin
// =====================================================================
function ResetAllPasswordsCard() {
  const { user } = useAuth();
  const [newPw, setNewPw] = useState("Mega2026*");
  const [running, setRunning] = useState(false);
  const [expanded, setExpanded] = useState(false);

  if (user?.role !== "admin") return null;

  async function doReset() {
    const confirm1 = window.confirm(
      `Se reseteará la contraseña de TODOS los usuarios NO administradores a "${newPw}" y se les obligará a cambiarla en el próximo login. ¿Continuar?`,
    );
    if (!confirm1) return;
    const confirm2 = window.prompt(
      'Esta acción es masiva e irreversible.\n\nEscribe la palabra CONFIRMAR (en mayúsculas) para proceder:',
    );
    if (confirm2 !== "CONFIRMAR") { toast.error("Cancelado — palabra de confirmación incorrecta"); return; }
    setRunning(true);
    try {
      const { data } = await api.post("/admin/reset-all-passwords", { new_password: newPw });
      toast.success(`Contraseñas reseteadas: ${data.affected} usuario(s)`);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally { setRunning(false); }
  }

  return (
    <Card className="border-red-200 bg-red-50/40" data-testid="reset-all-passwords-card">
      <CardHeader>
        <div className="flex items-center gap-2">
          <KeyRound className="h-5 w-5 text-red-700" />
          <CardTitle className="text-red-900">Reset masivo de contraseñas</CardTitle>
        </div>
        <CardDescription className="text-red-900/80">
          Resetea la contraseña de <b>todos los usuarios no-administradores</b> a un valor único y los obliga a cambiarla
          al próximo login. Los admins NO se ven afectados.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {!expanded ? (
          <Button
            variant="outline"
            onClick={() => setExpanded(true)}
            className="rounded-full border-red-300 text-red-800 hover:bg-red-100"
            data-testid="reset-all-passwords-expand"
          >
            <AlertTriangle className="h-4 w-4 mr-1.5" /> Mostrar acción destructiva
          </Button>
        ) : (
          <>
            <div className="flex items-start gap-2 rounded-lg border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-900">
              <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
              <div>
                Acción <b>masiva e irreversible</b>. Todos los usuarios (excepto admins) tendrán que iniciar sesión con
                esta clave temporal y cambiarla al primer acceso. Úsala solo en migraciones o bootstrap inicial.
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs">Nueva contraseña temporal</Label>
              <Input
                value={newPw}
                onChange={(e) => setNewPw(e.target.value)}
                data-testid="reset-all-passwords-input"
              />
              <p className="text-[11px] text-muted-foreground">
                Los usuarios deberán cambiarla al primer login (política: 8+ caracteres, mayúscula, minúscula, número y especial).
              </p>
            </div>
            <div className="flex gap-2 flex-wrap">
              <Button
                onClick={doReset}
                disabled={running || !newPw}
                className="rounded-full bg-red-600 hover:bg-red-700 text-white"
                data-testid="reset-all-passwords-run"
              >
                <KeyRound className="h-4 w-4 mr-1.5" />
                {running ? "Ejecutando…" : "Resetear todas las contraseñas ahora"}
              </Button>
              <Button
                variant="ghost"
                onClick={() => setExpanded(false)}
                className="rounded-full text-muted-foreground"
              >
                Cancelar
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}



// =====================================================================
// Kioscos activos — liberación manual de sedes (solo admin)
// =====================================================================
function KioskSessionsCard() {
  const { user } = useAuth();
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);
  const [confirmTarget, setConfirmTarget] = useState(null);

  const isAdmin = user?.role === "admin";

  async function load() {
    if (!isAdmin) { setLoading(false); return; }
    setLoading(true);
    try {
      const { data } = await api.get("/admin/kiosk/sessions");
      setSessions(Array.isArray(data) ? data : []);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  async function forceClose(session) {
    setBusyId(session.session_id);
    try {
      const { data } = await api.post("/admin/kiosk/sessions/force-close", {
        session_id: session.session_id,
      });
      toast.success(`Sede liberada · ${data.closed || 0} sesión(es) cerrada(s)`);
      setConfirmTarget(null);
      await load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally { setBusyId(null); }
  }

  if (!isAdmin) return null;

  function fmt(iso) {
    if (!iso) return "—";
    try {
      const d = new Date(iso);
      return d.toLocaleString("es-VE", { dateStyle: "short", timeStyle: "short" });
    } catch (_) { return iso; }
  }
  function heartbeatAgo(iso) {
    if (!iso) return "—";
    const ms = Date.now() - new Date(iso).getTime();
    if (ms < 0) return "ahora";
    const s = Math.floor(ms / 1000);
    if (s < 60) return `${s}s`;
    const m = Math.floor(s / 60);
    if (m < 60) return `${m}m`;
    const h = Math.floor(m / 60);
    return `${h}h ${m % 60}m`;
  }

  return (
    <Card className="border-blue-200 bg-blue-50/40" data-testid="kiosk-sessions-card">
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="text-blue-900 flex items-center gap-2">
              <MonitorSmartphone className="h-4 w-4" /> Kioscos activos por sede
            </CardTitle>
            <CardDescription className="text-blue-900/80 mt-1">
              Si un kiosco se cae sin cerrar sesión, su sede queda “pegada” y no puede ser reasignada.
              Aquí puedes liberarla manualmente para que otro dispositivo pueda tomarla.
            </CardDescription>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={load}
            disabled={loading}
            className="rounded-full h-8 shrink-0 border-blue-200 text-blue-900 hover:bg-blue-100"
            data-testid="kiosk-sessions-refresh"
          >
            <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${loading ? "animate-spin" : ""}`} />
            Refrescar
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {loading ? (
          <p className="text-sm text-blue-900/70 py-4 text-center">Cargando kioscos activos…</p>
        ) : sessions.length === 0 ? (
          <div className="rounded-xl border border-dashed border-blue-200 bg-white/60 p-6 text-center" data-testid="kiosk-sessions-empty">
            <MonitorSmartphone className="h-6 w-6 text-blue-400 mx-auto mb-2" />
            <p className="text-sm text-blue-900/80">No hay kioscos activos en este momento.</p>
            <p className="text-[11px] text-blue-900/60 mt-1">Todas las sedes están libres para asignación.</p>
          </div>
        ) : (
          <div className="rounded-xl border border-blue-200 bg-white/70 divide-y divide-blue-100 overflow-hidden">
            {sessions.map((s) => (
              <div
                key={s.session_id}
                className="p-3 flex items-start gap-3"
                data-testid={`kiosk-session-row-${s.site_id}`}
              >
                <div className={`mt-0.5 h-2.5 w-2.5 rounded-full ${s.stale ? "bg-amber-500 animate-pulse" : "bg-emerald-500"}`} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-semibold text-blue-950 flex items-center gap-1.5">
                      <MapPin className="h-3.5 w-3.5" /> {s.site_name || s.site_id}
                    </p>
                    {s.stale ? (
                      <Badge variant="outline" className="border-amber-300 bg-amber-50 text-amber-900 text-[10px] px-1.5 py-0">
                        Sin heartbeat · posiblemente caído
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="border-emerald-300 bg-emerald-50 text-emerald-900 text-[10px] px-1.5 py-0">
                        Activo
                      </Badge>
                    )}
                  </div>
                  <div className="text-[11px] text-blue-900/70 mt-1 flex flex-wrap gap-x-4 gap-y-0.5">
                    <span className="flex items-center gap-1">
                      <Clock className="h-3 w-3" /> Abierta: {fmt(s.opened_at)}
                    </span>
                    <span>
                      Último heartbeat: hace <b>{heartbeatAgo(s.last_heartbeat)}</b>
                    </span>
                    <span className="font-mono text-blue-800/70">{s.session_id}</span>
                  </div>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setConfirmTarget(s)}
                  disabled={busyId === s.session_id}
                  className="rounded-full border-blue-300 bg-white text-blue-900 hover:bg-blue-100 shrink-0"
                  data-testid={`kiosk-session-force-close-${s.site_id}`}
                >
                  <Unlock className="h-3.5 w-3.5 mr-1.5" />
                  {busyId === s.session_id ? "Liberando…" : "Liberar sede"}
                </Button>
              </div>
            ))}
          </div>
        )}

        {confirmTarget && (
          <div
            className="rounded-xl border border-amber-300 bg-amber-50 p-4 space-y-3"
            data-testid="kiosk-session-confirm"
          >
            <div className="flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 text-amber-700 mt-0.5 shrink-0" />
              <div className="text-sm text-amber-900">
                <p className="font-semibold">¿Liberar la sede “{confirmTarget.site_name || confirmTarget.site_id}”?</p>
                <p className="text-xs mt-1">
                  Cerrará forzosamente la sesión activa. Si el dispositivo original sigue vivo, dejará de poder marcar
                  hasta que se reinicie el kiosco.
                </p>
              </div>
            </div>
            <div className="flex gap-2 justify-end">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setConfirmTarget(null)}
                className="rounded-full text-amber-900 hover:bg-amber-100"
                data-testid="kiosk-session-confirm-cancel"
              >
                Cancelar
              </Button>
              <Button
                size="sm"
                onClick={() => forceClose(confirmTarget)}
                disabled={busyId === confirmTarget.session_id}
                className="rounded-full bg-amber-600 hover:bg-amber-700 text-white"
                data-testid="kiosk-session-confirm-ok"
              >
                <Unlock className="h-3.5 w-3.5 mr-1.5" />
                {busyId === confirmTarget.session_id ? "Cerrando…" : "Sí, liberar sede"}
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
