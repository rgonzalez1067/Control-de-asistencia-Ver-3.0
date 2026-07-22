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
import { toast } from "sonner";
import {
  Search, Plus, MoreVertical, Pencil, Trash2, KeyRound, Upload,
  Download, ShieldCheck, BadgeCheck, CircleUserRound, Image as ImageIcon, UserCircle2,
} from "lucide-react";

const ROLE_LABEL = {
  admin: { label: "Admin", cls: "bg-primary text-primary-foreground" },
  supervisor: { label: "Supervisor", cls: "bg-fuchsia-600 text-white" },
  employee: { label: "Empleado", cls: "bg-emerald-600 text-white" },
};

const EMPTY_USER = {
  email: "", name: "", cedula: "", role: "employee", position: "",
  department_id: "", site_id: "", supervisor_id: "", schedule_id: "", password: "",
};

export default function UsersPage() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [roleFilter, setRoleFilter] = useState("all");
  const [departments, setDepartments] = useState([]);
  const [sites, setSites] = useState([]);
  const [schedules, setSchedules] = useState([]);
  const [editing, setEditing] = useState(null);      // {mode:'create'|'edit', form}
  const [deleteTarget, setDeleteTarget] = useState(null);
  const [resetTarget, setResetTarget] = useState(null);
  const [importing, setImporting] = useState(false);
  const [photoTarget, setPhotoTarget] = useState(null); // {user_id, name, selfie_base64, loading}
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
      if (!needle) return true;
      return (
        (u.name || "").toLowerCase().includes(needle) ||
        (u.email || "").toLowerCase().includes(needle) ||
        (u.cedula || "").toLowerCase().includes(needle)
      );
    });
  }, [users, q, roleFilter]);

  async function saveUser(form) {
    try {
      // sanea "" -> undefined en selects opcionales
      const payload = { ...form };
      ["department_id", "site_id", "supervisor_id", "schedule_id", "position", "cedula"].forEach(
        (k) => { if (!payload[k]) delete payload[k]; }
      );
      if (editing.mode === "create") {
        if (!payload.password) payload.password = Math.random().toString(36).slice(2, 10) + "A1";
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

  async function handleImport(file) {
    if (!file) return;
    setImporting(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/users/import", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success(`Importación: ${data.created} creados · ${data.skipped} omitidos${data.errors?.length ? ` · ${data.errors.length} errores` : ""}`);
      if (data.errors?.length) {
        console.warn("Errores de importación:", data.errors);
      }
      loadAll();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally {
      setImporting(false);
      if (fileRef.current) fileRef.current.value = "";
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

  function downloadTemplate() {
    const url = `${API}/users/import/template`;
    // el endpoint requiere Bearer — hacemos fetch autenticado y descargamos
    fetch(url, { headers: { Authorization: `Bearer ${getToken()}` } })
      .then((r) => r.blob())
      .then((blob) => {
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "users_template.csv";
        a.click();
      })
      .catch((e) => toast.error(e.message));
  }

  return (
    <div className="p-4 sm:p-8 max-w-7xl mx-auto space-y-6" data-testid="users-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <Badge variant="secondary" className="rounded-full mb-3">Gestión</Badge>
          <h1 className="text-3xl sm:text-4xl font-bold text-primary flex items-center gap-2">
            Empleados
            <span className="text-xl font-normal text-muted-foreground">·</span>
            <span className="text-xl font-normal text-muted-foreground">{users.length}</span>
          </h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Crea, edita y organiza a tu equipo. Puedes importar por CSV para cargas masivas.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            className="rounded-full"
            onClick={downloadTemplate}
            data-testid="users-template-btn"
          >
            <Download className="h-4 w-4 mr-1.5" /> Plantilla CSV
          </Button>
          <input
            ref={fileRef}
            type="file"
            accept=".csv,text/csv"
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
            <Upload className="h-4 w-4 mr-1.5" /> {importing ? "Importando…" : "Importar CSV"}
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

      <Card className="border-border/70 bg-white/80 backdrop-blur">
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
            <SelectTrigger className="w-[180px] h-10" data-testid="users-role-filter">
              <SelectValue placeholder="Rol" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos los roles</SelectItem>
              <SelectItem value="admin">Admin</SelectItem>
              <SelectItem value="supervisor">Supervisor</SelectItem>
              <SelectItem value="employee">Empleado</SelectItem>
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground ml-auto">
            Mostrando {filtered.length} de {users.length}
          </p>
        </CardContent>
      </Card>

      <Card className="border-border/70 bg-white/80 backdrop-blur overflow-hidden">
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
                const roleMeta = ROLE_LABEL[u.role] || { label: u.role, cls: "bg-muted text-foreground" };
                return (
                  <TableRow key={u.user_id} data-testid={`user-row-${u.user_id}`}>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <button
                          onClick={() => openPhoto(u)}
                          data-testid={`user-photo-${u.user_id}`}
                          className="relative h-9 w-9 rounded-full bg-primary/10 text-primary grid place-items-center text-xs font-semibold overflow-hidden hover:ring-2 hover:ring-primary/40 transition"
                          title={u.onboarded ? "Ver foto registrada" : "Sin foto — click para ver"}
                        >
                          {(u.name || "?").split(" ").slice(0, 2).map((p) => p[0]).join("")}
                          {u.onboarded && (
                            <span className="absolute bottom-0 right-0 h-2.5 w-2.5 rounded-full bg-emerald-500 border-2 border-white" />
                          )}
                        </button>
                        <div>
                          <p className="text-sm font-medium text-primary leading-tight">{u.name}</p>
                          <p className="text-xs text-muted-foreground leading-tight">{u.email}</p>
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="text-sm">{u.cedula || <span className="text-muted-foreground/60">—</span>}</TableCell>
                    <TableCell>
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium ${roleMeta.cls}`}>
                        {u.role === "admin" ? <ShieldCheck className="h-3 w-3" /> : u.role === "supervisor" ? <BadgeCheck className="h-3 w-3" /> : <CircleUserRound className="h-3 w-3" />}
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
                          <DropdownMenuItem onClick={() => setEditing({ mode: "edit", form: { ...EMPTY_USER, ...u } })}>
                            <Pencil className="h-4 w-4 mr-2" /> Editar
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => setResetTarget(u)}>
                            <KeyRound className="h-4 w-4 mr-2" /> Resetear contraseña
                          </DropdownMenuItem>
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
                <SelectItem value="admin">Admin</SelectItem>
                <SelectItem value="supervisor">Supervisor</SelectItem>
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
                {supervisors.filter((s) => s.user_id !== form.user_id).map((s) => (
                  <SelectItem key={s.user_id} value={s.user_id}>{s.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {!isEdit && (
            <div className="space-y-1.5 sm:col-span-2">
              <Label>Contraseña temporal <span className="text-muted-foreground/60">(opcional)</span></Label>
              <Input {...bind("password")} type="text" placeholder="Se genera automáticamente si se deja vacío" data-testid="user-form-password" />
            </div>
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
