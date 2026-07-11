import type { Metadata, Viewport } from "next";
import "./globals.css";
export const metadata: Metadata = { title: "Workout Sync", description: "Notion vers Intervals.icu", manifest: "/manifest.webmanifest" };
export const viewport: Viewport = { themeColor: "#d8742a", width: "device-width", initialScale: 1 };
export default function RootLayout({ children }: { children: React.ReactNode }) { return <html lang="fr"><body>{children}</body></html>; }
