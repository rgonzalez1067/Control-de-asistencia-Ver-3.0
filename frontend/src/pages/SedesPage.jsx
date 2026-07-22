import { useEffect, useMemo, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
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
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { toast } from "sonner";
import { MapPin, Plus, MoreVertical, Pencil, Trash2, Search } from "lucide-react";

const EMPTY = { name: "", address: "" };

export default function SedesPage() {
  const [items, setItems] = useState([]);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [deleting, setDeleting] = useState(null);

  async function load() {
    setLoading(true);
    try {
      const [{ data: sites }, { data: users }] = await Promise.all([
        api.get("/sites"), api.get("/users"),
      ]);
      const counts = users.reduce((acc, u) => {
        if (u.site_id) acc[u.site_id] = (acc[u.site_id] || 0) + 1;
        return acc;
      }, {});
      setItems(sites.map((s) => ({ ...s, employees: counts[s.site_id] || 0 })));
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    const needle = q.toLowerCase().trim();
    if (!needle) return items;
    return items.filter((s) =>
      (s.name || "").toLowerCase().includes(needle) ||
      (s.address || "").toLowerCase().includes(needle));
  }, [items, q]);

  async function save(form) {
    try {
      if (editing.mode === "create") {
        await api.post("/sites", form);
        toast.success("Sede creada");
      } else {
        await api.put(`/sites/${editing.form.site_id}`, form);
        toast.success("Sede actualizada");
      }
      setEditing(null);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    }
  }

  async function confirmDelete() {
    try {
      await api.delete(`/sites/${deleting.site_id}`);
      toast.success("Sede eliminada");
      setDeleting(null);
      load();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    }
  }

  return (
    <div className="p-4 sm:p-8 max-w-6xl mx-auto space-y-6" data-testid="sedes-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <Badge variant="secondary" className="rounded-full mb-3">Configuración</Badge>
          <h1 className="text-3xl sm:text-4xl font-bold text-foreground flex items-center gap-2">
            Sedes <span className="text-xl font-normal text-muted-foreground">· {items.length}</span>
          </h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Lugares donde tu equipo puede marcar asistencia. Se asignan a empleados y horarios.
          </p>
        </div>
        <Button
          className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground shadow-lg shadow-primary/20"
          onClick={() => setEditing({ mode: "create", form: { ...EMPTY } })}
          data-testid="sedes-create-btn"
        >
          <Plus className="h-4 w-4 mr-1.5" /> Nueva sede
        </Button>
      </div>

      <Card className="border-border/70 bg-card/80 backdrop-blur">
        <CardContent className="p-3 sm:p-4">
          <div className="relative max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Buscar sede…"
              className="pl-9 h-10 border-border/60"
              data-testid="sedes-search"
            />
          </div>
        </CardContent>
      </Card>

      <Card className="border-border/70 bg-card/80 backdrop-blur overflow-hidden">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40">
                <TableHead className="w-[280px]">Nombre</TableHead>
                <TableHead>Dirección</TableHead>
                <TableHead className="w-[140px]">Empleados</TableHead>
                <TableHead className="w-[60px] text-right">·</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody data-testid="sedes-table">
              {loading && <TableRow><TableCell colSpan={4} className="text-center py-10 text-muted-foreground">Cargando…</TableCell></TableRow>}
              {!loading && filtered.length === 0 && <TableRow><TableCell colSpan={4} className="text-center py-10 text-muted-foreground">Sin sedes</TableCell></TableRow>}
              {!loading && filtered.map((s) => (
                <TableRow key={s.site_id}>
                  <TableCell>
                    <div className="flex items-center gap-3">
                      <div className="h-9 w-9 rounded-full bg-primary/10 text-foreground grid place-items-center">
                        <MapPin className="h-4 w-4" />
                      </div>
                      <p className="text-sm font-medium text-foreground">{s.name}</p>
                    </div>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">{s.address || "—"}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className="rounded-full text-xs">{s.employees}</Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" data-testid={`sedes-actions-${s.site_id}`}>
                          <MoreVertical className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => setEditing({ mode: "edit", form: { ...EMPTY, ...s } })}>
                          <Pencil className="h-4 w-4 mr-2" /> Editar
                        </DropdownMenuItem>
                        <DropdownMenuItem className="text-destructive focus:text-destructive" onClick={() => setDeleting(s)}>
                          <Trash2 className="h-4 w-4 mr-2" /> Eliminar
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </Card>

      <SedeDialog state={editing} onCancel={() => setEditing(null)} onSave={save} />

      <AlertDialog open={!!deleting} onOpenChange={(v) => !v && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Eliminar sede</AlertDialogTitle>
            <AlertDialogDescription>
              ¿Seguro que quieres eliminar <b>{deleting?.name}</b>? Los empleados y horarios asignados quedarán sin sede.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete} className="bg-destructive hover:bg-destructive/90" data-testid="sedes-delete-confirm">
              Eliminar
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function SedeDialog({ state, onCancel, onSave }) {
  const [form, setForm] = useState(state?.form || EMPTY);
  useEffect(() => { setForm(state?.form || EMPTY); }, [state]);
  const open = !!state;
  const isEdit = state?.mode === "edit";

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onCancel()}>
      <DialogContent className="max-w-lg" data-testid="sedes-dialog">
        <DialogHeader>
          <DialogTitle>{isEdit ? "Editar sede" : "Nueva sede"}</DialogTitle>
          <DialogDescription>
            Registra las oficinas o puntos de trabajo donde tu equipo marca asistencia.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label>Nombre</Label>
            <Input value={form.name || ""} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} placeholder="Sede principal Torre Banco Plaza" data-testid="sedes-form-name" />
          </div>
          <div className="space-y-1.5">
            <Label>Dirección <span className="text-muted-foreground/60">(opcional)</span></Label>
            <Textarea value={form.address || ""} onChange={(e) => setForm((f) => ({ ...f, address: e.target.value }))} rows={2} placeholder="Av. Principal, Piso 4, Caracas" data-testid="sedes-form-address" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onCancel}>Cancelar</Button>
          <Button onClick={() => onSave(form)} disabled={!form.name} className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground" data-testid="sedes-form-save">
            {isEdit ? "Guardar cambios" : "Crear sede"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
