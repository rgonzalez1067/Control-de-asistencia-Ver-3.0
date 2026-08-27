import { useEffect, useMemo, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Popover, PopoverContent, PopoverTrigger,
} from "@/components/ui/popover";
import {
  Command, CommandInput, CommandList, CommandItem, CommandGroup, CommandEmpty,
} from "@/components/ui/command";
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuLabel, DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  CalendarRange, Filter, Users, ChevronDown, RefreshCw,
  Clock, Palmtree, HeartPulse, Home, TicketCheck, Trash2, Sparkles,
  Bookmark, Save, FolderOpen, X, Pencil,
} from "lucide-react";

const NOVELTY_OPTIONS = [
  { value: "remote",     label: "Trabajo Remoto",   icon: Home,        color: "bg-emerald-100 text-emerald-800 border-emerald-300" },
  { value: "vacation",   label: "Vacaciones",        icon: Palmtree,    color: "bg-sky-100 text-sky-800 border-sky-300" },
  { value: "leave",      label: "Reposo",            icon: HeartPulse,  color: "bg-rose-100 text-rose-800 border-rose-300" },
  { value: "permission", label: "Permiso",           icon: TicketCheck, color: "bg-amber-100 text-amber-800 border-amber-300" },
];
const NOVELTY_MAP = Object.fromEntries(NOVELTY_OPTIONS.map((n) => [n.value, n]));

function todayISO(offset = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return d.toISOString().slice(0, 10);
}
function daysBetween(from, to) {
  const out = [];
  const a = new Date(from + "T12:00");
  const b = new Date(to + "T12:00");
  for (let d = new Date(a); d <= b; d.setDate(d.getDate() + 1)) {
    out.push(d.toISOString().slice(0, 10));
  }
  return out;
}
function shortDay(iso) {
  try {
    return new Date(iso + "T12:00").toLocaleDateString("es-VE",
      { weekday: "short", day: "2-digit", month: "short" });
  } catch (_) { return iso; }
}

/** true si la fecha ISO YYYY-MM-DD cae en sábado o domingo. */
function isWeekend(iso) {
  try {
    const dow = new Date(iso + "T12:00").getDay();
    return dow === 0 || dow === 6;
  } catch (_) { return false; }
}

