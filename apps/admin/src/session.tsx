import { createContext, useContext } from "react";

import type { Identity, Permission } from "./types";

export interface SessionValue {
  identity: Identity;
  can: (permission: Permission) => boolean;
  signOut: () => Promise<void>;
}

export const SessionContext = createContext<SessionValue | null>(null);

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession fora de uma sessão");
  return value;
}

export function makeCan(identity: Identity): (permission: Permission) => boolean {
  const granted = new Set(identity.permissions);
  return (permission) => granted.has(permission);
}
