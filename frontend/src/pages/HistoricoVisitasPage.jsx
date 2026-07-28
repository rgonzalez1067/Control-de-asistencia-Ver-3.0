import { useEffect, useMemo, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { toast } from "sonner";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  Building2, User as UserIcon, Camera, Search, X, Users, Calendar, Filter, Download, IdCard, Phone,
} from "lucide-react";

const TZ = "America/Caracas";
const dfDate = new Intl.DateTimeFormat("es-VE", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: TZ });
const dfTime = new Intl.DateTimeFormat("es-VE", { hour: "2-digit", minute: "2-digit", timeZone: TZ });

export default function HistoricoVisitasPage() {
  const [visits, setVisits] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState(null);
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [type, setType] = useState("all");
  const [q, setQ] = useState("");

  async function load() {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (fromDate) params.set("from_date", fromDate);
      if (toDate) params.set("to_date", toDate);
      if (type !== "all") params.set("type", type);
      const { data } = await api.get(`/visits?${params.toString()}`);
      setVisits(data);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally { setLoading(false); }
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, [fromDate, toDate, type]);

  const filtered = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return visits;
    return visits.filter((v) =>
      (v.host_name || "").toLowerCase().includes(s) ||
      (v.company_name || "").toLowerCase().includes(s) ||
      (v.visitors || []).some((vi) => (vi.name || "").toLowerCase().includes(s) || (vi.cedula || "").includes(s)),
    );
  }, [visits, q]);

  async function openDetail(v) {
    try {
      const { data } = await api.get(`/visits/${v.visit_id}`);
      setSelected(data);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    }
  }

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-4">
      <div>
        <h1 className="text-3xl font-bold">Histórico de visitas</h1>
        <p className="text-sm text-muted-foreground">Consulta y auditoría de todas las visitas registradas. Solo empleados con permiso <b>Acceso a registros de visita</b>.</p>
      </div>

      <Card>
        <CardContent className="pt-4 space-y-3">
          <div className="grid sm:grid-cols-5 gap-2">
            <div>
              <Label className="text-xs flex items-center gap-1"><Calendar className="h-3 w-3" /> Desde</Label>
              <Input type="date" value={fromDate} onChange={(e) => setFromDate(e.target.value)} className="h-10" data-testid="hv-from" />
            </div>
            <div>
              <Label className="text-xs flex items-center gap-1"><Calendar className="h-3 w-3" /> Hasta</Label>
              <Input type="date" value={toDate} onChange={(e) => setToDate(e.target.value)} className="h-10" data-testid="hv-to" />
            </div>
            <div>
              <Label className="text-xs flex items-center gap-1"><Filter className="h-3 w-3" /> Tipo</Label>
              <Select value={type} onValueChange={setType}>
                <SelectTrigger className="h-10" data-testid="hv-type"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  <SelectItem value="personal">Personal</SelectItem>
                  <SelectItem value="laboral">Laboral</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="sm:col-span-2">
              <Label className="text-xs flex items-center gap-1"><Search className="h-3 w-3" /> Buscar</Label>
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Anfitrión, empresa, visitante o cédula…" className="h-10" data-testid="hv-search" />
            </div>
          </div>

          <div className="text-xs text-muted-foreground">
            Mostrando {filtered.length} de {visits.length} visitas
          </div>

          <div className="overflow-x-auto rounded-lg border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Fecha</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Anfitrión</TableHead>
                  <TableHead>Empresa / Visitantes</TableHead>
                  <TableHead>Selfies</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {loading && <TableRow><TableCell colSpan={7} className="text-center py-6 text-muted-foreground">Cargando…</TableCell></TableRow>}
                {!loading && filtered.length === 0 && (
                  <TableRow><TableCell colSpan={7} className="text-center py-8 text-muted-foreground">Sin visitas para los filtros aplicados.</TableCell></TableRow>
                )}
                {filtered.map((v) => {
                  const d = new Date(v.scheduled_at);
                  const total = (v.visitors || []).length;
                  return (
                    <TableRow key={v.visit_id} data-testid={`visit-row-${v.visit_id}`}>
                      <TableCell className="text-xs">
                        {dfDate.format(d)} <span className="text-muted-foreground">· {dfTime.format(d)}</span>
                      </TableCell>
                      <TableCell>
                        <Badge className={v.type === "laboral" ? "bg-primary/10 text-primary" : "bg-emerald-50 text-emerald-700"}>
                          {v.type === "laboral" ? <><Building2 className="h-3 w-3 mr-1" />Laboral</> : <><UserIcon className="h-3 w-3 mr-1" />Personal</>}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-xs">{v.host_name || v.host_user_id}</TableCell>
                      <TableCell className="text-xs">
                        {v.type === "laboral" ? v.company_name : "—"}
                        <div className="text-muted-foreground">
                          <Users className="h-3 w-3 inline mr-1" /> {total} visitante{total !== 1 ? "s" : ""}
                        </div>
                      </TableCell>
                      <TableCell className="text-xs">
                        <span className={v.selfies_count === total && total > 0 ? "text-emerald-600 font-medium" : "text-muted-foreground"}>
                          {v.selfies_count || 0} / {total}
                        </span>
                      </TableCell>
                      <TableCell>
                        <Badge variant={v.status === "completed" ? "default" : "outline"} className="text-[10px]">
                          {v.status}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Button size="sm" variant="ghost" onClick={() => openDetail(v)} data-testid={`visit-open-${v.visit_id}`}>
                          Ver
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <VisitDetailDialog visit={selected} onClose={() => setSelected(null)} />
    </div>
  );
}

function VisitDetailDialog({ visit, onClose }) {
  if (!visit) return null;
  const scheduledD = new Date(visit.scheduled_at);
  const selfies = visit.selfies || [];
  const findSelfie = (idx) => selfies.find((s) => s.visitor_index === idx);

  function downloadPack() {
    const html = generatePrintable(visit);
    const win = window.open("", "_blank");
    win.document.write(html);
    win.document.close();
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto" data-testid="visit-detail-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {visit.type === "laboral" ? <Building2 className="h-5 w-5" /> : <UserIcon className="h-5 w-5" />}
            Visita {visit.type === "laboral" ? "Laboral" : "Personal"}
          </DialogTitle>
          <DialogDescription>{visit.visit_id} · {dfDate.format(scheduledD)} {dfTime.format(scheduledD)}</DialogDescription>
        </DialogHeader>

        <div className="grid sm:grid-cols-2 gap-3 text-sm">
          <InfoRow label="Anfitrión" value={visit.host_name} />
          <InfoRow label="Estado" value={visit.status} />
          {visit.type === "laboral" && <InfoRow label="Empresa" value={visit.company_name} />}
          {visit.motive && <InfoRow label="Motivo" value={visit.motive} />}
          {visit.notes && <InfoRow label="Notas" value={visit.notes} />}
        </div>

        <div className="space-y-3 pt-3 border-t">
          <div className="flex items-center justify-between">
            <h3 className="font-semibold text-sm flex items-center gap-1.5"><Users className="h-4 w-4" /> Visitantes ({visit.visitors?.length || 0})</h3>
            {selfies.length > 0 && (
              <Button size="sm" variant="outline" onClick={downloadPack} data-testid="visit-download">
                <Download className="h-4 w-4 mr-1.5" /> Imprimir / Exportar
              </Button>
            )}
          </div>
          <div className="grid sm:grid-cols-2 gap-3">
            {(visit.visitors || []).map((v, i) => {
              const s = findSelfie(i);
              return (
                <div key={i} className="rounded-xl border p-3 space-y-2">
                  <div className="flex items-center gap-3">
                    {s ? (
                      <img src={s.selfie_base64} alt={v.name} className="h-16 w-16 rounded-lg object-cover" />
                    ) : (
                      <div className="h-16 w-16 rounded-lg bg-muted grid place-items-center">
                        <Camera className="h-6 w-6 text-muted-foreground opacity-40" />
                      </div>
                    )}
                    <div className="min-w-0">
                      <div className="text-sm font-semibold truncate">{v.name}</div>
                      <div className="text-xs text-muted-foreground truncate flex items-center gap-1"><IdCard className="h-3 w-3" /> {v.cedula}</div>
                      {v.phone && <div className="text-xs text-muted-foreground truncate flex items-center gap-1"><Phone className="h-3 w-3" /> {v.phone}</div>}
                    </div>
                  </div>
                  {s && <p className="text-[10px] text-muted-foreground">Selfie capturada · {new Date(s.captured_at).toLocaleString("es-VE", { timeZone: TZ })}</p>}
                </div>
              );
            })}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} className="rounded-full" data-testid="visit-close">
            <X className="h-4 w-4 mr-1.5" /> Cerrar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function InfoRow({ label, value }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="text-sm">{value || "—"}</div>
    </div>
  );
}

function generatePrintable(v) {
  const scheduledD = new Date(v.scheduled_at);
  const rows = (v.visitors || []).map((vi, i) => {
    const s = (v.selfies || []).find((x) => x.visitor_index === i);
    return `
      <div style="display:flex;gap:12px;padding:8px;border:1px solid #ddd;border-radius:8px;margin:6px 0;">
        ${s ? `<img src="${s.selfie_base64}" style="width:80px;height:80px;border-radius:8px;object-fit:cover;">` : `<div style="width:80px;height:80px;background:#f0f0f0;border-radius:8px"></div>`}
        <div>
          <div style="font-weight:600">${vi.name}</div>
          <div style="color:#666;font-size:12px">Cédula: ${vi.cedula || "—"}</div>
          ${vi.phone ? `<div style="color:#666;font-size:12px">Tel: ${vi.phone}</div>` : ""}
        </div>
      </div>`;
  }).join("");
  return `<!doctype html><html><head><meta charset="utf-8"><title>Visita ${v.visit_id}</title>
    <style>body{font-family:system-ui,-apple-system,sans-serif;max-width:720px;margin:32px auto;padding:0 16px;color:#111}</style>
  </head><body>
    <h1>Registro de visita</h1>
    <p><b>${v.type === "laboral" ? "Laboral" : "Personal"}</b> · ${scheduledD.toLocaleString("es-VE", { timeZone: "America/Caracas" })}</p>
    <p><b>Anfitrión:</b> ${v.host_name}</p>
    ${v.company_name ? `<p><b>Empresa:</b> ${v.company_name}</p>` : ""}
    ${v.motive ? `<p><b>Motivo:</b> ${v.motive}</p>` : ""}
    <h3>Visitantes (${(v.visitors || []).length})</h3>
    ${rows}
    <script>window.onload=()=>window.print()</script>
  </body></html>`;
}
