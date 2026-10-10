import { redirect } from "next/navigation";

/**
 * /dashboard redirige a la raíz donde vive el dashboard con pestañas.
 * Mantiene compatibilidad con links externos o bookmarks viejos.
 */
export default function DashboardRedirect() {
  redirect("/");
}
