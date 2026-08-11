import { useEffect, useMemo, useState } from "react";
import { api, API, getToken, formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import {
  LayoutGrid, RefreshCw, FileText, FileSpreadsheet, Filter,
} from "lucide-react";

const TZ = "America/Caracas";
const dfDayLabel = new Intl.DateTimeFormat("es-VE", { day: "2-digit", month: "short", timeZone: TZ });

function todayISO(offsetDays = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

export default function ReporteMatricialPage() {
  const { user } = useAuth();
  const isEmployee = user?.role === "employee";

  const [filters, setFilters] = useState({
    from_date: todayISO(0),
    to_date: todayISO(0),
    department_id: "__all",
    user_id: "__all",
    site_id: "__all",
    schedule_id: "",
  });
  const [departments, setDepartments] = useState([]);
  const [users, setUsers] = useState([]);
  const [sites, setSites] = useState([]);
  const [schedules, setSchedules] = useState([]);
  const [data, setData] = useState({ days: [], rows: [], blocks_per_day: 1 });
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const calls = [api.get("/users"), api.get("/sites"), api.get("/schedules")];
        if (!isEmployee) calls.push(api.get("/departments"));
        const [u, s, sch, d] = await Promise.all(calls);
        setUsers(u.data);
        setSites(s.data);
        setSchedules(sch.data);
        if (d) setDepartments(d.data);
        // Selección por defecto del horario:
        //   1º) Preferimos el primer horario de 2 bloques (donde suele estar la mayoría del personal).
        //   2º) Si no hay ninguno de 2 bloques, tomamos el primero disponible.
        if (sch.data?.length && !filters.schedule_id) {
          const twoBlock = sch.data.find((s) => (s.blocks?.length || 0) >= 2);
          const defaultSch = twoBlock || sch.data[0];
          setFilters((f) => ({ ...f, schedule_id: defaultSch.schedule_id }));
        }
      } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message); }
    })();
    // eslint-disable-next-line
  }, [isEmployee]);

  const departmentOptions = useMemo(
    () => [...departments].sort((a, b) => (a.name || "").localeCompare(b.name || "", "es")),
    [departments],
  );
  const employeeOptions = useMemo(() => {
    const list = filters.department_id !== "__all"
      ? users.filter((u) => u.department_id === filters.department_id)
      : users;
    return [...list].sort((a, b) => (a.name || "").localeCompare(b.name || "", "es"));
  }, [users, filters.department_id]);

  async function load() {
    if (!filters.schedule_id) { toast.error("Selecciona un tipo de horario"); return; }
    setLoading(true);
    try {
      const params = {
        from_date: filters.from_date,
        to_date: filters.to_date,
        schedule_id: filters.schedule_id,
      };
      if (filters.department_id !== "__all") params.department_ids = filters.department_id;
      if (filters.user_id !== "__all") params.user_ids = filters.user_id;
      if (filters.site_id !== "__all") params.site_id = filters.site_id;
      const { data: d } = await api.get("/reports/matrix", { params });
      setData(d);
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message); }
    finally { setLoading(false); }
  }

  useEffect(() => { if (filters.schedule_id) load(); /* eslint-disable-next-line */ }, [filters.schedule_id]);

  async function download(kind) {
    if (!filters.schedule_id) { toast.error("Selecciona un tipo de horario"); return; }
    setExporting(kind);
    try {
      const params = new URLSearchParams({
        from_date: filters.from_date, to_date: filters.to_date,
        schedule_id: filters.schedule_id,
      });
      if (filters.department_id !== "__all") params.set("department_ids", filters.department_id);
      if (filters.user_id !== "__all") params.set("user_ids", filters.user_id);
      if (filters.site_id !== "__all") params.set("site_id", filters.site_id);
      const url = `${API}/reports/matrix/export.${kind}?${params}`;
      const resp = await fetch(url, { headers: { Authorization: `Bearer ${getToken()}` } });
      if (!resp.ok) throw new Error("Error al exportar");
      const blob = await resp.blob();
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `matriz_asistencia_${filters.from_date}_a_${filters.to_date}.${kind}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (e) { toast.error(e.message); }
    finally { setExporting(null); }
  }

  const bpd = data.blocks_per_day || 1;
  const dayLabels = bpd >= 2 ? ["E1", "S1", "E2", "S2"] : ["E1", "S1"];
  const perDay = 2 * bpd;

  const partialByRowDay = useMemo(() => {
    const m = {};
    (data.rows || []).forEach((r) => {
      if (!r.partial_novelties?.length) return;
      const byDay = {};
      for (const pn of r.partial_novelties) {
        byDay[pn.date] = byDay[pn.date] ? [...byDay[pn.date], pn] : [pn];
      }
      m[r.user_id] = byDay;
    });
    return m;
  }, [data.rows]);

  return (
    <div className="space-y-6" data-testid="matrix-report-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-2">
            <LayoutGrid className="h-5 w-5 text-primary" />
            <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Analítica avanzada</p>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold text-primary mt-1">Reporte matricial de asistencia</h1>
          <p className="text-sm text-muted-foreground max-w-2xl">
            Matriz consolidada de entradas, salidas y novedades por empleado y día — adaptada al tipo de horario.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => download("pdf")} disabled={exporting !== null} data-testid="matrix-export-pdf">
            <FileText className="h-4 w-4 mr-2" /> {exporting === "pdf" ? "Generando…" : "PDF"}
          </Button>
          <Button variant="outline" onClick={() => download("xlsx")} disabled={exporting !== null} data-testid="matrix-export-xlsx">
            <FileSpreadsheet className="h-4 w-4 mr-2" /> {exporting === "xlsx" ? "Generando…" : "Excel"}
          </Button>
        </div>
      </div>

      <Card className="border-border/70 bg-card/70 backdrop-blur">
        <CardContent className="p-5">
          <div className="flex items-center gap-2 mb-3">
            <Filter className="h-4 w-4 text-primary" />
            <p className="text-sm font-semibold text-foreground">Filtros</p>
          </div>
          <div className={`grid gap-3 grid-cols-2 sm:grid-cols-3 ${isEmployee ? "lg:grid-cols-4" : "lg:grid-cols-4"}`}>
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground">Desde</Label>
              <Input type="date" value={filters.from_date} onChange={(e) => setFilters((f) => ({ ...f, from_date: e.target.value }))} data-testid="matrix-from" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground">Hasta</Label>
              <Input type="date" value={filters.to_date} onChange={(e) => setFilters((f) => ({ ...f, to_date: e.target.value }))} data-testid="matrix-to" />
            </div>
            <div className="space-y-1.5 col-span-2 sm:col-span-1">
              <Label className="text-[11px] text-muted-foreground">Tipo de horario *</Label>
              <Select value={filters.schedule_id} onValueChange={(v) => setFilters((f) => ({ ...f, schedule_id: v }))}>
                <SelectTrigger data-testid="matrix-schedule" className="truncate"><SelectValue placeholder="Selecciona…" /></SelectTrigger>
                <SelectContent>
                  {schedules.map((s) => (
                    <SelectItem key={s.schedule_id} value={s.schedule_id} data-testid={`matrix-schedule-opt-${s.schedule_id}`}>
                      {s.name} {s.blocks?.length >= 2 ? " · 2 bloques" : " · 1 bloque"}
                    </SelectItem>
                  ))}
                  <SelectItem value="__special" data-testid="matrix-schedule-opt-special">
                    ⭐ Horario Especial · turnos rotativos
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground">Sede</Label>
              <Select value={filters.site_id} onValueChange={(v) => setFilters((f) => ({ ...f, site_id: v }))}>
                <SelectTrigger data-testid="matrix-site" className="truncate"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all">Todas</SelectItem>
                  {sites.map((s) => (
                    <SelectItem key={s.site_id} value={s.site_id}>{s.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {!isEmployee && (
              <>
                <div className="space-y-1.5 sm:col-span-1 lg:col-span-1">
                  <Label className="text-[11px] text-muted-foreground">Departamento</Label>
                  <Select value={filters.department_id} onValueChange={(v) => setFilters((f) => ({ ...f, department_id: v, user_id: "__all" }))}>
                    <SelectTrigger data-testid="matrix-department" className="truncate"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__all">Todos</SelectItem>
                      {departmentOptions.map((d) => (
                        <SelectItem key={d.department_id} value={d.department_id}>{d.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5 sm:col-span-2 lg:col-span-2">
                  <Label className="text-[11px] text-muted-foreground">Empleado</Label>
                  <Select value={filters.user_id} onValueChange={(v) => setFilters((f) => ({ ...f, user_id: v }))}>
                    <SelectTrigger data-testid="matrix-user" className="truncate"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__all">Todos</SelectItem>
                      {employeeOptions.map((u) => (
                        <SelectItem key={u.user_id} value={u.user_id}>{u.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </>
            )}
            <div className="flex items-end col-span-2 sm:col-span-1 lg:col-span-1">
              <Button onClick={load} disabled={loading || !filters.schedule_id} className="w-full rounded-full" data-testid="matrix-apply">
                <RefreshCw className={`h-4 w-4 mr-2 ${loading ? "animate-spin" : ""}`} />
                {loading ? "Cargando…" : "Aplicar filtros"}
              </Button>
            </div>
          </div>

          <div className="mt-4 flex flex-wrap gap-2 text-[11px]">
            <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-700">Hora <b className="text-black">negro</b> = dentro de tolerancia</span>
            <span className="px-2 py-0.5 rounded bg-red-100 text-red-800"><b>Rojo</b> = tardanza o descanso &gt; 60 min</span>
            <span className="px-2 py-0.5 rounded bg-amber-100 text-amber-800 italic">Ámbar cursiva = salida auto-imputada 23:59</span>
            <span className="px-2 py-0.5 rounded bg-blue-100 text-blue-800">Vacaciones / Reposo / Trabajo Remoto = día completo</span>
            <span className="px-2 py-0.5 rounded bg-red-100 text-red-800">Falta = día laboral sin marcaje</span>
            <span className="px-2 py-0.5 rounded bg-indigo-100 text-indigo-800">Sub-fila = Cita médica / Permiso / Visita</span>
          </div>
        </CardContent>
      </Card>

      <Card className="border-border/70 bg-card/70 backdrop-blur">
        <CardContent className="p-0 overflow-hidden">
          <div className="overflow-auto max-h-[70vh]">
            <table className="text-xs border-collapse w-full" data-testid="matrix-table">
              <thead className="sticky top-0 z-10 bg-primary text-primary-foreground">
                <tr>
                  <th rowSpan={2} className="sticky left-0 z-20 bg-primary text-left px-3 py-2 border-r border-white/10">Empleado</th>
                  <th rowSpan={2} className="px-2 py-2 border-r border-white/10">Cédula</th>
                  <th rowSpan={2} className="px-2 py-2 border-r border-white/10">Depto</th>
                  {data.days.map((day) => (
                    <th key={day} colSpan={perDay} className="px-2 py-1 text-center border-r border-white/10 whitespace-nowrap">
                      {dfDayLabel.format(new Date(day + "T12:00"))}
                    </th>
                  ))}
                  <th colSpan={5} className="px-2 py-1 text-center border-l border-white/20 bg-slate-800">Totales</th>
                </tr>
                <tr className="text-[10px] uppercase tracking-wider">
                  {data.days.map((day) => (
                    dayLabels.map((lab) => (
                      <th key={day + lab} className="px-1 py-1 border-r border-white/10">{lab}</th>
                    ))
                  ))}
                  <th className="px-1 py-1 bg-slate-800">Min. perd.</th>
                  <th className="px-1 py-1 bg-slate-800">T-J</th>
                  <th className="px-1 py-1 bg-slate-800">T-NJ</th>
                  <th className="px-1 py-1 bg-slate-800">Novedades</th>
                  <th className="px-1 py-1 bg-slate-800">Faltas</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40">
                {loading && (<tr><td className="p-8 text-center text-muted-foreground" colSpan={99}>Cargando…</td></tr>)}
                {!loading && data.rows.length === 0 && (
                  <tr><td className="p-10 text-center text-muted-foreground" colSpan={99}>Sin resultados para los filtros aplicados.</td></tr>
                )}
                {!loading && data.rows.map((r) => {
                  const novTotal = r.totals.vacation_days + r.totals.leave_days + r.totals.remote_days + r.totals.permission_days + (r.totals.medical_days || 0) + (r.totals.client_visit_days || 0);
                  const partials = partialByRowDay[r.user_id] || {};
                  const hasPartials = Object.keys(partials).length > 0;
                  return (
                    <>
                      <tr key={r.user_id} className="hover:bg-muted/30" data-testid={`matrix-row-${r.user_id}`}>
                        <td className="sticky left-0 bg-card px-3 py-1.5 font-medium whitespace-nowrap border-r border-border/50">
                          <div className="text-foreground">{r.name}</div>
                          <div className="text-[10px] text-muted-foreground">{r.position || "—"}</div>
                        </td>
                        <td className="px-2 py-1.5 whitespace-nowrap border-r border-border/50">{r.cedula || "—"}</td>
                        <td className="px-2 py-1.5 whitespace-nowrap border-r border-border/50">{r.department || "—"}</td>
                        {data.days.map((day) => {
                          const c = r.cells[day] || {};
                          if (c.status === "novelty_full") {
                            return (
                              <td key={day} colSpan={perDay}
                                className="px-2 py-2 text-center bg-blue-100 text-blue-800 font-bold uppercase tracking-wide whitespace-nowrap border-r border-border/40"
                                title={c.reason || ""}>
                                {c.novelty_label}
                              </td>
                            );
                          }
                          if (c.status === "absent") {
                            return (
                              <td key={day} colSpan={perDay}
                                className="px-2 py-2 text-center bg-red-100 text-red-800 font-bold whitespace-nowrap border-r border-border/40">
                                FALTA
                              </td>
                            );
                          }
                          if (c.status === "non_working") {
                            return (
                              <td key={day} colSpan={perDay} className="px-2 py-1 text-center bg-slate-50 text-slate-300 border-r border-border/40">—</td>
                            );
                          }
                          if (c.status === "future") {
                            return (
                              <td key={day} colSpan={perDay} className="px-2 py-1 text-center bg-white text-slate-300 border-r border-border/40"></td>
                            );
                          }
                          const blocks = c.blocks || [];
                          const cells = [];
                          for (let i = 0; i < bpd; i++) {
                            const b = blocks[i] || {};
                            const inRed = b.in_late || b.break_over;
                            const inTitle = b.break_over
                              ? `Exceso de descanso: +${b.break_excess_minutes} min sumados a Min. perdidos`
                              : b.in_site_mismatch ? "Marcaje en sede distinta a la asignada" : undefined;
                            const inCls = b.in_site_mismatch
                              ? "bg-orange-100 text-orange-800 font-semibold"
                              : inRed ? "text-red-700 font-bold" : "text-slate-900";
                            const outTitle = b.auto_closed
                              ? "Salida imputada automáticamente al cierre del día (23:59)"
                              : b.out_site_mismatch ? "Marcaje en sede distinta a la asignada" : undefined;
                            const outCls = b.out_site_mismatch
                              ? "bg-orange-100 text-orange-800 font-semibold"
                              : b.auto_closed ? "text-amber-700 italic" : "text-slate-900";
                            cells.push(
                              <td key={day + "in" + i} title={inTitle}
                                className={`px-1 py-1 text-center whitespace-nowrap border-r border-border/40 ${inCls}`}>
                                {b.in || "–"}
                              </td>
                            );
                            cells.push(
                              <td key={day + "out" + i} title={outTitle}
                                className={`px-1 py-1 text-center whitespace-nowrap border-r border-border/40 ${outCls}`}>
                                {b.out || "–"}
                              </td>
                            );
                          }
                          return cells;
                        })}
                        <td className="px-1 py-1 text-center bg-slate-50 font-semibold text-red-700">{r.totals.lost_minutes}</td>
                        <td className="px-1 py-1 text-center bg-slate-50">{r.totals.late_justified}</td>
                        <td className="px-1 py-1 text-center bg-slate-50 font-semibold text-red-700">{r.totals.late_unjustified}</td>
                        <td className="px-1 py-1 text-center bg-slate-50">{novTotal}</td>
                        <td className="px-1 py-1 text-center bg-slate-50 font-semibold text-red-700">{r.totals.absent_days}</td>
                      </tr>
                      {hasPartials && (
                        <tr className="bg-indigo-50/60" data-testid={`matrix-partial-${r.user_id}`}>
                          <td className="sticky left-0 bg-indigo-50/60 px-3 py-1 text-[11px] italic text-indigo-700 whitespace-nowrap border-r border-border/50" colSpan={3}>
                            ↳ Novedades parciales
                          </td>
                          {data.days.map((day) => (
                            <td key={day + "p"} colSpan={perDay} className="px-1 py-1 text-[11px] text-indigo-800 text-center whitespace-nowrap border-r border-border/40 italic">
                              {(partials[day] || []).map((pn, i) => (
                                <div key={i}>{pn.label}: {pn.start_time || "?"}–{pn.end_time || "?"}</div>
                              ))}
                            </td>
                          ))}
                          <td className="bg-slate-50" colSpan={5}></td>
                        </tr>
                      )}
                    </>
                  );
                })}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
