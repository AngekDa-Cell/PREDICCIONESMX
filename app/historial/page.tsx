/**
 * /historial — Compat: redirige a /resultados.
 *
 * La ruta canónica ahora es /resultados (más clara).
 * Mantenemos /historial para no romper links viejos.
 */

import { redirect } from "next/navigation";

export default function HistorialPage() {
  redirect("/resultados");
}