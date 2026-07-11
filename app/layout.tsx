import type { Metadata, Viewport } from "next";
import Script from "next/script";
import "./globals.css";

export const metadata: Metadata = {
  title: "Workout Sync",
  description: "Notion vers Intervals.icu et Garmin",
  manifest: "/manifest.webmanifest",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#d8742a",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body>
        {children}
        <Script id="register-sw" strategy="afterInteractive">
          {`if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");`}
        </Script>
      </body>
    </html>
  );
}
