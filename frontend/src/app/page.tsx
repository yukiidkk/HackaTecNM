"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import {
  Warehouse,
  ClipboardList,
  ScanLine,
  RefreshCw,
  Search,
  AlertTriangle,
  PackageX,
  CheckCircle2,
  XCircle,
  Camera,
} from "lucide-react";
import { TabBar, StockCard, Badge } from "@/components";
import type { Tab } from "@/components";
import {
  getShortages,
  getWorkOrderMaterials,
  getReorderSuggestions,
  postIssue,
  postTransfer,
  postCount,
} from "@/services/api";
import type {
  Shortage,
  WorkOrderMaterials,
  ReorderSuggestion,
} from "@/services/api";
import { cn, formatDate, formatQty, STAGE_LABELS } from "@/lib/utils";

// ─── Tipos locales ────────────────────────────────────────────────────────────

interface LocationStock {
  location_id: number;
  code: string;
  name: string;
  on_hand: number;
  reserved: number;
  available: number;
}

// ─── Constantes ───────────────────────────────────────────────────────────────

/** Ubicaciones de estante definidas en el contrato (U-100 es recepción) */
const SHELF_CODES = [
  "U-100", "U-101", "U-102", "U-103",
  "U-104", "U-105", "U-106", "U-107",
  "U-108", "U-109", "U-110", "U-111", "U-112",
];

// ─── Página principal ─────────────────────────────────────────────────────────

