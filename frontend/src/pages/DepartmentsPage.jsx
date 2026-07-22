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
import { Building2, Plus, MoreVertical, Pencil, Trash2, Search } from "lucide-react";

const EMPTY = { name: "", description: "" };

export default function DepartmentsPage() {
  const [items, setItems] = useState([]);
  const [q, setQ] = useState("");
  const [counts, setCounts] = useState({});
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [deleting, setDeleting] = useState(null);

  async function load() {
    setLoading(true);
    try {
      const [{ data: depts }, { data: users }] = await Promise.all([
        api.get("/departments"), api.get("/users"),
      ]);
      const c = users.reduce((acc, u) => {
        if (u.department_id) acc[u.department_id] = (acc[u.department_id] || 0) + 1;
        return acc;
      }, {});
      setCounts(c);
      setItems(depts);
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);

  const filtered = useMemo(() => {
    const n = q.toLowerCase().trim();
    if (!n) return items;
    return items.filter((d) => (d.name || "").toLowerCase().includes(n));
  }, [items, q]);

  async function save(form) {
    try {
      if (editing.mode === "create") { await api.post("/departments", form); toast.success("Departamento creado"); }
      else { await api.put(`/departments/${editing.form.department_id}`, form); toast.success("Departamento actualizado"); }
      setEditing(null); load();
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message); }
  }
  async function confirmDelete() {
    try {
      await api.delete(`/departments/${deleting.department_id}`);
      toast.success("Departamento eliminado");
      setDeleting(null); load();
    } catch (e) { toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message); }
  }

  return (
    <div className="p-4 sm:p-8 max-w-6xl mx-auto space-y-6" data-testid="depts-page">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <Badge variant="secondary" className="rounded-full mb-3">Estructura</Badge>
          <h1 className="text-3xl sm:text-4xl font-bold text-primary flex items-center gap-2">
            Departamentos <span className="text-xl font-normal text-muted-foreground">· {items.length}</span>
          </h1>
          <p className="text-muted-foreground mt-1 text-sm">Áreas funcionales de la empresa. Se usan para filtrar reportes y agrupar equipos.</p>
        </div>
        <Button className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground shadow-lg shadow-primary/20"
          onClick={() => setEditing({ mode: "create", form: { ...EMPTY } })}
          data-testid="depts-create-btn">
          <Plus className="h-4 w-4 mr-1.5" /> Nuevo departamento
        </Button>
      </div>

      <Card className="border-border/70 bg-white/80 backdrop-blur">
        <CardContent className="p-3 sm:p-4">
          <div className="relative max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar departamento…" className="pl-9 h-10" data-testid="depts-search" />
          </div>
        </CardContent>
      </Card>

      <Card className="border-border/70 bg-white/80 backdrop-blur overflow-hidden">
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40">
                <TableHead className="w-[280px]">Nombre</TableHead>
                <TableHead>Descripción</TableHead>
                <TableHead className="w-[140px]">Empleados</TableHead>
                <TableHead className="w-[60px] text-right">·</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody data-testid="depts-table">
              {loading && <TableRow><TableCell colSpan={4} className="text-center py-10 text-muted-foreground">Cargando…</TableCell></TableRow>}
              {!loading && filtered.map((d) => (
                <TableRow key={d.department_id}>
                  <TableCell>
                    <div className="flex items-center gap-3">
                      <div className="h-9 w-9 rounded-full bg-primary/10 text-primary grid place-items-center">
                        <Building2 className="h-4 w-4" />
                      </div>
                      <p className="text-sm font-medium text-primary">{d.name}</p>
                    </div>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">{d.description || "—"}</TableCell>
                  <TableCell><Badge variant="outline" className="rounded-full text-xs">{counts[d.department_id] || 0}</Badge></TableCell>
                  <TableCell className="text-right">
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon"><MoreVertical className="h-4 w-4" /></Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => setEditing({ mode: "edit", form: { ...EMPTY, ...d } })}>
                          <Pencil className="h-4 w-4 mr-2" /> Editar
                        </DropdownMenuItem>
                        <DropdownMenuItem className="text-destructive focus:text-destructive" onClick={() => setDeleting(d)}>
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

      <Dialog open={!!editing} onOpenChange={(v) => !v && setEditing(null)}>
        <DialogContent className="max-w-lg" data-testid="depts-dialog">
          <DialogHeader>
            <DialogTitle>{editing?.mode === "edit" ? "Editar" : "Nuevo"} departamento</DialogTitle>
            <DialogDescription>Nombre y descripción breve del área.</DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1.5">
              <Label>Nombre</Label>
              <Input value={editing?.form?.name || ""} onChange={(e) => setEditing((s) => ({ ...s, form: { ...s.form, name: e.target.value } }))} data-testid="depts-form-name" />
            </div>
            <div className="space-y-1.5">
              <Label>Descripción</Label>
              <Textarea value={editing?.form?.description || ""} onChange={(e) => setEditing((s) => ({ ...s, form: { ...s.form, description: e.target.value } }))} rows={3} data-testid="depts-form-desc" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setEditing(null)}>Cancelar</Button>
            <Button onClick={() => save(editing.form)} disabled={!editing?.form?.name} className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground" data-testid="depts-form-save">
              Guardar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!deleting} onOpenChange={(v) => !v && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Eliminar departamento</AlertDialogTitle>
            <AlertDialogDescription>¿Seguro que quieres eliminar <b>{deleting?.name}</b>? Los empleados quedarán sin departamento asignado.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={confirmDelete} className="bg-destructive hover:bg-destructive/90" data-testid="depts-delete-confirm">Eliminar</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
