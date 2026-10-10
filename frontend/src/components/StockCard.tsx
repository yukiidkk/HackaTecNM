import { cn, formatQty, stockBadgeClass } from "@/lib/utils";
import Badge from "./Badge";
import type { BadgeVariant } from "./Badge";

interface StockCardProps {
  locationCode: string;
  locationName: string;
  onHand: number;
  reserved: number;
  available: number;
  /** Mínimo de stock para determinar si está bajo */
  minStock?: number;
  className?: string;
  /** Callback al hacer clic — útil para despacho */
  onClick?: () => void;
}

/**
 * Tarjeta de estante/ubicación con saldo de inventario.
 * Muestra on_hand, reserved y available con color semafórico.
 */
export default function StockCard({
  locationCode,
  locationName,
  onHand,
  reserved,
  available,
  minStock = 1,
  className,
  onClick,
}: StockCardProps) {
  // Determinar variante del badge según nivel de stock
  const badgeVariantMap: Record<string, BadgeVariant> = {
    "badge-ok":       "ok",
    "badge-low":      "low",
    "badge-zero":     "zero",
    "badge-reserved": "reserved",
  };
  const badgeClass = stockBadgeClass(onHand, available, minStock);
  const badgeVariant = badgeVariantMap[badgeClass] ?? "default";

  const stockLabel =
    onHand === 0 ? "Sin stock" :
    available < minStock ? "Stock bajo" :
    "Disponible";

  return (
    <div
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={onClick ? (e) => e.key === "Enter" && onClick() : undefined}
      className={cn(
        "card-shelf p-4 flex flex-col gap-3",
        onClick && "cursor-pointer hover:border-primary/50 focus:outline-none focus:ring-2 focus:ring-ring",
        className
      )}
    >
      {/* Encabezado: código y badge de estado */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs font-mono font-semibold text-muted-foreground uppercase tracking-wider">
            {locationCode}
          </p>
          <p className="mt-0.5 truncate text-sm font-medium text-foreground">
            {locationName}
          </p>
        </div>
        <Badge variant={badgeVariant}>{stockLabel}</Badge>
      </div>

      {/* Métricas de stock */}
      <div className="grid grid-cols-3 divide-x divide-border rounded-md border border-border">
        <Metric label="En mano" value={formatQty(onHand)} />
        <Metric label="Reservado" value={formatQty(reserved)} highlight="reserved" />
        <Metric
          label="Disponible"
          value={formatQty(available)}
          highlight={available === 0 ? "zero" : available < minStock ? "low" : undefined}
        />
      </div>
    </div>
  );
}

// ─── Subcomponente métrica ───────────────────────────────────────────────────

interface MetricProps {
  label: string;
  value: string;
  highlight?: "zero" | "low" | "reserved";
}

function Metric({ label, value, highlight }: MetricProps) {
  const valueColor =
    highlight === "zero"     ? "text-red-600 dark:text-red-400" :
    highlight === "low"      ? "text-amber-600 dark:text-amber-400" :
    highlight === "reserved" ? "text-blue-600 dark:text-blue-400" :
    "text-foreground";

  return (
    <div className="flex flex-col items-center gap-0.5 px-2 py-2">
      <span className={cn("text-base font-bold tabular-nums", valueColor)}>
        {value}
      </span>
      <span className="text-[10px] text-muted-foreground">{label}</span>
    </div>
  );
}
