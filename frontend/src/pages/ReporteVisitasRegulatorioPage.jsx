import { useEffect, useMemo, useState } from "react";
import { api, API, getToken, formatApiErrorDetail } from "@/lib/api";
import useCompanyBranding from "@/hooks/useCompanyBranding";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  ShieldCheck, Calendar, Filter, MapPin, User as UserIcon, RefreshCw,
  FileDown, FileSpreadsheet, Printer, Camera, Building2, Users,
} from "lucide-react";

const TZ = "America/Caracas";
const dfDateTime = new Intl.DateTimeFormat("es-VE", {
  day: "2-digit", month: "2-digit", year: "numeric",
  hour: "2-digit", minute: "2-digit", timeZone: TZ,
});

function fmtDT(v) {
  if (!v) return "—";
  const d = new Date(v);
  return Number.isNaN(d.getTime()) ? "—" : dfDateTime.format(d);
}

function todayISO(offsetDays = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  return d.toISOString().slice(0, 10);
}

export default function ReporteVisitasRegulatorioPage() {
  const branding = useCompanyBranding();
  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState({ visits_count: 0, visitors_count: 0 });
  const [sites, setSites] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState("");
  const [filters, setFilters] = useState({
    from_date: todayISO(-30),
    to_date: todayISO(0),
    visit_type: "all",
    site_id: "__all",
    host_user_id: "__all",
  });

  useEffect(() => {
    async function loadRefs() {
      try {
        const [s, u] = await Promise.all([api.get("/sites"), api.get("/users")]);
        setSites(s.data);
        setUsers([...u.data].sort((a, b) => (a.name || "").localeCompare(b.name || "", "es", { sensitivity: "base" })));
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
    if (filters.visit_type !== "all") p.set("visit_type", filters.visit_type);
    if (filters.site_id !== "__all") p.set("site_id", filters.site_id);
    if (filters.host_user_id !== "__all") p.set("host_user_id", filters.host_user_id);
    return p;
  }, [filters]);

  async function fetchReport() {
    if (!filters.from_date || !filters.to_date) {
      toast.error("El rango de fechas (Desde/Hasta) es obligatorio");
      return;
    }
    setLoading(true);
    try {
      const { data } = await api.get(`/reports/visits?${params.toString()}`);
      setRows(data.rows || []);
      setMeta({ visits_count: data.visits_count || 0, visitors_count: data.visitors_count || 0 });
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally { setLoading(false); }
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetchReport(); }, []);

  async function exportFile(fmt) {
    if (!filters.from_date || !filters.to_date) {
      toast.error("El rango de fechas (Desde/Hasta) es obligatorio");
      return;
    }
    setExporting(fmt);
    try {
      const r = await fetch(`${API}/reports/visits/export.${fmt}?${params.toString()}`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!r.ok) {
        const data = await r.json().catch(() => null);
        throw new Error(formatApiErrorDetail(data?.detail) || "Error al exportar");
      }
      const blob = await r.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `reporte_visitas_${filters.from_date}_a_${filters.to_date}.${fmt}`;
      a.click();
      toast.success(fmt === "pdf" ? "PDF descargado" : "Excel descargado");
    } catch (e) {
      toast.error(e.message);
    } finally { setExporting(""); }
  }

  function printReport() {
    if (rows.length === 0) {
      toast.error("No hay datos para imprimir — ejecuta la consulta primero");
      return;
    }
    const win = window.open("", "_blank");
    win.document.write(buildPrintableHtml({
      rows, meta, filters, sites, users,
      company: branding?.company_name || "Mega Soft",
      logo: branding?.logo_base64,
    }));
    win.document.close();
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-4" data-testid="visits-report-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <Badge variant="secondary" className="rounded-full mb-2">Auditoría de Control de Acceso</Badge>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <ShieldCheck className="h-7 w-7 text-primary/70" /> Reporte de Visitas Realizadas
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Trazabilidad completa de visitas con evidencia biométrica. Formato oficial para entes reguladores.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Button variant="outline" onClick={fetchReport} disabled={loading} className="rounded-full" data-testid="vr-refresh">
            <RefreshCw className={"h-4 w-4 mr-1.5 " + (loading ? "animate-spin" : "")} /> Actualizar
          </Button>
          <Button variant="outline" onClick={() => exportFile("pdf")} disabled={!!exporting || rows.length === 0}
                  className="rounded-full" data-testid="vr-export-pdf">
            <FileDown className="h-4 w-4 mr-1.5" /> {exporting === "pdf" ? "Generando…" : "PDF"}
          </Button>
          <Button variant="outline" onClick={() => exportFile("xlsx")} disabled={!!exporting || rows.length === 0}
                  className="rounded-full" data-testid="vr-export-xlsx">
            <FileSpreadsheet className="h-4 w-4 mr-1.5" /> {exporting === "xlsx" ? "Generando…" : "Excel"}
          </Button>
          <Button onClick={printReport} disabled={rows.length === 0}
                  className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground" data-testid="vr-print">
            <Printer className="h-4 w-4 mr-1.5" /> Imprimir
          </Button>
        </div>
      </div>

      <Card>
        <CardContent className="pt-4 space-y-3">
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-muted-foreground">
            <Filter className="h-3.5 w-3.5" /> Parámetros de búsqueda
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground flex items-center gap-1"><Calendar className="h-3 w-3" /> Desde *</Label>
              <Input type="date" value={filters.from_date} className="h-10" data-testid="vr-from"
                     onChange={(e) => setFilters((f) => ({ ...f, from_date: e.target.value }))} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground flex items-center gap-1"><Calendar className="h-3 w-3" /> Hasta *</Label>
              <Input type="date" value={filters.to_date} className="h-10" data-testid="vr-to"
                     onChange={(e) => setFilters((f) => ({ ...f, to_date: e.target.value }))} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground">Tipo de visita</Label>
              <Select value={filters.visit_type} onValueChange={(v) => setFilters((f) => ({ ...f, visit_type: v }))}>
                <SelectTrigger className="h-10" data-testid="vr-type"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  <SelectItem value="laboral">Laboral</SelectItem>
                  <SelectItem value="personal">Personal</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground flex items-center gap-1"><MapPin className="h-3 w-3" /> Sede</Label>
              <Select value={filters.site_id} onValueChange={(v) => setFilters((f) => ({ ...f, site_id: v }))}>
                <SelectTrigger className="h-10" data-testid="vr-site"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all">Todas</SelectItem>
                  {sites.map((s) => <SelectItem key={s.site_id} value={s.site_id}>{s.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5 lg:col-span-2">
              <Label className="text-[11px] text-muted-foreground flex items-center gap-1"><UserIcon className="h-3 w-3" /> Anfitrión / Empleado responsable</Label>
              <Select value={filters.host_user_id} onValueChange={(v) => setFilters((f) => ({ ...f, host_user_id: v }))}>
                <SelectTrigger className="h-10" data-testid="vr-host"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all">Todos</SelectItem>
                  {users.map((u) => <SelectItem key={u.user_id} value={u.user_id}>{u.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <p className="text-xs text-muted-foreground" data-testid="vr-count">
              {meta.visits_count} visita{meta.visits_count !== 1 ? "s" : ""} · {meta.visitors_count} visitante{meta.visitors_count !== 1 ? "s" : ""}
            </p>
            <Button size="sm" onClick={fetchReport} disabled={loading}
                    className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground" data-testid="vr-apply">
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
                <TableHead className="w-16">Foto</TableHead>
                <TableHead>Código</TableHead>
                <TableHead>Programada</TableHead>
                <TableHead>Entrada real</TableHead>
                <TableHead>Salida real</TableHead>
                <TableHead>Sede</TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead>Anfitrión</TableHead>
                <TableHead>Visitante</TableHead>
                <TableHead>Clasif.</TableHead>
                <TableHead>Empresa / Motivo</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody data-testid="vr-table">
              {loading && <TableRow><TableCell colSpan={11} className="text-center py-10 text-muted-foreground">Cargando…</TableCell></TableRow>}
              {!loading && rows.length === 0 && (
                <TableRow><TableCell colSpan={11} className="text-center py-10 text-muted-foreground">Sin visitas para los filtros aplicados</TableCell></TableRow>
              )}
              {!loading && rows.map((r, i) => (
                <TableRow key={`${r.visit_id}-${i}`} data-testid={`vr-row-${r.visit_id}-${i}`}>
                  <TableCell>
                    {r.selfie_thumb ? (
                      <img src={r.selfie_thumb} alt={r.visitor_name} className="h-12 w-12 rounded-lg object-cover border" />
                    ) : (
                      <div className="h-12 w-12 rounded-lg bg-muted grid place-items-center" title="Sin evidencia biométrica">
                        <Camera className="h-5 w-5 text-muted-foreground opacity-40" />
                      </div>
                    )}
                  </TableCell>
                  <TableCell className="text-[11px] font-mono text-muted-foreground">{(r.visit_id || "").replace("visit_", "")}</TableCell>
                  <TableCell className="text-xs whitespace-nowrap">{fmtDT(r.scheduled_at)}</TableCell>
                  <TableCell className="text-xs whitespace-nowrap">
                    {r.entry_at ? fmtDT(r.entry_at) : <span className="text-amber-600">Sin marcaje</span>}
                  </TableCell>
                  <TableCell className="text-xs whitespace-nowrap">{fmtDT(r.exit_at)}</TableCell>
                  <TableCell className="text-xs">{r.site_name}</TableCell>
                  <TableCell>
                    <Badge className={r.type === "laboral" ? "bg-primary/10 text-primary" : "bg-emerald-50 text-emerald-700"}>
                      {r.type === "laboral" ? <><Building2 className="h-3 w-3 mr-1" />Laboral</> : <><UserIcon className="h-3 w-3 mr-1" />Personal</>}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-xs">
                    <p className="font-medium leading-tight">{r.host_name}</p>
                    <p className="text-[11px] text-muted-foreground leading-tight">{r.host_cedula} · {r.host_department}</p>
                  </TableCell>
                  <TableCell className="text-xs">
                    <p className="font-medium leading-tight">{r.visitor_name}</p>
                    <p className="text-[11px] text-muted-foreground leading-tight">{r.visitor_cedula}</p>
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-[10px]">
                      <Users className="h-3 w-3 mr-1" /> {r.visitor_kind}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-xs max-w-56">
                    {r.type === "laboral" ? (
                      <>
                        <p className="leading-tight">{r.company_name || "—"}</p>
                        <p className="text-[11px] text-muted-foreground leading-tight">{r.motive}</p>
                      </>
                    ) : (
                      <span className="text-muted-foreground">{r.motive}</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Card>
    </div>
  );
}

function buildPrintableHtml({ rows, meta, filters, sites, users, company, logo }) {
  const siteName = filters.site_id !== "__all" ? (sites.find((s) => s.site_id === filters.site_id)?.name || "") : "Todas";
  const hostName = filters.host_user_id !== "__all" ? (users.find((u) => u.user_id === filters.host_user_id)?.name || "") : "Todos";
  const typeName = filters.visit_type === "all" ? "Todos" : filters.visit_type === "laboral" ? "Laboral" : "Personal";
  const bodyRows = rows.map((r) => `
    <tr>
      <td>${r.selfie_thumb ? `<img src="${r.selfie_thumb}" alt="">` : '<div class="noimg"></div>'}</td>
      <td class="mono">${(r.visit_id || "").replace("visit_", "")}</td>
      <td>${fmtDT(r.scheduled_at)}</td>
      <td>${r.entry_at ? fmtDT(r.entry_at) : "Sin marcaje"}</td>
      <td>${fmtDT(r.exit_at)}</td>
      <td>${r.site_name || "—"}</td>
      <td>${r.type === "laboral" ? "Laboral" : "Personal"}</td>
      <td><b>${r.host_name}</b><br><span class="muted">${r.host_cedula} · ${r.host_department}</span></td>
      <td><b>${r.visitor_name}</b><br><span class="muted">${r.visitor_cedula}</span></td>
      <td>${r.visitor_kind}</td>
      <td>${r.type === "laboral" ? `${r.company_name || "—"}<br><span class="muted">${r.motive || ""}</span>` : (r.motive || "Visita personal")}</td>
    </tr>`).join("");
  return `<!doctype html><html><head><meta charset="utf-8"><title>Reporte de Visitas Realizadas</title>
  <style>
    *{box-sizing:border-box} body{font-family:Arial,Helvetica,sans-serif;margin:24px;color:#0f172a;font-size:10px}
    .head{display:flex;align-items:center;gap:14px;border-bottom:3px solid #0f172a;padding-bottom:10px;margin-bottom:10px}
    .head img{height:38px} h1{font-size:16px;margin:0} .sub{color:#64748b;font-size:10px;margin-top:2px}
    table{width:100%;border-collapse:collapse} th{background:#0f172a;color:#fff;text-align:left;padding:5px 6px;font-size:9px}
    td{border:1px solid #cbd5e1;padding:5px 6px;vertical-align:middle} tr:nth-child(even) td{background:#f8fafc}
    td img{width:46px;height:46px;object-fit:cover;border-radius:6px} .noimg{width:46px;height:46px;background:#e2e8f0;border-radius:6px}
    .muted{color:#64748b;font-size:9px} .mono{font-family:monospace;color:#64748b}
    .foot{margin-top:10px;color:#94a3b8;font-size:9px;display:flex;justify-content:space-between}
    @page{size:landscape;margin:10mm}
  </style></head><body>
  <div class="head">
    ${logo ? `<img src="${logo}" alt="logo">` : ""}
    <div>
      <h1>${company} · Reporte de Visitas Realizadas</h1>
      <div class="sub">Auditoría de Control de Acceso · Período: ${filters.from_date} — ${filters.to_date} · Tipo: ${typeName} · Sede: ${siteName} · Anfitrión: ${hostName}</div>
      <div class="sub">${meta.visits_count} visitas · ${meta.visitors_count} visitantes · Generado: ${new Date().toLocaleString("es-VE", { timeZone: "America/Caracas" })}</div>
    </div>
  </div>
  <table>
    <thead><tr><th>Foto</th><th>Código</th><th>Programada</th><th>Entrada real</th><th>Salida real</th><th>Sede</th><th>Tipo</th><th>Anfitrión</th><th>Visitante</th><th>Clasif.</th><th>Empresa / Motivo</th></tr></thead>
    <tbody>${bodyRows}</tbody>
  </table>
  <div class="foot"><span>${company} · Sistema de Asistencia y Control de Visitas</span><span>Documento generado electrónicamente — válido para auditoría</span></div>
  <script>window.onload=()=>setTimeout(()=>window.print(),300)</script>
  </body></html>`;
}
