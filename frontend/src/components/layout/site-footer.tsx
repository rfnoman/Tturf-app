import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { LEGAL_DOCUMENTS } from "@/content/legal";

/**
 * The footer exists for one reason: the policy pages have to be reachable.
 *
 * A refund policy nobody can find is not a policy, and SSLCommerz's merchant onboarding
 * asks for links that resolve from the site itself (Phase 11 step 7).
 */
export async function SiteFooter() {
  const t = await getTranslations("footer");

  return (
    <footer className="mt-12 border-t">
      <div className="text-muted-foreground mx-auto flex w-full max-w-5xl flex-wrap items-center justify-between gap-4 px-4 py-6 text-sm">
        <p>{t("copyright", { year: new Date().getFullYear() })}</p>
        <nav className="flex flex-wrap gap-4">
          {LEGAL_DOCUMENTS.map((document) => (
            <Link key={document.slug} href={`/legal/${document.slug}`} className="hover:underline">
              {document.title}
            </Link>
          ))}
        </nav>
      </div>
    </footer>
  );
}
