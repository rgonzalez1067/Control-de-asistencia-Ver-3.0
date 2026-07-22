import { useAuth } from "@/context/AuthContext";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Sparkles } from "lucide-react";

/** Placeholder para las pantallas que se implementan en fases posteriores. */
export default function ComingSoon({ title, phase, description }) {
  const { user } = useAuth();
  return (
    <div className="p-8 max-w-3xl mx-auto" data-testid="coming-soon">
      <Badge variant="secondary" className="rounded-full mb-3">Próximamente</Badge>
      <h1 className="text-3xl sm:text-4xl font-bold text-foreground">
        {title}
        <span className="block font-serif-display text-primary/50 text-2xl mt-1">
          disponible en la {phase}.
        </span>
      </h1>
      <p className="mt-4 text-muted-foreground max-w-xl">{description}</p>
      <Card className="mt-8 border-dashed border-2 border-primary/20 bg-white/60">
        <CardContent className="py-10 grid place-items-center">
          <div className="h-12 w-12 rounded-2xl bg-primary/10 text-foreground grid place-items-center mb-3">
            <Sparkles className="h-6 w-6" />
          </div>
          <p className="text-sm text-muted-foreground">Sesión: <b className="text-foreground">{user?.name}</b></p>
        </CardContent>
      </Card>
    </div>
  );
}
