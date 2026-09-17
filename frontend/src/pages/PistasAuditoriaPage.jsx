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
  ShieldCheck, Filter, RefreshCw, FileDown, FileSpreadsheet, Search,
  Calendar, Users, Layers, PlusCircle, Pencil, Trash2, ChevronRight, Check,
} from "lucide-react";

function nowISOLocal(offsetDays = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offsetDays);
  d.setSeconds(0, 0);
  return d.toISOString().slice(0, 16); // datetime-local
}

function toIsoUTC(v) {
  if (!v) return null;
  return new Date(v).toISOString();
}

const ACTIONS = [
  { key: "CREATE", label: "Creación",     icon: PlusCircle, cls: "text-emerald-600 bg-emerald-50" },
  { key: "UPDATE", label: "Modificación", icon: Pencil,      cls: "text-amber-700 bg-amber-50" },
  { key: "DELETE", label: "Eliminación",  icon: Trash2,      cls: "text-rose-700 bg-rose-50" },
];

export default function PistasAuditoriaPage() {
  const [rows, setRows] = useState([]);
  const [meta, setMeta] = useState({ rows_count: 0, summary: {}, modules: {} });
  const [modules, setModules] = useState([]);
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState("");
  const [expanded, setExpanded] = useState(null);
  const [filters, setFilters] = useState({
    from_dt: nowISOLocal(-7),
    to_dt: nowISOLocal(0),
    module: "__all",
    actions: [],
    user_ids: [],
    q: "",
  });

  useEffect(() => {
    (async () => {
      try {
        const [m, u] = await Promise.all([api.get("/audit-logs/modules"), api.get("/users")]);
        setModules(m.data.modules || []);
        setUsers((u.data || []).sort((a, b) => (a.name || "").localeCompare(b.name || "", "es")));
      } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message); }
    })();
  }, []);

  const params = useMemo(() => {
    const p = new URLSearchParams();
    p.set("from_dt", toIsoUTC(filters.from_dt));
    p.set("to_dt", toIsoUTC(filters.to_dt));
    if (filters.module !== "__all") p.append("modules", filters.module);
    filters.actions.forEach((a) => p.append("actions", a));
    filters.user_ids.forEach((u) => p.append("user_ids", u));
    if (filters.q.trim()) p.set("q", filters.q.trim());
    return p;
  }, [filters]);

  async function fetchLogs() {
    setLoading(true);
    try {
      const { data } = await api.get(`/audit-logs?${params.toString()}`);
      setRows(data.rows || []);
      setMeta({ rows_count: data.rows_count || 0, summary: data.summary || {}, modules: data.modules || {} });
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message); }
    finally { setLoading(false); }
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { fetchLogs(); }, []);

  async function exportFile(fmt) {
    setExporting(fmt);
    try {
      const r = await fetch(`${API}/audit-logs/export.${fmt}?${params.toString()}`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!r.ok) throw new Error("Error al exportar");
      const blob = await r.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `auditoria_${filters.from_dt.slice(0,10)}_a_${filters.to_dt.slice(0,10)}.${fmt}`;
      a.click();
      toast.success(fmt === "pdf" ? "PDF descargado" : "Excel descargado");
    } catch (e) { toast.error(e.message); }
    finally { setExporting(""); }
  }

  function toggleAction(k) {
    setFilters((f) => ({
      ...f,
      actions: f.actions.includes(k) ? f.actions.filter((x) => x !== k) : [...f.actions, k],
    }));
  }
  function toggleUser(uid) {
    setFilters((f) => ({
      ...f,
      user_ids: f.user_ids.includes(uid) ? f.user_ids.filter((x) => x !== uid) : [...f.user_ids, uid],
    }));
  }

  const fmtDT = (v) => {
    if (!v) return "—";
    const d = new Date(v);
    return Number.isNaN(d.getTime()) ? v : d.toLocaleString("es-VE", { timeZone: "America/Caracas", hour12: false });
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-4" data-testid="audit-logs-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <Badge variant="secondary" className="rounded-full mb-2">Seguridad · Auditoría</Badge>
          <h1 className="text-3xl font-bold flex items-center gap-2">
            <ShieldCheck className="h-7 w-7 text-primary/70" /> Pistas de Auditoría
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Trazabilidad inmutable de operaciones sobre datos. Registro CREATE/UPDATE/DELETE con estado antes/después.
          </p>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <Button variant="outline" onClick={fetchLogs} disabled={loading} className="rounded-full" data-testid="al-refresh">
            <RefreshCw className={"h-4 w-4 mr-1.5 " + (loading ? "animate-spin" : "")} /> Actualizar
          </Button>
          <Button variant="outline" onClick={() => exportFile("pdf")} disabled={!!exporting || rows.length === 0}
                  className="rounded-full" data-testid="al-export-pdf">
            <FileDown className="h-4 w-4 mr-1.5" /> {exporting === "pdf" ? "Generando…" : "PDF"}
          </Button>
          <Button onClick={() => exportFile("xlsx")} disabled={!!exporting || rows.length === 0}
                  className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground" data-testid="al-export-xlsx">
            <FileSpreadsheet className="h-4 w-4 mr-1.5" /> {exporting === "xlsx" ? "Generando…" : "Excel"}
          </Button>
        </div>
      </div>

      {/* Sumario semaforizado */}
      <div className="grid grid-cols-3 gap-3">
        {ACTIONS.map((a) => {
          const Icon = a.icon;
          return (
            <Card key={a.key} className={`${a.cls} border-0`}>
              <CardContent className="pt-4 pb-3 flex items-center gap-3">
                <div className="h-9 w-9 rounded-xl bg-white/60 grid place-items-center"><Icon className="h-5 w-5" /></div>
                <div>
                  <p className="text-2xl font-bold tabular-nums" data-testid={`al-count-${a.key.toLowerCase()}`}>{meta.summary?.[a.key] || 0}</p>
                  <p className="text-[11px] uppercase tracking-wider opacity-70">{a.label}</p>
                </div>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Card>
        <CardContent className="pt-4 space-y-3">
          <div className="flex items-center gap-2 text-xs uppercase tracking-wider text-muted-foreground">
            <Filter className="h-3.5 w-3.5" /> Parámetros de búsqueda
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground flex items-center gap-1"><Calendar className="h-3 w-3" /> Desde *</Label>
              <Input type="datetime-local" value={filters.from_dt} className="h-10" data-testid="al-from"
                     onChange={(e) => setFilters((f) => ({ ...f, from_dt: e.target.value }))} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground flex items-center gap-1"><Calendar className="h-3 w-3" /> Hasta *</Label>
              <Input type="datetime-local" value={filters.to_dt} className="h-10" data-testid="al-to"
                     onChange={(e) => setFilters((f) => ({ ...f, to_dt: e.target.value }))} />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground flex items-center gap-1"><Layers className="h-3 w-3" /> Módulo</Label>
              <Select value={filters.module} onValueChange={(v) => setFilters((f) => ({ ...f, module: v }))}>
                <SelectTrigger className="h-10" data-testid="al-module"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__all">Todos</SelectItem>
                  {modules.map((m) => <SelectItem key={m.key} value={m.key}>{m.label}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground">Tipo de acción</Label>
              <div className="flex gap-1 h-10 items-center flex-wrap">
                {ACTIONS.map((a) => {
                  const on = filters.actions.includes(a.key);
                  return (
                    <button key={a.key} type="button" onClick={() => toggleAction(a.key)}
                            className={`px-2 py-0.5 rounded-full text-[10px] border ${on ? a.cls + " border-transparent font-semibold" : "border-border text-muted-foreground"}`}
                            data-testid={`al-action-${a.key.toLowerCase()}`}>
                      {a.label}
                    </button>
                  );
                })}
              </div>
            </div>
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground flex items-center gap-1"><Users className="h-3 w-3" /> Usuario</Label>
              <Popover>
                <PopoverTrigger asChild>
                  <Button variant="outline" className="h-10 w-full justify-start font-normal" data-testid="al-users-trigger">
                    {filters.user_ids.length === 0
                      ? <span className="text-muted-foreground">Todos</span>
                      : `${filters.user_ids.length} seleccionado(s)`}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-64 p-0" align="start">
                  <div className="p-2 border-b flex items-center justify-between text-xs">
                    <span className="text-muted-foreground">{filters.user_ids.length} de {users.length}</span>
                    <button className="text-primary hover:underline" onClick={() => setFilters((f) => ({ ...f, user_ids: [] }))}>Limpiar</button>
                  </div>
                  <div className="max-h-60 overflow-y-auto">
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
                  </div>
                </PopoverContent>
              </Popover>
            </div>
            <div className="space-y-1.5">
              <Label className="text-[11px] text-muted-foreground flex items-center gap-1"><Search className="h-3 w-3" /> Texto libre</Label>
              <Input value={filters.q} placeholder="entity_id, JSON…" className="h-10" data-testid="al-q"
                     onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value }))}
                     onKeyDown={(e) => e.key === "Enter" && fetchLogs()} />
            </div>
          </div>
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <p className="text-xs text-muted-foreground" data-testid="al-count">
              {meta.rows_count} evento{meta.rows_count !== 1 ? "s" : ""} en el período
            </p>
            <Button size="sm" onClick={fetchLogs} disabled={loading}
                    className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground" data-testid="al-apply">
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
                <TableHead className="w-6"></TableHead>
                <TableHead>Fecha/Hora</TableHead>
                <TableHead>Usuario</TableHead>
                <TableHead>IP</TableHead>
                <TableHead>Módulo</TableHead>
                <TableHead>Acción</TableHead>
                <TableHead>Entidad</TableHead>
                <TableHead>Resumen</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody data-testid="al-table">
              {loading && <TableRow><TableCell colSpan={8} className="text-center py-10 text-muted-foreground">Cargando…</TableCell></TableRow>}
              {!loading && rows.length === 0 && (
                <TableRow><TableCell colSpan={8} className="text-center py-10 text-muted-foreground">Sin eventos para los filtros aplicados</TableCell></TableRow>
              )}
              {!loading && rows.map((r, i) => {
                const key = r.log_id || `${r.timestamp}-${i}`;
                const isOpen = expanded === key;
                const action = ACTIONS.find((a) => a.key === r.action_type);
                const detail = r.change_detail || {};
                const changedFields = detail.changed_fields || [];
                const summary = r.action_type === "UPDATE"
                  ? changedFields.length ? `${changedFields.length} campo(s): ${changedFields.slice(0,3).join(", ")}${changedFields.length > 3 ? "…" : ""}` : "Sin cambios detectados"
                  : r.action_type === "CREATE" ? "Nuevo registro creado"
                  : r.action_type === "DELETE" ? "Registro eliminado"
                  : (r.event || "—");
                return (
                  <>
                    <TableRow key={key} data-testid={`al-row-${key}`} className="cursor-pointer hover:bg-muted/30"
                              onClick={() => setExpanded(isOpen ? null : key)}>
                      <TableCell>
                        <ChevronRight className={"h-4 w-4 transition-transform " + (isOpen ? "rotate-90" : "")} />
                      </TableCell>
                      <TableCell className="text-xs font-mono whitespace-nowrap">{fmtDT(r.timestamp)}</TableCell>
                      <TableCell className="text-xs">
                        <p className="font-medium leading-tight">{r.email || r.user_id || "—"}</p>
                        <p className="text-[10px] text-muted-foreground">{r.role || ""}</p>
                      </TableCell>
                      <TableCell className="text-xs font-mono text-muted-foreground">{r.ip || "—"}</TableCell>
                      <TableCell className="text-xs">{meta.modules?.[r.module_name] || r.module_name || "—"}</TableCell>
                      <TableCell>
                        {action ? (
                          <Badge className={`${action.cls} border-0 text-[10px]`}>
                            <action.icon className="h-3 w-3 mr-1" /> {action.label}
                          </Badge>
                        ) : (
                          <Badge variant="outline" className="text-[10px]">{r.event || "otro"}</Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-[11px] font-mono">{r.entity_id || "—"}</TableCell>
                      <TableCell className="text-xs text-muted-foreground max-w-md truncate">{summary}</TableCell>
                    </TableRow>
                    {isOpen && (
                      <TableRow key={`${key}-detail`} className="bg-muted/20">
                        <TableCell colSpan={8} className="p-4">
                          <div className="grid gap-3 md:grid-cols-2 text-xs">
                            <div>
                              <p className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Antes</p>
                              <pre className="bg-white rounded border p-2 max-h-64 overflow-auto text-[10px] leading-snug">{JSON.stringify(detail.before ?? detail.snapshot ?? {}, null, 2)}</pre>
                            </div>
                            <div>
                              <p className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1">Después</p>
                              <pre className="bg-white rounded border p-2 max-h-64 overflow-auto text-[10px] leading-snug">{JSON.stringify(detail.after ?? detail.snapshot ?? {}, null, 2)}</pre>
                            </div>
                          </div>
                          {r.path && <p className="mt-2 text-[10px] text-muted-foreground font-mono">{r.method} {r.path}</p>}
                        </TableCell>
                      </TableRow>
                    )}
                  </>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </Card>
    </div>
  );
}
