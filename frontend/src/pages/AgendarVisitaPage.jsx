import { useEffect, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { UserPlus, Users, Building2, Trash2, Save, X, User as UserIcon, IdCard, Phone } from "lucide-react";

export default function AgendarVisitaPage() {
  const [type, setType] = useState("personal");
  const [hostUserId, setHostUserId] = useState("");
  const [scheduledAt, setScheduledAt] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [motive, setMotive] = useState("");
  const [notes, setNotes] = useState("");
  const [visitors, setVisitors] = useState([{ name: "", cedula: "", phone: "", is_minor: false }]);
  const [employees, setEmployees] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get("/users")
      .then(({ data }) => setEmployees(data.filter((u) => u.role !== "admin")))
      .catch(() => setEmployees([]));
  }, []);

  function updateVisitor(i, field, val) {
    setVisitors((prev) => prev.map((v, idx) => idx === i ? { ...v, [field]: val } : v));
  }
  function addVisitor() { setVisitors((v) => [...v, { name: "", cedula: "", phone: "", is_minor: false }]); }
  function removeVisitor(i) { setVisitors((v) => v.length > 1 ? v.filter((_, idx) => idx !== i) : v); }

  function reset() {
    setHostUserId(""); setScheduledAt(""); setCompanyName(""); setMotive(""); setNotes("");
    setVisitors([{ name: "", cedula: "", phone: "", is_minor: false }]);
  }

  async function submit() {
    if (!hostUserId) { toast.error("Selecciona el empleado anfitrión"); return; }
    // Personal: cédula requerida SALVO menores. Laboral: siempre requerida.
    if (type === "personal") {
      if (visitors.some((v) => !v.name.trim())) {
        toast.error("Cada visitante requiere nombre"); return;
      }
      if (visitors.some((v) => !v.is_minor && !v.cedula.trim())) {
        toast.error("Cédula requerida (o marcar visitante como menor de edad)"); return;
      }
    } else {
      if (visitors.some((v) => !v.name.trim() || !v.cedula.trim())) {
        toast.error("Cada visitante requiere nombre y cédula"); return;
      }
    }
    if (type === "laboral") {
      if (!companyName.trim()) { toast.error("Nombre de empresa requerido"); return; }
      if (visitors.some((v) => !v.phone?.trim())) {
        toast.error("Cada visitante laboral requiere teléfono"); return;
      }
    }
    setSaving(true);
    try {
      const payload = {
        type,
        host_user_id: hostUserId,
        scheduled_at: scheduledAt ? new Date(scheduledAt).toISOString() : null,
        company_name: type === "laboral" ? companyName.trim() : null,
        motive: motive.trim() || null,
        notes: notes.trim() || null,
        visitors: visitors.map((v) => ({
          name: v.name.trim(),
          cedula: v.cedula?.trim() || null,
          phone: v.phone?.trim() || null,
          is_minor: type === "personal" ? !!v.is_minor : false,
        })),
      };
      await api.post("/visits", payload);
      toast.success("Visita agendada correctamente");
      reset();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally { setSaving(false); }
  }

  return (
    <div className="max-w-3xl mx-auto px-4 py-6 space-y-4">
      <div>
        <h1 className="text-3xl font-bold">Agendar visita</h1>
        <p className="text-sm text-muted-foreground">Registra una visita personal o laboral. En el kiosco se disparará la captura de selfies cuando el anfitrión marque entrada.</p>
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
              <VisitorsList visitors={visitors} updateVisitor={updateVisitor} removeVisitor={removeVisitor} addVisitor={addVisitor} withPhone={false} withMinor={true} />
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
                  <Label className="text-xs">Motivo / descripción</Label>
                  <Input value={motive} onChange={(e) => setMotive(e.target.value)} placeholder="Reunión, capacitación, etc."
                    data-testid="visit-motive" className="h-11" />
                </div>
              </div>
              <VisitorsList visitors={visitors} updateVisitor={updateVisitor} removeVisitor={removeVisitor} addVisitor={addVisitor} withPhone={true} withMinor={false} />
            </TabsContent>
          </Tabs>

          <div>
            <Label className="text-xs">Notas internas (opcional)</Label>
            <Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Observaciones, número de piso, etc." data-testid="visit-notes" />
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

function VisitorsList({ visitors, updateVisitor, removeVisitor, addVisitor, withPhone, withMinor }) {
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
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">Visitante {i + 1}</span>
            <div className="flex items-center gap-3">
              {withMinor && (
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
        </div>
      ))}
    </div>
  );
}
