"use client";

import { cn } from "@/lib/utils";

export interface Tab {
  id: string;
  label: string;
  icon?: React.ReactNode;
  /** Número que aparece como badge (ej: faltantes abiertos) */
  count?: number;
}

interface TabBarProps {
  tabs: Tab[];
  activeTab: string;
  onChange: (id: string) => void;
  className?: string;
}

/**
 * Barra de pestañas horizontal reutilizable.
 * En móvil se hace scroll horizontal si las pestañas no caben.
 */
export default function TabBar({
  tabs,
  activeTab,
  onChange,
  className,
}: TabBarProps) {
  return (
    <div
      role="tablist"
      aria-label="Secciones principales"
      className={cn(
        "flex gap-1 overflow-x-auto border-b border-border pb-0 scrollbar-none",
        className
      )}
    >
      {tabs.map((tab) => {
        const isActive = tab.id === activeTab;
        return (
          <button
            key={tab.id}
            role="tab"
            aria-selected={isActive}
            aria-controls={`tabpanel-${tab.id}`}
            id={`tab-${tab.id}`}
            onClick={() => onChange(tab.id)}
            className={cn(
              // Base
              "relative flex shrink-0 items-center gap-2 whitespace-nowrap px-4 py-2.5 text-sm font-medium transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
              // Indicador inferior
              "border-b-2 -mb-px",
              isActive
                ? "border-primary text-primary"
                : "border-transparent text-muted-foreground hover:text-foreground hover:border-border"
            )}
          >
            {tab.icon && (
              <span className="h-4 w-4 shrink-0" aria-hidden="true">
                {tab.icon}
              </span>
            )}
            {tab.label}
            {tab.count != null && tab.count > 0 && (
              <span
                className={cn(
                  "ml-1 inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-[10px] font-semibold",
                  isActive
                    ? "bg-primary/10 text-primary"
                    : "bg-muted text-muted-foreground"
                )}
                aria-label={`${tab.count} elementos`}
              >
                {tab.count > 99 ? "99+" : tab.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
