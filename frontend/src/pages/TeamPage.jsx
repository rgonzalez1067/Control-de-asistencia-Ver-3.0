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
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import {
  Users, LogIn, LogOut as LogOutIcon, AlertTriangle, RefreshCw, Building2,
  CalendarClock, UserCircle2, FileWarning, CheckCircle2, XCircle, Clock3,
} from "lucide-react";

const TZ = "America/Caracas";
const dfTime = new Intl.DateTimeFormat("es-VE", { hour: "2-digit", minute: "2-digit", timeZone: TZ });
const dfDay = new Intl.DateTimeFormat("es-VE", { day: "2-digit", month: "short", timeZone: TZ });
const dfLongDate = new Intl.DateTimeFormat("es-VE", { weekday: "long", day: "2-digit", month: "long", year: "numeric", timeZone: TZ });

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
  const [schedules, setSchedules] = useState([]);
  const [days, setDays] = useState("7");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [assigning, setAssigning] = useState(null); // user_id in progress
  const [reviewCell, setReviewCell] = useState(null); // { member, dayKey, records }
  const [rejectReason, setRejectReason] = useState("");
  const [rejectMode, setRejectMode] = useState(false);
  const [deciding, setDeciding] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [{ data: recs }, { data: allUsers }, { data: allDepts }, { data: allSchedules }] = await Promise.all([
        api.get(`/attendance/team?days=${days}`),
        api.get("/users"),
        api.get("/departments"),
        api.get("/schedules"),
      ]);
      setRecords(recs);
      setUsers(allUsers);
      setDepts(allDepts);
      setSchedules(allSchedules);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally { setLoading(false); setRefreshing(false); }
  }
  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [days]);

  const isAdmin = user?.role === "admin";
  const canManageSchedules = isAdmin || !!user?.can_manage_schedules;
  const scheduleMap = useMemo(
    () => Object.fromEntries((schedules || []).map((s) => [s.schedule_id, s.name])),
    [schedules],
  );
  const sortedSchedules = useMemo(
    () => [...(schedules || [])].sort((a, b) => (a.name || "").localeCompare(b.name || "", "es", { sensitivity: "base" })),
    [schedules],
  );

  async function assignSchedule(userId, scheduleId) {
    setAssigning(userId);
    try {
      await api.patch(`/users/${userId}/schedule`, { schedule_id: scheduleId || null });
      setUsers((prev) => prev.map((u) => u.user_id === userId ? { ...u, schedule_id: scheduleId || null } : u));
      toast.success("Horario actualizado");
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally {
      setAssigning(null);
    }
  }
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
    const pendingJust = teamRecords.filter((r) => r.type === "in" && r.justification_status === "pending").length;
    return {
      team: teamMembers.length,
      inToday: todayRecs.filter((r) => r.type === "in").length,
      late: teamRecords.filter((r) => r.type === "in" && r.is_late).length,
      pendingJust,
    };
  }, [teamMembers, teamRecords]);

  // Matrix por día (columna) y usuario (fila)
  const dayList = useMemo(() => daysBackList(Number(days)), [days]);
  const matrix = useMemo(() => {
    const sortedMembers = [...teamMembers].sort(
      (a, b) => (a.name || "").localeCompare(b.name || "", "es", { sensitivity: "base" }),
    );
    return sortedMembers.map((m) => {
      const byDay = {};
      for (const d of dayList) {
        const key = d.toLocaleDateString("en-CA", { timeZone: TZ });
        byDay[key] = {
          key, ins: [], outs: [],
          is_late: false, late_minutes: 0, severity: "on_time",
          justification_status: "none", // "none" | "pending" | "approved" | "rejected"
          just_text: null, rejection_reason: null,
          records: [],
        };
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
            if (sev === "late_major" || byDay[key].severity !== "late_major") {
              byDay[key].severity = sev;
            }
            const st = r.justification_status || "none";
            // Prioridad de estado en celda: pending > rejected > approved > none
            const rank = (s) => ({ pending: 3, rejected: 2, approved: 1, none: 0 }[s] || 0);
            if (rank(st) > rank(byDay[key].justification_status)) {
              byDay[key].justification_status = st;
            }
            if (r.justification) byDay[key].just_text = r.justification;
            if (r.rejection_reason) byDay[key].rejection_reason = r.rejection_reason;
          }
        } else {
          byDay[key].outs.push(new Date(r.timestamp));
        }
      }
      return { user: m, days: byDay };
    });
  }, [teamMembers, teamRecords, dayList]);

  function openReview(member, dayKey, cell) {
    // Toma el primer registro "in" del día con justification (o pending o cualquiera con texto)
    const inRec = (cell.records || []).find((r) => r.type === "in" && r.justification)
                || (cell.records || []).find((r) => r.type === "in" && r.is_late);
    if (!inRec) return;
    setReviewCell({ member, dayKey, cell, record: inRec });
    setRejectReason("");
    setRejectMode(false);
  }

  async function decide(decision) {
    if (!reviewCell) return;
    if (decision === "rejected") {
      if (!rejectMode) { setRejectMode(true); return; }
      if (rejectReason.trim().length < 3) {
        toast.error("Ingresa la razón del rechazo (mín. 3 caracteres)");
        return;
      }
    }
    setDeciding(true);
    try {
      await api.post("/attendance/justify/decide", {
        record_id: reviewCell.record.record_id,
        decision,
        rejection_reason: decision === "rejected" ? rejectReason.trim() : null,
      });
      toast.success(decision === "approved" ? "Justificación aceptada" : "Justificación rechazada");
      setReviewCell(null);
      setRejectMode(false);
      setRejectReason("");
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally {
      setDeciding(false);
    }
  }

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
        <MiniStat icon={FileWarning} tint="text-red-600" label="Justif. pendientes" value={kpis.pendingJust} testId="team-kpi-pending-just" />
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
                  <TableHead className="min-w-[280px] sticky left-0 bg-muted/40">Empleado</TableHead>
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
                        <div className="min-w-0">
                          <p className="text-sm font-medium text-foreground leading-tight">{m.name}</p>
                          <p className="text-[11px] text-muted-foreground leading-tight flex items-center gap-1">
                            <Building2 className="h-3 w-3" /> {deptMap[m.department_id] || m.position || "—"}
                          </p>
                          {canManageSchedules ? (
                            <div className="mt-1.5 flex items-center gap-1.5" data-testid={`team-schedule-assign-${m.user_id}`}>
                              <CalendarClock className="h-3 w-3 text-muted-foreground shrink-0" />
                              <Select
                                value={m.schedule_id || "__none"}
                                onValueChange={(v) => assignSchedule(m.user_id, v === "__none" ? "" : v)}
                                disabled={assigning === m.user_id}
                              >
                                <SelectTrigger
                                  className="h-7 text-[11px] px-2 min-w-[160px] max-w-[220px]"
                                  data-testid={`team-schedule-select-${m.user_id}`}
                                >
                                  <SelectValue placeholder="— sin horario —" />
                                </SelectTrigger>
                                <SelectContent>
                                  <SelectItem value="__none">— sin horario —</SelectItem>
                                  {sortedSchedules.map((s) => (
                                    <SelectItem key={s.schedule_id} value={s.schedule_id}>{s.name}</SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </div>
                          ) : m.schedule_id && (
                            <p className="text-[11px] text-muted-foreground leading-tight mt-0.5 flex items-center gap-1">
                              <CalendarClock className="h-3 w-3" /> {scheduleMap[m.schedule_id] || "—"}
                            </p>
                          )}
                        </div>
                      </div>
                    </TableCell>
                    {dayList.map((d) => {
                      const key = d.toLocaleDateString("en-CA", { timeZone: TZ });
                      const cell = byDay[key];
                      const firstIn = cell.ins.sort((a, b) => a - b)[0];
                      const lastOut = cell.outs.sort((a, b) => b - a)[0];
                      const hasAny = cell.ins.length + cell.outs.length > 0;
                      const jStatus = cell.justification_status;
                      const clickable = cell.is_late && (jStatus === "pending" || cell.just_text);
                      return (
                        <TableCell key={key} className="text-center align-top py-3">
                          {!hasAny && (
                            <span className="inline-block h-2 w-2 rounded-full bg-muted-foreground/25" title="Sin marca" />
                          )}
                          {hasAny && (() => {
                            const isMajor = cell.severity === "late_major";
                            const isMinor = cell.severity === "late_minor";
                            let bg = "bg-emerald-50";
                            let textColor = "text-emerald-800";
                            if (jStatus === "approved") { bg = "bg-emerald-100 ring-1 ring-emerald-300"; textColor = "text-emerald-800"; }
                            else if (jStatus === "rejected") { bg = "bg-red-100 ring-1 ring-red-300"; textColor = "text-red-800"; }
                            else if (jStatus === "pending") { bg = "bg-amber-100 ring-1 ring-amber-400 animate-pulse-slow"; textColor = "text-amber-900"; }
                            else if (isMajor) { bg = "bg-red-50"; textColor = "text-red-800"; }
                            else if (isMinor) { bg = "bg-amber-100"; textColor = "text-amber-800"; }

                            const cellTitle = jStatus === "pending"
                              ? "Justificación pendiente — clic para revisar"
                              : jStatus === "approved" ? "Retraso justificado"
                              : jStatus === "rejected" ? "Retraso injustificado (rechazado)"
                              : (cell.just_text ? "Ver justificación" : undefined);

                            const Wrapper = clickable ? "button" : "div";
                            const wrapperProps = clickable ? {
                              onClick: () => openReview(m, key, cell),
                              "data-testid": `team-cell-review-${m.user_id}-${key}`,
                              className: "inline-block rounded-lg px-2 py-1 " + bg + " cursor-pointer hover:opacity-80 transition",
                            } : { className: "inline-block rounded-lg px-2 py-1 " + bg };
                            return (
                              <Wrapper {...wrapperProps} title={cellTitle}>
                                <div className="text-[11px] font-mono text-foreground">
                                  {firstIn ? dfTime.format(firstIn) : "—"} / {lastOut ? dfTime.format(lastOut) : "—"}
                                </div>
                                {cell.is_late && (
                                  <div className={"text-[9px] flex items-center justify-center gap-0.5 " + textColor}>
                                    {jStatus === "pending"
                                      ? <FileWarning className="h-2.5 w-2.5" />
                                      : jStatus === "approved"
                                        ? <CheckCircle2 className="h-2.5 w-2.5" />
                                        : jStatus === "rejected"
                                          ? <XCircle className="h-2.5 w-2.5" />
                                          : <AlertTriangle className="h-2.5 w-2.5" />}
                                    {cell.late_minutes}m {jStatus === "pending" ? "· pendiente" : jStatus === "approved" ? "· justif." : jStatus === "rejected" ? "· injustif." : isMajor ? "· mayor" : "leve"}
                                  </div>
                                )}
                              </Wrapper>
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
          <span className="h-3 w-3 rounded-sm bg-red-50 border border-red-300" /> Retraso mayor
        </span>
        <span className="inline-flex items-center gap-1.5">
          <FileWarning className="h-3 w-3 text-amber-600" /> Pendiente aprobación
        </span>
        <span className="inline-flex items-center gap-1.5">
          <CheckCircle2 className="h-3 w-3 text-emerald-600" /> Justificado
        </span>
        <span className="inline-flex items-center gap-1.5">
          <XCircle className="h-3 w-3 text-red-600" /> Injustificado
        </span>
      </div>

      <p className="text-[11px] text-muted-foreground text-center">
        <UserCircle2 className="h-3 w-3 inline mr-1" />
        {isAdmin ? "Vista global (todos los empleados no-admin)." : "Vista limitada a empleados con supervisor_id = tu ID."}
      </p>

      {/* Dialog de revisión de justificación */}
      <Dialog open={!!reviewCell} onOpenChange={(v) => { if (!v) { setReviewCell(null); setRejectMode(false); setRejectReason(""); } }}>
        <DialogContent data-testid="team-justify-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileWarning className="h-5 w-5 text-amber-600" />
              Revisar justificación
            </DialogTitle>
            <DialogDescription>
              {reviewCell && `${reviewCell.member.name} — ${dfLongDate.format(new Date(reviewCell.dayKey + "T12:00:00"))}`}
            </DialogDescription>
          </DialogHeader>

          {reviewCell && (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="rounded-md border border-border/60 p-2.5 bg-muted/40">
                  <p className="text-[10px] uppercase text-muted-foreground tracking-wide">Minutos de retraso</p>
                  <p className="font-mono text-lg text-foreground">{reviewCell.cell.late_minutes}m</p>
                </div>
                <div className="rounded-md border border-border/60 p-2.5 bg-muted/40">
                  <p className="text-[10px] uppercase text-muted-foreground tracking-wide">Estado actual</p>
                  <StatusBadge status={reviewCell.cell.justification_status} />
                </div>
              </div>

              <div className="rounded-md border border-border/60 p-3 bg-card">
                <p className="text-[10px] uppercase text-muted-foreground tracking-wide mb-1">
                  Justificación del empleado
                </p>
                <p className="text-sm text-foreground italic leading-relaxed" data-testid="team-justify-text">
                  {reviewCell.cell.just_text
                    ? <>&ldquo;{reviewCell.cell.just_text}&rdquo;</>
                    : <span className="text-muted-foreground">El empleado aún no ha justificado este retraso.</span>}
                </p>
              </div>

              {reviewCell.cell.justification_status === "rejected" && reviewCell.cell.rejection_reason && (
                <div className="rounded-md border border-red-200 p-3 bg-red-50">
                  <p className="text-[10px] uppercase text-red-700 tracking-wide mb-1">Razón del rechazo</p>
                  <p className="text-sm text-red-900">{reviewCell.cell.rejection_reason}</p>
                </div>
              )}

              {rejectMode && (
                <div className="space-y-1.5">
                  <Label htmlFor="reject-reason" className="text-red-700">Razón del rechazo (obligatorio)</Label>
                  <Textarea
                    id="reject-reason"
                    rows={3}
                    value={rejectReason}
                    onChange={(e) => setRejectReason(e.target.value)}
                    placeholder="Ej. La justificación no contiene evidencia suficiente."
                    data-testid="team-reject-reason"
                    className="border-red-300 focus-visible:ring-red-500"
                  />
                </div>
              )}
            </div>
          )}

          {reviewCell && reviewCell.cell.just_text && (reviewCell.cell.justification_status === "pending" || reviewCell.cell.justification_status === "none") && (
            <DialogFooter className="gap-2 sm:justify-between">
              {!rejectMode ? (
                <>
                  <Button
                    variant="outline"
                    onClick={() => decide("rejected")}
                    disabled={deciding}
                    className="rounded-full border-red-300 text-red-700 hover:bg-red-50"
                    data-testid="team-btn-reject"
                  >
                    <XCircle className="h-4 w-4 mr-1.5" /> Rechazar
                  </Button>
                  <Button
                    onClick={() => decide("approved")}
                    disabled={deciding}
                    className="rounded-full bg-emerald-600 hover:bg-emerald-700 text-white"
                    data-testid="team-btn-approve"
                  >
                    <CheckCircle2 className="h-4 w-4 mr-1.5" /> Aceptar justificación
                  </Button>
                </>
              ) : (
                <>
                  <Button variant="ghost" onClick={() => { setRejectMode(false); setRejectReason(""); }} disabled={deciding}>
                    Cancelar
                  </Button>
                  <Button
                    onClick={() => decide("rejected")}
                    disabled={deciding || rejectReason.trim().length < 3}
                    className="rounded-full bg-red-600 hover:bg-red-700 text-white"
                    data-testid="team-btn-reject-confirm"
                  >
                    Confirmar rechazo
                  </Button>
                </>
              )}
            </DialogFooter>
          )}
          {reviewCell && (reviewCell.cell.justification_status === "approved" || reviewCell.cell.justification_status === "rejected") && (
            <DialogFooter>
              <Button variant="ghost" onClick={() => setReviewCell(null)}>Cerrar</Button>
            </DialogFooter>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}

function StatusBadge({ status }) {
  const map = {
    pending: { icon: Clock3, cls: "bg-amber-100 text-amber-900 border-amber-300", label: "Pendiente" },
    approved: { icon: CheckCircle2, cls: "bg-emerald-100 text-emerald-800 border-emerald-300", label: "Justificado" },
    rejected: { icon: XCircle, cls: "bg-red-100 text-red-800 border-red-300", label: "Injustificado" },
    none: { icon: AlertTriangle, cls: "bg-slate-100 text-slate-700 border-slate-300", label: "Sin justificar" },
  };
  const cfg = map[status] || map.none;
  const Icon = cfg.icon;
  return (
    <span className={"inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium " + cfg.cls}>
      <Icon className="h-3 w-3" /> {cfg.label}
    </span>
  );
}

function MiniStat({ icon: Icon, label, value, tint, testId }) {
  return (
    <Card className="border-border/70 bg-card/80 backdrop-blur" data-testid={testId}>
      <CardContent className="pt-5">
        <Icon className={`h-5 w-5 mb-1 ${tint}`} />
        <p className="text-3xl font-bold text-foreground tracking-tight">{value}</p>
        <p className="text-xs text-muted-foreground mt-0.5">{label}</p>
      </CardContent>
    </Card>
  );
}
