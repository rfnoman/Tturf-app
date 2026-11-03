import type { Metadata } from "next";
import { ClerkProvider } from "@clerk/nextjs";
import { NextIntlClientProvider } from "next-intl";
import { getLocale } from "next-intl/server";

import { SiteHeader } from "@/components/layout/site-header";

import { Providers } from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "TurfApp",
  description: "Book sports turfs in Bangladesh, fill your match, build your profile.",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // Locale comes from the cookie, resolved in src/i18n/request.ts (no URL prefix, D13).
  const locale = await getLocale();

  return (
    <html lang={locale} suppressHydrationWarning>
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
