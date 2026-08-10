import { useEffect, useState } from "react";
import { api, formatApiErrorDetail } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { PasswordInput } from "@/components/ui/password-input";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { KeyRound, Check } from "lucide-react";

/** Diálogo de crear/cambiar PIN de kiosco.
 *  Props: open, onOpenChange, userId, userName, onSuccess */
export default function SetPinDialog({ open, onOpenChange, userId, userName, onSuccess }) {
  const [pin, setPin] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { setPin(""); setConfirm(""); }, [open, userId]);

  const valid = pin.length >= 4 && pin.length <= 8 && pin === confirm;

  async function save() {
    if (!valid) return;
    setBusy(true);
    try {
      await api.post(`/users/${userId}/pin`, { pin });
      toast.success("PIN actualizado");
      onOpenChange(false);
      onSuccess?.();
    } catch (e) {
      toast.error(formatApiErrorDetail(e.response?.data?.detail) || e.message);
    } finally { setBusy(false); }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-sm" data-testid="set-pin-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <KeyRound className="h-4 w-4 text-accent" /> PIN de kiosco
          </DialogTitle>
          <DialogDescription>
            Define un PIN de 4 a 8 dígitos {userName ? `para ${userName}` : ""}. Se usa para marcar sin rostro o para reintentar rostro en el kiosco.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>Nuevo PIN</Label>
            <PasswordInput
              inputMode="numeric"
              pattern="[0-9]*"
              value={pin}
              onChange={(e) => setPin(e.target.value.replace(/\D/g, "").slice(0, 8))}
              placeholder="••••"
              className="text-2xl text-center h-14 tracking-widest font-mono"
              data-testid="set-pin-input"
              toggleTestId="set-pin-input-toggle"
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <Label>Confirmar PIN</Label>
            <PasswordInput
              inputMode="numeric"
              pattern="[0-9]*"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value.replace(/\D/g, "").slice(0, 8))}
              placeholder="••••"
              className="text-2xl text-center h-14 tracking-widest font-mono"
              data-testid="set-pin-confirm"
              toggleTestId="set-pin-confirm-toggle"
            />
            {confirm.length > 0 && confirm !== pin && (
              <p className="text-xs text-destructive">Los PINs no coinciden</p>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancelar</Button>
          <Button
            onClick={save}
            disabled={!valid || busy}
            className="rounded-full bg-primary hover:bg-primary/90 text-primary-foreground"
            data-testid="set-pin-save"
          >
            <Check className="h-4 w-4 mr-1.5" /> {busy ? "Guardando…" : "Guardar PIN"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
