import { useEffect, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import {
  Trophy, Clock, TrendingUp, FileDown, Building2, Loader2, AlertTriangle,
} from "lucide-react";
import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";

const RANK_COLORS = ["bg-amber-400", "bg-slate-400", "bg-orange-400", "bg-primary/70", "bg-primary/50"];

function fmtMinutes(m) {
  if (!m) return "0 min";
  if (m < 60) return `${m} min`;
  const h = Math.floor(m / 60);
  const rest = Math.round(m % 60);
  return rest ? `${h} h ${rest} min` : `${h} h`;
}

export default function ExecutiveWidget() {
  const [data, setData] = useState(null);
  const [days, setDays] = useState("30");
  const [loading, setLoading] = useState(true);
  const [company, setCompany] = useState({});
  const [downloading, setDownloading] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [{ data: exec }, { data: settings }] = await Promise.all([
        api.get(`/stats/executive?days=${days}`),
        api.get("/settings"),
      ]);
      setData(exec);
      setCompany(settings);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally { setLoading(false); }
  }
  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [days]);

  async function downloadPDF() {
    if (!data) return;
    setDownloading(true);
    try {
      const doc = new jsPDF({ unit: "pt", format: "a4" });
      const now = new Date();
      const w = doc.internal.pageSize.getWidth();

      // Header band
      doc.setFillColor(14, 42, 71);
      doc.rect(0, 0, w, 90, "F");
      doc.setTextColor(247, 201, 72);
      doc.setFontSize(9);
      doc.text(String(company.name || "Mega Soft").toUpperCase(), 40, 32);
      doc.setTextColor(255, 255, 255);
      doc.setFontSize(20);
      doc.text("Resumen ejecutivo de asistencia", 40, 58);
      doc.setFontSize(10);
      doc.setTextColor(200, 210, 225);
      doc.text(`Último(s) ${data.days} día(s) · generado ${now.toLocaleString("es-VE", { timeZone: "America/Caracas" })}`, 40, 76);

      // KPI cards
      const kpis = [
        { label: "Marcas de entrada", value: String(data.total_check_ins) },
        { label: "Entradas tarde", value: String(data.total_late) },
        { label: "% tardanzas", value: `${data.late_pct}%` },
        { label: "Prom. min tarde", value: fmtMinutes(Math.round(data.avg_late_minutes)) },
      ];
      const cardW = (w - 80 - 30) / 4;
      kpis.forEach((k, i) => {
        const x = 40 + i * (cardW + 10);
        const y = 115;
        doc.setDrawColor(220, 225, 235);
        doc.setFillColor(248, 250, 252);
        doc.roundedRect(x, y, cardW, 60, 6, 6, "FD");
        doc.setTextColor(14, 42, 71);
        doc.setFontSize(18);
        doc.text(k.value, x + 14, y + 32);
        doc.setFontSize(9);
        doc.setTextColor(100, 116, 139);
        doc.text(k.label, x + 14, y + 48);
      });

      // Top late table
      autoTable(doc, {
        startY: 200,
        head: [["#", "Empleado", "Departamento", "Cargo", "# Tardanzas", "Minutos totales"]],
        body: (data.top_late || []).map((u, i) => [
          i + 1,
          u.name,
          u.department_name || "—",
          u.position || "—",
          String(u.late_count),
          fmtMinutes(u.total_minutes),
        ]),
        theme: "grid",
        headStyles: { fillColor: [14, 42, 71], textColor: [247, 201, 72], fontSize: 9 },
        bodyStyles: { fontSize: 9 },
        margin: { left: 40, right: 40 },
        didDrawPage: (d) => {
          doc.setFontSize(10);
          doc.setTextColor(14, 42, 71);
          doc.text("Top 5 · empleados con más tardanzas", 40, d.settings.startY - 8);
        },
      });

      // Department ranking
      const nextY = doc.lastAutoTable.finalY + 30;
      autoTable(doc, {
        startY: nextY,
        head: [["Departamento", "Entradas", "Tarde", "% Tarde"]],
        body: (data.department_ranking || []).map((d) => [
          d.department_name,
          String(d.total_ins),
          String(d.late),
          `${d.late_pct}%`,
        ]),
        theme: "striped",
        headStyles: { fillColor: [30, 41, 59], textColor: [247, 201, 72], fontSize: 9 },
        bodyStyles: { fontSize: 9 },
        margin: { left: 40, right: 40 },
        didDrawPage: (d) => {
          doc.setFontSize(10);
          doc.setTextColor(14, 42, 71);
          doc.text("Ranking por departamento", 40, d.settings.startY - 8);
        },
      });

      // Footer
      const total = doc.internal.getNumberOfPages();
      for (let i = 1; i <= total; i++) {
        doc.setPage(i);
        doc.setFontSize(8);
        doc.setTextColor(120, 130, 145);
        doc.text(
          `${company.name || "Mega Soft"} · Reporte confidencial · Página ${i} de ${total}`,
          w / 2, doc.internal.pageSize.getHeight() - 20, { align: "center" }
        );
      }

      doc.save(`resumen_ejecutivo_${data.days}d_${now.toISOString().slice(0, 10)}.pdf`);
      toast.success("PDF descargado");
    } catch (e) {
      toast.error(e.message || "No se pudo generar el PDF");
    } finally { setDownloading(false); }
  }

  return (
    <Card className="border-border/70 bg-white/80 dark:bg-card/80 backdrop-blur" data-testid="executive-widget">
      <CardHeader className="flex-row items-start justify-between gap-3 space-y-0 pb-3">
        <div>
          <CardTitle className="text-base text-foreground dark:text-foreground flex items-center gap-2">
            <Trophy className="h-4 w-4 text-accent" /> Resumen ejecutivo
          </CardTitle>
          <CardDescription>
            Top 5 con más tardanzas y ranking por departamento. Ideal para reuniones semanales.
          </CardDescription>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Select value={days} onValueChange={setDays}>
            <SelectTrigger className="h-9 w-[120px]" data-testid="executive-days"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="7">7 días</SelectItem>
              <SelectItem value="14">14 días</SelectItem>
              <SelectItem value="30">30 días</SelectItem>
              <SelectItem value="60">60 días</SelectItem>
              <SelectItem value="90">90 días</SelectItem>
            </SelectContent>
          </Select>
          <Button
            size="sm"
            onClick={downloadPDF}
            disabled={downloading || !data || (data?.top_late || []).length === 0}
            className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground shadow-lg shadow-primary/10"
            data-testid="executive-pdf-btn"
          >
            {downloading
              ? <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
              : <FileDown className="h-4 w-4 mr-1.5" />}
            PDF
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {loading && (
          <div className="py-6 text-center text-sm text-muted-foreground flex items-center justify-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin" /> Calculando…
          </div>
        )}

        {!loading && data && (
          <div className="grid gap-4 lg:grid-cols-[1.15fr_1fr]">
            {/* Top 5 */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <p className="text-xs uppercase tracking-wider text-muted-foreground">
                  Top 5 tardanzas
                </p>
                <div className="flex items-center gap-3 text-xs text-muted-foreground">
                  <span><Clock className="h-3 w-3 inline mr-1" /> {data.total_late} tardanzas</span>
                  <span><TrendingUp className="h-3 w-3 inline mr-1" /> {data.late_pct}%</span>
                </div>
              </div>
              <ol className="space-y-2" data-testid="executive-top-late">
                {(data.top_late || []).length === 0 && (
                  <li className="text-center py-10 text-sm text-muted-foreground">
                    Sin tardanzas en el período 🎉
                  </li>
                )}
                {data.top_late.map((u, i) => (
                  <li
                    key={u.user_id}
                    className="flex items-center gap-3 rounded-xl border border-border/60 bg-muted/30 hover:bg-muted/60 transition-colors px-3 py-2.5"
                    data-testid={`executive-top-${i + 1}`}
                  >
                    <div className={`h-8 w-8 rounded-full grid place-items-center text-foreground font-bold text-sm ${RANK_COLORS[i]}`}>
                      {i + 1}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-foreground dark:text-foreground truncate">{u.name}</p>
                      <p className="text-[11px] text-muted-foreground truncate flex items-center gap-1">
                        <Building2 className="h-3 w-3" /> {u.department_name} · {u.position || "—"}
                      </p>
                    </div>
                    <div className="text-right shrink-0">
                      <p className="text-sm font-semibold text-amber-600">{u.late_count}<span className="text-xs text-muted-foreground ml-0.5">×</span></p>
                      <p className="text-[11px] text-muted-foreground">{fmtMinutes(u.total_minutes)}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </div>

            {/* Department ranking */}
            <div>
              <p className="text-xs uppercase tracking-wider text-muted-foreground mb-3">
                Ranking por departamento
              </p>
              <ul className="space-y-1.5" data-testid="executive-dept-ranking">
                {(data.department_ranking || []).length === 0 && (
                  <li className="text-center py-10 text-sm text-muted-foreground">Sin datos aún</li>
                )}
                {(data.department_ranking || []).map((d) => (
                  <li key={d.department_name} className="text-sm">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-foreground dark:text-foreground truncate">{d.department_name}</span>
                      <span className={"text-xs font-mono " + (d.late_pct > 50 ? "text-destructive" : d.late_pct > 20 ? "text-amber-600" : "text-emerald-700")}>
                        {d.late_pct}%
                      </span>
                    </div>
                    <div className="h-1.5 w-full bg-muted rounded-full overflow-hidden">
                      <div
                        className={"h-full transition-[width] " + (d.late_pct > 50 ? "bg-destructive" : d.late_pct > 20 ? "bg-amber-500" : "bg-emerald-500")}
                        style={{ width: `${Math.min(100, d.late_pct)}%` }}
                      />
                    </div>
                    <p className="text-[10px] text-muted-foreground mt-0.5">
                      {d.late}/{d.total_ins} entradas tarde
                    </p>
                  </li>
                ))}
              </ul>
              {data.total_late > 20 && (
                <div className="mt-3 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 dark:bg-amber-950/20 dark:border-amber-900/40 px-3 py-2 text-[11px] text-amber-800 dark:text-amber-200">
                  <AlertTriangle className="h-3.5 w-3.5 mt-0.5" />
                  Muchas tardanzas en el período — considera revisar horarios o tolerancia.
                </div>
              )}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
