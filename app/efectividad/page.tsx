/**
 * /efectividad — Compat: redirige a /resultados.
 *
 * Ruta legacy. La página canónica de track-record del modelo es /resultados.
 * Mantenemos /efectividad para no romper links viejos o marcadores.
 */

import { redirect } from "next/navigation";

export default function EfectividadPage() {
  redirect("/resultados");
}