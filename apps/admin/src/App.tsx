import { useCallback, useEffect, useMemo, useState } from "react";

import { ApiError, get, post, setCsrfToken } from "./api";
import { ErrorBox, Loading, Symbol } from "./components/ui";
import { AccountPage } from "./pages/AccountPage";
import { AuditPage } from "./pages/AuditPage";
import { CategoriesPage } from "./pages/CategoriesPage";
import { ContentEditor } from "./pages/ContentEditor";
import { ContentList } from "./pages/ContentList";
import { DashboardPage } from "./pages/DashboardPage";
import { HomepagePage } from "./pages/HomepagePage";
import { LoginPage, RecoverPage } from "./pages/LoginPage";
import { MediaPage } from "./pages/MediaPage";
import { ReleasesPage } from "./pages/ReleasesPage";
import { UsersPage } from "./pages/UsersPage";
import { href, useRoute } from "./router";
import { makeCan, SessionContext, useSession, type SessionValue } from "./session";
import type { Identity, Permission } from "./types";

interface NavItem { path: string; label: string; permission: Permission }

export const NAV: NavItem[] = [
  { path: "", label: "Resumo", permission: "dashboard.read" },
  { path: "pages", label: "Páginas", permission: "content.read" },
  { path: "news", label: "Notícias", permission: "content.read" },
  { path: "categories", label: "Categorias", permission: "categories.manage" },
  { path: "media", label: "Mídia", permission: "media.read" },
  { path: "homepage", label: "Página inicial", permission: "homepage.edit" },
  { path: "releases", label: "Downloads", permission: "releases.manage" },
  { path: "users", label: "Usuários", permission: "users.manage" },
  { path: "audit", label: "Auditoria", permission: "audit.read" },
];

export function visibleNav(permissions: Permission[]): NavItem[] {
  const granted = new Set(permissions);
  return NAV.filter((item) => granted.has(item.permission));
}

export function App() {
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [checking, setChecking] = useState(true);
  const [failure, setFailure] = useState<unknown>(null);
  const route = useRoute();

  const accept = useCallback((value: Identity) => {
    setCsrfToken(value.csrf_token);
    setIdentity(value);
  }, []);

  const check = useCallback(() => {
    setChecking(true);
    setFailure(null);
    get<Identity>("/auth/session")
      .then(accept)
      .catch((e) => {
        if (!(e instanceof ApiError && e.status === 401)) setFailure(e);
        setIdentity(null);
      })
      .finally(() => setChecking(false));
  }, [accept]);

  useEffect(check, [check]);

  const session = useMemo<SessionValue | null>(() => identity && {
    identity,
    can: makeCan(identity),
    signOut: async () => {
      try {
        await post("/auth/logout");
      } finally {
        setCsrfToken("");
        setIdentity(null);
        window.location.hash = "#/";
      }
    },
  }, [identity]);

  if (checking) return <main className="tela-cheia"><Loading label="Verificando a sessão…" /></main>;
  if (failure) return <main className="tela-cheia"><ErrorBox error={failure} onRetry={check} /></main>;
  if (route[0] === "recuperar") return <RecoverPage />;
  if (!session) return <LoginPage onSignedIn={accept} />;
  return (
    <SessionContext.Provider value={session}>
      <Shell route={route} />
    </SessionContext.Provider>
  );
}

function Shell({ route }: { route: string[] }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const session = useSession();
  const items = visibleNav(session.identity.permissions);
  const section = route[0] ?? "";
  useEffect(() => setMenuOpen(false), [section, route[1]]);
  return (
    <div className="painel">
      <a className="pular" href="#principal" onClick={(e) => { e.preventDefault(); document.getElementById("principal")?.focus(); }}>Pular para o conteúdo</a>
      <header className="painel__topo">
        <a className="marca" href={href("")}><Symbol size={30} /><span>SAFRA</span><small>painel</small></a>
        <button type="button" className="botao botao--discreto painel__menu" aria-expanded={menuOpen} aria-controls="navegacao"
          onClick={() => setMenuOpen((open) => !open)}>Menu</button>
        <div className="painel__usuario">
          <a href={href("account")} className="painel__nome">{session.identity.user.name}<small>{session.identity.user.role_name}</small></a>
          <a className="botao botao--discreto" href="/" target="_blank" rel="noopener">Ver o site</a>
          <button type="button" className="botao botao--secundario" onClick={() => void session.signOut()}>Sair</button>
        </div>
      </header>
      <nav id="navegacao" className={`painel__nav${menuOpen ? " painel__nav--aberto" : ""}`} aria-label="Seções do painel">
        <ul>
          {items.map((item) => (
            <li key={item.path}>
              <a href={href(item.path)} aria-current={section === item.path ? "page" : undefined}>{item.label}</a>
            </li>
          ))}
        </ul>
      </nav>
      <main id="principal" className="painel__conteudo" tabIndex={-1}>
        <Page route={route} />
      </main>
    </div>
  );
}

function Page({ route }: { route: string[] }) {
  const { can } = useSession();
  const [section, id] = route;
  const denied = <ErrorBox error={new Error("Seu papel não dá acesso a esta seção.")} />;
  switch (section ?? "") {
    case "": return can("dashboard.read") ? <DashboardPage /> : denied;
    case "pages":
    case "news": {
      const kind = section as "pages" | "news";
      if (!can("content.read")) return denied;
      return id ? <ContentEditor kind={kind} id={id === "novo" ? null : Number(id)} key={`${kind}-${id}`} /> : <ContentList kind={kind} key={kind} />;
    }
    case "categories": return can("categories.manage") ? <CategoriesPage /> : denied;
    case "media": return can("media.read") ? <MediaPage /> : denied;
    case "homepage": return can("homepage.edit") ? <HomepagePage /> : denied;
    case "releases": return can("releases.manage") ? <ReleasesPage /> : denied;
    case "users": return can("users.manage") ? <UsersPage /> : denied;
    case "audit": return can("audit.read") ? <AuditPage /> : denied;
    case "account": return <AccountPage />;
    default: return <ErrorBox error={new Error("Seção não encontrada.")} />;
  }
}
