import { useEffect, useMemo, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Popover, PopoverContent, PopoverTrigger,
} from "@/components/ui/popover";
import { Calendar as CalendarWidget } from "@/components/ui/calendar";
import {
  Tabs, TabsList, TabsTrigger, TabsContent,
} from "@/components/ui/tabs";
import { toast } from "sonner";
import {
  Bell, Plus, CheckCircle2, XCircle, Clock, Calendar,
  Palmtree, Stethoscope, FileText, Sparkles, Trash2, Home, Pencil, Briefcase,
} from "lucide-react";

const TYPE_META = {
  vacation:     { label: "Vacaciones",     icon: Palmtree,     tint: "bg-emerald-100 text-emerald-800" },
  leave:        { label: "Reposo",         icon: Stethoscope,  tint: "bg-rose-100 text-rose-800" },
  medical:      { label: "Cita médica",    icon: Stethoscope,  tint: "bg-rose-100 text-rose-800" },
  permission:   { label: "Permiso",        icon: FileText,     tint: "bg-blue-100 text-blue-800" },
  remote:       { label: "Trabajo remoto", icon: Home,         tint: "bg-indigo-100 text-indigo-800" },
  client_visit: { label: "Visita a Clientes/Integradores", icon: Briefcase, tint: "bg-cyan-100 text-cyan-800" },
  other:        { label: "Otro",           icon: Sparkles,     tint: "bg-slate-200 text-slate-700" },
};
const STATUS_META = {
  pending:  { label: "Pendiente",  icon: Clock,        cls: "bg-amber-100 text-amber-800" },
  approved: { label: "Aprobada",   icon: CheckCircle2, cls: "bg-emerald-600 text-white" },
  rejected: { label: "Rechazada",  icon: XCircle,      cls: "bg-destructive text-white" },
};

const EMPTY_FORM = { type: "permission", start_date: "", end_date: "", start_time: "08:00", end_time: "17:00", reason: "", user_id: "", dates: [], mode: "range" };

// Tipos de novedad que admiten selección multi-fecha no consecutiva
const MULTIDATE_TYPES = new Set(["remote", "permission", "leave"]);

