"use client";

import { useAuth } from "@clerk/nextjs";
import { useLocale } from "next-intl";
import { useMemo } from "react";

import { type ApiClient, createApiClient } from "./client";

/** Typed API client for Client Components, carrying the signed-in user's token. */
export function useApiClient(): ApiClient {
  const { getToken } = useAuth();
  const locale = useLocale();
  return useMemo(() => createApiClient(() => getToken(), undefined, locale), [getToken, locale]);
}
