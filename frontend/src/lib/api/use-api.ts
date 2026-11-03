"use client";

import { useAuth } from "@clerk/nextjs";
import { useMemo } from "react";

import { type ApiClient, createApiClient } from "./client";

/** Typed API client for Client Components, carrying the signed-in user's token. */
export function useApiClient(): ApiClient {
  const { getToken } = useAuth();
  return useMemo(() => createApiClient(() => getToken()), [getToken]);
}