export default function NoveltiesPage() {
  const { user } = useAuth();
  const isManager = user?.role === "admin" || ["coordinador", "gerente", "director"].includes(user?.role);
  const isAdmin = user?.role === "admin";

  const [items, setItems] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState(isManager ? "pending" : "mine");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState(null); // objeto novelty o null
  const [form, setForm] = useState(EMPTY_FORM);
  const [selected, setSelected] = useState(new Set());
  const [decisionModal, setDecisionModal] = useState(null);
  const [decisionComment, setDecisionComment] = useState("");

  async function load() {
    setLoading(true);
    try {
      const calls = [api.get("/novelties")];
      if (isManager) calls.push(api.get("/users"));
      const [nov, us] = await Promise.all(calls);
      setItems(nov.data);
      if (us) setUsers(us.data);
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);

  const userMap = useMemo(() => Object.fromEntries(users.map((u) => [u.user_id, u])), [users]);
  // IDs del equipo directo del líder actual — se usa para mostrar "Eliminar"
  // sólo en novedades de miembros del equipo (Adenda sep-2026).
  const teamIds = useMemo(() => {
    if (!user?.user_id) return new Set();
    const set = new Set([user.user_id]);
    users.forEach((u) => {
      if (u.supervisor_id === user.user_id) set.add(u.user_id);
    });
    return set;
  }, [users, user]);

  const filtered = useMemo(() => {
    if (!isManager) return items.filter((n) => n.user_id === user?.user_id);
    if (tab === "pending") return items.filter((n) => n.status === "pending");
    if (tab === "decided") return items.filter((n) => n.status !== "pending");
    return items;
  }, [items, tab, isManager, user]);

  async function createNovelty() {
    // Modo multi-fecha (remote/permission/leave)
    const useMulti = MULTIDATE_TYPES.has(form.type) && form.mode === "multi";
    if (useMulti) {
      if (!form.dates || form.dates.length === 0) { toast.error("Selecciona al menos una fecha"); return; }
      if (!form.start_time || !form.end_time) { toast.error("Indica el rango horario"); return; }
    } else {
      if (!form.start_date || !form.end_date) { toast.error("Selecciona las fechas"); return; }
      if (form.type !== "vacation" && (!form.start_time || !form.end_time)) {
        toast.error("Indica el rango horario"); return;
      }
    }
    try {
      const payload = { ...form };
      delete payload.mode;
      if (useMulti) {
        payload.start_date = form.dates[0];
        payload.end_date = form.dates[form.dates.length - 1];
      } else {
        delete payload.dates;
      }
      if (payload.type === "vacation") {
        delete payload.start_time;
        delete payload.end_time;
        delete payload.dates;
      }
      if (!isManager) delete payload.user_id;
      else if (!payload.user_id) delete payload.user_id;
      const { data } = await api.post("/novelties", payload);
      const n = data?.created;
      toast.success(useMulti && n > 1 ? `${n} novedades enviadas` : "Novedad enviada");
      setCreating(false); setForm(EMPTY_FORM); load();
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message); }
  }

  async function deleteMine(nov) {
    try {
      await api.delete(`/novelties/${nov.novelty_id}`);
      toast.success("Novedad eliminada");
      load();
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message); }
  }

  // ----- Admin: editar y borrar cualquier novedad -----
  function startEdit(nov) {
    setEditing(nov);
    setForm({
      type: nov.type,
      start_date: nov.start_date || "",
      end_date: nov.end_date || "",
      start_time: nov.start_time || "08:00",
      end_time: nov.end_time || "17:00",
      reason: nov.reason || "",
      user_id: nov.user_id || "",
    });
  }

  async function saveEdit() {
    if (!editing) return;
    if (!form.start_date || !form.end_date) { toast.error("Selecciona las fechas"); return; }
    if (form.type !== "vacation" && (!form.start_time || !form.end_time)) {
      toast.error("Indica el rango horario"); return;
    }
    try {
      const payload = {
        type: form.type,
        start_date: form.start_date,
        end_date: form.end_date,
        reason: form.reason,
      };
      if (form.type !== "vacation") {
        payload.start_time = form.start_time;
        payload.end_time = form.end_time;
      }
      if (form.user_id && form.user_id !== editing.user_id) payload.user_id = form.user_id;
      await api.patch(`/novelties/${editing.novelty_id}`, payload);
      toast.success("Novedad actualizada");
      setEditing(null); setForm(EMPTY_FORM); load();
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message); }
  }

  async function adminDelete(nov) {
    if (!window.confirm(`¿Eliminar la novedad de ${users.find((u) => u.user_id === nov.user_id)?.name || "este empleado"}? Esta acción no se puede deshacer.`)) return;
    try {
      await api.delete(`/novelties/${nov.novelty_id}`);
      toast.success("Novedad eliminada");
      load();
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message); }
  }

  function toggleOne(id) {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }
  function toggleAll(ids) {
    setSelected((s) => {
      const all = ids.every((id) => s.has(id));
      return all ? new Set() : new Set(ids);
    });
  }

  async function applyDecision() {
    if (!decisionModal) return;
    try {
      const ids = Array.from(decisionModal.ids || selected);
      await api.post("/novelties/bulk-decide", {
        novelty_ids: ids,
        decision: decisionModal.decision,
        comment: decisionComment || undefined,
      });
      toast.success(`${ids.length} novedad(es) ${decisionModal.decision === "approved" ? "aprobadas" : "rechazadas"}`);
      setDecisionModal(null); setDecisionComment(""); setSelected(new Set());
      load();
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message); }
  }

  const pendingSelected = useMemo(
    () => filtered.filter((n) => selected.has(n.novelty_id) && n.status === "pending"),
    [filtered, selected]);
  const pendingIds = useMemo(() => filtered.filter((n) => n.status === "pending").map((n) => n.novelty_id), [filtered]);

  return (
    <div className="p-4 sm:p-8 max-w-6xl mx-auto space-y-6" data-testid="novelties-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <Badge variant="secondary" className="rounded-full mb-3">
            {isManager ? "Aprobaciones" : "Mis solicitudes"}
          </Badge>
          <h1 className="text-3xl sm:text-4xl font-bold text-foreground flex items-center gap-3">
            <Bell className="h-8 w-8 text-primary/70" /> Novedades
          </h1>
          <p className="text-muted-foreground mt-1 text-sm">
            {isManager
              ? "Vacaciones, reposos y permisos del equipo. Aprueba o rechaza en bloque."
              : "Solicita vacaciones, reposos y permisos. Tu supervisor decidirá."}
          </p>
        </div>
        <Button
          onClick={() => setCreating(true)}
          className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground shadow-lg shadow-primary/20"
          data-testid="novelties-create-btn"
        >
          <Plus className="h-4 w-4 mr-1.5" /> Nueva novedad
        </Button>
      </div>

      {isManager && (
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList data-testid="novelties-tabs">
            <TabsTrigger value="pending" data-testid="novelties-tab-pending">
              Pendientes ({items.filter((n) => n.status === "pending").length})
            </TabsTrigger>
            <TabsTrigger value="decided" data-testid="novelties-tab-decided">Historial</TabsTrigger>
            <TabsTrigger value="all" data-testid="novelties-tab-all">Todas</TabsTrigger>
          </TabsList>
          <TabsContent value={tab} />
        </Tabs>
      )}

      {isManager && pendingSelected.length > 0 && (
        <div className="sticky top-16 z-10 rounded-2xl border border-primary/30 bg-primary text-primary-foreground shadow-lg px-4 py-2.5 flex items-center gap-3" data-testid="novelties-bulk-bar">
          <span className="text-sm">
            <b>{pendingSelected.length}</b> pendiente(s) seleccionada(s)
          </span>
          <div className="ml-auto flex gap-2">
            <Button
              size="sm"
              onClick={() => setDecisionModal({ decision: "approved" })}
              className="rounded-full bg-emerald-600 hover:bg-emerald-700"
              data-testid="novelties-bulk-approve"
            >
              <CheckCircle2 className="h-4 w-4 mr-1.5" /> Aprobar
            </Button>
            <Button
              size="sm"
              onClick={() => setDecisionModal({ decision: "rejected" })}
              className="rounded-full bg-destructive hover:bg-destructive/90"
              data-testid="novelties-bulk-reject"
            >
              <XCircle className="h-4 w-4 mr-1.5" /> Rechazar
            </Button>
          </div>
        </div>
      )}

      <Card className="border-border/70 bg-card/80 backdrop-blur">
        <CardContent className="p-0">
          {loading && <p className="p-8 text-center text-sm text-muted-foreground">Cargando…</p>}
          {!loading && filtered.length === 0 && (
            <p className="p-10 text-center text-sm text-muted-foreground">
              {tab === "pending" && isManager ? "No hay novedades pendientes 🎉" : "Sin novedades registradas"}
            </p>
          )}
          {!loading && filtered.length > 0 && (
            <>
              {isManager && pendingIds.length > 0 && (
                <div className="flex items-center gap-2 px-4 py-2 border-b border-border/60 bg-muted/30">
                  <Checkbox
                    checked={pendingIds.length > 0 && pendingIds.every((id) => selected.has(id))}
                    onCheckedChange={() => toggleAll(pendingIds)}
                    data-testid="novelties-select-all"
                  />
                  <span className="text-xs text-muted-foreground">Seleccionar todas las pendientes</span>
                </div>
              )}
              <ul className="divide-y divide-border/60" data-testid="novelties-list">
                {filtered.map((n) => (
                  <NoveltyRow
                    key={n.novelty_id}
                    n={n}
                    user={userMap[n.user_id]}
                    isManager={isManager}
                    isAdmin={isAdmin}
                    isMine={n.user_id === user?.user_id}
                    canSupervisorDelete={isManager && !isAdmin && teamIds.has(n.user_id)}
                    isSelected={selected.has(n.novelty_id)}
                    onToggle={() => toggleOne(n.novelty_id)}
                    onDelete={() => deleteMine(n)}
                    onEdit={() => startEdit(n)}
                    onAdminDelete={() => adminDelete(n)}
                    onApprove={() => setDecisionModal({ decision: "approved", ids: new Set([n.novelty_id]) })}
                    onReject={() => setDecisionModal({ decision: "rejected", ids: new Set([n.novelty_id]) })}
                  />
                ))}
              </ul>
            </>
          )}
        </CardContent>
      </Card>

      {/* Create dialog */}
      <Dialog open={creating} onOpenChange={(v) => !v && setCreating(false)}>
        <DialogContent className="max-w-lg" data-testid="novelties-create-dialog">
          <DialogHeader>
            <DialogTitle>Nueva novedad</DialogTitle>
            <DialogDescription>Registra el tipo, fechas y motivo. Tu supervisor recibirá la solicitud.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            {isManager && (
              <div className="space-y-1.5">
                <Label>Empleado</Label>
                <Select value={form.user_id || user?.user_id} onValueChange={(v) => setForm((f) => ({ ...f, user_id: v }))}>
                  <SelectTrigger data-testid="novelties-form-user"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value={user?.user_id}>Yo — {user?.name}</SelectItem>
                    {[...users.filter((u) => u.user_id !== user?.user_id)]
                      .sort((a, b) => (a.name || "").localeCompare(b.name || "", "es", { sensitivity: "base" }))
                      .map((u) => (
                        <SelectItem key={u.user_id} value={u.user_id}>{u.name}</SelectItem>
                      ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            <div className="space-y-1.5">
              <Label>Tipo</Label>
              <Select value={form.type} onValueChange={(v) => setForm((f) => ({
                ...f, type: v,
                // reinicia modo si el nuevo tipo no admite multi-fecha
                mode: MULTIDATE_TYPES.has(v) ? f.mode : "range",
              }))}>
                <SelectTrigger data-testid="novelties-form-type"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Object.entries(TYPE_META).map(([k, m]) => (
                    <SelectItem key={k} value={k}>{m.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {MULTIDATE_TYPES.has(form.type) && (
              <div className="flex items-center gap-2 text-xs">
                <button
                  type="button"
                  onClick={() => setForm((f) => ({ ...f, mode: "range", dates: [] }))}
                  className={`px-3 py-1.5 rounded-full border ${form.mode === "range" ? "bg-primary text-primary-foreground border-primary" : "bg-transparent"}`}
                  data-testid="novelties-mode-range"
                >Rango continuo</button>
                <button
                  type="button"
                  onClick={() => setForm((f) => ({ ...f, mode: "multi", start_date: "", end_date: "" }))}
                  className={`px-3 py-1.5 rounded-full border ${form.mode === "multi" ? "bg-primary text-primary-foreground border-primary" : "bg-transparent"}`}
                  data-testid="novelties-mode-multi"
                >Días alternos</button>
              </div>
            )}
            {form.mode === "multi" && MULTIDATE_TYPES.has(form.type) ? (
              <div className="space-y-1.5">
                <Label>Fechas seleccionadas</Label>
                <Popover>
                  <PopoverTrigger asChild>
                    <Button
                      type="button"
                      variant="outline"
                      className="w-full justify-start gap-2"
                      data-testid="novelties-multi-open"
                    >
                      <Calendar className="h-4 w-4" />
                      {form.dates.length === 0
                        ? "Selecciona los días…"
                        : `${form.dates.length} día(s) seleccionado(s)`}
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-auto p-0" align="start">
                    <CalendarWidget
                      mode="multiple"
                      selected={form.dates.map((d) => new Date(`${d}T12:00`))}
                      onSelect={(days) => {
                        const arr = (days || []).map((d) => d.toISOString().slice(0, 10)).sort();
                        setForm((f) => ({ ...f, dates: arr }));
                      }}
                      initialFocus
                    />
                  </PopoverContent>
                </Popover>
                {form.dates.length > 0 && (
                  <div className="flex flex-wrap gap-1 pt-1" data-testid="novelties-multi-chips">
                    {form.dates.map((d) => (
                      <Badge key={d} variant="outline" className="text-[10px]">{d}</Badge>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label>Desde</Label>
                  <Input type="date" value={form.start_date} onChange={(e) => setForm((f) => ({ ...f, start_date: e.target.value }))} data-testid="novelties-form-from" />
                </div>
                <div className="space-y-1.5">
                  <Label>Hasta</Label>
                  <Input type="date" value={form.end_date} onChange={(e) => setForm((f) => ({ ...f, end_date: e.target.value }))} data-testid="novelties-form-to" />
                </div>
              </div>
            )}
            {form.type !== "vacation" && (
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label>Hora inicio</Label>
                  <Input
                    type="time"
                    value={form.start_time || ""}
                    onChange={(e) => setForm((f) => ({ ...f, start_time: e.target.value }))}
                    data-testid="novelties-form-time-from"
                  />
                </div>
                <div className="space-y-1.5">
                  <Label>Hora fin</Label>
                  <Input
                    type="time"
                    value={form.end_time || ""}
                    onChange={(e) => setForm((f) => ({ ...f, end_time: e.target.value }))}
                    data-testid="novelties-form-time-to"
                  />
                </div>
              </div>
            )}
            <div className="space-y-1.5">
              <Label>Motivo <span className="text-muted-foreground/60 text-xs">(opcional)</span></Label>
              <Textarea rows={3} value={form.reason || ""} onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))} placeholder="Ej. viaje familiar programado" data-testid="novelties-form-reason" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setCreating(false)}>Cancelar</Button>
            <Button
              onClick={createNovelty}
              disabled={
                (form.mode === "multi" && MULTIDATE_TYPES.has(form.type)
                  ? (form.dates.length === 0 || !form.start_time || !form.end_time)
                  : (!form.start_date || !form.end_date ||
                     (form.type !== "vacation" && (!form.start_time || !form.end_time))))
              }
              className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground"
              data-testid="novelties-form-submit"
            >
              Enviar solicitud
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit dialog (admin only) */}
      <Dialog open={!!editing} onOpenChange={(v) => { if (!v) { setEditing(null); setForm(EMPTY_FORM); } }}>
        <DialogContent className="max-w-lg" data-testid="novelties-edit-dialog">
          <DialogHeader>
            <DialogTitle>Editar novedad (admin)</DialogTitle>
            <DialogDescription>
              Modifica cualquier campo de la novedad. Los cambios se guardan de inmediato.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>Empleado</Label>
              <Select value={form.user_id || editing?.user_id || ""} onValueChange={(v) => setForm((f) => ({ ...f, user_id: v }))}>
                <SelectTrigger data-testid="novelties-edit-user"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {[...users].sort((a, b) => (a.name || "").localeCompare(b.name || "", "es", { sensitivity: "base" })).map((u) => (
                    <SelectItem key={u.user_id} value={u.user_id}>{u.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Tipo</Label>
              <Select value={form.type} onValueChange={(v) => setForm((f) => ({ ...f, type: v }))}>
                <SelectTrigger data-testid="novelties-edit-type"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Object.entries(TYPE_META).map(([k, v]) => (
                    <SelectItem key={k} value={k}>{v.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label>Desde</Label>
                <Input type="date" value={form.start_date} onChange={(e) => setForm((f) => ({ ...f, start_date: e.target.value }))} />
              </div>
              <div className="space-y-1.5">
                <Label>Hasta</Label>
                <Input type="date" value={form.end_date} onChange={(e) => setForm((f) => ({ ...f, end_date: e.target.value }))} />
              </div>
            </div>
            {form.type !== "vacation" && (
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1.5">
                  <Label>Hora inicio</Label>
                  <Input type="time" value={form.start_time || ""} onChange={(e) => setForm((f) => ({ ...f, start_time: e.target.value }))} />
                </div>
                <div className="space-y-1.5">
                  <Label>Hora fin</Label>
                  <Input type="time" value={form.end_time || ""} onChange={(e) => setForm((f) => ({ ...f, end_time: e.target.value }))} />
                </div>
              </div>
            )}
            <div className="space-y-1.5">
              <Label>Motivo</Label>
              <Textarea rows={3} value={form.reason || ""} onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => { setEditing(null); setForm(EMPTY_FORM); }}>Cancelar</Button>
            <Button
              onClick={saveEdit}
              className="rounded-full bg-blue-600 hover:bg-blue-700 text-white"
              data-testid="novelties-edit-submit"
            >
              Guardar cambios
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Decision dialog */}
      <Dialog open={!!decisionModal} onOpenChange={(v) => !v && setDecisionModal(null)}>
        <DialogContent data-testid="novelties-decide-dialog">
          <DialogHeader>
            <DialogTitle>
              {decisionModal?.decision === "approved" ? "Aprobar novedades" : "Rechazar novedades"}
            </DialogTitle>
            <DialogDescription>
              Puedes añadir un comentario opcional para el/los empleado(s).
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label>Comentario</Label>
            <Textarea rows={3} value={decisionComment} onChange={(e) => setDecisionComment(e.target.value)} placeholder="Ej. aprobado según política de vacaciones." data-testid="novelties-decide-comment" />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDecisionModal(null)}>Cancelar</Button>
            <Button
              onClick={applyDecision}
              className={
                "rounded-full " +
                (decisionModal?.decision === "approved"
                  ? "bg-emerald-600 hover:bg-emerald-700 text-white"
                  : "bg-destructive hover:bg-destructive/90")
              }
              data-testid="novelties-decide-confirm"
            >
              Confirmar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function NoveltyRow({ n, user, isManager, isAdmin, isMine, canSupervisorDelete, isSelected, onToggle, onDelete, onEdit, onAdminDelete, onApprove, onReject }) {
  const t = TYPE_META[n.type] || TYPE_META.other;
  const st = STATUS_META[n.status] || STATUS_META.pending;
  const TypeIcon = t.icon;
  const StIcon = st.icon;

  return (
    <li className="flex items-start gap-3 px-4 py-3 hover:bg-muted/30 transition-colors" data-testid={`novelty-item-${n.novelty_id}`}>
      {isManager && n.status === "pending" && (
        <Checkbox checked={isSelected} onCheckedChange={onToggle} className="mt-1.5" data-testid={`novelty-check-${n.novelty_id}`} />
      )}
      <div className={"h-10 w-10 rounded-xl grid place-items-center shrink-0 " + t.tint}>
        <TypeIcon className="h-5 w-5" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-sm font-semibold text-foreground truncate">
            {isManager && user ? user.name : t.label}
          </p>
          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium ${t.tint}`}>
            <TypeIcon className="h-3 w-3" /> {t.label}
          </span>
          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium ${st.cls}`}>
            <StIcon className="h-3 w-3" /> {st.label}
          </span>
        </div>
        <p className="text-xs text-muted-foreground mt-0.5 flex items-center gap-1.5">
          <Calendar className="h-3 w-3" /> {n.start_date} — {n.end_date}
          {n.start_time && n.end_time && (
            <span className="ml-2 inline-flex items-center gap-1 text-slate-500">
              <Clock className="h-3 w-3" /> {n.start_time} — {n.end_time}
            </span>
          )}
        </p>
        {n.reason && <p className="text-sm text-muted-foreground mt-1 italic">&ldquo;{n.reason}&rdquo;</p>}
        {n.decision_comment && (
          <p className="text-xs text-primary/80 mt-1">
            <b>Comentario:</b> {n.decision_comment}
          </p>
        )}
      </div>
      <div className="flex items-center gap-1 shrink-0">
        {isManager && n.status === "pending" && (
          <>
            <Button size="sm" variant="ghost" className="text-emerald-700 hover:bg-emerald-50" onClick={onApprove} data-testid={`novelty-approve-${n.novelty_id}`}>
              <CheckCircle2 className="h-4 w-4 mr-1" /> Aprobar
            </Button>
            <Button size="sm" variant="ghost" className="text-destructive hover:bg-destructive/10" onClick={onReject} data-testid={`novelty-reject-${n.novelty_id}`}>
              <XCircle className="h-4 w-4 mr-1" /> Rechazar
            </Button>
          </>
        )}
        {isAdmin && (
          <>
            <Button
              size="icon"
              variant="ghost"
              title="Editar (admin)"
              className="text-blue-700 hover:bg-blue-50"
              onClick={onEdit}
              data-testid={`novelty-admin-edit-${n.novelty_id}`}
            >
              <Pencil className="h-4 w-4" />
            </Button>
            <Button
              size="icon"
              variant="ghost"
              title="Eliminar (admin)"
              className="text-destructive hover:bg-destructive/10"
              onClick={onAdminDelete}
              data-testid={`novelty-admin-delete-${n.novelty_id}`}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </>
        )}
        {!isAdmin && isMine && n.status === "pending" && (
          <Button size="icon" variant="ghost" className="text-destructive hover:bg-destructive/10" onClick={onDelete} data-testid={`novelty-delete-${n.novelty_id}`}>
            <Trash2 className="h-4 w-4" />
          </Button>
        )}
        {canSupervisorDelete && !isMine && (
          <Button
            size="icon"
            variant="ghost"
            title="Eliminar (supervisor · miembro del equipo)"
            className="text-destructive hover:bg-destructive/10"
            onClick={onAdminDelete}
            data-testid={`novelty-team-delete-${n.novelty_id}`}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        )}
      </div>
    </li>
  );
}
