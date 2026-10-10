import type { Metadata, Viewport } from "next";
import "./globals.css";

// Usamos fuente del sistema para evitar requests a Google Fonts en build time
// (entornos con TLS corporativo bloquean esa descarga).
// El CSS define font-family: system-ui como fallback limpio.

export const metadata: Metadata = {
  title: {
    default: "Almacén Inteligente",
    template: "%s | Almacén Inteligente",
  },
  description:
    "Sistema de inventario en tiempo real para taller de reparación de husillos y motores industriales.",
  manifest: "/manifest.json",
};

// Viewport separado de metadata (requerido en Next.js 14)
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1, // Evita zoom accidental en inputs móviles
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f8fafc" },
    { media: "(prefers-color-scheme: dark)",  color: "#0d1117" },
  ],
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es" suppressHydrationWarning>
      <body className="min-h-screen bg-background font-sans antialiased">
        {/* Header global */}
        <header className="sticky top-0 z-50 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
          <div className="mx-auto flex h-14 max-w-screen-xl items-center gap-3 px-4">
            {/* Ícono industrial */}
            <div className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="h-4 w-4"
                aria-hidden="true"
              >
                <path d="M2 20a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8l-7-7H4a2 2 0 0 0-2 2v17z" />
                <path d="M14 2v6h6" />
                <path d="M12 18v-6" />
                <path d="M8 18v-1" />
                <path d="M16 18v-3" />
              </svg>
            </div>
            <div>
              <span className="text-sm font-semibold leading-none">
                Almacén Inteligente
              </span>
              <p className="text-xs text-muted-foreground">Taller Industrial</p>
            </div>

            {/* Indicador de conexión — placeholder */}
            <div className="ml-auto flex items-center gap-1.5">
              <span
                className="h-2 w-2 rounded-full bg-green-500"
                aria-label="Conectado"
              />
              <span className="text-xs text-muted-foreground hidden sm:inline">
                En línea
              </span>
            </div>
          </div>
        </header>

        {/* Contenido de la página */}
        <main className="mx-auto max-w-screen-xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
