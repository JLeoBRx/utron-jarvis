const dateTime = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" });

export function when(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : dateTime.format(date);
}

export function bytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1).replace(".", ",")} KiB`;
  return `${(size / 1024 / 1024).toFixed(1).replace(".", ",")} MiB`;
}

const ACTIONS: Record<string, string> = {
  "login.ok": "entrou no painel", "login.failed": "tentativa de entrada recusada", "login.locked": "conta bloqueada por tentativas",
  "login.rate_limited": "limite de tentativas atingido", logout: "saiu do painel", "password.change": "trocou a senha",
  "recovery.create": "gerou código de recuperação", "recovery.used": "redefiniu a senha", "recovery.failed": "código de recuperação recusado",
  "user.create": "criou usuário", "user.update": "alterou usuário", "page.create": "criou página", "page.save": "salvou página",
  "page.publish": "publicou página", "page.unpublish": "despublicou página", "page.restore": "restaurou versão de página",
  "page.delete": "excluiu página", "news.create": "criou notícia", "news.save": "salvou notícia", "news.publish": "publicou notícia",
  "news.unpublish": "despublicou notícia", "news.restore": "restaurou versão de notícia", "news.delete": "excluiu notícia",
  "media.upload": "enviou imagem", "media.update": "alterou imagem", "media.delete": "removeu imagem",
  "category.create": "criou categoria", "category.update": "alterou categoria", "category.delete": "removeu categoria",
  "homepage.update": "alterou a página inicial", "site.update": "alterou os dados do site", "release.create": "cadastrou versão",
  "release.update": "alterou versão", "release.delete": "removeu versão", "release.publish_blocked": "tentou publicar versão (bloqueado)",
};

export function action(code: string): string {
  return ACTIONS[code] ?? code;
}
