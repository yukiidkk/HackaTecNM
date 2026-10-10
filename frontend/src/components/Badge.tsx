import { cn } from "@/lib/utils";

export type BadgeVariant = "ok" | "low" | "zero" | "reserved" | "default" | "warning";

interface BadgeProps {
  variant?: BadgeVariant;
  children: React.ReactNode;
  className?: string;
}

const variantClasses: Record<BadgeVariant, string> = {
  ok:       "badge-ok",
  low:      "badge-low",
  zero:     "badge-zero",
  reserved: "badge-reserved",
  warning:  "bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400",
  default:  "bg-secondary text-secondary-foreground",
};

/**
 * Badge de estado reutilizable.
 * Uso: <Badge variant="ok">Disponible</Badge>
 */
export default function Badge({
  variant = "default",
  children,
  className,
}: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium",
        variantClasses[variant],
        className
      )}
    >
      {children}
    </span>
  );
}
