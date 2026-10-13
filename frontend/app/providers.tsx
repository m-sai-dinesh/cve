"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { useApp } from "@/lib/store";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = React.useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 15_000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      }),
  );

  // Re-apply the persisted theme on mount: zustand rehydrates after the first
  // paint, so the data-theme attribute has to be set from the client.
  const theme = useApp((s) => s.theme);
  React.useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
