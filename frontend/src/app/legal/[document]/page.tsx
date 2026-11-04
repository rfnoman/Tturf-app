import Link from "next/link";
import { notFound } from "next/navigation";
import { getLocale, getTranslations } from "next-intl/server";
import type { Metadata } from "next";

import { LEGAL_DOCUMENTS, legalDocument } from "@/content/legal";
import { formatDay } from "@/i18n/formats";

/**
 * The policy pages.
 *
 * Public and static: a player has to be able to read the refund policy before deciding
 * to pay, and SSLCommerz's merchant onboarding asks for the URL, which has to resolve
 * without an account.
 *
 * Every page carries a Bangla plain-language summary above the English text, and says
 * which one governs. Translating binding terms without a Bangladeshi lawyer reading both
 * would create two documents that can disagree — worse than one document and an honest
 * summary (DECISIONS D69).
 */
export function generateStaticParams() {
  return LEGAL_DOCUMENTS.map((document) => ({ document: document.slug }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ document: string }>;
}): Promise<Metadata> {
  const { document } = await params;
  const found = legalDocument(document);
  if (!found) return { title: "Not found" };

  return { title: `${found.title} · TurfApp`, description: found.summary };
}

export default async function LegalPage({ params }: { params: Promise<{ document: string }> }) {
  const { document } = await params;
  const found = legalDocument(document);
  if (!found) notFound();

  const locale = await getLocale();
  // The page chrome is UI, so it follows the reader's language; the document itself
  // does not, and says so.
  const t = await getTranslations("legal");

  return (
    <article className="mx-auto flex max-w-2xl flex-col gap-8">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">{found.title}</h1>
        <p className="text-muted-foreground">{found.summary}</p>
        <p className="text-muted-foreground text-xs">
          {t("lastUpdated", { date: formatDay(found.updated, locale, "dayMonthYear") })}
        </p>
      </header>

      <section className="bg-muted/50 flex flex-col gap-3 rounded-lg border p-4">
        <h2 className="font-semibold">{found.bangla.title}</h2>
        <ul className="flex list-disc flex-col gap-1.5 pl-5 text-sm">
          {found.bangla.points.map((point) => (
            <li key={point}>{point}</li>
          ))}
        </ul>
        <p className="text-muted-foreground text-xs">
          এটি সহজ ভাষায় সারসংক্ষেপ। কোনো অমিল হলে নিচের ইংরেজি লেখাটিই প্রযোজ্য।
        </p>
      </section>

      <div className="flex flex-col gap-6">
        {found.sections.map((section) => (
          <section key={section.heading} className="flex flex-col gap-2">
            <h2 className="text-lg font-semibold tracking-tight">{section.heading}</h2>
            {section.body.map((paragraph) => (
              <p key={paragraph} className="text-sm leading-relaxed">
                {paragraph}
              </p>
            ))}
            {section.points && (
              <ul className="flex list-disc flex-col gap-1.5 pl-5 text-sm leading-relaxed">
                {section.points.map((point) => (
                  <li key={point}>{point}</li>
                ))}
              </ul>
            )}
          </section>
        ))}
      </div>

      <nav className="flex flex-col gap-2 border-t pt-6 text-sm">
        <span className="text-muted-foreground text-xs">{t("alsoRead")}</span>
        <span className="flex flex-wrap gap-3">
          {LEGAL_DOCUMENTS.filter((other) => other.slug !== found.slug).map((other) => (
            <Link key={other.slug} href={`/legal/${other.slug}`} className="hover:underline">
              {other.title}
            </Link>
          ))}
        </span>
      </nav>
    </article>
  );
}
