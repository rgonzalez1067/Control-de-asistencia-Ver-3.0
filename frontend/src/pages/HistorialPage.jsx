import { useEffect, useMemo, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { toast } from "sonner";
import { History, LogIn, LogOut, MessageSquarePlus, AlertTriangle, MapPin } from "lucide-react";

const TZ = "America/Caracas";
const dfDate = new Intl.DateTimeFormat("es-VE", { day: "2-digit", month: "short", year: "numeric", timeZone: TZ });
const dfTime = new Intl.DateTimeFormat("es-VE", { hour: "2-digit", minute: "2-digit", timeZone: TZ });

export default function HistorialPage() {
  const { user } = useAuth();
  const [records, setRecords] = useState([]);
  const [sites, setSites] = useState({});
  const [loading, setLoading] = useState(true);
  const [justifying, setJustifying] = useState(null);
  const [justText, setJustText] = useState("");
  const [checking, setChecking] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [{ data: recs }, { data: siteList }] = await Promise.all([
        api.get("/attendance/me?limit=200"),
        api.get("/sites"),
      ]);
      setRecords(recs);
      setSites(Object.fromEntries(siteList.map((s) => [s.site_id, s.name])));
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);

  const stats = useMemo(() => {
    const today = new Date().toLocaleDateString("en-CA", { timeZone: TZ });
    const isToday = (r) => new Date(r.timestamp).toLocaleDateString("en-CA", { timeZone: TZ }) === today;
    const monthKey = new Date().toISOString().slice(0, 7);
    const isThisMonth = (r) => new Date(r.timestamp).toISOString().slice(0, 7) === monthKey;
    const monthly = records.filter(isThisMonth);
    return {
      todayIns: records.filter((r) => isToday(r) && r.type === "in").length,
      todayOuts: records.filter((r) => isToday(r) && r.type === "out").length,
      monthlyIns: monthly.filter((r) => r.type === "in").length,
      monthlyLate: monthly.filter((r) => r.type === "in" && r.is_late).length,
    };
  }, [records]);

  async function submitJustification() {
    try {
      await api.post("/attendance/justify", {
        record_id: justifying.record_id,
        justification: justText,
      });
      toast.success("Justificación registrada");
      setJustifying(null); setJustText(""); load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    }
  }

  return (
    <div className="p-4 sm:p-8 max-w-5xl mx-auto space-y-6" data-testid="historial-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <Badge variant="secondary" className="rounded-full mb-3">Mi actividad</Badge>
          <h1 className="text-3xl sm:text-4xl font-bold text-foreground flex items-center gap-3">
            <History className="h-8 w-8 text-primary/70" /> Mi historial
          </h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Todas tus marcas — hechas desde el kiosco con reconocimiento facial. Justifica tardanzas si es necesario.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3" data-testid="hist-kpis">
        <StatCard label="Entradas hoy" value={stats.todayIns} />
        <StatCard label="Salidas hoy" value={stats.todayOuts} />
        <StatCard label="Entradas del mes" value={stats.monthlyIns} />
        <StatCard label="Tardanzas del mes" value={stats.monthlyLate} tint="text-amber-600" />
      </div>

      <Card className="border-border/70 bg-card/80 backdrop-blur overflow-hidden">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40">
                <TableHead>Fecha</TableHead>
                <TableHead>Hora</TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead>Sede</TableHead>
                <TableHead>Estado</TableHead>
                <TableHead>Justificación</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody data-testid="hist-table">
              {loading && <TableRow><TableCell colSpan={6} className="text-center py-10 text-muted-foreground">Cargando…</TableCell></TableRow>}
              {!loading && records.length === 0 && (
                <TableRow><TableCell colSpan={6} className="text-center py-10 text-muted-foreground">Aún no tienes marcas registradas</TableCell></TableRow>
              )}
              {!loading && records.map((r) => {
                const d = new Date(r.timestamp);
                return (
                  <TableRow key={r.record_id}>
                    <TableCell className="text-sm">{dfDate.format(d)}</TableCell>
                    <TableCell className="text-sm font-mono">{dfTime.format(d)}</TableCell>
                    <TableCell>
                      {r.type === "in" ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 text-[11px] font-medium">
                          <LogIn className="h-3 w-3" /> Entrada
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-200 text-slate-700 text-[11px] font-medium">
                          <LogOut className="h-3 w-3" /> Salida
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-sm">
                      <span className="inline-flex items-center gap-1 text-muted-foreground">
                        <MapPin className="h-3 w-3" /> {sites[r.site_id] || "—"}
                      </span>
                    </TableCell>
                    <TableCell>
                      {r.is_late ? (() => {
                        const isMajor = r.late_severity === "late_major";
                        const cls = isMajor
                          ? "bg-red-100 text-red-800"
                          : "bg-amber-100 text-amber-800";
                        const label = isMajor ? "Retraso mayor" : "Retraso leve";
                        return (
                          <span className={"inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium " + cls}>
                            <AlertTriangle className="h-3 w-3" /> {label} · {r.late_minutes}m
                            {r.requires_justification && !r.justification && <span className="ml-0.5 font-bold">!</span>}
                          </span>
                        );
                      })() : r.type === "in" ? (
                        <span className="text-[11px] text-emerald-700">A tiempo</span>
                      ) : (
                        <span className="text-[11px] text-muted-foreground">—</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {r.justification ? (
                        <span className="text-xs text-muted-foreground italic">&ldquo;{r.justification}&rdquo;</span>
                      ) : r.is_late ? (
                        <Button variant="ghost" size="sm" onClick={() => setJustifying(r)} className="text-xs" data-testid={`hist-justify-${r.record_id}`}>
                          <MessageSquarePlus className="h-3.5 w-3.5 mr-1" /> Justificar
                        </Button>
                      ) : <span className="text-muted-foreground/60">—</span>}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </Card>

      <Dialog open={!!justifying} onOpenChange={(v) => !v && setJustifying(null)}>
        <DialogContent data-testid="hist-justify-dialog">
          <DialogHeader>
            <DialogTitle>Justificar tardanza</DialogTitle>
            <DialogDescription>Explica brevemente el motivo. Tu supervisor podrá verlo en los reportes.</DialogDescription>
          </DialogHeader>
          <div className="space-y-2">
            <Label>Motivo</Label>
            <Textarea rows={4} value={justText} onChange={(e) => setJustText(e.target.value)} placeholder="Ej. Retraso por tráfico en la autopista Francisco Fajardo." data-testid="hist-justify-textarea" />
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setJustifying(null)}>Cancelar</Button>
            <Button onClick={submitJustification} disabled={justText.trim().length < 5} className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground" data-testid="hist-justify-submit">
              Enviar justificación
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function StatCard({ label, value, tint = "text-foreground" }) {
  return (
    <Card className="border-border/70 bg-card/80 backdrop-blur">
      <CardContent className="pt-5">
        <p className={`text-3xl font-bold tracking-tight ${tint}`}>{value}</p>
        <p className="text-xs text-muted-foreground mt-1">{label}</p>
      </CardContent>
    </Card>
  );
}
