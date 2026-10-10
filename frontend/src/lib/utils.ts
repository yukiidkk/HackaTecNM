import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Combina clases de Tailwind resolviendo conflictos.
 * Uso: cn("px-2 py-1", condition && "bg-red-500", className)
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

/**
 * Formatea un número como cantidad con separador de miles.
 * Ejemplo: 1500 → "1,500"
 */
export function formatQty(value: number | null | undefined): string {
  if (value == null) return "—";
  return value.toLocaleString("es-MX");
}

/**
 * Formatea una fecha ISO 8601 a formato legible en español.
 * Ejemplo: "2026-10-06T16:42:11Z" → "06/oct/2026 16:42"
 */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("es-MX", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "America/Mexico_City",
  }).format(new Date(iso));
}

/**
 * Devuelve la clase de badge según el nivel de stock.
 * on_hand=0 → zero, available < min_stock → low, else ok
 */
export function stockBadgeClass(
  onHand: number,
  available: number,
  minStock = 1
): string {
  if (onHand === 0) return "badge-zero";
  if (available < minStock) return "badge-low";
  return "badge-ok";
}

/**
 * Etiqueta legible para el estado de una reserva.
 */
export const RESERVATION_STATUS: Record<string, string> = {
  active: "Activa",
  fulfilled: "Entregada",
  cancelled: "Cancelada",
};

/**
 * Etiqueta legible para el estado de un faltante.
 */
export const SHORTAGE_STATUS: Record<string, string> = {
  open: "Abierto",
  resolved: "Resuelto",
  cancelled: "Cancelado",
};

/**
 * Etiquetas de etapa de orden de trabajo (en español).
 */
export const STAGE_LABELS: Record<string, string> = {
  awaiting_quick_inspection: "Esperando insp. rápida",
  quick_inspection: "Inspección rápida",
  awaiting_full_inspection: "Esperando insp. completa",
  full_inspection: "Inspección completa",
  cleaning: "Limpieza",
  assembly: "Ensamble",
  run_in: "Rodaje",
  final_assembly: "Ensamble final",
  final_release: "Liberación final",
};