export default function AsignarHorariosPage() {
  const { user } = useAuth();
  const canAccess = user?.role === "admin"
    || !!user?.can_assign_schedules
    || !!(user?.effective_permissions || {}).asignar_horarios;

  const [fromDate, setFromDate] = useState(todayISO(0));
  const [toDate, setToDate] = useState(todayISO(13));
  const [eligibleUsers, setEligibleUsers] = useState([]);
  const [selectedUsers, setSelectedUsers] = useState([]);   // user_ids
  const [schedules, setSchedules] = useState([]);
  const [built, setBuilt] = useState(false);
  const [loading, setLoading] = useState(false);
  const [assignments, setAssignments] = useState({});      // key `${uid}|${date}` → asg
  const [selectedCells, setSelectedCells] = useState(new Set());  // Set of `${uid}|${date}`
  const [saving, setSaving] = useState(false);

  // Planificaciones guardadas
  const [plans, setPlans] = useState([]);
  const [currentPlan, setCurrentPlan] = useState(null);  // plan_id de la planificación abierta
  const [saveDialog, setSaveDialog] = useState(null);    // { mode: 'new'|'rename', name, plan_id? }
  const [overlapDialog, setOverlapDialog] = useState(null); // { name, plan_id?, conflicts[] }

  useEffect(() => {
    if (!canAccess) return;
    (async () => {
      try {
        const [eu, sc, pl] = await Promise.all([
          api.get("/schedule-assignments/eligible-users"),
          api.get("/schedules"),
          api.get("/schedule-assignment-plans"),
        ]);
        setEligibleUsers(eu.data || []);
        setSchedules(sc.data || []);
        setPlans(pl.data || []);
      } catch (e) {
        toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
      }
    })();
  }, [canAccess]);

  async function refreshPlans() {
    try {
      const { data } = await api.get("/schedule-assignment-plans");
      setPlans(data || []);
    } catch (_) { /* silencioso */ }
  }

  const days = useMemo(
    () => (fromDate && toDate && fromDate <= toDate) ? daysBetween(fromDate, toDate) : [],
    [fromDate, toDate],
  );
  const userMap = useMemo(
    () => Object.fromEntries(eligibleUsers.map((u) => [u.user_id, u])),
    [eligibleUsers],
  );
  const scheduleMap = useMemo(
    () => Object.fromEntries(schedules.map((s) => [s.schedule_id, s])),
    [schedules],
  );
  const rows = useMemo(() => {
    if (!built) return [];
    const uids = selectedUsers.length > 0 ? selectedUsers : eligibleUsers.map((u) => u.user_id);
    return uids
      .map((id) => userMap[id])
      .filter(Boolean)
      .sort((a, b) => (a.name || "").localeCompare(b.name || "", "es", { sensitivity: "base" }));
  }, [built, selectedUsers, eligibleUsers, userMap]);

  async function buildMatrix() {
    if (fromDate > toDate) { toast.error("El rango de fechas es inválido"); return; }
    if (days.length > 62) { toast.error("Selecciona un rango de hasta 62 días"); return; }
    if (selectedUsers.length === 0 && eligibleUsers.length === 0) {
      toast.error("No hay empleados sin horario fijo"); return;
    }
    setLoading(true);
    try {
      // Regla explícita: al construir una matriz nueva NO se hereda contenido de
      // asignaciones ya guardadas. La matriz arranca siempre en blanco para que
      // el usuario decida qué asignar, sin residuos de planificaciones previas.
      // Para retomar una planificación específica, se usa "Cargar planificación existente".
      setAssignments({});
      setSelectedCells(new Set());
      setCurrentPlan(null);
      setBuilt(true);
    } finally { setLoading(false); }
  }

  /** Carga una planificación guardada: restaura fechas y empleados y arma la matriz. */
  async function loadPlan(plan) {
    setFromDate(plan.from_date);
    setToDate(plan.to_date);
    setSelectedUsers(plan.user_ids || []);
    setCurrentPlan(plan.plan_id);
    setLoading(true);
    try {
      const uids = (plan.user_ids && plan.user_ids.length > 0)
        ? plan.user_ids
        : eligibleUsers.map((u) => u.user_id);
      const { data } = await api.get("/schedule-assignments", {
        params: {
          from_date: plan.from_date,
          to_date: plan.to_date,
          user_ids: uids.join(","),
        },
      });
      const map = {};
      (data || []).forEach((a) => { map[`${a.user_id}|${a.date}`] = a; });
      setAssignments(map);
      setSelectedCells(new Set());
      setBuilt(true);
      toast.success(`Planificación "${plan.name}" cargada`);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally { setLoading(false); }
  }

  /** Guarda la vista actual (rango + empleados) como planificación. */
  async function savePlan(name, planId = null, overwrite = false) {
    const trimmed = (name || "").trim();
    if (!trimmed) { toast.error("Escribe un nombre"); return false; }
    const body = {
      name: trimmed, from_date: fromDate, to_date: toDate,
      user_ids: selectedUsers, overwrite,
    };
    try {
      const { data } = planId
        ? await api.put(`/schedule-assignment-plans/${planId}`, body)
        : await api.post("/schedule-assignment-plans", body);
      setCurrentPlan(data.plan_id);
      await refreshPlans();
      toast.success(planId ? "Planificación actualizada" : `Planificación "${data.name}" guardada`);
      return true;
    } catch (e) {
      const detail = e.response?.data?.detail;
      // El backend responde con estructura { code, message, conflicts[] } cuando hay solape.
      if (e.response?.status === 409 && typeof detail === "object" && detail?.code === "plan_range_overlap") {
        setOverlapDialog({
          name: trimmed,
          plan_id: planId,
          conflicts: detail.conflicts || [],
          message: detail.message,
        });
        return false;
      }
      toast.error(formatApiErrorDetail(detail) || e.message);
      return false;
    }
  }

  async function deletePlan(plan) {
    if (!window.confirm(`¿Eliminar la planificación "${plan.name}"?\n(Las asignaciones diarias NO se borran.)`)) return;
    try {
      await api.delete(`/schedule-assignment-plans/${plan.plan_id}`);
      if (currentPlan === plan.plan_id) setCurrentPlan(null);
      await refreshPlans();
      toast.success("Planificación eliminada");
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    }
  }

  const currentPlanObj = plans.find((p) => p.plan_id === currentPlan) || null;

  function toggleCell(uid, date, e) {
    const key = `${uid}|${date}`;
    setSelectedCells((prev) => {
      const next = new Set(prev);
      // Shift-click para selección de rango dentro de la misma fila
      if (e?.shiftKey) {
        const rowKeys = days.map((d) => `${uid}|${d}`);
        const lastActive = Array.from(prev).findLast?.((k) => k.startsWith(`${uid}|`));
        if (lastActive) {
          const i1 = rowKeys.indexOf(lastActive);
          const i2 = rowKeys.indexOf(key);
          if (i1 >= 0 && i2 >= 0) {
            const [a, b] = i1 < i2 ? [i1, i2] : [i2, i1];
            for (let i = a; i <= b; i++) next.add(rowKeys[i]);
            return next;
          }
        }
      }
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function selectAll() {
    const s = new Set();
    rows.forEach((u) => days.forEach((d) => s.add(`${u.user_id}|${d}`)));
    setSelectedCells(s);
  }
  function clearSelection() { setSelectedCells(new Set()); }

  async function applyShift(schedule_id) {
    if (selectedCells.size === 0) { toast.error("Selecciona al menos una celda"); return; }
    await bulkApply({ kind: "shift", schedule_id });
  }
  async function applyNovelty(novelty_type) {
    if (selectedCells.size === 0) { toast.error("Selecciona al menos una celda"); return; }
    await bulkApply({ kind: "novelty", novelty_type });
  }
  async function clearCells() {
    if (selectedCells.size === 0) { toast.error("Selecciona al menos una celda"); return; }
    setSaving(true);
    try {
      const { user_ids, dates } = groupSelection();
      await api.post("/schedule-assignments/clear", { user_ids, dates });
      const next = { ...assignments };
      selectedCells.forEach((k) => delete next[k]);
      setAssignments(next);
      setSelectedCells(new Set());
      toast.success("Asignaciones eliminadas");
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally { setSaving(false); }
  }

  function groupSelection() {
    const uids = new Set();
    const dts = new Set();
    selectedCells.forEach((k) => {
      const [uid, d] = k.split("|");
      uids.add(uid); dts.add(d);
    });
    return { user_ids: [...uids], dates: [...dts] };
  }

  async function bulkApply(body) {
    setSaving(true);
    try {
      const { user_ids, dates } = groupSelection();
      // Enviamos sólo la cartesiana explícita — pero como el backend hace el cruce,
      // filtramos localmente para actualizar el estado con los pares reales.
      await api.post("/schedule-assignments/bulk", { ...body, user_ids, dates });
      // Actualiza estado local sólo para las celdas realmente seleccionadas.
      const now = new Date().toISOString();
      const next = { ...assignments };
      selectedCells.forEach((k) => {
        next[k] = { ...body, updated_at: now };
      });
      setAssignments(next);
      toast.success(`${body.kind === "shift" ? "Turno" : "Novedad"} aplicad${body.kind === "shift" ? "o" : "a"} a ${selectedCells.size} celda(s)`);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally { setSaving(false); }
  }

  if (!canAccess) {
    return (
      <div className="max-w-3xl mx-auto p-8 text-center text-muted-foreground">
        No tienes permiso para acceder a Asignación de Horarios.
      </div>
    );
  }

  return (
    <div className="px-4 py-6 space-y-4 max-w-[1600px] mx-auto">
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-xs uppercase tracking-widest text-muted-foreground">
            <Sparkles className="h-3 w-3" /> Planificación
          </div>
          <h1 className="text-3xl font-bold">Asignación de horarios</h1>
          <p className="text-sm text-muted-foreground max-w-2xl">
            Planifica turnos rotativos y novedades para el personal sin horario fijo. Todo lo que asignes aquí
            alimenta el <b>Reporte Matricial</b> y define la tolerancia con la que se evalúan sus marcajes.
          </p>
        </div>
        {/* Cargar planificación existente — disponible desde el primer momento */}
        <PlansMenu
          plans={plans}
          onLoad={loadPlan}
          onRename={(p) => setSaveDialog({ mode: "rename", name: p.name, plan_id: p.plan_id })}
          onDelete={deletePlan}
          testid="asg-plans-menu-header"
        />
      </div>

      {/* Filtros */}
      <Card>
        <CardContent className="pt-5 pb-4">
          <div className="grid gap-3 md:grid-cols-12 items-end">
            <div className="md:col-span-3">
              <Label className="text-xs flex items-center gap-1 mb-1.5">
                <CalendarRange className="h-3 w-3" /> Desde
              </Label>
              <Input type="date" className="h-11"
                value={fromDate} onChange={(e) => setFromDate(e.target.value)}
                data-testid="asg-from" />
            </div>
            <div className="md:col-span-3">
              <Label className="text-xs flex items-center gap-1 mb-1.5">
                <CalendarRange className="h-3 w-3" /> Hasta
              </Label>
              <Input type="date" className="h-11"
                value={toDate} onChange={(e) => setToDate(e.target.value)}
                data-testid="asg-to" />
            </div>
            <div className="md:col-span-4">
              <Label className="text-xs flex items-center gap-1 mb-1.5">
                <Users className="h-3 w-3" /> Empleados sin horario fijo
              </Label>
              <EmployeePicker
                all={eligibleUsers}
                value={selectedUsers}
                onChange={setSelectedUsers}
              />
            </div>
            <div className="md:col-span-2">
              <Button
                onClick={buildMatrix}
                disabled={loading}
                className="w-full h-11 rounded-full bg-primary hover:bg-primary/90 font-semibold"
                data-testid="asg-build"
              >
                {loading
                  ? (<><RefreshCw className="h-4 w-4 mr-1.5 animate-spin" /> Cargando…</>)
                  : (<><Filter className="h-4 w-4 mr-1.5" /> Construir matriz</>)}
              </Button>
            </div>
          </div>
          <p className="text-[11px] text-muted-foreground mt-3">
            {eligibleUsers.length} empleado(s) elegibles · {days.length} día(s) ·{" "}
            {selectedUsers.length > 0 ? `${selectedUsers.length} seleccionados` : "todos los elegibles"}
          </p>
        </CardContent>
      </Card>

      {/* Toolbar + Matriz */}
      {built && (
        <>
          <div className="flex flex-wrap items-center gap-2 sticky top-0 z-20 bg-background/95 backdrop-blur py-2 border-b">
            {currentPlanObj && (
              <Badge className="rounded-full bg-primary/10 text-primary dark:text-foreground border-primary/30" variant="outline"
                     data-testid="asg-current-plan-badge">
                <Bookmark className="h-3 w-3 mr-1" /> {currentPlanObj.name}
                <button
                  type="button"
                  onClick={() => setCurrentPlan(null)}
                  className="ml-1.5 text-xs hover:text-red-600"
                  title="Cerrar planificación"
                  data-testid="asg-close-plan"
                >
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            )}
            <Badge variant="outline" className="rounded-full" data-testid="asg-selection-count">
              {selectedCells.size} celda(s) seleccionada(s)
            </Badge>
            <Button size="sm" variant="outline" onClick={selectAll} className="rounded-full h-8" data-testid="asg-select-all">
              Seleccionar todo
            </Button>
            <Button size="sm" variant="ghost" onClick={clearSelection} className="rounded-full h-8" data-testid="asg-clear-selection">
              Limpiar
            </Button>

            <PlansMenu
              plans={plans}
              onLoad={loadPlan}
              onRename={(p) => setSaveDialog({ mode: "rename", name: p.name, plan_id: p.plan_id })}
              onDelete={deletePlan}
              compact
              testid="asg-plans-menu"
            />

            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                if (currentPlan) {
                  const p = plans.find((x) => x.plan_id === currentPlan);
                  savePlan(p?.name || "Planificación", currentPlan);
                } else {
                  setSaveDialog({ mode: "new", name: "" });
                }
              }}
              className="rounded-full h-8 border-primary/30 text-primary dark:text-foreground hover:bg-primary/10"
              data-testid="asg-save-plan"
            >
              <Save className="h-3.5 w-3.5 mr-1.5" />
              {currentPlan ? "Guardar cambios" : "Guardar planificación"}
            </Button>
            {currentPlan && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  const p = plans.find((x) => x.plan_id === currentPlan);
                  setSaveDialog({ mode: "new", name: (p?.name || "") + " (copia)" });
                }}
                className="rounded-full h-8"
                data-testid="asg-save-plan-as"
              >
                Guardar como…
              </Button>
            )}

            <div className="flex-1" />
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button size="sm" disabled={selectedCells.size === 0 || saving}
                  className="rounded-full h-9 bg-primary hover:bg-primary/90"
                  data-testid="asg-assign-shift">
                  <Clock className="h-4 w-4 mr-1.5" /> Asignar turno <ChevronDown className="h-3 w-3 ml-1" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-64">
                <DropdownMenuLabel>Turnos disponibles</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {schedules.length === 0 && <p className="px-2 py-1 text-xs text-muted-foreground">No hay horarios creados</p>}
                {schedules.map((s) => (
                  <DropdownMenuItem key={s.schedule_id} onClick={() => applyShift(s.schedule_id)}
                    data-testid={`asg-shift-opt-${s.schedule_id}`}>
                    <Clock className="h-3.5 w-3.5 mr-1.5 text-muted-foreground" />
                    <span className="flex-1">{s.name}</span>
                    <span className="text-[10px] text-muted-foreground">
                      {(s.blocks?.length || 1) >= 2 ? "2 bloques" : "1 bloque"}
                    </span>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button size="sm" disabled={selectedCells.size === 0 || saving}
                  className="rounded-full h-9 bg-accent hover:bg-accent/90 text-primary font-semibold"
                  data-testid="asg-assign-novelty">
                  <Sparkles className="h-4 w-4 mr-1.5" /> Asignar novedad <ChevronDown className="h-3 w-3 ml-1" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuLabel>Catálogo de novedades</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {NOVELTY_OPTIONS.map((n) => (
                  <DropdownMenuItem key={n.value} onClick={() => applyNovelty(n.value)}
                    data-testid={`asg-novelty-opt-${n.value}`}>
                    <n.icon className="h-3.5 w-3.5 mr-1.5 text-muted-foreground" />
                    {n.label}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
            <Button size="sm" variant="outline" disabled={selectedCells.size === 0 || saving}
              onClick={clearCells} className="rounded-full h-9 border-red-300 text-red-700 hover:bg-red-50"
              data-testid="asg-clear-cells">
              <Trash2 className="h-4 w-4 mr-1.5" /> Vaciar
            </Button>
          </div>

          <Card className="overflow-hidden">
            <div className="overflow-auto max-h-[70vh]">
              <table className="text-xs w-full border-collapse" data-testid="asg-matrix">
                <thead>
                  <tr>
                    <th className="sticky top-0 left-0 z-30 bg-muted/95 backdrop-blur px-2 py-2 text-left min-w-[240px] border-r border-b">
                      Empleado
                    </th>
                    {days.map((d) => {
                      const we = isWeekend(d);
                      return (
                        <th key={d}
                            className={
                              "sticky top-0 z-20 backdrop-blur px-2 py-2 text-center border-b border-r min-w-[120px] " +
                              (we ? "bg-slate-200/90 text-slate-700" : "bg-muted/95")
                            }>
                          <div className="font-semibold">{shortDay(d)}</div>
                        </th>
                      );
                    })}
                  </tr>
                </thead>
                <tbody>
                  {rows.length === 0 && (
                    <tr><td colSpan={days.length + 1} className="text-center text-muted-foreground py-8">
                      No hay empleados en la matriz — ajusta los filtros y construye de nuevo.
                    </td></tr>
                  )}
                  {rows.map((u) => (
                    <tr key={u.user_id} className="border-b hover:bg-muted/20">
                      <td className="sticky left-0 z-10 bg-card px-2 py-2 border-r whitespace-nowrap">
                        <p className="font-medium text-foreground text-sm">{u.name}</p>
                        <p className="text-[10px] text-muted-foreground">{u.position || u.email}</p>
                      </td>
                      {days.map((d) => {
                        const key = `${u.user_id}|${d}`;
                        const asg = assignments[key];
                        const isSel = selectedCells.has(key);
                        const we = isWeekend(d);
                        let cellCls = "border-r px-1 py-1 cursor-pointer transition-colors text-center align-middle ";
                        let content = null;
                        if (asg) {
                          if (asg.kind === "shift") {
                            const sname = scheduleMap[asg.schedule_id]?.name || "Turno";
                            content = (
                              <div className="px-1.5 py-1 rounded-md border border-primary/30 bg-primary/10 text-primary dark:text-foreground font-medium truncate">
                                <Clock className="h-3 w-3 inline mr-1 -mt-0.5" />
                                {sname}
                              </div>
                            );
                          } else {
                            const nv = NOVELTY_MAP[asg.novelty_type];
                            const Icon = nv?.icon || Sparkles;
                            content = (
                              <div className={"px-1.5 py-1 rounded-md border font-medium truncate " + (nv?.color || "bg-slate-100 text-slate-800 border-slate-300")}>
                                <Icon className="h-3 w-3 inline mr-1 -mt-0.5" />
                                {nv?.label || "Novedad"}
                              </div>
                            );
                          }
                        } else {
                          content = <span className="text-slate-300">—</span>;
                        }
                        cellCls += isSel
                          ? "bg-accent/25 outline outline-2 outline-accent -outline-offset-2 "
                          : (we ? "bg-slate-100/70 hover:bg-slate-200/70 " : "hover:bg-muted/40 ");
                        return (
                          <td key={key} className={cellCls} onClick={(e) => toggleCell(u.user_id, d, e)}
                              data-testid={`asg-cell-${u.user_id}-${d}`}>
                            {content}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          <p className="text-[11px] text-muted-foreground text-center">
            Clic sobre las celdas para seleccionar · Shift+clic para rangos dentro de una fila
          </p>
        </>
      )}

      <SavePlanDialog
        state={saveDialog}
        onCancel={() => setSaveDialog(null)}
        onConfirm={async (name, planId) => {
          const ok = await savePlan(name, planId);
          if (ok) setSaveDialog(null);
        }}
      />

      <OverlapPlanDialog
        state={overlapDialog}
        onCancel={() => setOverlapDialog(null)}
        onOverwrite={async () => {
          const ok = await savePlan(overlapDialog.name, overlapDialog.plan_id, true);
          if (ok) {
            setOverlapDialog(null);
            setSaveDialog(null);
          }
        }}
      />
    </div>
  );
}

function PlansMenu({ plans, onLoad, onRename, onDelete, compact = false, testid }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          size={compact ? "sm" : "default"}
          variant={compact ? "outline" : "default"}
          className={
            compact
              ? "rounded-full h-8"
              : "rounded-full h-11 bg-primary hover:bg-primary/90 shadow-md"
          }
          data-testid={testid || "asg-plans-menu-header"}
        >
          <FolderOpen className={compact ? "h-3.5 w-3.5 mr-1.5" : "h-4 w-4 mr-1.5"} />
          {compact ? "Planificaciones" : "Cargar planificación existente"}
          {plans.length > 0 && (
            <span className={compact ? "ml-1.5 text-[10px] text-muted-foreground" : "ml-2 text-[11px] bg-white/15 rounded-full px-1.5"}>
              {plans.length}
            </span>
          )}
          <ChevronDown className="h-3 w-3 ml-1" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align={compact ? "start" : "end"} className="w-96">
        <DropdownMenuLabel className="flex items-center justify-between">
          <span>Planificaciones guardadas</span>
          <span className="text-[10px] text-muted-foreground font-normal">
            {plans.length} disponibles
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {plans.length === 0 && (
          <div className="px-3 py-6 text-center">
            <Bookmark className="h-5 w-5 text-muted-foreground/50 mx-auto mb-1" />
            <p className="text-xs text-muted-foreground">
              Aún no tienes planificaciones guardadas. Construye una matriz y usa
              <b> Guardar planificación</b> para conservarla.
            </p>
          </div>
        )}
        <div className="max-h-[380px] overflow-y-auto">
          {[...plans]
            .sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || ""))
            .map((p) => (
              <div key={p.plan_id} className="flex items-center px-1 group hover:bg-muted/40 rounded-md"
                   data-testid={`asg-plan-row-${p.plan_id}`}>
                <button
                  type="button"
                  onClick={() => onLoad(p)}
                  className="flex-1 text-left px-2 py-2 rounded-md cursor-pointer min-w-0"
                  data-testid={`asg-plan-load-${p.plan_id}`}
                >
                  <p className="text-sm font-medium truncate">{p.name}</p>
                  <p className="text-[10px] text-muted-foreground truncate">
                    {p.from_date} → {p.to_date} · {(p.user_ids && p.user_ids.length) || "todos los"} empleado(s)
                    {p.updated_at && (
                      <> · <span title={p.updated_at}>actualizada {timeAgo(p.updated_at)}</span></>
                    )}
                  </p>
                </button>
                <button
                  type="button"
                  onClick={() => onRename(p)}
                  className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground opacity-0 group-hover:opacity-100 transition-opacity"
                  title="Renombrar"
                  data-testid={`asg-plan-rename-${p.plan_id}`}
                >
                  <Pencil className="h-3 w-3" />
                </button>
                <button
                  type="button"
                  onClick={() => onDelete(p)}
                  className="p-1.5 rounded-md hover:bg-red-50 text-muted-foreground hover:text-red-600 opacity-0 group-hover:opacity-100 transition-opacity"
                  title="Eliminar"
                  data-testid={`asg-plan-delete-${p.plan_id}`}
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </div>
            ))}
        </div>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function timeAgo(iso) {
  try {
    const d = new Date(iso).getTime();
    const s = Math.max(0, Math.floor((Date.now() - d) / 1000));
    if (s < 60) return "hace un momento";
    const m = Math.floor(s / 60);
    if (m < 60) return `hace ${m} min`;
    const h = Math.floor(m / 60);
    if (h < 24) return `hace ${h} h`;
    const dd = Math.floor(h / 24);
    if (dd < 30) return `hace ${dd} d`;
    return new Date(iso).toLocaleDateString("es-VE", { day: "2-digit", month: "short" });
  } catch (_) { return ""; }
}

function SavePlanDialog({ state, onCancel, onConfirm }) {
  const [name, setName] = useState("");
  useEffect(() => { setName(state?.name || ""); }, [state]);
  const isRename = state?.mode === "rename";
  return (
    <Dialog open={!!state} onOpenChange={(v) => !v && onCancel()}>
      <DialogContent className="max-w-sm" data-testid="asg-save-dialog">
        <DialogHeader className="items-center text-center">
          <div className="h-12 w-12 rounded-2xl bg-primary/10 grid place-items-center mb-2">
            <Bookmark className="h-6 w-6 text-primary dark:text-foreground" />
          </div>
          <DialogTitle>{isRename ? "Renombrar planificación" : "Guardar planificación"}</DialogTitle>
          <DialogDescription className="text-center">
            {isRename
              ? "Cambia el nombre y los filtros asociados a esta planificación."
              : "Dale un nombre que puedas reconocer luego (ej. “Guardias Julio 2026”)."}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-1.5">
          <Label className="text-xs">Nombre</Label>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value.slice(0, 80))}
            placeholder="Planificación Julio · Monitoreo"
            className="h-11"
            autoFocus
            data-testid="asg-save-name"
          />
          <p className="text-[10px] text-muted-foreground">{name.length}/80</p>
        </div>
        <DialogFooter className="flex-row gap-2 sm:justify-stretch pt-2">
          <Button variant="outline" onClick={onCancel} className="rounded-full flex-1 h-11"
                  data-testid="asg-save-cancel">
            Cancelar
          </Button>
          <Button onClick={() => onConfirm(name, state?.plan_id || null)}
                  className="rounded-full flex-1 h-11 bg-primary hover:bg-primary/90"
                  data-testid="asg-save-confirm">
            <Save className="h-4 w-4 mr-1.5" /> {isRename ? "Guardar" : "Crear"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function OverlapPlanDialog({ state, onCancel, onOverwrite }) {
  const [busy, setBusy] = useState(false);
  const conflicts = state?.conflicts || [];

  async function handleOverwrite() {
    setBusy(true);
    try { await onOverwrite(); }
    finally { setBusy(false); }
  }

  return (
    <Dialog open={!!state} onOpenChange={(v) => !v && !busy && onCancel()}>
      <DialogContent className="max-w-md" data-testid="asg-overlap-dialog">
        <DialogHeader className="items-center text-center">
          <div className="h-12 w-12 rounded-2xl bg-amber-100 grid place-items-center mb-2">
            <Sparkles className="h-6 w-6 text-amber-700" />
          </div>
          <DialogTitle>Rango de fechas ya planificado</DialogTitle>
          <DialogDescription className="text-center">
            {state?.message
              || "Ya existen planificaciones cuyo rango se solapa con este."}
          </DialogDescription>
        </DialogHeader>

        <div className="rounded-xl border border-amber-200 bg-amber-50/60 divide-y divide-amber-100 max-h-56 overflow-y-auto"
             data-testid="asg-overlap-conflicts">
          {conflicts.map((c) => (
            <div key={c.plan_id} className="px-3 py-2">
              <p className="text-sm font-semibold text-amber-900">{c.name}</p>
              <p className="text-[11px] text-amber-800/80">
                {c.from_date} → {c.to_date} · {(c.user_ids && c.user_ids.length) || "todos"} empleado(s)
              </p>
            </div>
          ))}
        </div>

        <p className="text-[11px] text-muted-foreground">
          Puedes <b>rechazar</b> para volver a editar el rango o los empleados,
          o <b>reescribir</b>: la(s) planificación(es) anterior(es) se eliminarán
          y esta pasará a ocupar el rango. Las asignaciones diarias ya cargadas
          en <i>schedule_assignments</i> permanecen intactas.
        </p>

        <DialogFooter className="flex-row gap-2 sm:justify-stretch pt-2">
          <Button
            variant="outline"
            onClick={onCancel}
            disabled={busy}
            className="rounded-full flex-1 h-11"
            data-testid="asg-overlap-cancel"
          >
            <X className="h-4 w-4 mr-1.5" /> Rechazar
          </Button>
          <Button
            onClick={handleOverwrite}
            disabled={busy}
            className="rounded-full flex-1 h-11 bg-amber-600 hover:bg-amber-700 text-white font-semibold"
            data-testid="asg-overlap-overwrite"
          >
            {busy
              ? (<><RefreshCw className="h-4 w-4 mr-1.5 animate-spin" /> Reescribiendo…</>)
              : (<><Save className="h-4 w-4 mr-1.5" /> Reescribir</>)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}


function EmployeePicker({ all, value, onChange }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const filtered = useMemo(() => {
    const q = query.toLowerCase();
    return all.filter((u) => (u.name || "").toLowerCase().includes(q));
  }, [all, query]);
  const label = value.length === 0
    ? "Todos los elegibles"
    : value.length === 1
      ? all.find((u) => u.user_id === value[0])?.name || "1 seleccionado"
      : `${value.length} seleccionados`;

  function toggle(uid) {
    onChange(value.includes(uid) ? value.filter((v) => v !== uid) : [...value, uid]);
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="outline" className="w-full justify-between h-10 rounded-md font-normal" data-testid="asg-employees-picker">
          <span className="truncate">{label}</span>
          <ChevronDown className="h-4 w-4 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[360px] p-0" align="start">
        <Command>
          <CommandInput placeholder="Buscar empleado…" value={query} onValueChange={setQuery} />
          <CommandList className="max-h-64">
            <CommandEmpty>Sin resultados</CommandEmpty>
            <CommandGroup>
              <CommandItem onSelect={() => onChange([])} className="text-xs">
                <span className="flex-1">— Todos los elegibles —</span>
              </CommandItem>
              {filtered.map((u) => (
                <CommandItem key={u.user_id} onSelect={() => toggle(u.user_id)}
                  data-testid={`asg-employees-opt-${u.user_id}`}>
                  <input type="checkbox" readOnly checked={value.includes(u.user_id)} className="mr-2 h-3.5 w-3.5 accent-primary" />
                  <span className="flex-1 truncate">{u.name}</span>
                  <span className="text-[10px] text-muted-foreground">{u.position || ""}</span>
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
