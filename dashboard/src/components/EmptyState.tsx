import type { ReactNode } from "react";
import { Inbox } from "lucide-react";

/**
 * Friendly placeholder shown when an endpoint returns no rows.
 *
 * Per the user contract: every page shows a useful empty state instead
 * of a blank screen. The most likely visit-with-no-data scenario is a
 * fresh clone where the seed script hasn't run yet, so the default
 * message points the user at exactly that command.
 */
export function EmptyState({
  title = "No data yet",
  description = (
    <>
      Run the seed script to populate the database:
      <code className="ml-1 inline-block rounded bg-ink-100 px-1.5 py-0.5 font-mono text-ink-800">
        python -m ingestion.seed --partial
      </code>
    </>
  ),
  icon,
}: {
  title?: string;
  description?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-ink-200 bg-pk-50 p-10 text-center">
      <div className="rounded-full bg-white p-3 shadow-card">
        {icon ?? <Inbox className="h-6 w-6 text-pk-700" aria-hidden />}
      </div>
      <h3 className="mt-4 text-lg font-semibold text-ink-900">{title}</h3>
      <p className="mt-1 max-w-md text-sm text-ink-600">{description}</p>
    </div>
  );
}
