import { useEffect, useMemo, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid,
} from "recharts";
import { Users2, Clock3, AlertTriangle, Inbox, TrendingUp } from "lucide-react";

const num = (n) => new Intl.NumberFormat("es-VE").format(n ?? 0);

export default function DashboardHome() {
  const [stats, setStats] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    api.get("/stats/dashboard")
      .then((r) => setStats(r.data))
      .catch((e) => setErr(formatApiErrorDetail(e.response?.data?.detail) || e.message));
  }, []);

  const kpis = useMemo(() => {
    if (!stats) return [];
    return [
      { icon: Users2, label: "Empleados", value: stats.total_users, hint: `${stats.onboarded_users} con rostro registrado`, tint: "text-primary" },
      { icon: Clock3, label: "Marcas de entrada hoy", value: stats.check_ins_today, hint: "check-ins registrados", tint: "text-emerald-600" },
      { icon: AlertTriangle, label: "Tarde hoy", value: stats.late_today, hint: "fuera de tolerancia", tint: "text-amber-600" },
      { icon: Inbox, label: "Novedades pendientes", value: stats.pending_novelties, hint: "esperando decisión", tint: "text-fuchsia-600" },
    ];
  }, [stats]);

  return (
    <div className="p-4 sm:p-8 max-w-7xl mx-auto space-y-8" data-testid="dashboard-home">
      <div>
        <Badge variant="secondary" className="rounded-full mb-3">Panel administrativo</Badge>
        <h1 className="text-3xl sm:text-4xl font-bold text-primary">
          Resumen operativo
          <span className="block font-serif-display text-primary/60 text-2xl mt-1">
            todo lo que pasa hoy en la empresa.
          </span>
        </h1>
      </div>

      {err && (
        <Card className="border-destructive/40 bg-destructive/5">
          <CardContent className="py-4 text-sm text-destructive">{err}</CardContent>
        </Card>
      )}

      <div className="grid gap-3 grid-cols-2 lg:grid-cols-4" data-testid="dashboard-kpis">
        {kpis.map((k) => (
          <Card key={k.label} className="border-border/70 bg-white/80 backdrop-blur">
            <CardHeader className="pb-2">
              <div className="flex items-center justify-between">
                <k.icon className={`h-5 w-5 ${k.tint}`} />
                <TrendingUp className="h-3.5 w-3.5 text-muted-foreground/70" />
              </div>
            </CardHeader>
            <CardContent>
              <p className="text-3xl font-bold text-primary tracking-tight">{num(k.value)}</p>
              <p className="text-xs text-muted-foreground mt-0.5">{k.label}</p>
              <p className="text-[11px] text-muted-foreground/80 mt-2">{k.hint}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card className="border-border/70 bg-white/80 backdrop-blur">
        <CardHeader>
          <CardTitle className="text-base text-primary">Actividad — últimos 7 días</CardTitle>
          <CardDescription>Entradas totales vs. entradas fuera de tolerancia.</CardDescription>
        </CardHeader>
        <CardContent className="h-72 pl-0" data-testid="dashboard-chart">
          {stats && (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={stats.series_7d || []} margin={{ left: 12, right: 20, top: 8 }}>
                <defs>
                  <linearGradient id="gIn" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="hsl(var(--chart-1))" stopOpacity={0.6} />
                    <stop offset="100%" stopColor="hsl(var(--chart-1))" stopOpacity={0.02} />
                  </linearGradient>
                  <linearGradient id="gLate" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="hsl(var(--warning))" stopOpacity={0.55} />
                    <stop offset="100%" stopColor="hsl(var(--warning))" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" />
                <YAxis allowDecimals={false} tick={{ fontSize: 11 }} stroke="hsl(var(--muted-foreground))" width={30} />
                <Tooltip
                  contentStyle={{
                    borderRadius: 12, border: "1px solid hsl(var(--border))",
                    background: "white", fontSize: 12,
                  }}
                />
                <Area type="monotone" dataKey="check_ins" name="Check-ins" stroke="hsl(var(--chart-1))" fill="url(#gIn)" strokeWidth={2} />
                <Area type="monotone" dataKey="late" name="Tarde" stroke="hsl(var(--warning))" fill="url(#gLate)" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      <div className="rounded-2xl border border-amber-200/70 bg-amber-50/60 px-5 py-4 text-sm text-amber-900">
        <b>Fase 1 en curso.</b> Ya puedes gestionar empleados y registrar tu rostro.
        Las secciones de sedes, departamentos y kiosco llegan en las próximas fases.
      </div>
    </div>
  );
}
