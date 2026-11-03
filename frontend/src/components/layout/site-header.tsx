import Link from "next/link";
import { Suspense } from "react";
import { SignInButton, SignUpButton, Show, UserButton } from "@clerk/nextjs";
import { getTranslations } from "next-intl/server";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

import { LanguageSwitcher } from "./language-switcher";

export async function SiteHeader() {
  const t = await getTranslations();

  return (
    <header className="border-border/60 bg-background/95 sticky top-0 z-40 border-b backdrop-blur">
      <div className="mx-auto flex h-14 max-w-5xl items-center gap-2 px-4">
        <Link href="/" className="mr-auto text-base font-semibold tracking-tight">
          {t("app.name")}
        </Link>

        <nav className="hidden items-center gap-1 sm:flex" aria-label={t("nav.home")}>
          <Button variant="ghost" size="sm" asChild>
            <Link href="/play">{t("nav.play")}</Link>
          </Button>
          <Button variant="ghost" size="sm" asChild>
            <Link href="/profile">{t("nav.profile")}</Link>
          </Button>
          <Button variant="ghost" size="sm" asChild>
            <Link href="/turfs">{t("nav.owner")}</Link>
          </Button>
          <Button variant="ghost" size="sm" asChild>
            <Link href="/me">{t("nav.debug")}</Link>
          </Button>
        </nav>

        <LanguageSwitcher />

        {/* <Show> reads auth state, so it needs a Suspense boundary. */}
        <Suspense fallback={<Skeleton className="h-8 w-16" />}>
          <Show when="signed-out">
            <SignInButton mode="modal">
              <Button variant="ghost" size="sm">
                {t("auth.signIn")}
              </Button>
            </SignInButton>
            <SignUpButton mode="modal">
              <Button size="sm">{t("auth.signUp")}</Button>
            </SignUpButton>
          </Show>
          <Show when="signed-in">
            <UserButton />
          </Show>
        </Suspense>
      </div>
    </header>
  );
}
