import type { Metadata, Viewport } from "next";
import { Hind_Siliguri } from "next/font/google";
import { ClerkProvider } from "@clerk/nextjs";
import { headers } from "next/headers";
import { NextIntlClientProvider } from "next-intl";
import { getLocale } from "next-intl/server";

import { InstallPrompt } from "@/components/layout/install-prompt";
import { RegisterServiceWorker } from "@/components/layout/register-service-worker";
import { SiteHeader } from "@/components/layout/site-header";

import { Providers } from "./providers";
import "./globals.css";

/**
 * Bangla needs a real Bengali face. Without one the script falls back to whatever the
 * device has — on low-end Android that is often a font with the wrong conjunct forms,
 * which native readers notice immediately.
 *
 * It is appended to the Latin stack rather than replacing it (see `--font-sans` in
 * globals.css): font fallback is per glyph, so English keeps the system face and only
 * Bengali codepoints reach Hind Siliguri. The weights are the two the UI actually uses.
 */
const bengali = Hind_Siliguri({
  subsets: ["bengali", "latin"],
  weight: ["400", "600"],
  variable: "--font-bengali",
  display: "swap",
});

export const metadata: Metadata = {
  // Absolute URLs for Open Graph images: a shared scorecard link is previewed by
  // Messenger and WhatsApp from their own servers, where a relative path means nothing.
  metadataBase: new URL(process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000"),
  title: "TurfApp",
  description: "Book sports turfs in Bangladesh, fill your match, build your profile.",
};

/**
 * Installed, the app has no browser chrome, so the status bar takes its colour from
 * here. `maximum-scale` is deliberately left alone: pinch-zoom is an accessibility
 * feature and blocking it on a phone-first app would be a mistake.
 */
export const viewport: Viewport = {
  themeColor: "#16a34a",
  width: "device-width",
  initialScale: 1,
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // Locale comes from the cookie, resolved in src/i18n/request.ts (no URL prefix, D13).
  const locale = await getLocale();

  // Clerk renders its own <script src>, which `strict-dynamic` blocks unless it carries
  // the same nonce `src/proxy.ts` minted for this response. Next stamps its own scripts
  // automatically; Clerk has to be told.
  const nonce = (await headers()).get("x-nonce") ?? undefined;

  return (
    <html lang={locale} className={bengali.variable} suppressHydrationWarning>
      <body className="bg-background text-foreground min-h-dvh antialiased">
        {/* ClerkProvider belongs inside <body>, not wrapping <html>. */}
        <ClerkProvider nonce={nonce}>
          <NextIntlClientProvider>
            <Providers>
              <RegisterServiceWorker />
              <SiteHeader />
              <main className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-8">
                <InstallPrompt />
                {children}
              </main>
            </Providers>
          </NextIntlClientProvider>
        </ClerkProvider>
      </body>
    </html>
  );
}
