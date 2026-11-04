/**
 * The legal pages (Phase 11 step 7).
 *
 * Kept here rather than in `messages/*.json` on purpose. Those files are the UI string
 * catalogue, where a key-parity test and an ICU-argument test earn their keep; three
 * thousand words of prose in them would drown both and make every future translation
 * diff unreadable.
 *
 * **English is the authoritative text, and each document says so.** The Bangla on each
 * page is a plain-language summary, not a parallel legal translation — translating
 * binding terms without a Bangladeshi lawyer reading both versions would create two
 * documents that can disagree, which is worse than one document plus an honest summary
 * (DECISIONS D69).
 */
export type Section = {
  heading: string;
  /** Paragraphs. Each renders as its own `<p>`. */
  body: string[];
  /** Optional bulleted points under the paragraphs. */
  points?: string[];
};

export type LegalDocument = {
  slug: string;
  title: string;
  /** One line under the title. */
  summary: string;
  /** When the text last changed, as an ISO date. */
  updated: string;
  sections: Section[];
  /** The Bangla plain-language summary shown above the English text. */
  bangla: { title: string; points: string[] };
};
