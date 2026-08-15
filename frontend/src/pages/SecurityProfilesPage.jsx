import { useEffect, useMemo, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Card, CardContent } from "@/components/ui/card";
import { toast } from "sonner";
import {
  ShieldCheck, Plus, Trash2, Save, Lock, Search, Check, X, Users as UsersIcon,
} from "lucide-react";

/**
 * Página: Seguridad → Creación de Perfiles de Acceso.
 *
 * Layout:
 *  - Columna izquierda: lista de perfiles con un botón "Nuevo perfil".
 *  - Columna derecha: grilla de permisos del perfil seleccionado, agrupada por
 *    sección. Cada permiso es un toggle Activo / Inactivo.
 *  - Los perfiles con `is_system=true` no se pueden borrar; su contenido (nombre,
 *    descripción y toggles) sí se puede editar.
 */
export default function SecurityProfilesPage() {
  const [catalog, setCatalog] = useState([]);     // MENU_CATALOG desde backend
  const [profiles, setProfiles] = useState([]);
  const [selected, setSelected] = useState(null); // profile_id activo
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState(null);

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [permissions, setPermissions] = useState({});
  const [dirty, setDirty] = useState(false);

  const currentProfile = useMemo(
    () => profiles.find((p) => p.profile_id === selected) || null,
    [profiles, selected],
  );

  async function loadAll() {
    setLoading(true);
    try {
      const [{ data: cat }, { data: profs }] = await Promise.all([
        api.get("/access-profiles/catalog"),
        api.get("/access-profiles"),
      ]);
      setCatalog(cat.items || []);
      setProfiles(profs);
      if (!selected && profs.length) setSelected(profs[0].profile_id);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { loadAll(); }, []);

  // Al cambiar el perfil seleccionado, cargamos su contenido al formulario.
  useEffect(() => {
    if (!currentProfile) return;
    setName(currentProfile.name || "");
    setDescription(currentProfile.description || "");
    setPermissions({ ...currentProfile.permissions });
    setDirty(false);
  }, [currentProfile]);

  // Agrupa permisos por sección (respetando el orden del catálogo).
  const grouped = useMemo(() => {
    const acc = {};
    for (const item of catalog) {
      const sec = item.section || "Otros";
      if (!acc[sec]) acc[sec] = [];
      acc[sec].push(item);
    }
    return acc;
  }, [catalog]);

  const filteredProfiles = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return profiles;
    return profiles.filter((p) =>
      (p.name || "").toLowerCase().includes(q) ||
      (p.description || "").toLowerCase().includes(q));
  }, [profiles, search]);

  function toggle(key) {
    setPermissions((p) => ({ ...p, [key]: !p[key] }));
    setDirty(true);
  }

  function toggleSection(section, value) {
    setPermissions((p) => {
      const next = { ...p };
      for (const item of grouped[section] || []) next[item.key] = value;
      return next;
    });
    setDirty(true);
  }

  async function save() {
    if (!currentProfile) return;
    if (!name.trim()) { toast.error("El nombre del perfil es obligatorio"); return; }
    setSaving(true);
    try {
      const { data } = await api.put(`/access-profiles/${currentProfile.profile_id}`, {
        name: name.trim(),
        description: description.trim() || null,
        permissions,
      });
      toast.success(`Perfil "${data.name}" actualizado`);
      setProfiles((list) => list.map((p) => (p.profile_id === data.profile_id ? data : p)));
      setDirty(false);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally {
      setSaving(false);
    }
  }

  async function handleCreate(newName, newDesc) {
    try {
      const { data } = await api.post("/access-profiles", {
        name: newName,
        description: newDesc || null,
        permissions: {}, // arranca todo en OFF
      });
      toast.success(`Perfil "${data.name}" creado`);
      setProfiles((list) => [...list, data].sort((a, b) => a.name.localeCompare(b.name)));
      setSelected(data.profile_id);
      setCreating(false);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    }
  }

  async function handleDelete() {
    if (!deleting) return;
    try {
      await api.delete(`/access-profiles/${deleting.profile_id}`);
      toast.success(`Perfil "${deleting.name}" eliminado`);
      setProfiles((list) => list.filter((p) => p.profile_id !== deleting.profile_id));
      if (selected === deleting.profile_id) {
        const rest = profiles.filter((p) => p.profile_id !== deleting.profile_id);
        setSelected(rest[0]?.profile_id || null);
      }
      setDeleting(null);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    }
  }

  const activeCount = Object.values(permissions).filter(Boolean).length;

  return (
    <div className="space-y-6" data-testid="security-profiles-page">
      <header className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <p className="text-xs uppercase tracking-[0.24em] text-muted-foreground">Seguridad</p>
          <h1 className="text-3xl font-bold flex items-center gap-2 mt-1">
            <ShieldCheck className="h-7 w-7 text-primary" /> Creación de perfiles de acceso
          </h1>
          <p className="text-sm text-muted-foreground max-w-2xl mt-1">
            Define perfiles con la combinación exacta de opciones del menú que cada
            colaborador podrá visualizar y utilizar. El menú de autoservicio (Registrar rostro,
            Cambiar contraseña, Cambiar PIN) siempre está disponible para todos.
          </p>
        </div>
        <Button onClick={() => setCreating(true)} className="rounded-full bg-primary hover:bg-primary/90" data-testid="profiles-new-btn">
          <Plus className="h-4 w-4 mr-1.5" /> Nuevo perfil
        </Button>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-[320px,1fr] gap-6">
        {/* Sidebar: lista de perfiles */}
        <Card className="rounded-2xl border-muted-foreground/10">
          <CardContent className="p-3 space-y-2">
            <div className="relative">
              <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Buscar perfil…"
                className="pl-9 h-10 rounded-xl"
                data-testid="profiles-search"
              />
            </div>
            <div className="space-y-1 max-h-[70vh] overflow-y-auto pr-1">
              {loading && <p className="text-xs text-muted-foreground px-2 py-4">Cargando…</p>}
              {!loading && filteredProfiles.length === 0 && (
                <p className="text-xs text-muted-foreground px-2 py-4">Sin perfiles.</p>
              )}
              {filteredProfiles.map((p) => {
                const isActive = p.profile_id === selected;
                const count = Object.values(p.permissions || {}).filter(Boolean).length;
                return (
                  <button
                    key={p.profile_id}
                    onClick={() => setSelected(p.profile_id)}
                    className={
                      "w-full text-left rounded-xl px-3 py-2.5 transition-colors border " +
                      (isActive
                        ? "bg-primary text-primary-foreground border-primary shadow-sm"
                        : "bg-background hover:bg-muted border-transparent")
                    }
                    data-testid={`profile-item-${p.profile_id}`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium truncate">{p.name}</span>
                      {p.is_system && (
                        <Lock className={"h-3.5 w-3.5 " + (isActive ? "opacity-90" : "text-muted-foreground")}
                              title="Perfil del sistema — no se puede eliminar" />
                      )}
                    </div>
                    <p className={"text-[11px] mt-0.5 " + (isActive ? "text-primary-foreground/70" : "text-muted-foreground")}>
                      {count} de {(catalog.length || 0)} permisos activos
                    </p>
                  </button>
                );
              })}
            </div>
          </CardContent>
        </Card>

        {/* Grilla de permisos */}
        <Card className="rounded-2xl border-muted-foreground/10">
          <CardContent className="p-5 space-y-5">
            {!currentProfile ? (
              <div className="text-center py-14 text-muted-foreground text-sm">
                Selecciona un perfil o crea uno nuevo para configurar sus permisos.
              </div>
            ) : (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <Label className="text-xs">Nombre del perfil</Label>
                    <Input
                      value={name}
                      onChange={(e) => { setName(e.target.value); setDirty(true); }}
                      className="h-11 rounded-xl"
                      data-testid="profile-name-input"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Descripción (opcional)</Label>
                    <Input
                      value={description}
                      onChange={(e) => { setDescription(e.target.value); setDirty(true); }}
                      placeholder="Ej. Sólo lectura del histórico de visitas"
                      className="h-11 rounded-xl"
                      data-testid="profile-description-input"
                    />
                  </div>
                </div>

                <div className="flex items-center justify-between gap-3 flex-wrap">
                  <div className="text-xs text-muted-foreground flex items-center gap-1.5">
                    {currentProfile.is_system && (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
                        <Lock className="h-3 w-3" /> Perfil del sistema
                      </span>
                    )}
                    <span>{activeCount} de {catalog.length} permisos activos</span>
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setPermissions(Object.fromEntries(catalog.map((c) => [c.key, true])));
                        setDirty(true);
                      }}
                      data-testid="profile-all-on"
                    >
                      Activar todo
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setPermissions(Object.fromEntries(catalog.map((c) => [c.key, false])));
                        setDirty(true);
                      }}
                      data-testid="profile-all-off"
                    >
                      Desactivar todo
                    </Button>
                  </div>
                </div>

                <div className="space-y-5">
                  {Object.entries(grouped).map(([section, items]) => {
                    const allOn = items.every((i) => permissions[i.key]);
                    const someOn = items.some((i) => permissions[i.key]);
                    return (
                      <div key={section} className="rounded-xl border p-4 space-y-2 bg-muted/30" data-testid={`section-${section}`}>
                        <div className="flex items-center justify-between">
                          <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                            {section}
                          </h3>
                          <button
                            type="button"
                            onClick={() => toggleSection(section, !allOn)}
                            className="text-[11px] font-medium text-primary hover:underline"
                            data-testid={`section-toggle-${section}`}
                          >
                            {allOn ? "Desactivar sección" : (someOn ? "Activar toda la sección" : "Activar todo")}
                          </button>
                        </div>
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                          {items.map((item) => {
                            const on = !!permissions[item.key];
                            return (
                              <button
                                key={item.key}
                                type="button"
                                onClick={() => toggle(item.key)}
                                className={
                                  "flex items-center justify-between gap-2 rounded-xl px-3 py-2.5 border transition-colors text-sm " +
                                  (on
                                    ? "bg-primary/5 border-primary/40 text-foreground"
                                    : "bg-background border-transparent hover:border-muted-foreground/30")
                                }
                                data-testid={`perm-${item.key}`}
                              >
                                <span className="truncate">{item.label}</span>
                                <span
                                  className={
                                    "shrink-0 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] uppercase tracking-wider " +
                                    (on
                                      ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300"
                                      : "bg-muted text-muted-foreground")
                                  }
                                >
                                  {on ? <><Check className="h-3 w-3" /> Activo</> : <><X className="h-3 w-3" /> Inactivo</>}
                                </span>
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    );
                  })}
                </div>

                <div className="flex items-center justify-end gap-2 pt-2 border-t">
                  {!currentProfile.is_system && (
                    <Button
                      variant="outline"
                      onClick={() => setDeleting(currentProfile)}
                      className="rounded-full text-destructive hover:text-destructive"
                      data-testid="profile-delete-btn"
                    >
                      <Trash2 className="h-4 w-4 mr-1.5" /> Eliminar
                    </Button>
                  )}
                  <Button
                    onClick={save}
                    disabled={saving || !dirty}
                    className="rounded-full bg-primary hover:bg-primary/90"
                    data-testid="profile-save-btn"
                  >
                    <Save className="h-4 w-4 mr-1.5" /> {saving ? "Guardando…" : "Guardar cambios"}
                  </Button>
                </div>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      <NewProfileDialog open={creating} onClose={() => setCreating(false)} onCreate={handleCreate} />
      <ConfirmDeleteDialog
        open={!!deleting}
        onClose={() => setDeleting(null)}
        profile={deleting}
        onConfirm={handleDelete}
      />
    </div>
  );
}

function NewProfileDialog({ open, onClose, onCreate }) {
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [submitting, setSubmitting] = useState(false);

  function reset() { setName(""); setDesc(""); setSubmitting(false); }

  async function submit(e) {
    e.preventDefault();
    if (!name.trim()) return;
    setSubmitting(true);
    try { await onCreate(name.trim(), desc.trim()); reset(); }
    finally { setSubmitting(false); }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!v) { reset(); onClose(); } }}>
      <DialogContent className="max-w-md" data-testid="new-profile-dialog">
        <DialogHeader>
          <DialogTitle>Nuevo perfil de acceso</DialogTitle>
          <DialogDescription>
            El perfil se crea con todos los permisos <b>inactivos</b>. Luego actívalos
            desde la grilla de la derecha.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3">
          <div className="space-y-1.5">
            <Label className="text-xs">Nombre</Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ej. Recepción"
              required
              autoFocus
              className="h-11 rounded-xl"
              data-testid="new-profile-name"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Descripción (opcional)</Label>
            <Textarea
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              placeholder="Sólo agenda de visitas y consulta del histórico."
              rows={2}
              maxLength={300}
              className="rounded-xl"
              data-testid="new-profile-desc"
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose} disabled={submitting}>Cancelar</Button>
            <Button type="submit" disabled={submitting || !name.trim()}
                    className="rounded-full bg-primary hover:bg-primary/90"
                    data-testid="new-profile-submit">
              {submitting ? "Creando…" : "Crear perfil"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function ConfirmDeleteDialog({ open, onClose, profile, onConfirm }) {
  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-sm" data-testid="delete-profile-dialog">
        <DialogHeader>
          <DialogTitle>Eliminar perfil</DialogTitle>
          <DialogDescription>
            El perfil <b>{profile?.name}</b> quedará eliminado. Los usuarios que lo
            tuvieran asignado pasarán a usar los permisos por defecto de su rol.
          </DialogDescription>
        </DialogHeader>
        <div className="rounded-xl bg-muted/40 border p-3 text-xs text-muted-foreground flex items-center gap-2">
          <UsersIcon className="h-4 w-4" />
          Esta acción no se puede deshacer.
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancelar</Button>
          <Button onClick={onConfirm} className="rounded-full bg-destructive hover:bg-destructive/90"
                  data-testid="delete-profile-confirm">
            Eliminar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
