// Formas dos dados devolvidos pela API do painel (backend/portal/src/safra_portal/api/admin.py).

export type Permission =
  | "admin.access" | "dashboard.read" | "content.read" | "content.edit" | "content.publish" | "content.delete"
  | "categories.manage" | "media.read" | "media.upload" | "media.delete" | "homepage.edit" | "releases.manage"
  | "users.manage" | "audit.read";

export interface Identity {
  user: { id: number; email: string; name: string; role: string; role_name: string };
  permissions: Permission[];
  csrf_token: string;
}

export type ContentKind = "pages" | "news";

export interface ContentSummary {
  id: number;
  type: "page" | "news";
  slug: string;
  title: string;
  summary: string;
  status: "draft" | "published";
  lock_version: number;
  category_id: number | null;
  cover_media_id: number | null;
  published_at: string | null;
  updated_at: string;
  has_unpublished_changes: boolean;
  public_path: string | null;
  preview_path: string;
}

export interface Content extends ContentSummary {
  blocks: Block[];
  seo_title: string;
  seo_description: string;
}

export interface Version {
  id: number;
  number: number;
  title: string;
  kind: "save" | "restore" | "seed";
  note: string;
  author: string;
  created_at: string;
  published: boolean;
}

export type Tag = "" | "implementado" | "em desenvolvimento" | "planejado";

export type Block =
  | { type: "heading"; level: 2 | 3; text: string }
  | { type: "paragraph"; text: string }
  | { type: "list"; ordered: boolean; items: string[] }
  | { type: "quote"; text: string; cite: string }
  | { type: "callout"; tone: "info" | "attention" | "status"; title: string; text: string }
  | { type: "image"; media_id: number; caption: string }
  | { type: "cards"; items: { title: string; text: string; tag: Tag }[] }
  | { type: "faq"; items: { question: string; answer: string }[] }
  | { type: "button"; label: string; href: string }
  | { type: "divider" };

export type BlockType = Block["type"];

export interface Category { id: number; slug: string; name: string }

export interface Media {
  id: number;
  url: string;
  original_name: string;
  content_type: string;
  size: number;
  width: number | null;
  height: number | null;
  alt_text: string;
  category: string;
  created_at: string;
}

export interface Link { label: string; href: string }

export interface HomeSection {
  key: "features" | "hybrid_ai" | "security" | "status" | "news" | "resources";
  enabled: boolean;
  title: string;
  text: string;
  items: { title: string; text: string; tag: Tag }[];
  links: Link[];
}

export interface Homepage {
  title: string;
  subtitle: string;
  image_media_id: number | null;
  buttons: Link[];
  sections: HomeSection[];
  featured_news: number;
}

export interface SiteInfo {
  tagline: string;
  footer_text: string;
  footer_links: Link[];
  contact_email: string;
  contact_links: Link[];
}

export interface Release {
  id: number;
  version: string;
  platform: "windows";
  channel: "stable" | "beta" | "experimental";
  notes: string;
  status: "draft" | "published";
  published_at: string | null;
  updated_at: string;
}

export interface AdminUser {
  id: number;
  email: string;
  name: string;
  role: string;
  role_name: string;
  is_active: boolean;
  has_password: boolean;
  locked: boolean;
  last_login_at: string | null;
}

export interface RoleInfo { key: string; name: string; permissions: Permission[] }

export interface AuditEntry {
  id: number;
  action: string;
  actor: string;
  actor_id: number | null;
  target_type: string;
  target_id: string;
  detail: Record<string, unknown>;
  at: string;
}

export interface Dashboard {
  pages: { published: number; draft: number };
  news: { published: number; draft: number };
  media: number;
  recent_changes: ContentSummary[];
  activity: AuditEntry[];
  downloads_blocked: boolean;
}

export interface SessionInfo {
  id: number;
  current: boolean;
  ip: string;
  user_agent: string;
  created_at: string;
  last_seen_at: string;
}
