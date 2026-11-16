import { useEffect, useRef } from "react";

import { SafraSymbol, SideNav, StatusBadge, ToastProvider, type NavGroup } from "@safra/ui";

import { BusyProvider, useSymbolState } from "./activity";
import { ConnectionBanner } from "./components";
import { ConnectionProvider, useConnection } from "./connection";
import { PreferencesProvider, useReducedMotion } from "./preferences";
import { href, useRoute, type Route } from "./router";
import { AiPage } from "./pages/Ai";
import { ConsolePage } from "./pages/Console";
import { ConversationsPage } from "./pages/Conversations";
import { HistoryPage } from "./pages/History";
import { HomePage } from "./pages/Home";
import { MemoryPage } from "./pages/Memory";
import { MonitoringPage } from "./pages/Monitoring";
import { NotFoundPage } from "./pages/NotFound";
import { ProfilePage } from "./pages/Profile";
import { ProjectsPage } from "./pages/Projects";
import { SettingsPage } from "./pages/Settings";
import { ToolsPage } from "./pages/Tools";

export const NAV: NavGroup[] = [
  { items: [
    { id: "inicio", label: "Início", href: href("/"), icon: "inicio" },
    { id: "conversas", label: "Conversas", href: href("/conversas"), icon: "conversa" },
    { id: "historico", label: "Histórico", href: href("/historico"), icon: "historico" },
  ] },
  { label: "Organização", items: [
    { id: "projetos", label: "Projetos", href: href("/projetos"), icon: "projetos" },
    { id: "memoria", label: "Memória", href: href("/memoria"), icon: "memoria" },
  ] },
  { label: "Assistente", items: [
    { id: "ferramentas", label: "Ferramentas", href: href("/ferramentas"), icon: "ferramentas" },
    { id: "ia", label: "Inteligência artificial", href: href("/ia"), icon: "ia" },
  ] },
  { label: "Sistema", items: [
    { id: "monitoramento", label: "Monitoramento", href: href("/monitoramento"), icon: "monitoramento" },
    { id: "console", label: "Console", href: href("/console"), icon: "painel" },
    { id: "configuracoes", label: "Configurações", href: href("/configuracoes"), icon: "configuracoes" },
    { id: "perfil", label: "Perfil e preferências", href: href("/perfil"), icon: "perfil" },
  ] },
];

function Page({ route }: { route: Route }) {
  switch (route.name) {
    case "inicio": return <HomePage />;
    case "conversas": return <ConversationsPage id={route.id} />;
    case "historico": return <HistoryPage />;
    case "projetos": return <ProjectsPage id={route.id} />;
    case "memoria": return <MemoryPage />;
    case "ferramentas": return <ToolsPage />;
    case "ia": return <AiPage />;
    case "configuracoes": return <SettingsPage />;
    case "monitoramento": return <MonitoringPage />;
    case "perfil": return <ProfilePage />;
    case "console": return <ConsolePage />;
    default: return <NotFoundPage />;
  }
}

function Brand() {
  const state = useSymbolState();
  const reduced = useReducedMotion();
  return (
    <a className="marca" href={href("/")} aria-label="SAFRA — início">
      <SafraSymbol state={state} size={32} reducedMotion={reduced} />
      <span className="marca__nome">SAFRA</span>
    </a>
  );
}

function ConnectionFooter() {
  const { state, health } = useConnection();
  const tone = state === "conectado" ? (health?.status === "ok" ? "sucesso" : "atencao") : state === "conectando" ? "informacao" : "erro";
  const text = state === "conectado" ? (health?.status === "ok" ? "conectado" : "com problemas") : state === "conectando" ? "conectando" : state === "reconectando" ? "reconectando" : "sem conexão";
  return (
    <div className="rodape-navegacao">
      <StatusBadge tone={tone}>{text}</StatusBadge>
      {health && <span className="rodape-navegacao__versao">Assistant {health.version}</span>}
    </div>
  );
}

function Shell() {
  const route = useRoute();
  const main = useRef<HTMLElement>(null);
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    // ao trocar de área, o foco vai para o título (leitores de tela anunciam a página nova)
    window.scrollTo(0, 0);
    const title = document.getElementById("titulo-da-pagina");
    (title ?? main.current)?.focus({ preventScroll: true });
  }, [route]);
  const current = route.name === "nao-encontrada" ? "" : route.name;
  return (
    <div className="app">
      <a className="pular" href="#conteudo" onClick={(event) => { event.preventDefault(); main.current?.focus(); }}>
        Pular para o conteúdo
      </a>
      <aside className="app__lateral">
        <SideNav label="Áreas do SAFRA" groups={NAV} current={current} header={<Brand />} footer={<ConnectionFooter />} />
      </aside>
      <main className="app__conteudo" id="conteudo" ref={main} tabIndex={-1}>
        <ConnectionBanner />
        <Page route={route} />
      </main>
    </div>
  );
}

export function App({ pollMs }: { pollMs?: number } = {}) {
  return (
    <ConnectionProvider pollMs={pollMs}>
      <PreferencesProvider>
        <BusyProvider>
          <ToastProvider>
            <Shell />
          </ToastProvider>
        </BusyProvider>
      </PreferencesProvider>
    </ConnectionProvider>
  );
}
