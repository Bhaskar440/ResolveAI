import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { getAuthSession, SESSION_COOKIE, type AuthSession } from "./api";

export async function readSession(): Promise<AuthSession | null> {
  const store = await cookies();
  const token = store.get(SESSION_COOKIE)?.value;
  if (!token) return null;
  try {
    return await getAuthSession(token);
  } catch {
    return null;
  }
}

export async function requireSession(): Promise<AuthSession> {
  const session = await readSession();
  if (!session) redirect("/login");
  return session;
}
