import { useEffect, useMemo, useRef, useState } from "react";
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
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuTrigger, DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  Tabs, TabsContent, TabsList, TabsTrigger,
} from "@/components/ui/tabs";
import { toast } from "sonner";
import {
  Search, Plus, MoreVertical, Pencil, Trash2, KeyRound, Upload,
  Download, ShieldCheck, BadgeCheck, CircleUserRound, Image as ImageIcon, UserCircle2, Camera,
  FileSpreadsheet, AlertTriangle, CheckCircle2, XCircle, ArrowRight, RefreshCw, ClipboardList,
  ImageOff,
} from "lucide-react";
import SelfieCaptureDialog from "@/components/SelfieCaptureDialog";
import SetPinDialog from "@/components/SetPinDialog";

const ROLE_LABEL = {
  admin:       { label: "Administrador", cls: "bg-primary text-primary-foreground" },
  director:    { label: "Director",      cls: "bg-indigo-600 text-white" },
  gerente:     { label: "Gerente",       cls: "bg-fuchsia-600 text-white" },
  coordinador: { label: "Coordinador",   cls: "bg-sky-600 text-white" },
  employee:    { label: "Empleado",      cls: "bg-emerald-600 text-white" },
};

// Mapea variantes de rol (ES/EN, case-insensitive) a las claves canónicas.
const ROLE_ALIASES = {
  admin: "admin", administrador: "admin", administradora: "admin",
  director: "director", directora: "director",
  gerente: "gerente",
  coordinador: "coordinador", coordinadora: "coordinador",
  // Rol legacy: supervisor → coordinador (backend migra la BD).
  supervisor: "coordinador", supervisora: "coordinador",
  employee: "employee", empleado: "employee", empleada: "employee", user: "employee",
};
// Roles que califican como "líder" — pueden ser supervisor de otros usuarios
// y NO son elegibles como target del filtro "sólo empleados".
const LEADER_ROLES = ["admin", "director", "gerente", "coordinador"];

function normalizeRole(v) {
  if (!v) return "employee";
  return ROLE_ALIASES[String(v).trim().toLowerCase()] || "employee";
}
function roleBadge(v) {
  return ROLE_LABEL[normalizeRole(v)];
}

const EMPTY_USER = {
  email: "", name: "", cedula: "", role: "employee", position: "",
  department_id: "", site_id: "", supervisor_id: "", schedule_id: "",
  password: "", pin: "",
};

export default function UsersPage() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [roleFilter, setRoleFilter] = useState("all");
  const [deptFilter, setDeptFilter] = useState("all");
  const [pendingPhoto, setPendingPhoto] = useState(false);
  const [departments, setDepartments] = useState([]);
  const [sites, setSites] = useState([]);
  const [schedules, setSchedules] = useState([]);
  const [editing, setEditing] = useState(null);      // {mode:'create'|'edit', form}
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [resetTarget, setResetTarget] = useState(null);
  const [importing, setImporting] = useState(false);
  const [importPreview, setImportPreview] = useState(null); // {file, data} — abre diálogo
  const [importReport, setImportReport] = useState(null);   // resultado post-confirmar
  const [photoTarget, setPhotoTarget] = useState(null); // {user_id, name, selfie_base64, loading}
  const [selfieTarget, setSelfieTarget] = useState(null); // {user_id, name} — capture in behalf
  const [selfieSaving, setSelfieSaving] = useState(false);
  const [pinTarget, setPinTarget] = useState(null);       // {user_id, name}
  const fileRef = useRef(null);

  async function loadAll() {
    setLoading(true);
    try {
      const [u, d, s, sc] = await Promise.all([
        api.get("/users"),
        api.get("/departments"),
        api.get("/sites"),
        api.get("/schedules"),
      ]);
      setUsers(u.data);
      setDepartments(d.data);
      setSites(s.data);
      setSchedules(sc.data);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadAll(); }, []);

  const lookup = useMemo(() => ({
    dept: Object.fromEntries(departments.map((x) => [x.department_id, x.name])),
    site: Object.fromEntries(sites.map((x) => [x.site_id, x.name])),
    sched: Object.fromEntries(schedules.map((x) => [x.schedule_id, x.name])),
    user: Object.fromEntries(users.map((x) => [x.user_id, x.name])),
  }), [departments, sites, schedules, users]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return users.filter((u) => {
      if (roleFilter !== "all" && u.role !== roleFilter) return false;
      if (deptFilter !== "all") {
        if (deptFilter === "__none") {
          if (u.department_id) return false;
        } else if (u.department_id !== deptFilter) {
          return false;
        }
      }
      // Empleados pendientes de foto: `has_photo` viene del backend
      // (aggregate en /users). Excluye cuentas kiosk que no capturan selfie.
      if (pendingPhoto) {
        if (u.role === "kiosk") return false;
        if (u.has_photo) return false;
      }
      if (!needle) return true;
      return (
        (u.name || "").toLowerCase().includes(needle) ||
        (u.email || "").toLowerCase().includes(needle) ||
        (u.cedula || "").toLowerCase().includes(needle)
      );
    }).sort((a, b) => (a.name || "").localeCompare(b.name || "", "es", { sensitivity: "base" }));
  }, [users, q, roleFilter, deptFilter, pendingPhoto]);

  const pendingPhotoCount = useMemo(
    () => users.filter((u) => u.role !== "kiosk" && !u.has_photo).length,
    [users],
  );

