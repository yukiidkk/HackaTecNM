/**
 * Cliente HTTP base para el backend FastAPI.
 * Todas las rutas pasan por el proxy /api → localhost:8000
 * configurado en next.config.mjs.
 */

const BASE_URL = "/api";

// ─── Tipos de dominio ────────────────────────────────────────────────────────

export interface PartAvailability {
  part_id: number;
  name: string;
  sku: string | null;
  locations: {
    location_id: number;
    location_code: string;
    location_name: string;
    on_hand: number;
    reserved: number;
    available: number;
  }[];
}

export interface LedgerEntry {
  movement_id: number;
  part_id: number;
  location_id: number;
  delta: number;
  movement_type: string;
  reference_id: string | null;
  created_at: string;
  running_balance: number;
}

export interface WorkOrderMaterials {
  work_order_id: number;
  code: string;
  current_stage: string;
  lines: {
    inspection_item_id: number;
    bom_line_id: number;
    part_id: number | null;
    name: string;
    reserved: number;
    delivered: number;
    shortage: number | null;
  }[];
}

export interface Shortage {
  shortage_id: number;
  work_order_id: number;
  part_id: number | null;
  name: string;
  missing_quantity: number | null;
  status: "open" | "resolved" | "cancelled";
  created_at: string;
}

export interface ReorderSuggestion {
  part_id: number;
  name: string;
  sku: string | null;
  suggested_quantity: number;
  work_order_ids: number[];
}

export interface UnmatchedReceipt {
  id: number;
  purchase_line_id: number;
  part_number: string;
  description: string | null;
  quantity: number;
  work_order_code: string | null;
  status: "pending" | "resolved" | "ignored";
  received_at: string;
}

// ─── Helper fetch ────────────────────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`[${res.status}] ${path}: ${text}`);
  }

  return res.json() as Promise<T>;
}

// ─── Endpoints ───────────────────────────────────────────────────────────────

/** Saldo por ubicación para una pieza */
export const getPartAvailability = (partId: number) =>
  apiFetch<PartAvailability>(`/parts/${partId}/availability`);

/** Kardex (libro mayor) de una pieza */
export const getPartLedger = (partId: number) =>
  apiFetch<LedgerEntry[]>(`/parts/${partId}/ledger`);

/** Materiales (reservas, entregas, faltantes) de una orden de trabajo */
export const getWorkOrderMaterials = (code: string) =>
  apiFetch<WorkOrderMaterials>(`/work-orders/${encodeURIComponent(code)}/materials`);

/** Faltantes abiertos, opcionalmente filtrados por orden o pieza */
export const getShortages = (params?: { work_order_id?: number; part_id?: number }) => {
  const qs = params ? "?" + new URLSearchParams(
    Object.entries(params)
      .filter(([, v]) => v != null)
      .map(([k, v]) => [k, String(v)])
  ).toString() : "";
  return apiFetch<Shortage[]>(`/shortages${qs}`);
};

/** Sugerencias de reorden vigentes */
export const getReorderSuggestions = () =>
  apiFetch<ReorderSuggestion[]>("/reorder-suggestions");

/** Recepciones sin relacionar a pieza */
export const getUnmatchedReceipts = () =>
  apiFetch<UnmatchedReceipt[]>("/unmatched-receipts");

/** Resolver manualmente una recepción sin relacionar */
export const resolveUnmatchedReceipt = (id: number, partId: number) =>
  apiFetch<{ ok: boolean }>(`/unmatched-receipts/${id}/resolve`, {
    method: "POST",
    body: JSON.stringify({ part_id: partId }),
  });

/** Registrar salida de pieza contra una orden */
export const postIssue = (body: {
  work_order_code: string;
  part_id: number;
  location_id: number;
  quantity: number;
  issued_by: string;
}) => apiFetch<{ movement_id: number }>("/issues", { method: "POST", body: JSON.stringify(body) });

/** Transferir stock entre ubicaciones */
export const postTransfer = (body: {
  part_id: number;
  from_location_id: number;
  to_location_id: number;
  quantity: number;
}) => apiFetch<{ movement_id: number }>("/transfers", { method: "POST", body: JSON.stringify(body) });

/** Registrar conteo cíclico (ajuste) */
export const postCount = (body: {
  part_id: number;
  location_id: number;
  counted_quantity: number;
  reason: string;
}) => apiFetch<{ movement_id: number }>("/counts", { method: "POST", body: JSON.stringify(body) });
