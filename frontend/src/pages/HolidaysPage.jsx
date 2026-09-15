import { useEffect, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  CalendarDays, Plus, Pencil, Trash2, Repeat, Calendar as CalendarIcon,
} from "lucide-react";
import { toast } from "sonner";

const EMPTY = { date: "", name: "", is_recurrent: false };

export default function HolidaysPage() {
  const { user } = useAuth();
  const canManage = user?.role === "admin";
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);   // { mode:'new'|'edit', form:{...}, holiday_id? }
  const [deleting, setDeleting] = useState(null);

  async function load() {
    setLoading(true);
    try {
      const { data } = await api.get("/holidays");
      setItems(data || []);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);

  async function save() {
    const f = editing.form;
    if (!f.date || !f.name.trim()) { toast.error("Completa fecha y nombre"); return; }
    const body = { date: f.date, name: f.name.trim(), is_recurrent: !!f.is_recurrent };
    try {
      if (editing.mode === "edit") {
        await api.put(`/holidays/${editing.holiday_id}`, body);
        toast.success("Feriado actualizado");
      } else {
        await api.post("/holidays", body);
        toast.success("Feriado creado");
      }
      setEditing(null); load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    }
  }

  async function del() {
    try {
      await api.delete(`/holidays/${deleting.holiday_id}`);
      toast.success("Feriado eliminado");
      setDeleting(null); load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    }
  }

  const sorted = [...items].sort((a, b) => {
    // Recurrentes primero (por MM-DD), luego fijos por fecha completa
    if (a.is_recurrent !== b.is_recurrent) return a.is_recurrent ? -1 : 1;
    return (a.date || "").localeCompare(b.date || "");
  });

  return (
    <div className="space-y-6" data-testid="holidays-page">
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-[11px] uppercase tracking-widest text-muted-foreground">Configuración</p>
          <h1 className="text-2xl font-bold tracking-tight">Calendario de días festivos</h1>
          <p className="text-sm text-muted-foreground max-w-2xl mt-1">
            En turnos de <b>día completo</b> los feriados exhiben la etiqueta “Día Festivo” y eximen marcajes.
            En <b>turnos especiales / rotativos</b> se conservan los marcajes para el reporte de horas festivas.
          </p>
        </div>
        {canManage && (
          <Button
            onClick={() => setEditing({ mode: "new", form: EMPTY })}
            className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground"
            data-testid="holidays-create-btn"
          >
            <Plus className="h-4 w-4 mr-1.5" /> Nuevo feriado
          </Button>
        )}
      </div>

      {loading ? (
        <p className="text-sm text-muted-foreground">Cargando…</p>
      ) : sorted.length === 0 ? (
        <Card className="border-dashed"><CardContent className="p-10 text-center text-muted-foreground">
          <CalendarDays className="h-10 w-10 mx-auto mb-3 opacity-50" />
          Aún no hay días festivos registrados.
        </CardContent></Card>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {sorted.map((h) => (
            <Card key={h.holiday_id} className="border-border/60" data-testid={`holiday-${h.holiday_id}`}>
              <CardContent className="p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-3">
                    <div className={"h-10 w-10 rounded-2xl grid place-items-center " + (h.is_recurrent ? "bg-amber-100 text-amber-800" : "bg-sky-100 text-sky-800")}>
                      {h.is_recurrent ? <Repeat className="h-5 w-5" /> : <CalendarIcon className="h-5 w-5" />}
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-foreground">{h.name}</p>
                      <p className="text-[11px] text-muted-foreground mt-0.5">
                        {h.is_recurrent
                          ? `Recurrente · cada ${h.date.slice(5, 7)}/${h.date.slice(8, 10)}`
                          : `Fecha fija · ${h.date}`}
                      </p>
                    </div>
                  </div>
                  {canManage && (
                    <div className="flex items-center gap-1">
                      <Button variant="ghost" size="icon"
                              onClick={() => setEditing({ mode: "edit", form: { date: h.date, name: h.name, is_recurrent: h.is_recurrent }, holiday_id: h.holiday_id })}
                              data-testid={`holiday-edit-${h.holiday_id}`}>
                        <Pencil className="h-4 w-4" />
                      </Button>
                      <Button variant="ghost" size="icon" className="text-destructive hover:text-destructive"
                              onClick={() => setDeleting(h)}
                              data-testid={`holiday-delete-${h.holiday_id}`}>
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  )}
                </div>
                {h.is_recurrent && (
                  <Badge variant="outline" className="mt-3 text-[10px] border-amber-300 text-amber-800 bg-amber-50">
                    Siempre festivo
                  </Badge>
                )}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Dialog crear/editar */}
      <Dialog open={!!editing} onOpenChange={(v) => !v && setEditing(null)}>
        <DialogContent className="max-w-md" data-testid="holidays-form-dialog">
          <DialogHeader>
            <DialogTitle>{editing?.mode === "edit" ? "Editar feriado" : "Nuevo feriado"}</DialogTitle>
            <DialogDescription>
              Los recurrentes se aplican al mismo mes/día en todos los años (ignoramos el año que introduzcas).
            </DialogDescription>
          </DialogHeader>
          {editing && (
            <div className="space-y-4 py-2">
              <div className="space-y-1.5">
                <Label>Fecha</Label>
                <Input type="date" value={editing.form.date}
                       onChange={(e) => setEditing((s) => ({ ...s, form: { ...s.form, date: e.target.value } }))}
                       data-testid="holidays-form-date" />
              </div>
              <div className="space-y-1.5">
                <Label>Nombre / descripción</Label>
                <Input value={editing.form.name}
                       onChange={(e) => setEditing((s) => ({ ...s, form: { ...s.form, name: e.target.value } }))}
                       placeholder="Ej. Año Nuevo, Día del Trabajador…"
                       data-testid="holidays-form-name" />
              </div>
              <div className="flex items-center justify-between rounded-xl border p-3 bg-muted/30">
                <div>
                  <p className="text-sm font-medium">Siempre festivo</p>
                  <p className="text-[11px] text-muted-foreground leading-snug">
                    Marca esta opción para feriados fijos que se repiten cada año (ej. 1 ene, 25 dic).
                    Los variables (Carnaval, Semana Santa) déjala apagada.
                  </p>
                </div>
                <Switch
                  checked={!!editing.form.is_recurrent}
                  onCheckedChange={(v) => setEditing((s) => ({ ...s, form: { ...s.form, is_recurrent: v } }))}
                  data-testid="holidays-form-recurrent"
                />
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="ghost" onClick={() => setEditing(null)}>Cancelar</Button>
            <Button className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground"
                    onClick={save} data-testid="holidays-form-save">
              {editing?.mode === "edit" ? "Guardar cambios" : "Crear feriado"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Confirmar eliminación */}
      <AlertDialog open={!!deleting} onOpenChange={(v) => !v && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Eliminar feriado</AlertDialogTitle>
            <AlertDialogDescription>
              ¿Seguro que deseas eliminar “{deleting?.name}”? Esta acción no se puede deshacer.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={del} className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                               data-testid="holidays-delete-confirm">
              Eliminar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
