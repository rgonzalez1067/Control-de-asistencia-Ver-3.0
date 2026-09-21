import { useEffect, useMemo, useState } from "react";
import { api, API, getToken, formatApiErrorDetail } from "@/lib/api";
import useCompanyBranding from "@/hooks/useCompanyBranding";
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
  Fingerprint, RefreshCw, FileDown, Building2, MapPin, Check,
  ChevronLeft, ChevronRight, ShieldCheck,
} from "lucide-react";

function todayISO(offsetDays = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

const fmtFecha = (iso) => {
  if (!iso) return "—";
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
};

const PAGE_SIZE = 15;

export default function ReporteGeneralAccesosPage() {
  const branding = useCompanyBranding();
  const logo = branding?.logo_base64;
  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState({ rows_count: 0, employees_count: 0, site_name: null });
  const [departments, setDepartments] = useState([]);
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState({
    from_date: todayISO(-7),
    to_date: todayISO(0),
    department_ids: [],
    site_id: "__all",
  });

  useEffect(() => {
    async function loadRefs() {
      try {
        const [d, s] = await Promise.all([api.get("/departments"), api.get("/sites")]);
        setDepartments(d.data || []);
        setSites(s.data || []);
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
    filters.department_ids.forEach((d) => p.append("department_ids", d));
    if (filters.site_id !== "__all") p.set("site_id", filters.site_id);
    return p;
  }, [filters]);

  async function fetchReport() {
    if (!filters.from_date || !filters.to_date) {
      toast.error("El rango de fechas (Desde/Hasta) es obligatorio");
      return;
    }
    setLoading(true);
    try {
      const { data } = await api.get(`/reports/general-access?${params.toString()}`);
      setRows(data.rows || []);
      setMeta({
        rows_count: data.rows_count || 0,
        employees_count: data.employees_count || 0,
        site_name: data.site_name || null,
      });
      setPage(1);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally { setLoading(false); }
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetchReport(); }, []);

  async function exportPdf() {
    if (!filters.from_date || !filters.to_date) {
      toast.error("El rango de fechas (Desde/Hasta) es obligatorio");
      return;
    }
    setExporting(true);
    try {
      const r = await fetch(`${API}/reports/general-access/export.pdf?${params.toString()}`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!r.ok) {
        const data = await r.json().catch(() => null);
        throw new Error(formatApiErrorDetail(data?.detail) || "Error al exportar");
      }
      const blob = await r.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `reporte_general_accesos_${filters.from_date}_a_${filters.to_date}.pdf`;
      a.click();
      toast.success("PDF descargado");
    } catch (e) { toast.error(e.message); }
    finally { setExporting(false); }
  }

  function toggleDept(did) {
    setFilters((f) => ({
      ...f,
      department_ids: f.department_ids.includes(did)
        ? f.department_ids.filter((x) => x !== did)
        : [...f.department_ids, did],
    }));
  }

  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const pageRows = rows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
  const siteLabel = filters.site_id === "__all"
    ? "Todas las Sedes"
    : (sites.find((s) => s.site_id === filters.site_id)?.name || "—");

  return (
    <div className="p-4 sm:p-8 max-w-7xl mx-auto space-y-5" data-testid="rga-page">
      {/* Encabezado de página */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Badge variant="secondary" className="rounded-full mb-2">Control de Visitas</Badge>
          <h1 className="text-2xl sm:text-3xl font-bold text-foreground flex items-center gap-2.5">
            <Fingerprint className="h-7 w-7 text-primary/70" /> Reporte General de Accesos
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Relación diaria de marcajes de entrada y salida de todo el personal.
          </p>
        </div>
        <Button onClick={exportPdf} disabled={exporting || loading}
          className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground"
          data-testid="rga-export-pdf">
          <FileDown className={`h-4 w-4 mr-1.5 ${exporting ? "animate-pulse" : ""}`} />
          {exporting ? "Generando…" : "Exportar PDF"}
        </Button>
      </div>

      {/* Filtros */}
      <Card className="border-border/70 bg-card/70 backdrop-blur">
        <CardContent className="p-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="space-y-1">
              <Label className="text-[11px] text-muted-foreground">Desde *</Label>
              <Input type="date" value={filters.from_date}
                onChange={(e) => setFilters((f) => ({ ...f, from_date: e.target.value }))}
                data-testid="rga-from" />
            </div>
            <div className="space-y-1">
              <Label className="text-[11px] text-muted-foreground">Hasta *</Label>
              <Input type="date" value={filters.to_date}
                onChange={(e) => setFilters((f) => ({ ...f, to_date: e.target.value }))}
                data-testid="rga-to" />
            </div>
            <div className="space-y-1">
              <Label className="text-[11px] text-muted-foreground">Departamentos</Label>
              <Popover>
                <PopoverTrigger asChild>
                  <Button variant="outline" className="h-10 w-full justify-start font-normal" data-testid="rga-departments-trigger">
                    <Building2 className="h-4 w-4 mr-2 text-muted-foreground" />
                    {filters.department_ids.length === 0
                      ? <span className="text-muted-foreground">Todos ({departments.length})</span>
                      : <span className="truncate">{filters.department_ids.length} seleccionado(s)</span>}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-72 p-0" align="start">
                  <div className="max-h-60 overflow-y-auto" data-testid="rga-departments-list">
                    {departments.map((d) => {
                      const on = filters.department_ids.includes(d.department_id);
                      return (
                        <button key={d.department_id} type="button" onClick={() => toggleDept(d.department_id)}
                          className="w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-muted/60 text-left"
                          data-testid={`rga-dept-${d.department_id}`}>
                          <span className={`h-4 w-4 rounded border grid place-items-center ${on ? "bg-primary border-primary text-primary-foreground" : "border-border"}`}>
                            {on && <Check className="h-3 w-3" />}
                          </span>
                          <span className="flex-1 truncate">{d.name}</span>
                        </button>
                      );
                    })}
                    {departments.length === 0 && <p className="p-3 text-xs text-muted-foreground">Sin departamentos</p>}
                  </div>
                </PopoverContent>
              </Popover>
            </div>
            <div className="space-y-1">
              <Label className="text-[11px] text-muted-foreground">Sede</Label>
              <Select value={filters.site_id} onValueChange={(v) => setFilters((f) => ({ ...f, site_id: v }))}>
                <SelectTrigger data-testid="rga-site" className="truncate">
                  <MapPin className="h-4 w-4 mr-2 text-muted-foreground shrink-0" />
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all">Todas las Sedes</SelectItem>
                  {sites.map((s) => (
                    <SelectItem key={s.site_id} value={s.site_id}>{s.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="flex justify-end mt-3">
            <Button onClick={fetchReport} disabled={loading} className="rounded-full" data-testid="rga-apply">
              <RefreshCw className={`h-4 w-4 mr-2 ${loading ? "animate-spin" : ""}`} />
              {loading ? "Cargando…" : "Aplicar filtros"}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Vista previa con maquetación institucional */}
      <Card className="border-border/70 bg-card overflow-hidden" data-testid="rga-report-card">
        <div className="flex items-start justify-between gap-4 px-6 pt-5 pb-4 border-b border-border/60">
          <div className="w-36 shrink-0">
            {logo ? (
              <img src={logo} alt="Mega Soft" className="h-10 w-auto max-w-[140px] object-contain" data-testid="rga-logo" />
            ) : (
              <div className="h-10 w-10 rounded-xl bg-primary grid place-items-center">
                <ShieldCheck className="h-5 w-5 text-accent" />
              </div>
            )}
          </div>
          <div className="text-center flex-1 min-w-0">
            <h2 className="text-lg font-bold text-foreground" data-testid="rga-title">Reporte General de Accesos</h2>
            <p className="text-xs text-muted-foreground mt-0.5" data-testid="rga-period">
              Periodo: {fmtFecha(filters.from_date)} - {fmtFecha(filters.to_date)}
            </p>
            <p className="text-[11px] text-muted-foreground/80">
              Sede: {meta.site_name || siteLabel} · {meta.employees_count} empleados · {meta.rows_count} registros
            </p>
          </div>
          <div className="w-36 shrink-0 text-right">
            <span className="inline-block rounded-lg border border-border/70 bg-muted/40 px-2.5 py-1 text-xs font-semibold tabular-nums"
              data-testid="rga-page-info">
              {page}/{totalPages}
            </span>
          </div>
        </div>

        <div className="overflow-x-auto">
          <Table data-testid="rga-table">
            <TableHeader>
              <TableRow className="bg-primary hover:bg-primary">
                <TableHead className="text-primary-foreground">Cédula</TableHead>
                <TableHead className="text-primary-foreground">Nombre y Apellido</TableHead>
                <TableHead className="text-primary-foreground">Departamento</TableHead>
                <TableHead className="text-primary-foreground">Cargo</TableHead>
                <TableHead className="text-primary-foreground">Fecha</TableHead>
                <TableHead className="text-primary-foreground text-center">E1</TableHead>
                <TableHead className="text-primary-foreground text-center">S1</TableHead>
                <TableHead className="text-primary-foreground text-center">E2</TableHead>
                <TableHead className="text-primary-foreground text-center">S2</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading && (
                <TableRow><TableCell colSpan={9} className="text-center py-10 text-sm text-muted-foreground">Cargando…</TableCell></TableRow>
              )}
              {!loading && pageRows.length === 0 && (
                <TableRow><TableCell colSpan={9} className="text-center py-10 text-sm text-muted-foreground">Sin marcajes en el periodo seleccionado.</TableCell></TableRow>
              )}
              {!loading && pageRows.map((r, i) => (
                <TableRow key={`${r.user_id}-${r.fecha}-${i}`} data-testid={`rga-row-${r.user_id}-${r.fecha}`}>
                  <TableCell className="text-xs">{r.cedula || "—"}</TableCell>
                  <TableCell className="text-xs font-medium">{r.nombre}</TableCell>
                  <TableCell className="text-xs">{r.departamento}</TableCell>
                  <TableCell className="text-xs">{r.cargo}</TableCell>
                  <TableCell className="text-xs tabular-nums">{fmtFecha(r.fecha)}</TableCell>
                  <TableCell className="text-xs text-center tabular-nums">{r.e1 || "—"}</TableCell>
                  <TableCell className="text-xs text-center tabular-nums">{r.s1 || "—"}</TableCell>
                  <TableCell className="text-xs text-center tabular-nums">{r.e2 || "—"}</TableCell>
                  <TableCell className="text-xs text-center tabular-nums">{r.s2 || "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>

        <div className="flex items-center justify-between px-6 py-3 border-t border-border/60">
          <p className="text-[11px] text-muted-foreground">
            Página {page} de {totalPages} · {rows.length} registro(s)
          </p>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" className="rounded-full h-8"
              disabled={page <= 1} onClick={() => setPage((p) => p - 1)} data-testid="rga-prev">
              <ChevronLeft className="h-4 w-4 mr-1" /> Anterior
            </Button>
            <Button variant="outline" size="sm" className="rounded-full h-8"
              disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} data-testid="rga-next">
              Siguiente <ChevronRight className="h-4 w-4 ml-1" />
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}
