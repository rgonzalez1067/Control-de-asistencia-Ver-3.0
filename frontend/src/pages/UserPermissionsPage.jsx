import { useEffect, useMemo, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Tabs, TabsContent, TabsList, TabsTrigger,
} from "@/components/ui/tabs";
import { toast } from "sonner";
import {
  Users2, Building, Search, Save, ShieldCheck, Filter, Info,
} from "lucide-react";

const NO_PROFILE_VALUE = "__none";

/**
 * Página: Seguridad → Permisos de usuario.
 *
 * Dos pestañas:
 *  a) "Por empleado" — lista todos los usuarios con su perfil actual y un
 *     dropdown para cambiarlo. Guardado individual (no en masa).
 *  b) "Por departamento" — selecciona un depto y aplica un perfil a TODOS
 *     los usuarios (excluyendo admin/kiosk).
 */
export default function UserPermissionsPage() {
  const [profiles, setProfiles] = useState([]);
  const [users, setUsers] = useState([]);
  const [depts, setDepts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("byUser");

  async function loadAll() {
    setLoading(true);
    try {
      const [{ data: profs }, { data: us }, { data: ds }] = await Promise.all([
        api.get("/access-profiles"),
        api.get("/users"),
        api.get("/departments"),
      ]);
      setProfiles(profs || []);
      setUsers((us || []).filter((u) => u.role !== "kiosk"));
      setDepts(ds || []);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadAll(); }, []);

  return (
    <div className="space-y-6" data-testid="user-permissions-page">
      <header>
        <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">Seguridad</p>
        <h1 className="text-3xl font-bold flex items-center gap-2 mt-1">
          <ShieldCheck className="h-7 w-7 text-primary" /> Permisos de usuario
        </h1>
        <p className="text-sm text-muted-foreground max-w-3xl mt-1">
          Asigna un perfil de acceso a un colaborador específico o a todos los miembros
          de un departamento. Sin un perfil explícito, cada usuario ve las opciones
          por defecto de su rol.
        </p>
      </header>

      <Tabs value={tab} onValueChange={setTab} className="space-y-4">
        <TabsList className="rounded-full h-10 p-1 bg-muted">
          <TabsTrigger value="byUser" className="rounded-full text-xs px-4" data-testid="tab-by-user">
            <Users2 className="h-4 w-4 mr-1.5" /> Por empleado
          </TabsTrigger>
          <TabsTrigger value="byDept" className="rounded-full text-xs px-4" data-testid="tab-by-dept">
            <Building className="h-4 w-4 mr-1.5" /> Por departamento
          </TabsTrigger>
        </TabsList>

        <TabsContent value="byUser">
          <ByUser
            profiles={profiles}
            users={users}
            depts={depts}
            loading={loading}
            onSaved={loadAll}
          />
        </TabsContent>
        <TabsContent value="byDept">
          <ByDepartment
            profiles={profiles}
            depts={depts}
            onDone={loadAll}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function ByUser({ profiles, users, depts, loading, onSaved }) {
  const [search, setSearch] = useState("");
  const [deptFilter, setDeptFilter] = useState("__all");
  const [pending, setPending] = useState({});  // { user_id: profile_id | "" }

  const deptMap = useMemo(() => Object.fromEntries((depts || []).map((d) => [d.department_id, d.name])), [depts]);
  const profMap = useMemo(() => Object.fromEntries(profiles.map((p) => [p.profile_id, p.name])), [profiles]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return users.filter((u) => {
      if (deptFilter !== "__all" && u.department_id !== deptFilter) return false;
      if (!q) return true;
      return (u.name || "").toLowerCase().includes(q)
          || (u.email || "").toLowerCase().includes(q)
          || (u.cedula || "").toLowerCase().includes(q);
    });
  }, [users, search, deptFilter]);

  function changeProfile(userId, profileId) {
    setPending((p) => ({ ...p, [userId]: profileId }));
  }

  async function saveUser(userId) {
    const desired = pending[userId];
    const value = desired === NO_PROFILE_VALUE ? null : desired;
    try {
      await api.put(`/users/${userId}/access-profile`, { profile_id: value });
      toast.success("Perfil actualizado");
      setPending((p) => { const n = { ...p }; delete n[userId]; return n; });
      onSaved();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    }
  }

  return (
    <Card className="rounded-2xl border-muted-foreground/10">
      <CardContent className="p-4 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-[1fr,240px] gap-3">
          <div className="relative">
            <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar por nombre, correo o cédula…"
              className="pl-9 h-10 rounded-xl"
              data-testid="user-perm-search"
            />
          </div>
          <Select value={deptFilter} onValueChange={setDeptFilter}>
            <SelectTrigger className="h-10 rounded-xl" data-testid="user-perm-dept-filter">
              <Filter className="h-3.5 w-3.5 mr-1.5" />
              <SelectValue placeholder="Filtrar por departamento" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__all">Todos los departamentos</SelectItem>
              {(depts || []).map((d) => (
                <SelectItem key={d.department_id} value={d.department_id}>{d.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="overflow-x-auto rounded-xl border">
          <table className="w-full text-sm">
            <thead className="bg-muted/60">
              <tr className="text-left">
                <th className="px-3 py-2 font-semibold text-xs uppercase tracking-wide text-muted-foreground">Empleado</th>
                <th className="px-3 py-2 font-semibold text-xs uppercase tracking-wide text-muted-foreground">Rol · Depto</th>
                <th className="px-3 py-2 font-semibold text-xs uppercase tracking-wide text-muted-foreground">Perfil actual</th>
                <th className="px-3 py-2 font-semibold text-xs uppercase tracking-wide text-muted-foreground text-right">Acción</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {loading && (
                <tr><td colSpan={4} className="px-3 py-6 text-center text-muted-foreground text-xs">Cargando…</td></tr>
              )}
              {!loading && filtered.length === 0 && (
                <tr><td colSpan={4} className="px-3 py-6 text-center text-muted-foreground text-xs">Sin resultados.</td></tr>
              )}
              {filtered.map((u) => {
                const isDirty = pending[u.user_id] !== undefined && pending[u.user_id] !== (u.access_profile_id || NO_PROFILE_VALUE);
                const currentValue = pending[u.user_id] ?? (u.access_profile_id || NO_PROFILE_VALUE);
                return (
                  <tr key={u.user_id} className="hover:bg-muted/30" data-testid={`user-row-${u.user_id}`}>
                    <td className="px-3 py-2.5">
                      <p className="font-medium truncate">{u.name}</p>
                      <p className="text-[11px] text-muted-foreground truncate">{u.email}</p>
                    </td>
                    <td className="px-3 py-2.5">
                      <span className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 bg-muted text-[10px] uppercase tracking-wider text-muted-foreground">
                        {u.role}
                      </span>
                      <p className="text-[11px] text-muted-foreground mt-1 truncate">{deptMap[u.department_id] || "—"}</p>
                    </td>
                    <td className="px-3 py-2.5">
                      <Select value={currentValue} onValueChange={(v) => changeProfile(u.user_id, v)}>
                        <SelectTrigger className="h-9 rounded-xl w-56" data-testid={`user-profile-select-${u.user_id}`}>
                          <SelectValue placeholder="Seleccionar…" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value={NO_PROFILE_VALUE}>— Sin asignar (por rol) —</SelectItem>
                          {profiles.map((p) => (
                            <SelectItem key={p.profile_id} value={p.profile_id}>{p.name}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      {!isDirty && u.access_profile_id && (
                        <p className="text-[11px] text-muted-foreground mt-1">Actual: <b>{profMap[u.access_profile_id] || "—"}</b></p>
                      )}
                    </td>
                    <td className="px-3 py-2.5 text-right">
                      <Button
                        size="sm"
                        disabled={!isDirty}
                        onClick={() => saveUser(u.user_id)}
                        className="rounded-full bg-primary hover:bg-primary/90"
                        data-testid={`user-profile-save-${u.user_id}`}
                      >
                        <Save className="h-3.5 w-3.5 mr-1" /> Guardar
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <p className="text-[11px] text-muted-foreground flex items-center gap-1.5">
          <Info className="h-3.5 w-3.5" />
          Los administradores no se listan aquí; siempre tienen acceso total. Los usuarios Kiosco tampoco (van directo al modo Kiosco).
        </p>
      </CardContent>
    </Card>
  );
}

function ByDepartment({ profiles, depts, onDone }) {
  const [deptId, setDeptId] = useState("");
  const [profileId, setProfileId] = useState(NO_PROFILE_VALUE);
  const [saving, setSaving] = useState(false);

  async function apply() {
    if (!deptId) { toast.error("Selecciona un departamento"); return; }
    setSaving(true);
    try {
      const value = profileId === NO_PROFILE_VALUE ? null : profileId;
      const { data } = await api.post("/access-profiles/assign-department", {
        department_id: deptId,
        profile_id: value,
      });
      toast.success(`Se aplicaron cambios a ${data.modified} de ${data.matched} empleados.`);
      onDone();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally {
      setSaving(false);
    }
  }

  const deptName = (depts || []).find((d) => d.department_id === deptId)?.name;
  const profName = profiles.find((p) => p.profile_id === profileId)?.name;

  return (
    <Card className="rounded-2xl border-muted-foreground/10">
      <CardContent className="p-6 space-y-5 max-w-2xl">
        <div className="rounded-xl bg-muted/30 border-l-2 border-primary p-3 text-xs text-muted-foreground flex items-start gap-2">
          <Info className="h-4 w-4 mt-0.5 shrink-0" />
          <span>
            Esta acción asigna el mismo perfil a <b>todos los empleados</b> del departamento
            elegido (excluye administradores y usuarios Kiosco). Puedes elegir
            &ldquo;Sin asignar&rdquo; para volver a los permisos por defecto del rol.
          </span>
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs">Departamento</Label>
          <Select value={deptId} onValueChange={setDeptId}>
            <SelectTrigger className="h-11 rounded-xl" data-testid="bulk-dept-select">
              <SelectValue placeholder="Selecciona un departamento" />
            </SelectTrigger>
            <SelectContent>
              {(depts || []).map((d) => (
                <SelectItem key={d.department_id} value={d.department_id}>{d.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs">Perfil a aplicar</Label>
          <Select value={profileId} onValueChange={setProfileId}>
            <SelectTrigger className="h-11 rounded-xl" data-testid="bulk-profile-select">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NO_PROFILE_VALUE}>— Sin asignar (por rol) —</SelectItem>
              {profiles.map((p) => (
                <SelectItem key={p.profile_id} value={p.profile_id}>{p.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="pt-2 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <p className="text-xs text-muted-foreground">
            {deptId && (
              <>Se aplicará <b>{profName || "Sin asignar"}</b> a todos los empleados de <b>{deptName}</b>.</>
            )}
          </p>
          <Button
            onClick={apply}
            disabled={!deptId || saving}
            className="rounded-full bg-primary hover:bg-primary/90"
            data-testid="bulk-apply-btn"
          >
            <Save className="h-4 w-4 mr-1.5" /> {saving ? "Aplicando…" : "Aplicar al departamento"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
