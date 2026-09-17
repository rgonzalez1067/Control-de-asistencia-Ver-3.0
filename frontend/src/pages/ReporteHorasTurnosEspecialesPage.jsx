import { useEffect, useMemo, useState } from "react";
import { api, API, getToken, formatApiErrorDetail } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Popover, PopoverContent, PopoverTrigger,
} from "@/components/ui/popover";
import {
  Timer, Calendar, Filter, RefreshCw, FileSpreadsheet, Users, Building2,
  Sun, Moon, PartyPopper, Bed, Check,
} from "lucide-react";

function todayISO(offsetDays = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}
const fmtH = (v) => Number(v || 0).toFixed(2).replace(/\.00$/, "");

export default function ReporteHorasTurnosEspecialesPage() {
  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState({ days_total: 0, rows_count: 0 });
  const [users, setUsers] = useState([]);
  const [departments, setDepartments] = useState([]);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [filters, setFilters] = useState({
    from_date: todayISO(-30),
    to_date: todayISO(0),
    department_id: "__all",
    user_ids: [],
  });

  useEffect(() => {
    async function loadRefs() {
      try {
        const [u, d] = await Promise.all([api.get("/users"), api.get("/departments")]);
        // Solo empleados sin horario fijo (Horario Especial)
        const specials = (u.data || []).filter((usr) => !usr.schedule_id);
        setUsers(specials.sort((a, b) => (a.name || "").localeCompare(b.name || "", "es", { sensitivity: "base" })));
        setDepartments(d.data);
      } catch (e) {
        toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
      }
    }
    loadRefs();
  }, []);

  const params = useMemo(() => {
    const p = new URLSearchParams();
    if (filters.from_date) p.set("from_date", filters.from_date);
    if (filters.to_date) p.set("to_date", filters.to_date);
    if (filters.department_id !== "__all") p.append("department_ids", filters.department_id);
    filters.user_ids.forEach((uid) => p.append("user_ids", uid));
    return p;
  }, [filters]);

  async function fetchReport() {
    if (!filters.from_date || !filters.to_date) {
      toast.error("El rango de fechas (Desde/Hasta) es obligatorio");
      return;
    }
    setLoading(true);
    try {
      const { data } = await api.get(`/reports/special-hours?${params.toString()}`);
      setRows(data.rows || []);
      setMeta({ days_total: data.days_total || 0, rows_count: data.rows_count || 0 });
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally { setLoading(false); }
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetchReport(); }, []);

  async function exportXlsx() {
    if (!filters.from_date || !filters.to_date) {
      toast.error("El rango de fechas (Desde/Hasta) es obligatorio");
      return;
    }
    setExporting(true);
    try {
      const r = await fetch(`${API}/reports/special-hours/export.xlsx?${params.toString()}`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!r.ok) {
        const data = await r.json().catch(() => null);
        throw new Error(formatApiErrorDetail(data?.detail) || "Error al exportar");
      }
      const blob = await r.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `asistencia_turnos_especiales_${filters.from_date}_a_${filters.to_date}.xlsx`;
      a.click();
      toast.success("Excel descargado");
    } catch (e) { toast.error(e.message); }
    finally { setExporting(false); }
  }

  const totals = useMemo(() => rows.reduce((acc, r) => ({
    trabajados: acc.trabajados + r.dias_trabajados,
    diurnas: acc.diurnas + r.horas_diurnas,
    nocturnas: acc.nocturnas + r.horas_nocturnas,
    fer_d: acc.fer_d + r.feriadas_diurnas,
    fer_n: acc.fer_n + r.feriadas_nocturnas,
    desc: acc.desc + r.horas_descanso,
  }), { trabajados: 0, diurnas: 0, nocturnas: 0, fer_d: 0, fer_n: 0, desc: 0 }), [rows]);

  function toggleUser(uid) {
    setFilters((f) => ({
      ...f,
      user_ids: f.user_ids.includes(uid) ? f.user_ids.filter((x) => x !== uid) : [...f.user_ids, uid],
    }));
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-4" data-testid="special-hours-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <Badge variant="secondary" className="rounded-full mb-2">Gerencia de Monitoreo · Turnos Especiales</Badge>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <Timer className="h-7 w-7 text-primary/70" /> Reporte de Asistencia Turnos Especiales
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Consolidado de horas diurnas, nocturnas, feriadas y descansos para personal con Horario Especial (rotativos/monitoreo).
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Button variant="outline" onClick={fetchReport} disabled={loading} className="rounded-full" data-testid="sh-refresh">
            <RefreshCw className={"h-4 w-4 mr-1.5 " + (loading ? "animate-spin" : "")} /> Actualizar
          </Button>
          <Button onClick={exportXlsx} disabled={exporting || rows.length === 0}
                  className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground shadow-lg shadow-primary/20"
                  data-testid="sh-export-xlsx">
            <FileSpreadsheet className="h-4 w-4 mr-1.5" /> {exporting ? "Generando…" : "Exportar a Excel"}
          </Button>
        </div>
      </div>

      <Card>
        <CardContent className="pt-4 space-y-3">
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-muted-foreground">
            <Filter className="h-3.5 w-3.5" /> Parámetros de búsqueda
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground flex items-center gap-1"><Calendar className="h-3 w-3" /> Desde *</Label>
              <Input type="date" value={filters.from_date} className="h-10" data-testid="sh-from"
                     onChange={(e) => setFilters((f) => ({ ...f, from_date: e.target.value }))} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground flex items-center gap-1"><Calendar className="h-3 w-3" /> Hasta *</Label>
              <Input type="date" value={filters.to_date} className="h-10" data-testid="sh-to"
                     onChange={(e) => setFilters((f) => ({ ...f, to_date: e.target.value }))} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground flex items-center gap-1"><Building2 className="h-3 w-3" /> Departamento</Label>
              <Select value={filters.department_id} onValueChange={(v) => setFilters((f) => ({ ...f, department_id: v }))}>
                <SelectTrigger className="h-10" data-testid="sh-dept"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all">Todos</SelectItem>
                  {departments.map((d) => <SelectItem key={d.department_id} value={d.department_id}>{d.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground flex items-center gap-1"><Users className="h-3 w-3" /> Empleados</Label>
              <Popover>
                <PopoverTrigger asChild>
                  <Button variant="outline" className="h-10 w-full justify-start font-normal" data-testid="sh-users-trigger">
                    {filters.user_ids.length === 0
                      ? <span className="text-muted-foreground">Todos ({users.length})</span>
                      : `${filters.user_ids.length} seleccionado(s)`}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-64 p-0" align="start">
                  <div className="p-2 border-b flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">{filters.user_ids.length} de {users.length}</span>
                    <button className="text-primary hover:underline" onClick={() => setFilters((f) => ({ ...f, user_ids: [] }))}>Limpiar</button>
                  </div>
                  <div className="max-h-60 overflow-y-auto" data-testid="sh-users-list">
                    {users.map((u) => {
                      const sel = filters.user_ids.includes(u.user_id);
                      return (
                        <button key={u.user_id} onClick={() => toggleUser(u.user_id)}
                                className={`w-full text-left px-3 py-1.5 text-xs hover:bg-muted flex items-center gap-2 ${sel ? "bg-primary/5" : ""}`}>
                          <span className={`h-3.5 w-3.5 rounded border grid place-items-center ${sel ? "bg-primary border-primary" : "border-muted-foreground/30"}`}>
                            {sel && <Check className="h-2.5 w-2.5 text-primary-foreground" />}
                          </span>
                          <span className="flex-1 truncate">{u.name}</span>
                        </button>
                      );
                    })}
                    {users.length === 0 && <p className="p-3 text-xs text-muted-foreground">Sin empleados con Horario Especial</p>}
                  </div>
                </PopoverContent>
              </Popover>
            </div>
          </div>
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <p className="text-xs text-muted-foreground" data-testid="sh-count">
              {meta.rows_count} empleado{meta.rows_count !== 1 ? "s" : ""} · {meta.days_total} día{meta.days_total !== 1 ? "s" : ""} en el periodo
            </p>
            <Button size="sm" onClick={fetchReport} disabled={loading}
                    className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground" data-testid="sh-apply">
              Aplicar filtros
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40">
                <TableHead>Cédula</TableHead>
                <TableHead>Nombre y Apellido</TableHead>
                <TableHead>Departamento</TableHead>
                <TableHead className="text-right">Días totales</TableHead>
                <TableHead className="text-right">Días trabajados</TableHead>
                <TableHead className="text-right"><Sun className="h-3 w-3 inline mr-1 text-amber-500" />Diurnas</TableHead>
                <TableHead className="text-right"><Moon className="h-3 w-3 inline mr-1 text-indigo-500" />Nocturnas</TableHead>
                <TableHead className="text-right"><PartyPopper className="h-3 w-3 inline mr-1 text-rose-500" />Fer. Diurnas</TableHead>
                <TableHead className="text-right"><PartyPopper className="h-3 w-3 inline mr-1 text-rose-500" />Fer. Nocturnas</TableHead>
                <TableHead className="text-right"><Bed className="h-3 w-3 inline mr-1 text-slate-500" />Descanso</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody data-testid="sh-table">
              {loading && <TableRow><TableCell colSpan={10} className="text-center py-10 text-muted-foreground">Cargando…</TableCell></TableRow>}
              {!loading && rows.length === 0 && (
                <TableRow><TableCell colSpan={10} className="text-center py-10 text-muted-foreground">Sin datos para los filtros aplicados</TableCell></TableRow>
              )}
              {!loading && rows.map((r) => (
                <TableRow key={r.user_id} data-testid={`sh-row-${r.user_id}`}>
                  <TableCell className="text-xs font-mono">{r.cedula || "—"}</TableCell>
                  <TableCell className="text-sm font-medium">
                    {r.nombre}
                    <p className="text-[10px] text-muted-foreground">Turno base: {r.turno_referencia}</p>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{r.departamento}</TableCell>
                  <TableCell className="text-right text-xs tabular-nums">{r.dias_total}</TableCell>
                  <TableCell className="text-right text-xs tabular-nums font-semibold">{r.dias_trabajados}</TableCell>
                  <TableCell className="text-right text-xs tabular-nums">{fmtH(r.horas_diurnas)}</TableCell>
                  <TableCell className="text-right text-xs tabular-nums">{fmtH(r.horas_nocturnas)}</TableCell>
                  <TableCell className="text-right text-xs tabular-nums">{fmtH(r.feriadas_diurnas)}</TableCell>
                  <TableCell className="text-right text-xs tabular-nums">{fmtH(r.feriadas_nocturnas)}</TableCell>
                  <TableCell className="text-right text-xs tabular-nums">{fmtH(r.horas_descanso)}</TableCell>
                </TableRow>
              ))}
              {!loading && rows.length > 0 && (
                <TableRow className="bg-amber-50/60 border-t-2 border-amber-200 font-semibold" data-testid="sh-totals">
                  <TableCell colSpan={3} className="text-xs uppercase tracking-wider">Total general</TableCell>
                  <TableCell className="text-right text-xs tabular-nums">{meta.days_total}</TableCell>
                  <TableCell className="text-right text-xs tabular-nums">{totals.trabajados}</TableCell>
                  <TableCell className="text-right text-xs tabular-nums">{fmtH(totals.diurnas)}</TableCell>
                  <TableCell className="text-right text-xs tabular-nums">{fmtH(totals.nocturnas)}</TableCell>
                  <TableCell className="text-right text-xs tabular-nums">{fmtH(totals.fer_d)}</TableCell>
                  <TableCell className="text-right text-xs tabular-nums">{fmtH(totals.fer_n)}</TableCell>
                  <TableCell className="text-right text-xs tabular-nums">{fmtH(totals.desc)}</TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </Card>
    </div>
  );
}
