import { useState } from "react";
import { Sheet } from "../../components/Sheet";
import { call } from "../../services/api";
import { Feedback, useOperation } from "./shared";
type Preview = {
  id: string;
  kind: string;
  source_hash: string;
  rows: {
    index: number;
    body: Record<string, unknown>;
    action: string;
    warnings: string[];
    deleted_source: boolean;
  }[];
  errors: { row: number; message: string }[];
};
export default function Interchange({
  kind,
  calendarId,
  onChanged,
}: {
  kind: "contact" | "event";
  calendarId?: string;
  onChanged: () => Promise<unknown>;
}) {
  const [format, setFormat] = useState<"csv" | "vcf" | "ics">(
      kind === "contact" ? "csv" : "ics",
    ),
    [preview, setPreview] = useState<Preview>(),
    [choices, setChoices] = useState<Record<string, string>>({}),
    [partial, setPartial] = useState(false);
  const op = useOperation(onChanged);
  const [outcome, setOutcome] = useState("");
  return (
    <>
      <div className="row">
        <select
          aria-label="Interchange format"
          value={format}
          onChange={(e) => setFormat(e.target.value as typeof format)}
        >
          {(kind === "contact" ? ["csv", "vcf"] : ["ics"]).map((x) => (
            <option key={x} value={x}>
              {x.toUpperCase()}
            </option>
          ))}
        </select>
        <button
          disabled={op.busy}
          onClick={() =>
            void op.run(async () => {
              const value = (await window.olive.fileAction({
                action: "personal-import",
                kind,
                format,
                ...(calendarId ? { calendar_id: calendarId } : {}),
              })) as Preview | null;
              if (value) {
                setOutcome("");
                setPreview(value);
                setChoices({});
                setPartial(false);
              }
            }, "Import staged. Nothing has been saved yet.")
          }
        >
          Import
        </button>
        <button
          disabled={op.busy}
          onClick={() =>
            void op.run(async () => {
              const result = await window.olive.fileAction({
                action: "personal-export",
                kind,
                format,
              });
              setOutcome(
                result
                  ? "Local export saved. Unsupported fields may not round-trip."
                  : "Export cancelled. No file was written.",
              );
            }, "")
          }
        >
          Export
        </button>
      </div>
      <Feedback error={op.error} notice={outcome || op.notice} />
      <Sheet
        open={!!preview}
        onOpenChange={(open) => {
          if (!open && preview) {
            void call("personal.import_cancel", { preview_id: preview.id });
            setPreview(undefined);
          }
        }}
        title="Review import"
        description="Only the selected local records will change. Imports cannot send messages, invitations or grant permissions."
      >
        {preview && (
          <>
            <p>
              {preview.rows.length} validated records · {preview.errors.length}{" "}
              errors
            </p>
            <div className="personal-import-list">
              {preview.rows.map((row) => (
                <div className="personal-import-row" key={row.index}>
                  <div>
                    <strong>
                      {String(
                        row.body.display_name ||
                          row.body.title ||
                          "Untitled record",
                      )}
                      <details>
                        <summary>Record details</summary>
                        <dl>
                          {Object.entries(row.body)
                            .filter(
                              ([key]) =>
                                !["original_ics", "unsupported"].includes(key),
                            )
                            .map(([key, value]) => (
                              <div key={key}>
                                <dt>{key.replaceAll("_", " ")}</dt>
                                <dd>
                                  {typeof value === "object"
                                    ? JSON.stringify(value)
                                    : String(value)}
                                </dd>
                              </div>
                            ))}
                        </dl>
                      </details>
                    </strong>
                    {row.warnings.map((w) => (
                      <p className="muted" key={w}>
                        {w}
                      </p>
                    ))}
                    {row.deleted_source && (
                      <p>Previously deleted. Kept skipped.</p>
                    )}
                  </div>
                  <select
                    aria-label={`Import choice ${row.index + 1}`}
                    disabled={row.deleted_source}
                    value={choices[row.index] || row.action}
                    onChange={(e) =>
                      setChoices({ ...choices, [row.index]: e.target.value })
                    }
                  >
                    <option value="skip">Skip</option>
                    {!row.deleted_source && (
                      <option
                        value={row.action === "create" ? "create" : "update"}
                      >
                        {row.action === "create" ? "Create" : "Update existing"}
                      </option>
                    )}
                  </select>
                </div>
              ))}
            </div>
            {preview.errors.map((e) => (
              <p role="alert" key={e.row}>
                Row {e.row}: {e.message}
              </p>
            ))}
            {!!preview.errors.length && (
              <label>
                <input
                  type="checkbox"
                  checked={partial}
                  onChange={(e) => setPartial(e.target.checked)}
                />
                Import valid records only; report partial outcome
              </label>
            )}
            <div className="row">
              <button
                disabled={
                  op.busy ||
                  !preview.rows.length ||
                  (!!preview.errors.length && !partial)
                }
                className="primary"
                onClick={() =>
                  void op.run(async () => {
                    const result = await call<{
                      saved_count: number;
                      skipped_count: number;
                      status: string;
                      errors: unknown[];
                    }>("personal.import_commit", {
                      preview_id: preview.id,
                      choices,
                      allow_partial: partial,
                    });
                    setPreview(undefined);
                    setOutcome(
                      `${result.status === "partial" ? "Partially imported" : "Import saved"}: ${result.saved_count} saved, ${result.skipped_count} skipped, ${result.errors.length} invalid. Existing records outside this selection are unchanged.`,
                    );
                  }, "Reviewed import committed locally.")
                }
              >
                Review and commit import
              </button>
              <button
                onClick={() => {
                  void call("personal.import_cancel", {
                    preview_id: preview.id,
                  });
                  setPreview(undefined);
                }}
              >
                Cancel import
              </button>
            </div>
          </>
        )}
      </Sheet>
    </>
  );
}
