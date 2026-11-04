import type { Metadata } from "next";
import { Hind_Siliguri } from "next/font/google";
import { ClerkProvider } from "@clerk/nextjs";
import { NextIntlClientProvider } from "next-intl";
import { getLocale } from "next-intl/server";

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

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // Locale comes from the cookie, resolved in src/i18n/request.ts (no URL prefix, D13).
  const locale = await getLocale();

  return (
    <html lang={locale} className={bengali.variable} suppressHydrationWarning>
      <body className="bg-background text-foreground min-h-dvh antialiased">
        {/* ClerkProvider belongs inside <body>, not wrapping <html>. */}
        <ClerkProvider>
          <NextIntlClientProvider>
            <Providers>
              <SiteHeader />
              <main className="mx-auto w-full max-w-5xl px-4 py-8">{children}</main>
            </Providers>
          </NextIntlClientProvider>
        </ClerkProvider>
      </body>
    </html>
  );
}