function generateSecureTempPassword() {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789!@#$";
  const bytes = new Uint8Array(10);
  if (typeof window !== "undefined" && window.crypto) {
    window.crypto.getRandomValues(bytes);
  }
  let res = "A1!";
  for (let i = 0; i < bytes.length; i++) {
    res += chars[bytes[i] % chars.length];
  }
  return res;
}

  async function saveUser(form) {
    try {
      const payload = { ...form };
      // Campos de texto opcionales: si están vacíos, no los enviamos.
      ["position", "cedula", "pin"].forEach(
        (k) => { if (!payload[k]) delete payload[k]; }
      );
      // Campos de referencia: si el usuario eligió "Sin asignar" (""),
      // enviamos `null` explícito para que el backend lo desasigne.
      ["department_id", "site_id", "supervisor_id", "schedule_id"].forEach((k) => {
        if (!payload[k]) payload[k] = null;
      });
      if (editing.mode === "create") {
        if (!payload.password) payload.password = generateSecureTempPassword();
        // En creación, no enviamos nulls (para no romper validaciones).
        ["department_id", "site_id", "supervisor_id", "schedule_id"].forEach((k) => {
          if (payload[k] === null) delete payload[k];
        });
        await api.post("/users", payload);
        toast.success("Empleado creado");
      } else {
        delete payload.password;
        delete payload.email;
        await api.put(`/users/${editing.form.user_id}`, payload);
        toast.success("Empleado actualizado");
      }
      setEditing(null);
      loadAll();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    }
  }

  async function confirmDelete() {
    try {
      await api.delete(`/users/${deleteTarget.user_id}`);
      toast.success("Empleado eliminado");
      setDeleteTarget(null);
      loadAll();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    }
  }

  async function confirmReset(newPass) {
    try {
      await api.post("/auth/reset-password", {
        user_id: resetTarget.user_id,
        new_password: newPass,
      });
      toast.success("Contraseña actualizada");
      setResetTarget(null);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    }
  }

  async function unlockAccount(u) {
    try {
      await api.post(`/users/${u.user_id}/unlock`);
      toast.success(`Cuenta de ${u.name} desbloqueada`);
      loadAll();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    }
  }

  async function handleImport(file) {
    if (!file) return;
    setImporting(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/users/import/preview", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setImportPreview({ file, data });
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally {
      setImporting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  async function confirmImport() {
    if (!importPreview?.file) return;
    setImporting(true);
    try {
      const fd = new FormData();
      fd.append("file", importPreview.file);
      const { data } = await api.post("/users/import", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setImportPreview(null);
      setImportReport(data);
      toast.success(`Importación completada · ${data.created} creados · ${data.updated} actualizados${data.errors?.length ? ` · ${data.errors.length} errores` : ""}`);
      loadAll();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally {
      setImporting(false);
    }
  }

  async function openPhoto(u) {
    setPhotoTarget({ user_id: u.user_id, name: u.name, loading: true, selfie_base64: null });
    try {
      const { data } = await api.get(`/users/${u.user_id}/photo`);
      setPhotoTarget({ ...data, loading: false });
    } catch (e) {
      setPhotoTarget({ user_id: u.user_id, name: u.name, loading: false, selfie_base64: null });
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    }
  }

  async function saveAdminSelfie(dataUrl, descriptor) {
    if (!selfieTarget) return;
    setSelfieSaving(true);
    try {
      const payload = { selfie_base64: dataUrl };
      if (Array.isArray(descriptor) && descriptor.length > 0) {
        payload.face_descriptor = descriptor;
      }
      await api.post(`/users/${selfieTarget.user_id}/selfie`, payload);
      toast.success(
        Array.isArray(descriptor) && descriptor.length > 0
          ? `Rostro registrado para ${selfieTarget.name.split(" ")[0]}`
          : `Foto guardada, pero el rostro no fue detectado. Repite la captura para habilitar el kiosco.`
      );
      setSelfieTarget(null);
      loadAll();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally {
      setSelfieSaving(false);
    }
  }

  function downloadTemplate() {
    const url = `${API}/users/import/template`;
    // el endpoint requiere Bearer — hacemos fetch autenticado y descargamos
    fetch(url, { headers: { Authorization: `Bearer ${getToken()}` } })
      .then((r) => r.blob())
      .then((blob) => {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "users_template.xlsx";
        a.click();
      })
      .catch((e) => toast.error(e.message));
  }

  return (
    <div className="p-4 sm:p-8 max-w-7xl mx-auto space-y-6" data-testid="users-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <Badge variant="secondary" className="rounded-full mb-3">Gestión</Badge>
          <h1 className="text-3xl sm:text-4xl font-bold text-foreground flex items-center gap-2">
            Empleados
            <span className="text-xl font-normal text-muted-foreground">·</span>
            <span className="text-xl font-normal text-muted-foreground">{users.length}</span>
          </h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Crea, edita y organiza a tu equipo. Puedes importar desde Excel para cargas y actualizaciones masivas.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            className="rounded-full"
            onClick={downloadTemplate}
            data-testid="users-template-btn"
          >
            <Download className="h-4 w-4 mr-1.5" /> Plantilla Excel
          </Button>
          <input
            ref={fileRef}
            type="file"
            accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            className="hidden"
            data-testid="users-import-input"
            onChange={(e) => handleImport(e.target.files?.[0])}
          />
          <Button
            variant="outline"
            className="rounded-full"
            disabled={importing}
            onClick={() => fileRef.current?.click()}
            data-testid="users-import-btn"
          >
            <Upload className="h-4 w-4 mr-1.5" /> {importing ? "Importando…" : "Importar Excel"}
          </Button>
          <Button
            className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground shadow-lg shadow-primary/20"
            onClick={() => setEditing({ mode: "create", form: { ...EMPTY_USER } })}
            data-testid="users-create-btn"
          >
            <Plus className="h-4 w-4 mr-1.5" /> Nuevo empleado
          </Button>
        </div>
      </div>

      <Card className="border-border/70 bg-card/80 backdrop-blur">
        <CardContent className="p-3 sm:p-4 flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[220px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Buscar por nombre, correo o cédula…"
              className="pl-9 h-10 border-border/60"
              data-testid="users-search-input"
            />
          </div>
          <Select value={roleFilter} onValueChange={setRoleFilter}>
            <SelectTrigger className="w-[160px] h-10" data-testid="users-role-filter">
              <SelectValue placeholder="Rol" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos los roles</SelectItem>
              <SelectItem value="admin">Administrador</SelectItem>
              <SelectItem value="director">Director</SelectItem>
              <SelectItem value="gerente">Gerente</SelectItem>
              <SelectItem value="coordinador">Coordinador</SelectItem>
              <SelectItem value="employee">Empleado</SelectItem>
            </SelectContent>
          </Select>
          <Select value={deptFilter} onValueChange={setDeptFilter}>
            <SelectTrigger className="w-[200px] h-10" data-testid="users-dept-filter">
              <SelectValue placeholder="Departamento" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos los departamentos</SelectItem>
              <SelectItem value="__none">Sin departamento</SelectItem>
              {departments.map((d) => (
                <SelectItem key={d.department_id} value={d.department_id}>{d.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            type="button"
            variant={pendingPhoto ? "default" : "outline"}
            onClick={() => setPendingPhoto((v) => !v)}
            data-testid="users-pending-photo-btn"
            className={`h-10 rounded-full ${pendingPhoto ? "bg-amber-500 hover:bg-amber-500/90 text-white" : ""}`}
            title={pendingPhoto ? "Mostrando solo empleados sin foto" : "Mostrar empleados pendientes de registrar foto"}
          >
            <ImageOff className="h-4 w-4 mr-1.5" />
            Pendientes de foto
            <span className="ml-2 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-white/25 px-1.5 text-[11px] font-semibold tabular-nums"
              data-testid="users-pending-photo-count">
              {pendingPhotoCount}
            </span>
          </Button>
          <p className="text-xs text-muted-foreground ml-auto">
            Mostrando {filtered.length} de {users.length}
          </p>
        </CardContent>
      </Card>

      <Card className="border-border/70 bg-card/80 backdrop-blur overflow-hidden">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40">
                <TableHead className="w-[280px]">Empleado</TableHead>
                <TableHead>Cédula</TableHead>
                <TableHead>Rol</TableHead>
                <TableHead>Departamento</TableHead>
                <TableHead>Sede</TableHead>
                <TableHead>Horario</TableHead>
                <TableHead>Rostro</TableHead>
                <TableHead className="w-[60px] text-right">·</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody data-testid="users-table-body">
              {loading && (
                <TableRow><TableCell colSpan={8} className="text-center text-muted-foreground py-10">Cargando…</TableCell></TableRow>
              )}
              {!loading && filtered.length === 0 && (
                <TableRow><TableCell colSpan={8} className="text-center text-muted-foreground py-10">Sin resultados</TableCell></TableRow>
              )}
              {!loading && filtered.map((u) => {
                const roleMeta = roleBadge(u.role) || { label: u.role, cls: "bg-muted text-foreground" };
                return (
                  <TableRow key={u.user_id} data-testid={`user-row-${u.user_id}`}>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <button
                          onClick={() => openPhoto(u)}
                          data-testid={`user-photo-${u.user_id}`}
                          className="relative h-9 w-9 rounded-full bg-primary/10 text-foreground grid place-items-center text-xs font-semibold overflow-hidden hover:ring-2 hover:ring-primary/40 transition"
                          title={u.onboarded ? "Ver foto registrada" : "Sin foto — click para ver"}
                        >
                          {(u.name || "?").split(" ").slice(0, 2).map((p) => p[0]).join("")}
                          {u.onboarded && (
                            <span className="absolute bottom-0 right-0 h-2.5 w-2.5 rounded-full bg-emerald-500 border-2 border-white" />
                          )}
                        </button>
                        <div>
                          <p className="text-sm font-medium text-foreground leading-tight">{u.name}</p>
                          <p className="text-xs text-muted-foreground leading-tight">{u.email}</p>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="text-sm">{u.cedula || <span className="text-muted-foreground/60">—</span>}</TableCell>
                    <TableCell>
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium ${roleMeta.cls}`}>
                        {u.role === "admin" ? <ShieldCheck className="h-3 w-3" /> : LEADER_ROLES.includes(u.role) ? <BadgeCheck className="h-3 w-3" /> : <CircleUserRound className="h-3 w-3" />}
                        {roleMeta.label}
                      </span>
                    </TableCell>
                    <TableCell className="text-sm">{lookup.dept[u.department_id] || <span className="text-muted-foreground/60">—</span>}</TableCell>
                    <TableCell className="text-sm">{lookup.site[u.site_id] || <span className="text-muted-foreground/60">—</span>}</TableCell>
                    <TableCell className="text-sm">{lookup.sched[u.schedule_id] || <span className="text-muted-foreground/60">—</span>}</TableCell>
                    <TableCell>
                      {u.onboarded ? (
                        <span className="inline-flex items-center gap-1 text-[11px] text-emerald-700">
                          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> registrado
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[11px] text-muted-foreground">
                          <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40" /> pendiente
                        </span>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" data-testid={`user-actions-${u.user_id}`}>
                            <MoreVertical className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => openPhoto(u)}>
                            <ImageIcon className="h-4 w-4 mr-2" /> Ver foto
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => setSelfieTarget({ user_id: u.user_id, name: u.name })} data-testid={`user-selfie-${u.user_id}`}>
                            <Camera className="h-4 w-4 mr-2" /> {u.onboarded ? "Reemplazar rostro" : "Registrar rostro"}
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => setPinTarget({ user_id: u.user_id, name: u.name })} data-testid={`user-pin-${u.user_id}`}>
                            <KeyRound className="h-4 w-4 mr-2" /> Definir PIN
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem onClick={() => setEditing({ mode: "edit", form: { ...EMPTY_USER, ...u } })}>
                            <Pencil className="h-4 w-4 mr-2" /> Editar
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => setResetTarget(u)}>
                            <KeyRound className="h-4 w-4 mr-2" /> Resetear contraseña
                          </DropdownMenuItem>
                          {u.locked_until && new Date(u.locked_until) > new Date() ? (
                            <DropdownMenuItem onClick={() => unlockAccount(u)} className="text-amber-700 focus:text-amber-800"
                                              data-testid={`user-unlock-${u.user_id}`}>
                              <KeyRound className="h-4 w-4 mr-2" /> Desbloquear cuenta
                            </DropdownMenuItem>
                          ) : null}
                          <DropdownMenuSeparator />
                          <DropdownMenuItem className="text-destructive focus:text-destructive" onClick={() => setDeleteTarget(u)}>
                            <Trash2 className="h-4 w-4 mr-2" /> Eliminar
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      </Card>

      <UserFormDialog
        state={editing}
        onCancel={() => setEditing(null)}
        onSave={saveUser}
        departments={departments}
        sites={sites}
        schedules={schedules}
        supervisors={users.filter((u) => u.role !== "employee")}
      />

      <ResetPasswordDialog
        target={resetTarget}
        onCancel={() => setResetTarget(null)}
        onConfirm={confirmReset}
      />

      <AlertDialog open={!!deleteTarget} onOpenChange={(v) => !v && setDeleteTarget(null)}>
        <AlertDialogContent data-testid="user-delete-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Eliminar empleado</AlertDialogTitle>
            <AlertDialogDescription>
              ¿Seguro que quieres eliminar a <b>{deleteTarget?.name}</b>? Esta acción no se puede deshacer.
              Sus registros de asistencia se conservarán en los reportes.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete} className="bg-destructive hover:bg-destructive/90" data-testid="user-delete-confirm">
              Eliminar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Dialog open={!!photoTarget} onOpenChange={(v) => !v && setPhotoTarget(null)}>
        <DialogContent className="max-w-md" data-testid="user-photo-dialog">
          <DialogHeader>
            <DialogTitle>Foto registrada</DialogTitle>
            <DialogDescription>{photoTarget?.name}</DialogDescription>
          </DialogHeader>
          <div className="aspect-square w-full rounded-2xl overflow-hidden bg-muted grid place-items-center">
            {photoTarget?.loading ? (
              <p className="text-sm text-muted-foreground">Cargando…</p>
            ) : photoTarget?.selfie_base64 ? (
              <img src={photoTarget.selfie_base64} alt={photoTarget.name}
                   className="h-full w-full object-cover" data-testid="user-photo-img" />
            ) : (
              <div className="text-center">
                <UserCircle2 className="h-16 w-16 text-muted-foreground/60 mx-auto" />
                <p className="text-sm text-muted-foreground mt-2">Este empleado no tiene rostro registrado.</p>
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <SelfieCaptureDialog
        open={!!selfieTarget}
        onOpenChange={(v) => !v && setSelfieTarget(null)}
        title={`Rostro de ${selfieTarget?.name || ""}`}
        description="El empleado debe mirar directo a la cámara con buena luz."
        onConfirm={saveAdminSelfie}
        saving={selfieSaving}
      />

      <SetPinDialog
        open={!!pinTarget}
        onOpenChange={(v) => !v && setPinTarget(null)}
        userId={pinTarget?.user_id}
        userName={pinTarget?.name}
      />

      <ImportPreviewDialog
        state={importPreview}
        loading={importing}
        onCancel={() => setImportPreview(null)}
        onConfirm={confirmImport}
      />

      <ImportReportDialog
        report={importReport}
        onClose={() => setImportReport(null)}
      />
    </div>
  );
}

/* --------- User create/edit dialog --------- */
function UserFormDialog({ state, onCancel, onSave, departments, sites, schedules, supervisors }) {
  const [form, setForm] = useState(state?.form || EMPTY_USER);
  useEffect(() => { setForm(state?.form || EMPTY_USER); }, [state]);
  const open = !!state;
  const isEdit = state?.mode === "edit";
  const bind = (k) => ({
    value: form[k] ?? "",
    onChange: (e) => setForm((f) => ({ ...f, [k]: e.target.value })),
  });
  const bindSel = (k) => ({
    value: form[k] || "__none",
    onValueChange: (v) => setForm((f) => ({ ...f, [k]: v === "__none" ? "" : v })),
  });

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onCancel()}>
      <DialogContent className="max-w-2xl" data-testid="user-form-dialog">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Editar empleado" : "Nuevo empleado"}</DialogTitle>
          <DialogDescription>
            {isEdit ? "Actualiza los datos y guarda para aplicar cambios." : "Se enviará una contraseña temporal si no defines una."}
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div className="space-y-1.5 sm:col-span-2">
            <Label>Nombre completo</Label>
            <Input {...bind("name")} placeholder="Ej. María Rodríguez" data-testid="user-form-name" />
          </div>
          <div className="space-y-1.5">
            <Label>Correo</Label>
            <Input {...bind("email")} type="email" disabled={isEdit} placeholder="maria@empresa.com" data-testid="user-form-email" />
          </div>
          <div className="space-y-1.5">
            <Label>Cédula</Label>
            <Input {...bind("cedula")} placeholder="V-12345678" data-testid="user-form-cedula" />
          </div>
          <div className="space-y-1.5">
            <Label>Rol</Label>
            <Select value={form.role} onValueChange={(v) => setForm((f) => ({ ...f, role: v }))}>
              <SelectTrigger data-testid="user-form-role"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="admin">Administrador</SelectItem>
                <SelectItem value="director">Director</SelectItem>
                <SelectItem value="gerente">Gerente</SelectItem>
                <SelectItem value="coordinador">Coordinador</SelectItem>
                <SelectItem value="employee">Empleado</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Cargo</Label>
            <Input {...bind("position")} placeholder="Ej. Analista de Ventas" data-testid="user-form-position" />
          </div>
          <div className="space-y-1.5">
            <Label>Departamento</Label>
            <Select {...bindSel("department_id")}>
              <SelectTrigger data-testid="user-form-dept"><SelectValue placeholder="—" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="__none">Sin asignar</SelectItem>
                {departments.map((d) => (
                  <SelectItem key={d.department_id} value={d.department_id}>{d.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Sede</Label>
            <Select {...bindSel("site_id")}>
              <SelectTrigger data-testid="user-form-site"><SelectValue placeholder="—" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="__none">Sin asignar</SelectItem>
                {sites.map((s) => (
                  <SelectItem key={s.site_id} value={s.site_id}>{s.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Horario</Label>
            <Select {...bindSel("schedule_id")}>
              <SelectTrigger data-testid="user-form-schedule"><SelectValue placeholder="—" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="__none">Sin asignar</SelectItem>
                {schedules.map((s) => (
                  <SelectItem key={s.schedule_id} value={s.schedule_id}>{s.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label>Supervisor</Label>
            <Select {...bindSel("supervisor_id")}>
              <SelectTrigger data-testid="user-form-supervisor"><SelectValue placeholder="—" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="__none">Sin supervisor</SelectItem>
                {[...supervisors.filter((s) => s.user_id !== form.user_id)]
                  .sort((a, b) => (a.name || "").localeCompare(b.name || "", "es", { sensitivity: "base" }))
                  .map((s) => (
                    <SelectItem key={s.user_id} value={s.user_id}>{s.name}</SelectItem>
                  ))}
              </SelectContent>
            </Select>
          </div>
          {!isEdit && (
            <>
              <div className="space-y-1.5">
                <Label>Contraseña temporal <span className="text-muted-foreground/60">(opcional)</span></Label>
                <Input {...bind("password")} type="text" placeholder="Se genera automáticamente si se deja vacío" data-testid="user-form-password" />
              </div>
              <div className="space-y-1.5">
                <Label>PIN kiosco <span className="text-muted-foreground/60">(opcional)</span></Label>
                <Input
                  value={form.pin || ""}
                  onChange={(e) => setForm((f) => ({ ...f, pin: e.target.value.replace(/\D/g, "").slice(0, 8) }))}
                  inputMode="numeric"
                  placeholder="4-8 dígitos · el empleado podrá cambiarlo"
                  data-testid="user-form-pin"
                />
              </div>
            </>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onCancel} data-testid="user-form-cancel">Cancelar</Button>
          <Button
            onClick={() => onSave(form)}
            disabled={!form.email || !form.name}
            className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground"
            data-testid="user-form-save"
          >
            {isEdit ? "Guardar cambios" : "Crear empleado"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* --------- Reset password dialog --------- */
function ResetPasswordDialog({ target, onCancel, onConfirm }) {
  const [pw, setPw] = useState("");
  useEffect(() => { setPw(""); }, [target]);

  return (
    <Dialog open={!!target} onOpenChange={(v) => !v && onCancel()}>
      <DialogContent className="max-w-md" data-testid="user-reset-dialog">
        <DialogHeader>
          <DialogTitle>Resetear contraseña</DialogTitle>
          <DialogDescription>
            Define una nueva contraseña para <b>{target?.name}</b>. Comunícasela por un canal seguro.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <Label>Nueva contraseña</Label>
          <Input value={pw} onChange={(e) => setPw(e.target.value)} type="text" placeholder="mínimo 6 caracteres" data-testid="user-reset-input" />
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onCancel}>Cancelar</Button>
          <Button onClick={() => onConfirm(pw)} disabled={pw.length < 6} className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground" data-testid="user-reset-confirm">
            Actualizar contraseña
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* --------- Import preview dialog (2-step confirmation) --------- */
function ImportPreviewDialog({ state, loading, onCancel, onConfirm }) {
  const open = !!state;
  const data = state?.data;
  const create = data?.to_create || [];
  const update = data?.to_update || [];
  const errors = data?.errors || [];
  const withDiff = update.filter((u) => u.changes && Object.keys(u.changes).length > 0);
  const forceOnly = update.filter((u) => !u.changes || Object.keys(u.changes).length === 0);
  const affected = create.length + update.length;

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onCancel()}>
      <DialogContent className="max-w-3xl" data-testid="import-preview-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileSpreadsheet className="h-5 w-5 text-primary" /> Vista previa de la importación
          </DialogTitle>
          <DialogDescription>
            Se escribirán los datos <b>exactamente como están en el archivo</b>. Los campos vacíos no sobrescriben datos existentes.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-3 gap-2 py-2">
          <SummaryPill icon={Plus} label="Nuevos" value={create.length} tone="emerald" testid="preview-count-create" />
          <SummaryPill icon={Pencil} label="A actualizar" value={update.length} tone="amber" testid="preview-count-update" />
          <SummaryPill icon={AlertTriangle} label="Errores" value={errors.length} tone="red" testid="preview-count-errors" />
        </div>

        <Tabs defaultValue="create" className="w-full">
          <TabsList className="grid grid-cols-3 h-9 rounded-full">
            <TabsTrigger value="create" data-testid="preview-tab-create" className="rounded-full text-xs">Nuevos ({create.length})</TabsTrigger>
            <TabsTrigger value="update" data-testid="preview-tab-update" className="rounded-full text-xs">Actualizar ({update.length})</TabsTrigger>
            <TabsTrigger value="errors" data-testid="preview-tab-errors" className="rounded-full text-xs">Errores ({errors.length})</TabsTrigger>
          </TabsList>

          <TabsContent value="create" className="mt-3 max-h-72 overflow-y-auto">
            {create.length === 0 ? <EmptyRow label="No hay empleados nuevos" /> : (
              <Table>
                <TableHeader><TableRow>
                  <TableHead className="w-14">#</TableHead><TableHead>Email</TableHead>
                  <TableHead>Nombre</TableHead><TableHead>Rol</TableHead>
                  <TableHead>Posición</TableHead><TableHead>PIN</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {create.map((r) => (
                    <TableRow key={`c-${r.row}`}>
                      <TableCell className="text-muted-foreground text-xs">{r.row}</TableCell>
                      <TableCell className="text-xs">{r.email}</TableCell>
                      <TableCell className="text-xs font-medium">{r.name}</TableCell>
                      <TableCell className="text-xs">{r.role}</TableCell>
                      <TableCell className="text-xs">{r.position || "—"}</TableCell>
                      <TableCell className="text-xs font-mono">{r.kiosk_pin || "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </TabsContent>

          <TabsContent value="update" className="mt-3 max-h-72 overflow-y-auto space-y-2">
            {update.length === 0 ? <EmptyRow label="No hay actualizaciones" /> : (
              <>
                {withDiff.length > 0 && (
                  <div className="space-y-2">
                    <p className="text-[10px] uppercase tracking-wide text-amber-600 font-medium">
                      Con cambios detectados ({withDiff.length})
                    </p>
                    {withDiff.map((r) => (
                      <div key={`u-${r.row}`} className="rounded-lg border border-amber-200 bg-amber-50/50 p-2.5 text-xs" data-testid={`preview-update-row-${r.row}`}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="font-medium">{r.name} <span className="text-muted-foreground">· {r.email}</span></span>
                          <span className="text-muted-foreground">fila {r.row}</span>
                        </div>
                        <div className="space-y-0.5">
                          {Object.entries(r.changes).map(([k, v]) => (
                            <div key={k} className="flex items-center gap-1.5">
                              <span className="text-muted-foreground min-w-[100px]">{k}</span>
                              <span className="text-red-600 line-through">{String(v.from || "—")}</span>
                              <ArrowRight className="h-3 w-3 text-muted-foreground" />
                              <span className="text-emerald-700 font-medium">{String(v.to)}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {forceOnly.length > 0 && (
                  <div className="space-y-1 mt-3">
                    <p className="text-[10px] uppercase tracking-wide text-slate-500 font-medium">
                      Reescritura sin diferencias visibles ({forceOnly.length})
                    </p>
                    <ul className="text-xs space-y-0.5 max-h-40 overflow-y-auto rounded-lg border bg-slate-50/50 p-2">
                      {forceOnly.map((r) => (
                        <li key={`f-${r.row}`} className="flex items-center gap-2">
                          <RefreshCw className="h-3 w-3 text-slate-400" />
                          <span className="text-muted-foreground">Fila {r.row}</span>
                          <span>·</span>
                          <span className="font-medium">{r.name}</span>
                          <span className="text-muted-foreground">· {r.email}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </>
            )}
          </TabsContent>

          <TabsContent value="errors" className="mt-3 max-h-72 overflow-y-auto">
            {errors.length === 0 ? <EmptyRow label="No se encontraron errores" tone="emerald" /> : (
              <ul className="space-y-1.5">
                {errors.map((e, i) => (
                  <li key={i} className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-2 text-xs">
                    <XCircle className="h-4 w-4 text-red-600 mt-0.5 shrink-0" />
                    <div>
                      <span className="font-medium">Fila {e.row}</span>
                      {e.email && <span className="text-muted-foreground"> · {e.email}</span>}
                      <p className="text-red-700 mt-0.5">{e.reason}</p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </TabsContent>
        </Tabs>

        <DialogFooter>
          <Button variant="outline" onClick={onCancel} disabled={loading} className="rounded-full" data-testid="import-cancel-btn">
            Cancelar
          </Button>
          <Button
            onClick={onConfirm}
            disabled={loading || affected === 0}
            className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground"
            data-testid="import-confirm-btn"
          >
            <CheckCircle2 className="h-4 w-4 mr-1.5" />
            {loading ? "Aplicando…" : `Confirmar importación (${affected})`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SummaryPill({ icon: Icon, label, value, tone, testid }) {
  const tones = {
    emerald: "bg-emerald-50 text-emerald-700 border-emerald-200",
    amber:   "bg-amber-50 text-amber-700 border-amber-200",
    slate:   "bg-slate-50 text-slate-700 border-slate-200",
    red:     "bg-red-50 text-red-700 border-red-200",
  };
  return (
    <div className={"rounded-xl border px-3 py-2 " + tones[tone]} data-testid={testid}>
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide">
        <Icon className="h-3.5 w-3.5" /> {label}
      </div>
      <div className="text-2xl font-bold mt-0.5">{value}</div>
    </div>
  );
}

function EmptyRow({ label, tone }) {
  return (
    <div className={"text-center text-xs py-6 " + (tone === "emerald" ? "text-emerald-600" : "text-muted-foreground")}>
      {label}
    </div>
  );
}

/* --------- Import report dialog (after commit) --------- */
function ImportReportDialog({ report, onClose }) {
  const open = !!report;
  if (!report) return null;
  const hasErrors = (report.errors || []).length > 0;

  function downloadReport() {
    const lines = [];
    lines.push(`Importación de empleados — ${new Date().toLocaleString("es-VE", { timeZone: "America/Caracas" })}`);
    lines.push(`Creados: ${report.created}  ·  Actualizados: ${report.updated}  ·  Errores: ${(report.errors || []).length}`);
    lines.push("");
    if ((report.created_emails || []).length) {
      lines.push("=== NUEVOS ===");
      (report.created_emails || []).forEach((e) => lines.push(`+ ${e}`));
      lines.push("");
    }
    if ((report.updated_emails || []).length) {
      lines.push("=== ACTUALIZADOS ===");
      (report.updated_emails || []).forEach((e) => lines.push(`~ ${e}`));
      lines.push("");
    }
    if (hasErrors) {
      lines.push("=== ERRORES ===");
      (report.errors || []).forEach((e) => lines.push(`✗ Fila ${e.row}${e.email ? " (" + e.email + ")" : ""}: ${e.reason}`));
    }
    const blob = new Blob([lines.join("\n")], { type: "text/plain;charset=utf-8" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `import_report_${Date.now()}.txt`;
    a.click();
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-2xl" data-testid="import-report-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {hasErrors
              ? <AlertTriangle className="h-5 w-5 text-amber-500" />
              : <CheckCircle2 className="h-5 w-5 text-emerald-600" />}
            Reporte de importación
          </DialogTitle>
          <DialogDescription>Resumen de los cambios aplicados en la base de datos.</DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-3 gap-2">
          <SummaryPill icon={Plus} label="Creados" value={report.created} tone="emerald" testid="report-created" />
          <SummaryPill icon={Pencil} label="Actualizados" value={report.updated} tone="amber" testid="report-updated" />
          <SummaryPill icon={AlertTriangle} label="Errores" value={(report.errors || []).length} tone={hasErrors ? "red" : "slate"} testid="report-errors" />
        </div>

        {hasErrors && (
          <div className="max-h-64 overflow-y-auto space-y-1.5 mt-2">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">Errores</p>
            <ul className="space-y-1.5">
              {(report.errors || []).map((e, i) => (
                <li key={i} className="flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 p-2 text-xs">
                  <XCircle className="h-4 w-4 text-red-600 mt-0.5 shrink-0" />
                  <div>
                    <span className="font-medium">Fila {e.row}</span>
                    {e.email && <span className="text-muted-foreground"> · {e.email}</span>}
                    <p className="text-red-700 mt-0.5">{e.reason}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={downloadReport} className="rounded-full" data-testid="import-download-report">
            <Download className="h-4 w-4 mr-1.5" /> Descargar reporte
          </Button>
          <Button onClick={onClose} className="rounded-full" data-testid="import-report-close">Cerrar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

