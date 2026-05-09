import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AppLayout } from "./components/AppLayout";
import { ComparisonPage } from "./pages/ComparisonPage";
import { HomePage } from "./pages/HomePage";
import { PlayerPage } from "./pages/PlayerPage";
import { PlayersListPage } from "./pages/PlayersListPage";

/**
 * Top-level router. Three primary pages per Phase 5.3 contract:
 *   /            HomePage         — landing + player picker
 *   /compare     ComparisonPage   — flagship side-by-side view
 *   /player/:id  PlayerPage       — single-player deep dive (supporting)
 *
 * /players is a small directory page so the sidebar's Players link
 * has somewhere to land. Per the user's pivot, H2H and Venue insights
 * live as panels inside ComparisonPage rather than as standalone pages.
 */
export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppLayout />}>
          <Route index element={<HomePage />} />
          <Route path="compare" element={<ComparisonPage />} />
          <Route path="players" element={<PlayersListPage />} />
          <Route path="player/:id" element={<PlayerPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
