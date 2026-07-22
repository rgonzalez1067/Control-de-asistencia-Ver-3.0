import { useEffect, useMemo, useState } from "react";
import { api, API, getToken, formatApiErrorDetail } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import {
  FileBarChart2, Download, LogIn, LogOut as LogOutIcon, MapPin,
  Filter, RefreshCw, AlertTriangle, CheckCircle2,
} from "lucide-react";

const TZ = "America/Caracas";
const dfDate = new Intl.DateTimeFormat("es-VE", { day: "2-digit", month: "short", year: "numeric", timeZone: TZ });
const dfTime = new Intl.DateTimeFormat("es-VE", { hour: "2-digit", minute: "2-digit", timeZone: TZ });

function todayISO(offsetDays = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

export default function ReportsPage() {
  const [users, setUsers] = useState([]);
  const [sites, setSites] = useState([]);
  const [records, setRecords] = useState([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({
    from_date: todayISO(-30),
    to_date: todayISO(0),
    user_id: "__all",
    site_id: "__all",
    type: "all",
    status: "all",
  });

  useEffect(() => {
    async function loadRefs() {
      try {
        const [u, s] = await Promise.all([api.get("/users"), api.get("/sites")]);
        setUsers(u.data);
        setSites(s.data);
      } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message); }
    }
    loadRefs();
  }, []);

  async function fetchReports() {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filters.from_date) params.set("from_date", filters.from_date);
      if (filters.to_date) params.set("to_date", filters.to_date);
      if (filters.user_id !== "__all") params.set("user_id", filters.user_id);
      if (filters.site_id !== "__all") params.set("site_id", filters.site_id);
      const { data } = await api.get(`/reports?${params.toString()}`);
      setRecords(data);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally { setLoading(false); }
  }

  useEffect(() => { fetchReports(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, []);

  const filtered = useMemo(() => {
    return records.filter((r) => {
      if (filters.type !== "all" && r.type !== filters.type) return false;
      if (filters.status === "late" && !r.is_late) return false;
      if (filters.status === "ontime" && (r.is_late || r.type !== "in")) return false;
      return true;
    });
  }, [records, filters.type, filters.status]);

  const userMap = useMemo(() => Object.fromEntries(users.map((u) => [u.user_id, u])), [users]);
  const siteMap = useMemo(() => Object.fromEntries(sites.map((s) => [s.site_id, s.name])), [sites]);

  const stats = useMemo(() => {
    const ins = filtered.filter((r) => r.type === "in");
    const outs = filtered.filter((r) => r.type === "out");
    const late = ins.filter((r) => r.is_late);
    const withJustification = filtered.filter((r) => r.justification);
    return { ins: ins.length, outs: outs.length, late: late.length, just: withJustification.length };
  }, [filtered]);

  function downloadCsv() {
    const params = new URLSearchParams();
    if (filters.from_date) params.set("from_date", filters.from_date);
    if (filters.to_date) params.set("to_date", filters.to_date);
    fetch(`${API}/reports/export?${params.toString()}`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
      .then((r) => { if (!r.ok) throw new Error("Export failed"); return r.blob(); })
      .then((blob) => {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `asistencia_${filters.from_date}_a_${filters.to_date}.csv`;
        a.click();
        toast.success("Reporte descargado");
      })
      .catch((e) => toast.error(e.message));
  }

  function resetFilters() {
    setFilters({
      from_date: todayISO(-30), to_date: todayISO(0),
      user_id: "__all", site_id: "__all", type: "all", status: "all",
    });
  }

  return (
    <div className="p-4 sm:p-8 max-w-7xl mx-auto space-y-6" data-testid="reports-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <Badge variant="secondary" className="rounded-full mb-3">Analítica</Badge>
          <h1 className="text-3xl sm:text-4xl font-bold text-foreground flex items-center gap-3">
            <FileBarChart2 className="h-8 w-8 text-primary/70" /> Reportes de asistencia
          </h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Filtra por rango de fechas, empleado, sede y tipo. Descarga CSV listo para RRHH o nómina.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={fetchReports} disabled={loading} className="rounded-full" data-testid="reports-refresh">
            <RefreshCw className={"h-4 w-4 mr-1.5 " + (loading ? "animate-spin" : "")} /> Actualizar
          </Button>
          <Button
            onClick={downloadCsv}
            disabled={records.length === 0}
            className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground shadow-lg shadow-primary/20"
            data-testid="reports-export-btn"
          >
            <Download className="h-4 w-4 mr-1.5" /> Exportar CSV
          </Button>
        </div>
      </div>

      <Card className="border-border/70 bg-card/80 backdrop-blur">
        <CardContent className="p-4 sm:p-5">
          <div className="flex items-center gap-2 mb-4 text-xs uppercase tracking-wider text-muted-foreground">
            <Filter className="h-3.5 w-3.5" /> Filtros
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground">Desde</Label>
              <Input type="date" value={filters.from_date} onChange={(e) => setFilters((f) => ({ ...f, from_date: e.target.value }))} data-testid="reports-from" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground">Hasta</Label>
              <Input type="date" value={filters.to_date} onChange={(e) => setFilters((f) => ({ ...f, to_date: e.target.value }))} data-testid="reports-to" />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground">Empleado</Label>
              <Select value={filters.user_id} onValueChange={(v) => setFilters((f) => ({ ...f, user_id: v }))}>
                <SelectTrigger data-testid="reports-user"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all">Todos</SelectItem>
                  {users.map((u) => (
                    <SelectItem key={u.user_id} value={u.user_id}>{u.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground">Sede</Label>
              <Select value={filters.site_id} onValueChange={(v) => setFilters((f) => ({ ...f, site_id: v }))}>
                <SelectTrigger data-testid="reports-site"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all">Todas</SelectItem>
                  {sites.map((s) => (
                    <SelectItem key={s.site_id} value={s.site_id}>{s.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground">Tipo</Label>
              <Select value={filters.type} onValueChange={(v) => setFilters((f) => ({ ...f, type: v }))}>
                <SelectTrigger data-testid="reports-type"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Entradas y salidas</SelectItem>
                  <SelectItem value="in">Solo entradas</SelectItem>
                  <SelectItem value="out">Solo salidas</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground">Estado</Label>
              <Select value={filters.status} onValueChange={(v) => setFilters((f) => ({ ...f, status: v }))}>
                <SelectTrigger data-testid="reports-status"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  <SelectItem value="ontime">A tiempo</SelectItem>
                  <SelectItem value="late">Tarde</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="mt-4 flex items-center gap-2 justify-end">
            <Button variant="ghost" size="sm" onClick={resetFilters} data-testid="reports-reset">Limpiar filtros</Button>
            <Button size="sm" onClick={fetchReports} disabled={loading} className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground" data-testid="reports-apply">
              Aplicar
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3" data-testid="reports-stats">
        <MiniStat icon={LogIn} tint="text-emerald-600" label="Entradas" value={stats.ins} />
        <MiniStat icon={LogOutIcon} tint="text-slate-700" label="Salidas" value={stats.outs} />
        <MiniStat icon={AlertTriangle} tint="text-amber-600" label="Tardanzas" value={stats.late} />
        <MiniStat icon={CheckCircle2} tint="text-fuchsia-600" label="Con justificación" value={stats.just} />
      </div>

      <Card className="border-border/70 bg-card/80 backdrop-blur overflow-hidden">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40">
                <TableHead>Fecha</TableHead>
                <TableHead>Hora</TableHead>
                <TableHead>Empleado</TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead>Sede</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead>Justificación</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody data-testid="reports-table">
              {loading && <TableRow><TableCell colSpan={7} className="text-center py-10 text-muted-foreground">Cargando…</TableCell></TableRow>}
              {!loading && filtered.length === 0 && (
                <TableRow><TableCell colSpan={7} className="text-center py-10 text-muted-foreground">No hay marcas en este rango con los filtros aplicados</TableCell></TableRow>
              )}
              {!loading && filtered.slice(0, 500).map((r) => {
                const u = userMap[r.user_id] || {};
                const d = new Date(r.timestamp);
                return (
                  <TableRow key={r.record_id}>
                    <TableCell className="text-sm whitespace-nowrap">{dfDate.format(d)}</TableCell>
                    <TableCell className="text-sm font-mono">{dfTime.format(d)}</TableCell>
                    <TableCell>
                      <div>
                        <p className="text-sm font-medium text-foreground leading-tight">{u.name || r.user_id}</p>
                        <p className="text-[11px] text-muted-foreground leading-tight">{u.cedula || u.email}</p>
                      </div>
                    </TableCell>
                    <TableCell>
                      {r.type === "in" ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 text-[11px] font-medium">
                          <LogIn className="h-3 w-3" /> Entrada
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-200 text-slate-700 text-[11px] font-medium">
                          <LogOutIcon className="h-3 w-3" /> Salida
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-sm">
                      <span className="inline-flex items-center gap-1 text-muted-foreground">
                        <MapPin className="h-3 w-3" /> {siteMap[r.site_id] || "—"}
                      </span>
                    </TableCell>
                    <TableCell>
                      {r.is_late ? (
                        <span className="inline-flex items-center gap-1 text-[11px] text-amber-700">
                          <AlertTriangle className="h-3 w-3" /> Tarde · {r.late_minutes}m
                        </span>
                      ) : r.type === "in" ? (
                        <span className="text-[11px] text-emerald-700">A tiempo</span>
                      ) : <span className="text-muted-foreground/60">—</span>}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground italic max-w-xs truncate">
                      {r.justification || "—"}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
        {filtered.length > 500 && (
          <p className="text-[11px] text-muted-foreground text-center py-3 border-t border-border/60">
            Mostrando primeras 500 filas de {filtered.length}. Descarga el CSV para el reporte completo.
          </p>
        )}
      </Card>
    </div>
  );
}

function MiniStat({ icon: Icon, label, value, tint }) {
  return (
    <Card className="border-border/70 bg-card/80 backdrop-blur">
      <CardContent className="pt-5">
        <Icon className={`h-5 w-5 mb-1 ${tint}`} />
        <p className="text-3xl font-bold text-foreground tracking-tight">{value}</p>
        <p className="text-xs text-muted-foreground mt-0.5">{label}</p>
      </CardContent>
    </Card>
  );
}
