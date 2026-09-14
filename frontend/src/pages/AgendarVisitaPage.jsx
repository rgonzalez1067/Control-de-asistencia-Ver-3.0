import { useEffect, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { UserPlus, Users, Building2, Trash2, Save, X, User as UserIcon, IdCard, Phone, KeyRound } from "lucide-react";

const PURPOSE_OPTIONS = [
  { value: "reunion", label: "Reunión" },
  { value: "capacitacion", label: "Capacitación" },
  { value: "visita_data_center_tbp", label: "Visita al Data Center de Torre Banco Plaza" },
  { value: "visita_data_center_lch", label: "Visita al Data Center de Los Chaguaramos" },
  { value: "visita_centro_cableado", label: "Visita al Centro de Cableado" },
  { value: "otra", label: "Otra (especificar)" },
];

const OBS_MAX = 300;

export default function AgendarVisitaPage() {
  const [type, setType] = useState("personal");
  const [hostUserId, setHostUserId] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [purpose, setPurpose] = useState("");
  const [purposeOther, setPurposeOther] = useState("");
  const [observations, setObservations] = useState("");
  const [visitors, setVisitors] = useState([{ name: "", cedula: "", phone: "", is_minor: false, kind: "external", internal_user_id: "" }]);
  const [employees, setEmployees] = useState([]);
  const [saving, setSaving] = useState(false);
  const [confirmation, setConfirmation] = useState(null);  // { visit_id, host_name, company_name, visitors:[{name, cedula, is_minor}] }

  useEffect(() => {
    api.get("/users")
      .then(({ data }) => setEmployees(data.filter((u) => u.role !== "admin")))
      .catch(() => setEmployees([]));
  }, []);

  function updateVisitor(i, field, val) {
    setVisitors((prev) => prev.map((v, idx) => idx === i ? { ...v, [field]: val } : v));
  }
  function addVisitor() { setVisitors((v) => [...v, { name: "", cedula: "", phone: "", is_minor: false, kind: "external", internal_user_id: "" }]); }
  function removeVisitor(i) { setVisitors((v) => v.length > 1 ? v.filter((_, idx) => idx !== i) : v); }

  function reset() {
    setHostUserId(""); setScheduledAt(""); setCompanyName("");
    setPurpose(""); setPurposeOther(""); setObservations("");
    setVisitors([{ name: "", cedula: "", phone: "", is_minor: false, kind: "external", internal_user_id: "" }]);
  }

  async function submit() {
    if (!hostUserId) { toast.error("Selecciona el empleado anfitrión"); return; }
    // Los visitantes internos (empleados) se auto-completan desde el catálogo — no se les valida por campo.
    const externals = visitors.filter((v) => v.kind !== "internal");
    const internals = visitors.filter((v) => v.kind === "internal");
    if (internals.some((v) => !v.internal_user_id)) {
      toast.error("Selecciona un empleado para cada visitante interno"); return;
    }
    if (type === "personal") {
      if (externals.some((v) => !v.name.trim())) { toast.error("Cada visitante externo requiere nombre"); return; }
      if (externals.some((v) => !v.is_minor && !v.cedula.trim())) {
        toast.error("Cédula requerida (o marcar visitante como menor de edad)"); return;
      }
    } else {
      if (externals.some((v) => !v.name.trim() || !v.cedula.trim())) {
        toast.error("Cada visitante externo requiere nombre y cédula"); return;
      }
      if (!companyName.trim()) { toast.error("Nombre de empresa requerido"); return; }
      if (externals.some((v) => !v.phone?.trim())) {
        toast.error("Cada visitante externo laboral requiere teléfono"); return;
      }
      if (!purpose) { toast.error("Selecciona un motivo del catálogo"); return; }
      if (purpose === "otra" && !purposeOther.trim()) {
        toast.error("Especifica el motivo cuando eliges “Otra”"); return;
      }
    }
    if (observations.length > OBS_MAX) {
      toast.error(`Observaciones no puede exceder ${OBS_MAX} caracteres`); return;
    }
    setSaving(true);
    try {
      const payload = {
        type,
        host_user_id: hostUserId,
        scheduled_at: scheduledAt ? new Date(scheduledAt).toISOString() : null,
        company_name: type === "laboral" ? companyName.trim() : null,
        purpose: type === "laboral" ? purpose : null,
        purpose_other: type === "laboral" && purpose === "otra" ? purposeOther.trim() : null,
        observations: observations.trim() || null,
        visitors: visitors.map((v) => ({
          name: v.name.trim(),
          cedula: v.cedula?.trim() || null,
          phone: v.phone?.trim() || null,
          is_minor: type === "personal" && v.kind !== "internal" ? !!v.is_minor : false,
          kind: v.kind || "external",
          internal_user_id: v.kind === "internal" ? v.internal_user_id : null,
        })),
      };
      const { data } = await api.post("/visits", payload);
      const host = employees.find((u) => u.user_id === hostUserId);
      setConfirmation({
        visit_id: data.visit_id,
        host_name: host?.name || "—",
        company_name: type === "laboral" ? companyName.trim() : null,
        visitors: visitors.map((v) => ({
          name: v.name.trim(),
          cedula: v.cedula?.trim() || "",
          is_minor: type === "personal" ? !!v.is_minor : false,
        })),
      });
      reset();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally { setSaving(false); }
  }

  const obsLeft = OBS_MAX - observations.length;

  return (
    <div className="max-w-3xl mx-auto px-4 py-6 space-y-4">
      <div>
        <h1 className="text-3xl font-bold">Agendar visita</h1>
        <p className="text-sm text-muted-foreground">
          Registra una visita personal o laboral. En el kiosco de recepción, cada
          visitante deberá ingresar los <b>últimos 3 dígitos de su cédula</b> para
          autorizar la captura de su selfie.
        </p>
      </div>

      <Card>
        <CardContent className="pt-6 space-y-5">
          <Tabs value={type} onValueChange={setType}>
            <TabsList className="grid grid-cols-2 h-11 rounded-full">
              <TabsTrigger value="personal" className="rounded-full gap-2" data-testid="visit-type-personal">
                <UserIcon className="h-4 w-4" /> Personal
              </TabsTrigger>
              <TabsTrigger value="laboral" className="rounded-full gap-2" data-testid="visit-type-laboral">
                <Building2 className="h-4 w-4" /> Laboral
              </TabsTrigger>
            </TabsList>

            <TabsContent value="personal" className="pt-4 space-y-4">
              <HostAndDate hostUserId={hostUserId} setHostUserId={setHostUserId} employees={employees} scheduledAt={scheduledAt} setScheduledAt={setScheduledAt} />
              <VisitorsList visitors={visitors} updateVisitor={updateVisitor} removeVisitor={removeVisitor} addVisitor={addVisitor} withPhone={false} withMinor={true} employees={employees} />
            </TabsContent>

            <TabsContent value="laboral" className="pt-4 space-y-4">
              <HostAndDate hostUserId={hostUserId} setHostUserId={setHostUserId} employees={employees} scheduledAt={scheduledAt} setScheduledAt={setScheduledAt} />
              <div className="grid sm:grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs">Empresa</Label>
                  <Input value={companyName} onChange={(e) => setCompanyName(e.target.value)} placeholder="Nombre de la empresa"
                    data-testid="visit-company" className="h-11" />
                </div>
                <div>
                  <Label className="text-xs">Motivo *</Label>
                  <Select value={purpose} onValueChange={setPurpose}>
                    <SelectTrigger className="h-11" data-testid="visit-purpose">
                      <SelectValue placeholder="Selecciona un motivo…" />
                    </SelectTrigger>
                    <SelectContent>
                      {PURPOSE_OPTIONS.map((o) => (
                        <SelectItem key={o.value} value={o.value} data-testid={`visit-purpose-opt-${o.value}`}>
                          {o.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              {purpose === "otra" && (
                <div data-testid="visit-purpose-other-wrap">
                  <Label className="text-xs">Especificar motivo *</Label>
                  <Input
                    value={purposeOther}
                    onChange={(e) => setPurposeOther(e.target.value)}
                    placeholder="Describe brevemente el motivo de la visita"
                    className="h-11"
                    maxLength={140}
                    data-testid="visit-purpose-other"
                  />
                </div>
              )}
              <VisitorsList visitors={visitors} updateVisitor={updateVisitor} removeVisitor={removeVisitor} addVisitor={addVisitor} withPhone={true} withMinor={false} employees={employees} />
            </TabsContent>
          </Tabs>

          <div>
            <div className="flex items-center justify-between mb-1">
              <Label className="text-xs">Observaciones (opcional)</Label>
              <span className={"text-[10px] " + (obsLeft < 0 ? "text-destructive font-semibold" : "text-muted-foreground")} data-testid="visit-observations-counter">
                {observations.length}/{OBS_MAX}
              </span>
            </div>
            <Textarea
              rows={4}
              value={observations}
              onChange={(e) => setObservations(e.target.value.slice(0, OBS_MAX))}
              placeholder="Detalles adicionales, número de piso, instrucciones de acceso, requisitos especiales, etc."
              data-testid="visit-observations"
              maxLength={OBS_MAX}
              className="resize-y"
            />
          </div>

          <div className="flex justify-end gap-2 pt-2 border-t">
            <Button variant="outline" onClick={reset} disabled={saving} className="rounded-full" data-testid="visit-reset">
              <X className="h-4 w-4 mr-1.5" /> Limpiar
            </Button>
            <Button onClick={submit} disabled={saving} className="rounded-full bg-primary hover:bg-primary/90" data-testid="visit-submit">
              <Save className="h-4 w-4 mr-1.5" /> {saving ? "Guardando…" : "Agendar visita"}
            </Button>
          </div>
        </CardContent>
      </Card>

      <VisitConfirmationDialog
        confirmation={confirmation}
        onClose={() => setConfirmation(null)}
      />
    </div>
  );
}

function HostAndDate({ hostUserId, setHostUserId, employees, scheduledAt, setScheduledAt }) {
  return (
    <div className="grid sm:grid-cols-2 gap-3">
      <div>
        <Label className="text-xs">Empleado anfitrión</Label>
        <Select value={hostUserId} onValueChange={setHostUserId}>
          <SelectTrigger className="h-11" data-testid="visit-host">
            <SelectValue placeholder="Selecciona un empleado…" />
          </SelectTrigger>
          <SelectContent>
            {[...employees].sort((a, b) => (a.name || "").localeCompare(b.name || "", "es", { sensitivity: "base" })).map((u) => (
              <SelectItem key={u.user_id} value={u.user_id}>
                {u.name} <span className="text-muted-foreground text-xs">· {u.email}</span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div>
        <Label className="text-xs">Fecha y hora (opcional)</Label>
        <Input type="datetime-local" value={scheduledAt} onChange={(e) => setScheduledAt(e.target.value)}
          className="h-11" data-testid="visit-datetime" />
      </div>
    </div>
  );
}

function VisitorsList({ visitors, updateVisitor, removeVisitor, addVisitor, withPhone, withMinor, employees }) {
  // Cuando el usuario cambia el kind a "internal" y selecciona un empleado,
  // autocompletamos name/cedula/phone a partir del catálogo de empleados.
  function pickInternal(i, userId) {
    const emp = employees.find((u) => u.user_id === userId);
    if (!emp) return;
    updateVisitor(i, "internal_user_id", emp.user_id);
    updateVisitor(i, "name", emp.name || "");
    updateVisitor(i, "cedula", emp.cedula || "");
    updateVisitor(i, "phone", emp.phone || emp.mobile || "");
  }
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-sm font-medium flex items-center gap-1.5"><Users className="h-4 w-4" /> Visitantes ({visitors.length})</div>
        <Button size="sm" variant="outline" className="rounded-full" onClick={addVisitor} data-testid="visit-add-visitor">
          <UserPlus className="h-4 w-4 mr-1.5" /> Agregar
        </Button>
      </div>
      {visitors.map((v, i) => (
        <div key={i} className={"rounded-xl border p-3 space-y-2 " + (i % 2 ? "bg-muted/30" : "")}
             data-testid={`visitor-row-${i}`}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs text-muted-foreground">Visitante {i + 1}</span>
            <div className="flex items-center gap-2">
              {/* Toggle Interno / Externo */}
              <div className="inline-flex rounded-full border p-0.5 text-[10px] bg-background">
                <button
                  type="button"
                  className={"px-2.5 py-1 rounded-full transition " + ((v.kind || "external") === "external" ? "bg-primary text-primary-foreground" : "text-muted-foreground")}
                  onClick={() => {
                    updateVisitor(i, "kind", "external");
                    updateVisitor(i, "internal_user_id", "");
                  }}
                  data-testid={`visitor-${i}-kind-external`}
                >Externo</button>
                <button
                  type="button"
                  className={"px-2.5 py-1 rounded-full transition " + (v.kind === "internal" ? "bg-primary text-primary-foreground" : "text-muted-foreground")}
                  onClick={() => updateVisitor(i, "kind", "internal")}
                  data-testid={`visitor-${i}-kind-internal`}
                >Interno</button>
              </div>
              {withMinor && v.kind !== "internal" && (
                <label className="flex items-center gap-1.5 text-xs cursor-pointer" data-testid={`visitor-${i}-minor-label`}>
                  <input
                    type="checkbox"
                    checked={!!v.is_minor}
                    onChange={(e) => updateVisitor(i, "is_minor", e.target.checked)}
                    className="h-3.5 w-3.5 accent-primary"
                    data-testid={`visitor-${i}-minor`}
                  />
                  <span className="text-muted-foreground">Menor de edad</span>
                </label>
              )}
              {visitors.length > 1 && (
                <Button variant="ghost" size="icon" className="h-7 w-7 text-red-500 hover:bg-red-50"
                  onClick={() => removeVisitor(i)} data-testid={`visitor-remove-${i}`}>
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              )}
            </div>
          </div>

          {v.kind === "internal" ? (
            <div className="space-y-2">
              <Label className="text-[10px] flex items-center gap-1"><UserIcon className="h-3 w-3" /> Empleado</Label>
              <select
                className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                value={v.internal_user_id || ""}
                onChange={(e) => pickInternal(i, e.target.value)}
                data-testid={`visitor-${i}-internal-picker`}
              >
                <option value="">— Selecciona un empleado —</option>
                {[...employees]
                  .sort((a, b) => (a.name || "").localeCompare(b.name || "", "es", { sensitivity: "base" }))
                  .map((u) => (
                    <option key={u.user_id} value={u.user_id}>
                      {u.name}{u.cedula ? ` · ${u.cedula}` : ""}
                    </option>
                  ))}
              </select>
              {v.internal_user_id && (
                <div className="text-[10px] text-muted-foreground grid gap-0.5 pl-1">
                  <span><b>Nombre:</b> {v.name || "—"}</span>
                  <span><b>Cédula:</b> {v.cedula || "—"}</span>
                  {withPhone && <span><b>Teléfono:</b> {v.phone || "—"}</span>}
                </div>
              )}
            </div>
          ) : (
            <div className={"grid gap-2 " + (withPhone ? "sm:grid-cols-3" : "sm:grid-cols-2")}>
              <div>
                <Label className="text-[10px] flex items-center gap-1"><UserIcon className="h-3 w-3" /> Nombre y apellido</Label>
                <Input value={v.name} onChange={(e) => updateVisitor(i, "name", e.target.value)}
                       placeholder="Ej. Juan Pérez" className="h-10" data-testid={`visitor-${i}-name`} />
              </div>
              <div>
                <Label className="text-[10px] flex items-center gap-1">
                  <IdCard className="h-3 w-3" /> Cédula {v.is_minor && withMinor ? "(opcional para menores)" : ""}
                </Label>
                <Input value={v.cedula} onChange={(e) => updateVisitor(i, "cedula", e.target.value)}
                       placeholder={v.is_minor && withMinor ? "Cédula escolar o del representante (opcional)" : "V-12345678"}
                       className="h-10" data-testid={`visitor-${i}-cedula`} />
              </div>
              {withPhone && (
                <div>
                  <Label className="text-[10px] flex items-center gap-1"><Phone className="h-3 w-3" /> Teléfono</Label>
                  <Input value={v.phone} onChange={(e) => updateVisitor(i, "phone", e.target.value)}
                         placeholder="+58 412…" className="h-10" data-testid={`visitor-${i}-phone`} />
                </div>
              )}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function VisitConfirmationDialog({ confirmation, onClose }) {
  const visitors = confirmation?.visitors || [];

  function last3(cedula) {
    const digits = String(cedula || "").replace(/\D/g, "");
    if (digits.length < 3) return null;
    return digits.slice(-3);
  }

  return (
    <Dialog open={!!confirmation} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-md" data-testid="visit-confirmation-dialog">
        <DialogHeader className="items-center text-center">
          <div className="h-14 w-14 rounded-2xl bg-primary/10 grid place-items-center mb-2">
            <KeyRound className="h-7 w-7 text-primary dark:text-foreground" />
          </div>
          <DialogTitle>Visita agendada</DialogTitle>
          <DialogDescription>
            En el kiosco, cada visitante deberá ingresar los{" "}
            <b>últimos 3 dígitos de su cédula</b> para autorizar la captura de su selfie.
          </DialogDescription>
        </DialogHeader>

        <div className="rounded-2xl border bg-muted/40 divide-y overflow-hidden my-2">
          {visitors.map((v, i) => {
            const pin = last3(v.cedula);
            return (
              <div key={i} className="flex items-center justify-between gap-3 px-4 py-3"
                   data-testid={`visit-confirmation-visitor-${i}`}>
                <div className="min-w-0">
                  <p className="text-sm font-medium truncate">{v.name || `Visitante ${i + 1}`}</p>
                  <p className="text-[11px] text-muted-foreground truncate">
                    {v.cedula
                      ? <>Cédula <span className="font-mono">{v.cedula}</span></>
                      : (v.is_minor ? "Menor de edad (sin cédula)" : "Sin cédula")}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-[10px] uppercase tracking-wider text-muted-foreground">PIN</p>
                  <p className="text-2xl font-black font-mono tracking-[0.25em]"
                     data-testid={`visit-confirmation-pin-${i}`}>
                    {pin || "—"}
                  </p>
                </div>
              </div>
            );
          })}
        </div>

        <div className="text-xs text-muted-foreground space-y-1">
          <p><b>Anfitrión:</b> {confirmation?.host_name}</p>
          {confirmation?.company_name && <p><b>Empresa:</b> {confirmation.company_name}</p>}
        </div>

        <DialogFooter className="pt-2">
          <Button
            onClick={onClose}
            className="h-11 rounded-full w-full bg-primary hover:bg-primary/90"
            data-testid="visit-pin-done"
          >
            Listo
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
