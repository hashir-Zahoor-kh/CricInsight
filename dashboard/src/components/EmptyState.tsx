import type { ReactNode } from "react";
import { Inbox } from "lucide-react";

export function EmptyState({
  title = "No data yet",
  description = (
    <>
      Run the seed script to populate the database:
      <code className="ml-1 inline-block border border-line bg-elevated px-1.5 py-0.5 font-mono text-xs text-fg">
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
    <div className="flex flex-col items-center justify-center border border-dashed border-line bg-surface p-10 text-center">
      <div className="border border-line bg-elevated p-3">
        {icon ?? <Inbox className="h-6 w-6 text-fg-secondary" aria-hidden />}
      </div>
      <h3 className="mt-4 font-display text-2xl uppercase tracking-tight text-fg">
        {title}
      </h3>
      <p className="mt-2 max-w-md font-sans text-sm text-fg-secondary">
        {description}
      </p>
    </div>
  );
}
