import { AppShell } from "@/components/AppShell";
import { getSystemStatus, type SystemStatus } from "@/lib/api";
import { requireSession } from "@/lib/auth";

export const dynamic = "force-dynamic";

export default async function AuthenticatedLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await requireSession();
  let status: SystemStatus | null = null;
  try {
    status = await getSystemStatus();
  } catch {
    status = null;
  }
  return (
    <AppShell session={session} status={status}>
      {children}
    </AppShell>
  );
}
