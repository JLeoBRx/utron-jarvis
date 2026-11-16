// Navegação por âncora (#/rota): o Portal serve um único index.html em /admin/, sem regra de reescrita.
import { useEffect, useState } from "react";

export function currentRoute(): string[] {
  const hash = window.location.hash.replace(/^#\/?/, "");
  return hash.split("/").filter(Boolean).map(decodeURIComponent);
}

export function useRoute(): string[] {
  const [route, setRoute] = useState(currentRoute);
  useEffect(() => {
    const update = () => setRoute(currentRoute());
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  return route;
}

export function go(path: string): void {
  window.location.hash = "#/" + path.replace(/^\/+/, "");
}

export function href(path: string): string {
  return "#/" + path.replace(/^\/+/, "");
}
