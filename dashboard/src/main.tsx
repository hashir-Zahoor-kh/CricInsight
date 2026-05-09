import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import App from "./App.tsx";
import "./index.css";

// Single QueryClient for the whole app. Defaults tuned for analytics:
//
//   staleTime 60s     — career stats and historical matches don't
//                       change minute-to-minute, so React Query can
//                       serve from cache without re-fetching when a
//                       user navigates back to a page.
//
//   refetchOnWindowFocus = false
//                     — keeps the dashboard quiet during demos /
//                       screenshot sessions; tab-switching shouldn't
//                       cause a flicker.
//
//   retry 1           — one retry on transient 5xx, but don't
//                       hammer a degraded backend.
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>
);
