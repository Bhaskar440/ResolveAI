import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ResolveAI — dispute control tower",
  description:
    "Autonomous PayPal dispute resolution with a deterministic policy gate and human approval.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen antialiased">{children}</body>
    </html>
  );
}
