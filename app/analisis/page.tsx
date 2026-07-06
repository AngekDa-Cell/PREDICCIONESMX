/**
 * /analisis — Compat: redirige a / (Home).
 *
 * Ruta legacy. La página principal ahora es /, que muestra los partidos
 * próximos con sus predicciones. Mantenemos /analisis para no romper
 * links viejos o marcadores de navegador.
 */

import { redirect } from "next/navigation";

export default function AnalisisPage() {
  redirect("/");
}