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
  CalendarRange, Filter, Users, ChevronDown, RefreshCw,
  Clock, Palmtree, HeartPulse, Home, TicketCheck, Trash2, Sparkles,
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

export default function AsignarHorariosPage() {
  const { user } = useAuth();
  const canAccess = user?.role === "admin" || !!user?.can_assign_schedules;

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

  useEffect(() => {
    if (!canAccess) return;
    (async () => {
      try {
        const [eu, sc] = await Promise.all([
          api.get("/schedule-assignments/eligible-users"),
          api.get("/schedules"),
        ]);
        setEligibleUsers(eu.data || []);
        setSchedules(sc.data || []);
      } catch (e) {
        toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
      }
    })();
  }, [canAccess]);

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
      const uids = selectedUsers.length > 0 ? selectedUsers : eligibleUsers.map((u) => u.user_id);
      const { data } = await api.get("/schedule-assignments", {
        params: {
          from_date: fromDate,
          to_date: toDate,
          user_ids: uids.join(","),
        },
      });
      const map = {};
      (data || []).forEach((a) => { map[`${a.user_id}|${a.date}`] = a; });
      setAssignments(map);
      setSelectedCells(new Set());
      setBuilt(true);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally { setLoading(false); }
  }

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
      <div>
        <div className="flex items-center gap-2 text-xs uppercase tracking-widest text-muted-foreground">
          <Sparkles className="h-3 w-3" /> Planificación
        </div>
        <h1 className="text-3xl font-bold">Asignación de horarios</h1>
        <p className="text-sm text-muted-foreground">
          Planifica turnos rotativos y novedades para el personal sin horario fijo. Todo lo que asignes aquí
          alimenta el <b>Reporte Matricial</b> y define la tolerancia con la que se evalúan sus marcajes.
        </p>
      </div>

      {/* Filtros */}
      <Card>
        <CardContent className="pt-5 pb-4 space-y-3">
          <div className="grid gap-3 md:grid-cols-4">
            <div>
              <Label className="text-xs flex items-center gap-1"><CalendarRange className="h-3 w-3" /> Desde</Label>
              <Input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} data-testid="asg-from" />
            </div>
            <div>
              <Label className="text-xs">Hasta</Label>
              <Input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} data-testid="asg-to" />
            </div>
            <div className="md:col-span-2">
              <Label className="text-xs flex items-center gap-1"><Users className="h-3 w-3" /> Empleados sin horario fijo</Label>
              <EmployeePicker
                all={eligibleUsers}
                value={selectedUsers}
                onChange={setSelectedUsers}
              />
            </div>
          </div>
          <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
            <p className="text-[11px] text-muted-foreground">
              {eligibleUsers.length} empleado(s) elegibles · {days.length} día(s) · {selectedUsers.length > 0 ? `${selectedUsers.length} seleccionados` : "todos los elegibles"}
            </p>
            <Button onClick={buildMatrix} disabled={loading} className="rounded-full" data-testid="asg-build">
              {loading
                ? (<><RefreshCw className="h-4 w-4 mr-1.5 animate-spin" /> Cargando…</>)
                : (<><Filter className="h-4 w-4 mr-1.5" /> Construir matriz</>)}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Toolbar + Matriz */}
      {built && (
        <>
          <div className="flex flex-wrap items-center gap-2 sticky top-0 z-20 bg-background/95 backdrop-blur py-2 border-b">
            <Badge variant="outline" className="rounded-full" data-testid="asg-selection-count">
              {selectedCells.size} celda(s) seleccionada(s)
            </Badge>
            <Button size="sm" variant="outline" onClick={selectAll} className="rounded-full h-8" data-testid="asg-select-all">
              Seleccionar todo
            </Button>
            <Button size="sm" variant="ghost" onClick={clearSelection} className="rounded-full h-8" data-testid="asg-clear-selection">
              Limpiar
            </Button>
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
                    {days.map((d) => (
                      <th key={d} className="sticky top-0 z-20 bg-muted/95 backdrop-blur px-2 py-2 text-center border-b border-r min-w-[120px]">
                        <div className="font-semibold">{shortDay(d)}</div>
                      </th>
                    ))}
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
                          : "hover:bg-muted/40 ";
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
    </div>
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
