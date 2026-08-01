import { useEffect, useMemo, useState } from "react";
import { api, API, getToken, formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import {
  LayoutGrid, Download, RefreshCw, FileText, FileSpreadsheet,
  Filter, ChevronDown,
} from "lucide-react";

const TZ = "America/Caracas";
const dfDayLabel = new Intl.DateTimeFormat("es-VE", { day: "2-digit", month: "short", timeZone: TZ });

function todayISO(offsetDays = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

const STATUS_STYLE = {
  normal:            { cls: "bg-emerald-50 text-emerald-700",    label: "OK" },
  late_justified:    { cls: "bg-amber-100 text-amber-800",       label: "Tarde-J" },
  late_unjustified:  { cls: "bg-red-100 text-red-800 font-bold", label: "Tarde-NJ" },
  novelty:           { cls: "bg-blue-100 text-blue-800",         label: "Novedad" },
  absent:            { cls: "bg-red-100 text-red-800 font-bold", label: "Falta" },
  non_working:       { cls: "bg-slate-100 text-slate-400",       label: "—" },
  future:            { cls: "bg-white text-slate-300",           label: "" },
};

export default function ReporteMatricialPage() {
  const { user } = useAuth();
  const isEmployee = user?.role === "employee";

  const [filters, setFilters] = useState({
    from_date: todayISO(-14),
    to_date: todayISO(0),
    department_id: "__all",
    user_id: "__all",
    site_id: "__all",
  });
  const [departments, setDepartments] = useState([]);
  const [users, setUsers] = useState([]);
  const [sites, setSites] = useState([]);
  const [data, setData] = useState({ days: [], rows: [] });
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(null); // 'pdf' | 'xlsx' | null

  useEffect(() => {
    (async () => {
      try {
        const calls = [api.get("/users"), api.get("/sites")];
        if (!isEmployee) calls.push(api.get("/departments"));
        const [u, s, d] = await Promise.all(calls);
        setUsers(u.data);
        setSites(s.data);
        if (d) setDepartments(d.data);
      } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message); }
    })();
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
    setLoading(true);
    try {
      const params = {
        from_date: filters.from_date,
        to_date: filters.to_date,
      };
      if (filters.department_id !== "__all") params.department_ids = filters.department_id;
      if (filters.user_id !== "__all") params.user_ids = filters.user_id;
      if (filters.site_id !== "__all") params.site_id = filters.site_id;
      const { data: d } = await api.get("/reports/matrix", { params });
      setData(d);
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message); }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  async function download(kind) {
    setExporting(kind);
    try {
      const params = new URLSearchParams({
        from_date: filters.from_date,
        to_date: filters.to_date,
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

  return (
    <div className="space-y-6" data-testid="matrix-report-page">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="flex items-center gap-2">
            <LayoutGrid className="h-5 w-5 text-primary" />
            <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Analítica avanzada</p>
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold text-primary mt-1">Reporte matricial de asistencia</h1>
          <p className="text-sm text-muted-foreground max-w-2xl">
            Matriz consolidada de entradas, salidas y novedades por empleado y día. Incluye totales de minutos perdidos y
            desglose por tipo de novedad.
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

      {/* Filtros */}
      <Card className="border-border/70 bg-card/70 backdrop-blur">
        <CardContent className="p-5">
          <div className="flex items-center gap-2 mb-3">
            <Filter className="h-4 w-4 text-primary" />
            <p className="text-sm font-semibold text-foreground">Filtros</p>
          </div>
          <div className={`grid grid-cols-2 sm:grid-cols-3 ${isEmployee ? "lg:grid-cols-4" : "lg:grid-cols-6"} gap-3`}>
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground">Desde</Label>
              <Input type="date" value={filters.from_date} onChange={(e) => setFilters((f) => ({ ...f, from_date: e.target.value }))} data-testid="matrix-from" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground">Hasta</Label>
              <Input type="date" value={filters.to_date} onChange={(e) => setFilters((f) => ({ ...f, to_date: e.target.value }))} data-testid="matrix-to" />
            </div>
            {!isEmployee && (
              <>
                <div className="space-y-1.5">
                  <Label className="text-[11px] text-muted-foreground">Departamento</Label>
                  <Select value={filters.department_id} onValueChange={(v) => setFilters((f) => ({ ...f, department_id: v, user_id: "__all" }))}>
                    <SelectTrigger data-testid="matrix-department"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="__all">Todos</SelectItem>
                      {departmentOptions.map((d) => (
                        <SelectItem key={d.department_id} value={d.department_id}>{d.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-1.5">
                  <Label className="text-[11px] text-muted-foreground">Empleado</Label>
                  <Select value={filters.user_id} onValueChange={(v) => setFilters((f) => ({ ...f, user_id: v }))}>
                    <SelectTrigger data-testid="matrix-user"><SelectValue /></SelectTrigger>
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
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground">Sede</Label>
              <Select value={filters.site_id} onValueChange={(v) => setFilters((f) => ({ ...f, site_id: v }))}>
                <SelectTrigger data-testid="matrix-site"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all">Todas</SelectItem>
                  {sites.map((s) => (
                    <SelectItem key={s.site_id} value={s.site_id}>{s.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-end">
              <Button onClick={load} disabled={loading} className="w-full rounded-full" data-testid="matrix-apply">
                <RefreshCw className={`h-4 w-4 mr-2 ${loading ? "animate-spin" : ""}`} />
                {loading ? "Cargando…" : "Aplicar"}
              </Button>
            </div>
          </div>

          {/* Leyenda */}
          <div className="mt-4 flex flex-wrap gap-2 text-[11px]">
            {Object.entries(STATUS_STYLE).filter(([k]) => k !== "future").map(([k, v]) => (
              <span key={k} className={`px-2 py-0.5 rounded ${v.cls}`}>{v.label || k}</span>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Matriz */}
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
                    <th key={day} colSpan={3} className="px-2 py-1 text-center border-r border-white/10 whitespace-nowrap">
                      {dfDayLabel.format(new Date(day + "T12:00"))}
                    </th>
                  ))}
                  <th colSpan={5} className="px-2 py-1 text-center border-l border-white/20 bg-slate-800">Totales</th>
                </tr>
                <tr className="text-[10px] uppercase tracking-wider">
                  {data.days.map((day) => (
                    <>
                      <th key={day + "in"}  className="px-1 py-1 border-r border-white/10">Ent.</th>
                      <th key={day + "out"} className="px-1 py-1 border-r border-white/10">Sal.</th>
                      <th key={day + "st"}  className="px-1 py-1 border-r border-white/10">Est.</th>
                    </>
                  ))}
                  <th className="px-1 py-1 bg-slate-800">Min. perd.</th>
                  <th className="px-1 py-1 bg-slate-800">T-J</th>
                  <th className="px-1 py-1 bg-slate-800">T-NJ</th>
                  <th className="px-1 py-1 bg-slate-800">Novedades</th>
                  <th className="px-1 py-1 bg-slate-800">Faltas</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40">
                {loading && (
                  <tr><td className="p-8 text-center text-muted-foreground" colSpan={99}>Cargando matriz…</td></tr>
                )}
                {!loading && data.rows.length === 0 && (
                  <tr><td className="p-10 text-center text-muted-foreground" colSpan={99}>Sin resultados para los filtros aplicados.</td></tr>
                )}
                {!loading && data.rows.map((r) => {
                  const novTotal = r.totals.vacation_days + r.totals.leave_days + r.totals.remote_days + r.totals.permission_days + (r.totals.medical_days || 0);
                  return (
                    <tr key={r.user_id} className="hover:bg-muted/30" data-testid={`matrix-row-${r.user_id}`}>
                      <td className="sticky left-0 bg-card px-3 py-1.5 font-medium whitespace-nowrap border-r border-border/50">
                        <div className="text-foreground">{r.name}</div>
                        <div className="text-[10px] text-muted-foreground">{r.position || "—"}</div>
                      </td>
                      <td className="px-2 py-1.5 whitespace-nowrap border-r border-border/50">{r.cedula || "—"}</td>
                      <td className="px-2 py-1.5 whitespace-nowrap border-r border-border/50">{r.department || "—"}</td>
                      {data.days.map((day) => {
                        const c = r.cells[day] || {};
                        const st = STATUS_STYLE[c.status] || STATUS_STYLE.normal;
                        const isNoInfo = c.status === "future";
                        return (
                          <>
                            <td key={day + "in"}  className="px-1 py-1 text-center whitespace-nowrap border-r border-border/40">{c.check_in || (isNoInfo ? "" : "–")}</td>
                            <td key={day + "out"} className="px-1 py-1 text-center whitespace-nowrap border-r border-border/40">{c.check_out || (isNoInfo ? "" : "–")}</td>
                            <td key={day + "st"}  className={`px-1 py-1 text-center whitespace-nowrap border-r border-border/40 ${st.cls}`} title={c.novelty_label || c.reason || ""}>
                              {c.status === "novelty"
                                ? (c.novelty_label || "Novedad")
                                : (st.label || "")}
                              {c.status === "late_unjustified" && c.late_minutes ? ` (${c.late_minutes}m)` : ""}
                            </td>
                          </>
                        );
                      })}
                      <td className="px-1 py-1 text-center bg-slate-50 font-semibold text-red-700">{r.totals.lost_minutes}</td>
                      <td className="px-1 py-1 text-center bg-slate-50">{r.totals.late_justified}</td>
                      <td className="px-1 py-1 text-center bg-slate-50 font-semibold text-red-700">{r.totals.late_unjustified}</td>
                      <td className="px-1 py-1 text-center bg-slate-50">{novTotal}</td>
                      <td className="px-1 py-1 text-center bg-slate-50 font-semibold text-red-700">{r.totals.absent_days}</td>
                    </tr>
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
