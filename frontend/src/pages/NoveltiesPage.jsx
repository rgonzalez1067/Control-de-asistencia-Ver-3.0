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
  Tabs, TabsList, TabsTrigger, TabsContent,
} from "@/components/ui/tabs";
import { toast } from "sonner";
import {
  Bell, Plus, CheckCircle2, XCircle, Clock, Calendar,
  Palmtree, Stethoscope, FileText, Sparkles, Trash2,
} from "lucide-react";

const TYPE_META = {
  vacation:   { label: "Vacaciones",     icon: Palmtree,     tint: "bg-emerald-100 text-emerald-800" },
  leave:      { label: "Reposo",         icon: Stethoscope,  tint: "bg-rose-100 text-rose-800" },
  medical:    { label: "Cita médica",    icon: Stethoscope,  tint: "bg-rose-100 text-rose-800" },
  permission: { label: "Permiso",        icon: FileText,     tint: "bg-blue-100 text-blue-800" },
  other:      { label: "Otro",           icon: Sparkles,     tint: "bg-slate-200 text-slate-700" },
};
const STATUS_META = {
  pending:  { label: "Pendiente",  icon: Clock,        cls: "bg-amber-100 text-amber-800" },
  approved: { label: "Aprobada",   icon: CheckCircle2, cls: "bg-emerald-600 text-white" },
  rejected: { label: "Rechazada",  icon: XCircle,      cls: "bg-destructive text-white" },
};

const EMPTY_FORM = { type: "permission", start_date: "", end_date: "", reason: "", user_id: "" };

export default function NoveltiesPage() {
  const { user } = useAuth();
  const isManager = user?.role === "admin" || user?.role === "supervisor";

  const [items, setItems] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState(isManager ? "pending" : "mine");
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [selected, setSelected] = useState(new Set());
  const [decisionModal, setDecisionModal] = useState(null); // { decision, ids }
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

  const filtered = useMemo(() => {
    if (!isManager) return items.filter((n) => n.user_id === user?.user_id);
    if (tab === "pending") return items.filter((n) => n.status === "pending");
    if (tab === "decided") return items.filter((n) => n.status !== "pending");
    return items;
  }, [items, tab, isManager, user]);

  async function createNovelty() {
    if (!form.start_date || !form.end_date) { toast.error("Selecciona las fechas"); return; }
    try {
      const payload = { ...form };
      if (!isManager) delete payload.user_id;
      else if (!payload.user_id) delete payload.user_id;
      await api.post("/novelties", payload);
      toast.success("Novedad enviada");
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
                    isMine={n.user_id === user?.user_id}
                    isSelected={selected.has(n.novelty_id)}
                    onToggle={() => toggleOne(n.novelty_id)}
                    onDelete={() => deleteMine(n)}
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
                    {users.filter((u) => u.user_id !== user?.user_id).map((u) => (
                      <SelectItem key={u.user_id} value={u.user_id}>{u.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
            <div className="space-y-1.5">
              <Label>Tipo</Label>
              <Select value={form.type} onValueChange={(v) => setForm((f) => ({ ...f, type: v }))}>
                <SelectTrigger data-testid="novelties-form-type"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Object.entries(TYPE_META).map(([k, m]) => (
                    <SelectItem key={k} value={k}>{m.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
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
            <div className="space-y-1.5">
              <Label>Motivo <span className="text-muted-foreground/60 text-xs">(opcional)</span></Label>
              <Textarea rows={3} value={form.reason || ""} onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))} placeholder="Ej. viaje familiar programado" data-testid="novelties-form-reason" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setCreating(false)}>Cancelar</Button>
            <Button onClick={createNovelty} disabled={!form.start_date || !form.end_date} className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground" data-testid="novelties-form-submit">
              Enviar solicitud
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

function NoveltyRow({ n, user, isManager, isMine, isSelected, onToggle, onDelete, onApprove, onReject }) {
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
        {isMine && n.status === "pending" && (
          <Button size="icon" variant="ghost" className="text-destructive hover:bg-destructive/10" onClick={onDelete} data-testid={`novelty-delete-${n.novelty_id}`}>
            <Trash2 className="h-4 w-4" />
          </Button>
        )}
      </div>
    </li>
  );
}
