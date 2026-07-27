import { useEffect, useMemo, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { Users, LogIn, LogOut as LogOutIcon, AlertTriangle, RefreshCw, Building2, CalendarClock, UserCircle2 } from "lucide-react";

const TZ = "America/Caracas";
const dfTime = new Intl.DateTimeFormat("es-VE", { hour: "2-digit", minute: "2-digit", timeZone: TZ });
const dfDay = new Intl.DateTimeFormat("es-VE", { day: "2-digit", month: "short", timeZone: TZ });

function daysBackList(days) {
  const arr = [];
  for (let i = 0; i < days; i++) {
    const d = new Date();
    d.setDate(d.getDate() - i);
    arr.push(d);
  }
  return arr;
}

export default function TeamPage() {
  const { user } = useAuth();
  const [records, setRecords] = useState([]);
  const [users, setUsers] = useState([]);
  const [depts, setDepts] = useState([]);
  const [days, setDays] = useState("7");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [{ data: recs }, { data: allUsers }, { data: allDepts }] = await Promise.all([
        api.get(`/attendance/team?days=${days}`),
        api.get("/users"),
        api.get("/departments"),
      ]);
      setRecords(recs);
      setUsers(allUsers);
      setDepts(allDepts);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally { setLoading(false); setRefreshing(false); }
  }
  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [days]);

  const isAdmin = user?.role === "admin";
  const teamMembers = useMemo(() => {
    if (isAdmin) return users.filter((u) => u.role !== "admin");
    return users.filter((u) => u.supervisor_id === user?.user_id);
  }, [users, user, isAdmin]);
  const teamIds = useMemo(() => new Set(teamMembers.map((m) => m.user_id)), [teamMembers]);
  const teamRecords = useMemo(() => records.filter((r) => teamIds.has(r.user_id)), [records, teamIds]);

  const deptMap = useMemo(() => Object.fromEntries(depts.map((d) => [d.department_id, d.name])), [depts]);

  const kpis = useMemo(() => {
    const today = new Date().toLocaleDateString("en-CA", { timeZone: TZ });
    const todayRecs = teamRecords.filter((r) => new Date(r.timestamp).toLocaleDateString("en-CA", { timeZone: TZ }) === today);
    return {
      team: teamMembers.length,
      inToday: todayRecs.filter((r) => r.type === "in").length,
      late: teamRecords.filter((r) => r.type === "in" && r.is_late).length,
      absentToday: teamMembers.filter((m) =>
        !todayRecs.some((r) => r.user_id === m.user_id && r.type === "in")).length,
    };
  }, [teamMembers, teamRecords]);

  // Matrix por día (columna) y usuario (fila) — muestra estado del día
  const dayList = useMemo(() => daysBackList(Number(days)), [days]);
  const matrix = useMemo(() => {
    // For each user: { user, days: {'2026-07-22': {first_in, last_out, late, severity, needs_justif}} }
    return teamMembers.map((m) => {
      const byDay = {};
      for (const d of dayList) {
        const key = d.toLocaleDateString("en-CA", { timeZone: TZ });
        byDay[key] = { key, ins: [], outs: [], is_late: false, late_minutes: 0, severity: "on_time", needs_justif: false, records: [] };
      }
      const userRecs = teamRecords.filter((r) => r.user_id === m.user_id);
      for (const r of userRecs) {
        const key = new Date(r.timestamp).toLocaleDateString("en-CA", { timeZone: TZ });
        if (!byDay[key]) continue;
        byDay[key].records.push(r);
        if (r.type === "in") {
          byDay[key].ins.push(new Date(r.timestamp));
          if (r.is_late) {
            byDay[key].is_late = true;
            byDay[key].late_minutes = Math.max(byDay[key].late_minutes, r.late_minutes || 0);
            const sev = r.late_severity || "late_minor";
            // late_major wins over late_minor
            if (sev === "late_major" || byDay[key].severity !== "late_major") {
              byDay[key].severity = sev;
            }
            if (r.requires_justification && !r.justification) {
              byDay[key].needs_justif = true;
            }
          }
        } else {
          byDay[key].outs.push(new Date(r.timestamp));
        }
      }
      return { user: m, days: byDay };
    });
  }, [teamMembers, teamRecords, dayList]);

  return (
    <div className="p-4 sm:p-8 max-w-7xl mx-auto space-y-6" data-testid="team-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <Badge variant="secondary" className="rounded-full mb-3">
            {isAdmin ? "Vista supervisora" : "Mi equipo"}
          </Badge>
          <h1 className="text-3xl sm:text-4xl font-bold text-foreground flex items-center gap-3">
            <Users className="h-8 w-8 text-primary/70" /> Asistencia del equipo
          </h1>
          <p className="text-muted-foreground mt-1 text-sm">
            {isAdmin
              ? "Todo el personal salvo administradores — ideal para chequear el día."
              : "Empleados que tienen tu cuenta asignada como supervisor."}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={days} onValueChange={setDays}>
            <SelectTrigger className="w-[140px]" data-testid="team-days"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="1">Hoy</SelectItem>
              <SelectItem value="3">3 días</SelectItem>
              <SelectItem value="7">7 días</SelectItem>
              <SelectItem value="14">14 días</SelectItem>
              <SelectItem value="30">30 días</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" className="rounded-full" onClick={() => { setRefreshing(true); load(); }} disabled={refreshing} data-testid="team-refresh">
            <RefreshCw className={"h-4 w-4 mr-1.5 " + (refreshing ? "animate-spin" : "")} /> Actualizar
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3" data-testid="team-kpis">
        <MiniStat icon={Users} tint="text-foreground" label="Miembros" value={kpis.team} />
        <MiniStat icon={LogIn} tint="text-emerald-600" label="Entradas hoy" value={kpis.inToday} />
        <MiniStat icon={AlertTriangle} tint="text-amber-600" label="Tarde en el período" value={kpis.late} />
        <MiniStat icon={LogOutIcon} tint="text-fuchsia-600" label="Sin marcar hoy" value={kpis.absentToday} />
      </div>

      <Card className="border-border/70 bg-card/80 backdrop-blur">
        <CardHeader className="pb-2">
          <CardTitle className="text-base text-foreground">Detalle diario · últimos {days} día(s)</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/40">
                  <TableHead className="min-w-[240px] sticky left-0 bg-muted/40">Empleado</TableHead>
                  {dayList.map((d) => (
                    <TableHead key={d.toISOString()} className="text-center whitespace-nowrap">
                      <div className="text-[11px] text-muted-foreground uppercase tracking-wide">
                        {d.toLocaleDateString("es-VE", { weekday: "short", timeZone: TZ }).slice(0, 3)}
                      </div>
                      <div className="text-sm font-semibold text-foreground">{dfDay.format(d)}</div>
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody data-testid="team-matrix">
                {loading && <TableRow><TableCell colSpan={dayList.length + 1} className="text-center py-10 text-muted-foreground">Cargando…</TableCell></TableRow>}
                {!loading && matrix.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={dayList.length + 1} className="text-center py-10 text-muted-foreground">
                      {isAdmin ? "No hay empleados activos." : "Aún no tienes empleados asignados como supervisor."}
                    </TableCell>
                  </TableRow>
                )}
                {!loading && matrix.map(({ user: m, days: byDay }) => (
                  <TableRow key={m.user_id} data-testid={`team-row-${m.user_id}`}>
                    <TableCell className="sticky left-0 bg-card/80">
                      <div className="flex items-center gap-3">
                        <div className="h-9 w-9 rounded-full bg-primary/10 text-foreground grid place-items-center text-xs font-semibold overflow-hidden">
                          {m.picture ? <img src={m.picture} alt="" className="h-full w-full object-cover" /> :
                            m.name.split(" ").slice(0, 2).map((p) => p[0]).join("")}
                        </div>
                        <div>
                          <p className="text-sm font-medium text-foreground leading-tight">{m.name}</p>
                          <p className="text-[11px] text-muted-foreground leading-tight flex items-center gap-1">
                            <Building2 className="h-3 w-3" /> {deptMap[m.department_id] || m.position || "—"}
                          </p>
                        </div>
                      </div>
                    </TableCell>
                    {dayList.map((d) => {
                      const key = d.toLocaleDateString("en-CA", { timeZone: TZ });
                      const cell = byDay[key];
                      const firstIn = cell.ins.sort((a, b) => a - b)[0];
                      const lastOut = cell.outs.sort((a, b) => b - a)[0];
                      const hasAny = cell.ins.length + cell.outs.length > 0;
                      return (
                        <TableCell key={key} className="text-center align-top py-3">
                          {!hasAny && (
                            <span className="inline-block h-2 w-2 rounded-full bg-muted-foreground/25" title="Sin marca" />
                          )}
                          {hasAny && (() => {
                            const isMajor = cell.severity === "late_major";
                            const isMinor = cell.severity === "late_minor";
                            const needsJ = cell.needs_justif;
                            const bg = isMajor
                              ? (needsJ ? "bg-red-100 ring-1 ring-red-300" : "bg-red-50")
                              : isMinor ? "bg-amber-100" : "bg-emerald-50";
                            const textColor = isMajor ? "text-red-800" : "text-amber-800";
                            return (
                              <div className={"inline-block rounded-lg px-2 py-1 " + bg}
                                   title={needsJ ? "Requiere justificación del supervisor" : undefined}>
                                <div className="text-[11px] font-mono text-foreground">
                                  {firstIn ? dfTime.format(firstIn) : "—"} / {lastOut ? dfTime.format(lastOut) : "—"}
                                </div>
                                {cell.is_late && (
                                  <div className={"text-[9px] flex items-center justify-center gap-0.5 " + textColor}>
                                    <AlertTriangle className="h-2.5 w-2.5" />
                                    {cell.late_minutes}m {isMajor ? "· mayor" : "leve"}
                                    {needsJ && <span className="ml-0.5">!</span>}
                                  </div>
                                )}
                              </div>
                            );
                          })()}
                        </TableCell>
                      );
                    })}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center justify-center gap-3 text-[11px] text-muted-foreground">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-sm bg-emerald-50 border border-emerald-200" /> A tiempo
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-sm bg-amber-100 border border-amber-300" /> Retraso leve
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-sm bg-red-100 border border-red-300" /> Retraso mayor
        </span>
        <span className="inline-flex items-center gap-1.5">
          <AlertTriangle className="h-3 w-3 text-red-500" /> Requiere justificar
        </span>
      </div>

      <p className="text-[11px] text-muted-foreground text-center">
        <UserCircle2 className="h-3 w-3 inline mr-1" />
        {isAdmin ? "Vista global (todos los empleados no-admin)." : "Vista limitada a empleados con supervisor_id = tu ID."}
      </p>
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