export default function HomePage() {
  const [activeTab, setActiveTab] = useState<string>("warehouse");
  const [shortageCount, setShortageCount] = useState<number>(0);

  // Carga la cantidad de faltantes abiertos para el badge del tab
  useEffect(() => {
    getShortages()
      .then((data) => setShortageCount(data.filter((s) => s.status === "open").length))
      .catch(() => setShortageCount(0));
  }, []);

  const tabs: Tab[] = [
    {
      id: "warehouse",
      label: "Almacén",
      icon: <Warehouse className="h-4 w-4" />,
    },
    {
      id: "orders",
      label: "Órdenes y Faltantes",
      icon: <ClipboardList className="h-4 w-4" />,
      count: shortageCount,
    },
    {
      id: "dispatch",
      label: "Despacho / Escáner",
      icon: <ScanLine className="h-4 w-4" />,
    },
  ];

  return (
    <div className="space-y-6">
      <TabBar tabs={tabs} activeTab={activeTab} onChange={setActiveTab} />

      <div
        id="tabpanel-warehouse"
        role="tabpanel"
        aria-labelledby="tab-warehouse"
        hidden={activeTab !== "warehouse"}
      >
        <WarehouseTab />
      </div>

      <div
        id="tabpanel-orders"
        role="tabpanel"
        aria-labelledby="tab-orders"
        hidden={activeTab !== "orders"}
      >
        <OrdersTab onShortageCountChange={setShortageCount} />
      </div>

      <div
        id="tabpanel-dispatch"
        role="tabpanel"
        aria-labelledby="tab-dispatch"
        hidden={activeTab !== "dispatch"}
      >
        <DispatchTab />
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// PESTAÑA 1 — ALMACÉN
// ═══════════════════════════════════════════════════════════════════════════════

function WarehouseTab() {
  const [locations, setLocations] = useState<LocationStock[]>([]);
  const [suggestions, setSuggestions] = useState<ReorderSuggestion[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Carga saldos por ubicación consultando disponibilidad de todas las ubicaciones
      const res = await fetch("/api/locations/stock-summary");
      if (res.ok) {
        const data: LocationStock[] = await res.json();
        setLocations(data);
      } else {
        // Fallback: mostrar ubicaciones vacías con códigos del contrato
        setLocations(
          SHELF_CODES.map((code, i) => ({
            location_id: 100 + i,
            code,
            name: code === "U-100" ? "Recepción" : `Estante ${code}`,
            on_hand: 0,
            reserved: 0,
            available: 0,
          }))
        );
      }
      const sugg = await getReorderSuggestions();
      setSuggestions(sugg);
    } catch (err) {
      setError("No se pudo conectar con el backend.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-6">
      {/* Encabezado con refresh */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Existencias por Ubicación</h2>
          <p className="text-sm text-muted-foreground">
            Saldos en tiempo real — on_hand, reservado y disponible
          </p>
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground hover:text-foreground hover:bg-accent disabled:opacity-50 transition-colors"
          aria-label="Actualizar saldos"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
          Actualizar
        </button>
      </div>

      {error && <ErrorBanner message={error} />}

      {/* Grid de tarjetas de estante */}
      {loading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {SHELF_CODES.map((code) => (
            <div key={code} className="card-shelf h-28 animate-pulse-slow bg-muted" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {locations.map((loc) => (
            <StockCard
              key={loc.location_id}
              locationCode={loc.code}
              locationName={loc.name}
              onHand={loc.on_hand}
              reserved={loc.reserved}
              available={loc.available}
            />
          ))}
        </div>
      )}

      {/* Sugerencias de reorden */}
      {suggestions.length > 0 && (
        <section className="space-y-3">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-amber-700 dark:text-amber-400">
            <AlertTriangle className="h-4 w-4" />
            Sugerencias de Reorden ({suggestions.length})
          </h3>
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="px-4 py-2.5 text-left font-medium text-muted-foreground">Pieza</th>
                  <th className="px-4 py-2.5 text-right font-medium text-muted-foreground">SKU</th>
                  <th className="px-4 py-2.5 text-right font-medium text-muted-foreground">Cant. sugerida</th>
                  <th className="px-4 py-2.5 text-right font-medium text-muted-foreground">Órdenes</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {suggestions.map((s) => (
                  <tr key={s.part_id} className="hover:bg-muted/30">
                    <td className="px-4 py-2.5 font-medium">{s.name}</td>
                    <td className="px-4 py-2.5 text-right font-mono text-xs text-muted-foreground">
                      {s.sku ?? "—"}
                    </td>
                    <td className="px-4 py-2.5 text-right font-semibold">
                      {formatQty(s.suggested_quantity)}
                    </td>
                    <td className="px-4 py-2.5 text-right text-muted-foreground">
                      {s.work_order_ids.length}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// PESTAÑA 2 — ÓRDENES Y FALTANTES
// ═══════════════════════════════════════════════════════════════════════════════

interface OrdersTabProps {
  onShortageCountChange: (n: number) => void;
}

function OrdersTab({ onShortageCountChange }: OrdersTabProps) {
  const [searchCode, setSearchCode] = useState("");
  const [orderData, setOrderData] = useState<WorkOrderMaterials | null>(null);
  const [shortages, setShortages] = useState<Shortage[]>([]);
  const [loadingOrder, setLoadingOrder] = useState(false);
  const [loadingShortages, setLoadingShortages] = useState(true);
  const [orderError, setOrderError] = useState<string | null>(null);

  // Carga faltantes al montar
  useEffect(() => {
    getShortages()
      .then((data) => {
        const open = data.filter((s) => s.status === "open");
        setShortages(open);
        onShortageCountChange(open.length);
      })
      .catch(() => setShortages([]))
      .finally(() => setLoadingShortages(false));
  }, [onShortageCountChange]);

  const searchOrder = async () => {
    if (!searchCode.trim()) return;
    setLoadingOrder(true);
    setOrderError(null);
    setOrderData(null);
    try {
      const data = await getWorkOrderMaterials(searchCode.trim().toUpperCase());
      setOrderData(data);
    } catch {
      setOrderError(`No se encontró la orden "${searchCode.trim().toUpperCase()}".`);
    } finally {
      setLoadingOrder(false);
    }
  };

  return (
    <div className="space-y-8">
      {/* ── Buscador de Orden ── */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Buscar Orden de Trabajo</h2>
        <form
          onSubmit={(e) => { e.preventDefault(); searchOrder(); }}
          className="flex gap-2"
        >
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              placeholder="Código de orden (ej: R061026012)"
              value={searchCode}
              onChange={(e) => setSearchCode(e.target.value)}
              className="w-full rounded-md border border-input bg-background pl-9 pr-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          <button
            type="submit"
            disabled={loadingOrder || !searchCode.trim()}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
          >
            {loadingOrder ? "Buscando…" : "Buscar"}
          </button>
        </form>

        {orderError && <ErrorBanner message={orderError} />}

        {orderData && (
          <div className="rounded-lg border border-border overflow-hidden">
            {/* Encabezado de la orden */}
            <div className="flex flex-wrap items-center gap-4 bg-muted/40 px-4 py-3 border-b border-border">
              <div>
                <p className="text-xs text-muted-foreground">Código</p>
                <p className="font-mono font-semibold">{orderData.code}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Etapa actual</p>
                <p className="text-sm font-medium">
                  {STAGE_LABELS[orderData.current_stage] ?? orderData.current_stage}
                </p>
              </div>
            </div>

            {/* Tabla de materiales */}
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-muted/30">
                  <tr>
                    <th className="px-4 py-2.5 text-left font-medium text-muted-foreground">Pieza</th>
                    <th className="px-4 py-2.5 text-right font-medium text-muted-foreground">Reservado</th>
                    <th className="px-4 py-2.5 text-right font-medium text-muted-foreground">Entregado</th>
                    <th className="px-4 py-2.5 text-right font-medium text-muted-foreground">Faltante</th>
                    <th className="px-4 py-2.5 text-center font-medium text-muted-foreground">Estado</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {orderData.lines.map((line) => {
                    const hasShortage = (line.shortage ?? 0) > 0;
                    const isComplete = line.delivered >= line.reserved && line.reserved > 0;
                    return (
                      <tr key={line.inspection_item_id} className="hover:bg-muted/20">
                        <td className="px-4 py-2.5">
                          <p className="font-medium">{line.name}</p>
                          {line.part_id == null && (
                            <p className="text-xs text-amber-600">Sin identificar</p>
                          )}
                        </td>
                        <td className="px-4 py-2.5 text-right tabular-nums">{formatQty(line.reserved)}</td>
                        <td className="px-4 py-2.5 text-right tabular-nums">{formatQty(line.delivered)}</td>
                        <td className={cn(
                          "px-4 py-2.5 text-right tabular-nums font-medium",
                          hasShortage && "text-red-600 dark:text-red-400"
                        )}>
                          {hasShortage ? formatQty(line.shortage) : "—"}
                        </td>
                        <td className="px-4 py-2.5 text-center">
                          {isComplete ? (
                            <Badge variant="ok">
                              <CheckCircle2 className="mr-1 h-3 w-3" />
                              Completo
                            </Badge>
                          ) : hasShortage ? (
                            <Badge variant="zero">
                              <XCircle className="mr-1 h-3 w-3" />
                              Faltante
                            </Badge>
                          ) : (
                            <Badge variant="reserved">Reservado</Badge>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </section>

      {/* ── Faltantes Abiertos ── */}
      <section className="space-y-3">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <PackageX className="h-5 w-5 text-red-500" />
          Faltantes Abiertos
          {shortages.length > 0 && (
            <Badge variant="zero">{shortages.length}</Badge>
          )}
        </h2>

        {loadingShortages ? (
          <div className="space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-12 rounded-lg bg-muted animate-pulse-slow" />
            ))}
          </div>
        ) : shortages.length === 0 ? (
          <div className="flex items-center gap-2 rounded-lg border border-green-200 bg-green-50 dark:border-green-900/40 dark:bg-green-900/10 px-4 py-3 text-sm text-green-700 dark:text-green-400">
            <CheckCircle2 className="h-4 w-4 shrink-0" />
            No hay faltantes abiertos en este momento.
          </div>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-sm">
              <thead className="bg-muted/50">
                <tr>
                  <th className="px-4 py-2.5 text-left font-medium text-muted-foreground">Pieza</th>
                  <th className="px-4 py-2.5 text-left font-medium text-muted-foreground">Orden</th>
                  <th className="px-4 py-2.5 text-right font-medium text-muted-foreground">Cantidad</th>
                  <th className="px-4 py-2.5 text-right font-medium text-muted-foreground">Detectado</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {shortages.map((s) => (
                  <tr key={s.shortage_id} className="hover:bg-muted/20">
                    <td className="px-4 py-2.5">
                      <p className="font-medium">{s.name}</p>
                      {s.part_id == null && (
                        <p className="text-xs text-amber-600 dark:text-amber-400">Sin identificar</p>
                      )}
                    </td>
                    <td className="px-4 py-2.5 font-mono text-xs text-muted-foreground">
                      WO-{s.work_order_id}
                    </td>
                    <td className="px-4 py-2.5 text-right font-semibold text-red-600 dark:text-red-400">
                      {s.missing_quantity != null ? formatQty(s.missing_quantity) : "?"}
                    </td>
                    <td className="px-4 py-2.5 text-right text-xs text-muted-foreground">
                      {formatDate(s.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════════════════
// PESTAÑA 3 — DESPACHO / ESCÁNER
// ═══════════════════════════════════════════════════════════════════════════════

type DispatchMode = "issue" | "transfer" | "count";

function DispatchTab() {
  const [mode, setMode] = useState<DispatchMode>("issue");
  const [scanning, setScanning] = useState(false);
  const [scanTarget, setScanTarget] = useState<"location" | "part" | null>(null);
  const [scannedLocation, setScannedLocation] = useState("");
  const [scannedPart, setScannedPart] = useState("");
  const [orderCode, setOrderCode] = useState("");
  const [quantity, setQuantity] = useState("");
  const [reason, setReason] = useState("");
  const [feedback, setFeedback] = useState<{ type: "ok" | "error"; msg: string } | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const scannerRef = useRef<HTMLDivElement>(null);

  // Inicializa html5-qrcode (solo en cliente, evita SSR)
  const startScanner = useCallback(async (target: "location" | "part") => {
    setScanTarget(target);
    setScanning(true);
    try {
      const { Html5QrcodeScanner } = await import("html5-qrcode");
      const scanner = new Html5QrcodeScanner(
        "qr-reader",
        { fps: 10, qrbox: { width: 250, height: 100 }, formatsToSupport: [1] /* CODE_128 */ },
        false
      );
      scanner.render(
        (decodedText: string) => {
          scanner.clear().catch(() => {});
          setScanning(false);
          if (target === "location") setScannedLocation(decodedText.trim());
          else setScannedPart(decodedText.trim());
          setFeedback({ type: "ok", msg: `Escaneado: ${decodedText.trim()}` });
          setTimeout(() => setFeedback(null), 3000);
        },
        () => {} // onError silencioso
      );
    } catch {
      setScanning(false);
      setFeedback({ type: "error", msg: "No se pudo iniciar la cámara." });
    }
  }, []);

  const reset = () => {
    setScannedLocation("");
    setScannedPart("");
    setOrderCode("");
    setQuantity("");
    setReason("");
    setFeedback(null);
    setScanning(false);
    setScanTarget(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!scannedPart || !scannedLocation || !quantity) {
      setFeedback({ type: "error", msg: "Completa todos los campos requeridos." });
      return;
    }
    setSubmitting(true);
    setFeedback(null);
    try {
      const qty = parseInt(quantity, 10);
      if (mode === "issue") {
        if (!orderCode) throw new Error("Ingresa el código de orden.");
        await postIssue({
          work_order_code: orderCode.toUpperCase(),
          part_id: parseInt(scannedPart, 10),
          location_id: parseInt(scannedLocation, 10),
          quantity: qty,
          issued_by: "operador",
        });
        setFeedback({ type: "ok", msg: "✓ Salida registrada correctamente." });
      } else if (mode === "transfer") {
        await postTransfer({
          part_id: parseInt(scannedPart, 10),
          from_location_id: parseInt(scannedLocation, 10),
          to_location_id: 0, // se ingresa destino en campo adicional
          quantity: qty,
        });
        setFeedback({ type: "ok", msg: "✓ Transferencia registrada." });
      } else if (mode === "count") {
        if (!reason) throw new Error("El motivo del ajuste es obligatorio.");
        await postCount({
          part_id: parseInt(scannedPart, 10),
          location_id: parseInt(scannedLocation, 10),
          counted_quantity: qty,
          reason,
        });
        setFeedback({ type: "ok", msg: "✓ Conteo cíclico registrado." });
      }
      reset();
    } catch (err) {
      setFeedback({
        type: "error",
        msg: err instanceof Error ? err.message : "Error al registrar la operación.",
      });
    } finally {
      setSubmitting(false);
    }
  };

  const modeLabels: Record<DispatchMode, string> = {
    issue: "Salida contra orden",
    transfer: "Transferencia",
    count: "Conteo cíclico",
  };

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div>
        <h2 className="text-lg font-semibold">Operaciones de Piso</h2>
        <p className="text-sm text-muted-foreground">
          Escanea los códigos de barras con la cámara de tu celular.
        </p>
      </div>

      {/* Selector de modo */}
      <div className="flex rounded-lg border border-border overflow-hidden">
        {(["issue", "transfer", "count"] as DispatchMode[]).map((m) => (
          <button
            key={m}
            onClick={() => { setMode(m); reset(); }}
            className={cn(
              "flex-1 px-3 py-2.5 text-xs font-medium transition-colors",
              mode === m
                ? "bg-primary text-primary-foreground"
                : "bg-background text-muted-foreground hover:bg-muted"
            )}
          >
            {modeLabels[m]}
          </button>
        ))}
      </div>

      {/* Área de escáner */}
      <div className="rounded-lg border border-dashed border-border bg-muted/20 p-4 space-y-3">
        {scanning ? (
          <div className="space-y-2">
            <p className="text-xs text-center text-muted-foreground">
              Apunta la cámara al código de barras Code 128
            </p>
            <div id="qr-reader" ref={scannerRef} className="w-full" />
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            <ScanField
              label="Ubicación"
              value={scannedLocation}
              placeholder="U-100"
              onScan={() => startScanner("location")}
              onChange={setScannedLocation}
              active={scanTarget === "location"}
            />
            <ScanField
              label="Pieza (ID)"
              value={scannedPart}
              placeholder="305"
              onScan={() => startScanner("part")}
              onChange={setScannedPart}
              active={scanTarget === "part"}
            />
          </div>
        )}
      </div>

      {/* Formulario de la operación */}
      <form onSubmit={handleSubmit} className="space-y-4">
        {mode === "issue" && (
          <FormField
            label="Código de orden *"
            type="text"
            placeholder="R061026012"
            value={orderCode}
            onChange={setOrderCode}
          />
        )}

        <FormField
          label="Cantidad *"
          type="number"
          placeholder="1"
          value={quantity}
          onChange={setQuantity}
          min="1"
        />

        {mode === "count" && (
          <FormField
            label="Motivo del ajuste *"
            type="text"
            placeholder="Conteo físico periódico"
            value={reason}
            onChange={setReason}
          />
        )}

        {feedback && (
          <div
            className={cn(
              "flex items-start gap-2 rounded-md px-3 py-2.5 text-sm",
              feedback.type === "ok"
                ? "bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400"
                : "bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-400"
            )}
            role="alert"
          >
            {feedback.type === "ok"
              ? <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5" />
              : <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" />}
            {feedback.msg}
          </div>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-md bg-primary py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          {submitting ? "Registrando…" : `Confirmar ${modeLabels[mode]}`}
        </button>
      </form>
    </div>
  );
}

// ─── Subcomponentes auxiliares ────────────────────────────────────────────────

interface ScanFieldProps {
  label: string;
  value: string;
  placeholder: string;
  onScan: () => void;
  onChange: (v: string) => void;
  active: boolean;
}

function ScanField({ label, value, placeholder, onScan, onChange, active }: ScanFieldProps) {
  return (
    <div className="space-y-1.5">
      <label className="text-xs font-medium text-muted-foreground">{label}</label>
      <div className="flex gap-1.5">
        <input
          type="text"
          placeholder={placeholder}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="min-w-0 flex-1 rounded-md border border-input bg-background px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        />
        <button
          type="button"
          onClick={onScan}
          className={cn(
            "rounded-md border px-2 py-1.5 transition-colors",
            active
              ? "border-primary bg-primary/10 text-primary"
              : "border-border bg-background text-muted-foreground hover:text-foreground hover:bg-accent"
          )}
          aria-label={`Escanear ${label}`}
          title="Abrir cámara"
        >
          <Camera className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}

interface FormFieldProps {
  label: string;
  type: string;
  placeholder: string;
  value: string;
  onChange: (v: string) => void;
  min?: string;
}

function FormField({ label, type, placeholder, value, onChange, min }: FormFieldProps) {
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium">{label}</label>
      <input
        type={type}
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        min={min}
        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
      />
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div
      className="flex items-center gap-2 rounded-md border border-red-200 bg-red-50 dark:border-red-900/40 dark:bg-red-900/10 px-4 py-3 text-sm text-red-700 dark:text-red-400"
      role="alert"
    >
      <AlertTriangle className="h-4 w-4 shrink-0" />
      {message}
    </div>
  );
}
