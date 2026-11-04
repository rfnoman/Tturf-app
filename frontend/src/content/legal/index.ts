import { owners } from "./owners";
import { privacy } from "./privacy";
import { refunds } from "./refunds";
import { terms } from "./terms";
import type { LegalDocument } from "./types";

export const LEGAL_DOCUMENTS: LegalDocument[] = [terms, privacy, refunds, owners];

export function legalDocument(slug: string): LegalDocument | undefined {
  return LEGAL_DOCUMENTS.find((document) => document.slug === slug);
}

export type { LegalDocument } from "./types";
