import * as React from "react";
import { Eye, EyeOff } from "lucide-react";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/**
 * Input de contraseña con toggle "ojito" para mostrar/ocultar el texto.
 *
 * Props:
 *  - toggleTestId (opcional): data-testid para el botón del ojito.
 *  - toggleClassName (opcional): clases extra para el botón (posición/color).
 *  - resto: se re-emiten al <Input/> subyacente (incluye value, onChange, placeholder, className, data-testid...).
 *
 * Nota: `type` no se acepta desde afuera — este componente lo controla internamente.
 */
const PasswordInput = React.forwardRef(function PasswordInput(
  { className, toggleTestId, toggleClassName, ...props },
  ref,
) {
  const [show, setShow] = React.useState(false);

  return (
    <div className="relative">
      <Input
        {...props}
        ref={ref}
        type={show ? "text" : "password"}
        className={cn("pr-11", className)}
      />
      <button
        type="button"
        onClick={() => setShow((s) => !s)}
        aria-label={show ? "Ocultar contraseña" : "Mostrar contraseña"}
        aria-pressed={show}
        tabIndex={-1}
        data-testid={toggleTestId || "password-toggle"}
        className={cn(
          "absolute right-1.5 top-1/2 -translate-y-1/2 h-8 w-8 grid place-items-center rounded-lg text-muted-foreground hover:text-primary hover:bg-muted transition-colors",
          toggleClassName,
        )}
      >
        {show ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </div>
  );
});

export { PasswordInput };
export default PasswordInput;
