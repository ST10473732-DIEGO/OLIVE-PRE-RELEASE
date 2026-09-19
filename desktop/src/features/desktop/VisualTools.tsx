import { useState } from "react";
import { call } from "../../services/api";
import { Details } from "../../components/WorkspacePage";
import type { Operation } from "./types";
interface Preview {
  id: string;
  image: string;
  width: number;
  height: number;
  original_width: number;
  original_height: number;
}
interface Vision {
  capture_id: string;
  target_found: boolean;
  confidence: number;
  target_label: string;
  bounds: { left: number; top: number; right: number; bottom: number };
  capture: { id: string };
  visible_state: string;
}
export default function VisualTools({
  operation,
  busy,
  objective,
}: {
  operation: Operation;
  busy: boolean;
  objective: string;
}) {
  const [preview, setPreview] = useState<Preview>();
  const [vision, setVision] = useState<Vision>();
  const [expected, setExpected] = useState("");
  const [result, setResult] = useState<unknown>();
  const load = async (id: string) =>
    setPreview(
      await call<Preview>("desktop.capture_preview", { capture_id: id }),
    );
  return (
    <section>
      <h2>Authorised window observation</h2>
      <p>
        Capture only the inspected application. Visual target suggestions
        require review and remain subject to freshness, focus and permission
        checks.
      </p>
      <div className="row">
        <button
          disabled={busy}
          onClick={() =>
            void operation(async () => {
              setVision(undefined);
              const value = await call<{ id: string }>(
                "desktop.screenshot",
                {},
              );
              await load(value.id);
            }, "Authorised capture opened.")
          }
        >
          Review window capture
        </button>
        <button
          disabled={busy}
          onClick={() =>
            void operation(async () => {
              const value = await call<Vision>("desktop.vision_observe", {
                question: objective || "Describe the visible application state",
              });
              setVision(value);
              await load(value.capture.id);
            }, "Visual observation returned; inspect the suggested target.")
          }
        >
          Inspect with vision
        </button>
      </div>
      <label className="field">
        Expected visible label or completion control
        <input value={expected} onChange={(e) => setExpected(e.target.value)} />
      </label>
      <button
        disabled={busy || !expected.trim()}
        onClick={() =>
          void operation(
            async () =>
              setResult(
                await call("desktop.vision_verify_label", { expected }),
              ),
            "Label observation returned; inspect whether it matched.",
          )
        }
      >
        Verify visible label
      </button>
      {preview && (
        <>
          <div className="capture-preview">
            <img
              src={preview.image}
              alt="Authorised application window capture"
            />
            {vision?.target_found && vision.bounds && (
              <span
                aria-label="Suggested target bounds"
                className="capture-target"
                style={{
                  left: `${(100 * vision.bounds.left) / preview.original_width}%`,
                  top: `${(100 * vision.bounds.top) / preview.original_height}%`,
                  width: `${(100 * (vision.bounds.right - vision.bounds.left)) / preview.original_width}%`,
                  height: `${(100 * (vision.bounds.bottom - vision.bounds.top)) / preview.original_height}%`,
                }}
              />
            )}
          </div>
          <button
            onClick={() => {
              setPreview(undefined);
              setVision(undefined);
            }}
          >
            Close capture preview
          </button>
        </>
      )}
      {vision && (
        <>
          <p>{vision.visible_state}</p>
          <p>
            Suggested target: {vision.target_label || "No target found"}. Model
            confidence is not proof of reliable localisation.
          </p>
          <button
            disabled={
              busy ||
              !vision.target_found ||
              vision.confidence < 0.85 ||
              !expected.trim()
            }
            onClick={() =>
              void operation(async () => {
                const id = vision.capture_id;
                setVision(undefined);
                setResult(
                  await call("desktop.visual_click", {
                    capture_id: id,
                    expected,
                  }),
                );
              }, "Reviewed click returned; inspect the observed result.")
            }
          >
            Review one target click
          </button>
          <Details value={vision} title="Visual observation details" />
        </>
      )}
      {result !== undefined && (
        <Details value={result} title="Verification result" />
      )}
    </section>
  );
}
