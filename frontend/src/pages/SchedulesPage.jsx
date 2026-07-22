import { useEffect, useMemo, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { toast } from "sonner";
import { CalendarClock, Plus, Pencil, Trash2, Timer, MapPin } from "lucide-react";

const EMPTY = { name: "", blocks: [{ start: "09:00", end: "17:00" }], tolerance_minutes: 10, site_id: "" };

export default function SchedulesPage() {
  const [items, setItems] = useState([]);
  const [sites, setSites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [deleting, setDeleting] = useState(null);

  async function load() {
    setLoading(true);
    try {
      const [{ data: schs }, { data: ss }] = await Promise.all([
        api.get("/schedules"), api.get("/sites"),
      ]);
      setItems(schs); setSites(ss);
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);

  const siteName = useMemo(
    () => Object.fromEntries(sites.map((s) => [s.site_id, s.name])), [sites]);

  async function save(form) {
    const payload = {
      name: form.name,
      blocks: form.blocks,
      tolerance_minutes: Number(form.tolerance_minutes) || 0,
      site_id: form.site_id || undefined,
    };
    try {
      if (editing.mode === "create") { await api.post("/schedules", payload); toast.success("Horario creado"); }
      else { await api.put(`/schedules/${editing.form.schedule_id}`, payload); toast.success("Horario actualizado"); }
      setEditing(null); load();
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message); }
  }

  async function confirmDelete() {
    try {
      await api.delete(`/schedules/${deleting.schedule_id}`);
      toast.success("Horario eliminado");
      setDeleting(null); load();
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message); }
  }

  return (
    <div className="p-4 sm:p-8 max-w-6xl mx-auto space-y-6" data-testid="schedules-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <Badge variant="secondary" className="rounded-full mb-3">Configuración</Badge>
          <h1 className="text-3xl sm:text-4xl font-bold text-primary flex items-center gap-2">
            Horarios <span className="text-xl font-normal text-muted-foreground">· {items.length}</span>
          </h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Turnos con uno o varios bloques y tolerancia para calcular tardanzas.
          </p>
        </div>
        <Button className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground shadow-lg shadow-primary/20"
          onClick={() => setEditing({ mode: "create", form: { ...EMPTY, blocks: [{ start: "09:00", end: "17:00" }] } })}
          data-testid="schedules-create-btn">
          <Plus className="h-4 w-4 mr-1.5" /> Nuevo horario
        </Button>
      </div>

      {loading && <p className="text-sm text-muted-foreground">Cargando…</p>}

      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3" data-testid="schedules-grid">
        {items.map((s) => (
          <Card key={s.schedule_id} className="border-border/70 bg-white/80 backdrop-blur">
            <CardContent className="p-5">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-2xl bg-primary/10 text-primary grid place-items-center">
                    <CalendarClock className="h-5 w-5" />
                  </div>
                  <div>
                    <p className="text-base font-semibold text-primary">{s.name}</p>
                    <p className="text-[11px] text-muted-foreground flex items-center gap-1 mt-0.5">
                      <MapPin className="h-3 w-3" /> {siteName[s.site_id] || "Sin sede"}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-1">
                  <Button variant="ghost" size="icon" onClick={() => setEditing({ mode: "edit", form: { ...EMPTY, ...s, site_id: s.site_id || "" } })} data-testid={`schedules-edit-${s.schedule_id}`}>
                    <Pencil className="h-4 w-4" />
                  </Button>
                  <Button variant="ghost" size="icon" onClick={() => setDeleting(s)} className="text-destructive hover:text-destructive" data-testid={`schedules-delete-${s.schedule_id}`}>
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </div>

              <div className="mt-4 space-y-1.5">
                {(s.blocks || []).map((b, i) => (
                  <div key={i} className="flex items-center justify-between text-sm bg-muted/40 rounded-lg px-3 py-1.5">
                    <span className="font-mono text-primary">{b.start} — {b.end}</span>
                    <span className="text-[11px] text-muted-foreground">Bloque {i + 1}</span>
                  </div>
                ))}
              </div>

              <div className="mt-4 flex items-center gap-1.5 text-xs text-muted-foreground">
                <Timer className="h-3.5 w-3.5" />
                Tolerancia: <b className="text-primary">{s.tolerance_minutes} min</b>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <ScheduleDialog state={editing} sites={sites} onCancel={() => setEditing(null)} onSave={save} />

      <AlertDialog open={!!deleting} onOpenChange={(v) => !v && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Eliminar horario</AlertDialogTitle>
            <AlertDialogDescription>¿Seguro que quieres eliminar <b>{deleting?.name}</b>?</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete} className="bg-destructive hover:bg-destructive/90" data-testid="schedules-delete-confirm">Eliminar</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function ScheduleDialog({ state, sites, onCancel, onSave }) {
  const [form, setForm] = useState(state?.form || EMPTY);
  useEffect(() => { setForm(state?.form || EMPTY); }, [state]);
  const open = !!state;
  const isEdit = state?.mode === "edit";

  function updateBlock(i, k, v) {
    setForm((f) => {
      const blocks = f.blocks.map((b, idx) => idx === i ? { ...b, [k]: v } : b);
      return { ...f, blocks };
    });
  }
  function addBlock() { setForm((f) => ({ ...f, blocks: [...f.blocks, { start: "14:00", end: "18:00" }] })); }
  function removeBlock(i) { setForm((f) => ({ ...f, blocks: f.blocks.filter((_, idx) => idx !== i) })); }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onCancel()}>
      <DialogContent className="max-w-lg" data-testid="schedules-dialog">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Editar" : "Nuevo"} horario</DialogTitle>
          <DialogDescription>Define bloques (ej. mañana y tarde) y la tolerancia en minutos.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Nombre</Label>
            <Input value={form.name || ""} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} placeholder="Ej. Día Completo" data-testid="schedules-form-name" />
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <Label>Bloques</Label>
              <Button type="button" variant="ghost" size="sm" onClick={addBlock} data-testid="schedules-form-add-block">+ Añadir</Button>
            </div>
            <div className="space-y-2">
              {form.blocks.map((b, i) => (
                <div key={i} className="flex items-center gap-2">
                  <Input type="time" value={b.start} onChange={(e) => updateBlock(i, "start", e.target.value)} className="w-32 font-mono" />
                  <span className="text-muted-foreground text-sm">—</span>
                  <Input type="time" value={b.end} onChange={(e) => updateBlock(i, "end", e.target.value)} className="w-32 font-mono" />
                  {form.blocks.length > 1 && (
                    <Button type="button" variant="ghost" size="icon" onClick={() => removeBlock(i)} className="text-destructive">
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label>Tolerancia (min)</Label>
              <Input type="number" min="0" max="120" value={form.tolerance_minutes ?? 10} onChange={(e) => setForm((f) => ({ ...f, tolerance_minutes: e.target.value }))} data-testid="schedules-form-tol" />
            </div>
            <div className="space-y-1.5">
              <Label>Sede</Label>
              <Select value={form.site_id || "__none"} onValueChange={(v) => setForm((f) => ({ ...f, site_id: v === "__none" ? "" : v }))}>
                <SelectTrigger data-testid="schedules-form-site"><SelectValue placeholder="—" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="__none">Sin sede</SelectItem>
                  {sites.map((s) => <SelectItem key={s.site_id} value={s.site_id}>{s.name}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onCancel}>Cancelar</Button>
          <Button onClick={() => onSave(form)} disabled={!form.name || form.blocks.length === 0} className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground" data-testid="schedules-form-save">
            Guardar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
