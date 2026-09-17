import { useEffect, useRef, useState } from "react";

/**
 * Hook de cierre por inactividad (sep-2026).
 * Escucha mousemove/click/keydown/touchstart y hace logout tras `idleMs`.
 * Muestra un banner de aviso `warnMs` antes.
 */
export default function useIdleTimeout({ idleMs, warnMs = 60_000, onLogout }) {
  const [warningLeft, setWarningLeft] = useState(null); // segundos restantes si está en warning
  const lastActivity = useRef(Date.now());
  const timerRef = useRef(null);
  const countdownRef = useRef(null);

  useEffect(() => {
    if (!idleMs || !onLogout) return undefined;

    const events = ["mousemove", "mousedown", "keydown", "touchstart", "scroll"];
    const reset = () => {
      lastActivity.current = Date.now();
      if (warningLeft !== null) setWarningLeft(null);
    };
    events.forEach((ev) => window.addEventListener(ev, reset, { passive: true }));

    timerRef.current = setInterval(() => {
      const elapsed = Date.now() - lastActivity.current;
      if (elapsed >= idleMs) {
        clearInterval(timerRef.current);
        clearInterval(countdownRef.current);
        setWarningLeft(null);
        onLogout();
      } else if (elapsed >= idleMs - warnMs && warningLeft === null) {
        const secs = Math.ceil((idleMs - elapsed) / 1000);
        setWarningLeft(secs);
        countdownRef.current = setInterval(() => {
          const left = Math.ceil((idleMs - (Date.now() - lastActivity.current)) / 1000);
          if (left <= 0) {
            clearInterval(countdownRef.current);
            setWarningLeft(0);
          } else {
            setWarningLeft(left);
          }
        }, 1000);
      }
    }, 5000);

    return () => {
      events.forEach((ev) => window.removeEventListener(ev, reset));
      clearInterval(timerRef.current);
      clearInterval(countdownRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [idleMs, warnMs, onLogout]);

  const stayActive = () => { lastActivity.current = Date.now(); setWarningLeft(null); };
  return { warningLeft, stayActive };
}
