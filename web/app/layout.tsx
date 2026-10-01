import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";

import { ThemeProvider } from "@/components/ThemeProvider";

import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover" as const,
};

export const metadata: Metadata = {
  title: "Car Market Tracker",
  description:
    "Live depreciation tracking for Skoda listings from mobile.bg.",
  icons: {
    icon: [{ url: "/favicon.svg", type: "image/svg+xml" }],
  },
  openGraph: {
    title: "Car Market Tracker",
    description:
      "Live depreciation tracking for Skoda listings from mobile.bg.",
    images: [
      {
        url: "/og.jpg",
        width: 1376,
        height: 768,
        alt: "Car Market Tracker",
      },
    ],
  },
  twitter: {
    card: "summary_large_image",
    title: "Car Market Tracker",
    description:
      "Live depreciation tracking for Skoda listings from mobile.bg.",
    images: ["/og.jpg"],
  },
};

const themeBootScript = `(() => {
  try {
    const stored = localStorage.getItem("car-market-theme");
    const theme = stored === "light" ? "light" : "dark";
    const root = document.documentElement;
    root.classList.toggle("dark", theme === "dark");
    root.classList.toggle("light", theme === "light");
    root.style.colorScheme = theme;
  } catch (_) {}
})();`;

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootScript }} />
      </head>
      <body
        className={`${geistSans.variable} ${geistMono.variable} min-h-screen bg-[var(--bg)] text-[var(--fg)] antialiased`}
      >
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
