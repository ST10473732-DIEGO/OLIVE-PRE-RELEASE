import { call, type Chat } from "../../services/api";
import { Feedback, useOperation } from "./shared";
export function NativeProposals({
  chat,
  onChanged,
}: {
  chat: Chat;
  onChanged: (chat: Chat) => void;
}) {
  const op = useOperation();
  if (!chat.native_proposals?.length) return null;
  return (
    <section className="native-proposals" aria-label="Native proposals">
      {chat.native_proposals.map((p) => (
        <article key={p.id} className="native-proposal">
          <strong>
            {String(p.body.title || p.body.display_name || p.method)}
          </strong>
          <span className="muted">
            Proposed · Not saved · Revision {p.revision}
          </span>
          <p>
            {[p.body.start, p.body.end, p.body.due, p.body.timezone]
              .filter(Boolean)
              .map(String)
              .join(" · ")}
          </p>
          <div className="row">
            <button
              disabled={op.busy}
              onClick={() =>
                void op.run(
                  async () =>
                    onChanged(
                      await call<Chat>("personal.review", {
                        chat_id: chat.id,
                        proposal_id: p.id,
                        revision: p.revision,
                        decision: "commit",
                      }),
                    ),
                  "Reviewed operation finished; see its actual result.",
                )
              }
            >
              Review save
            </button>
            <button
              disabled={op.busy}
              onClick={() =>
                void op.run(
                  async () =>
                    onChanged(
                      await call<Chat>("personal.review", {
                        chat_id: chat.id,
                        proposal_id: p.id,
                        revision: p.revision,
                        decision: "cancel",
                      }),
                    ),
                  "Proposal cancelled.",
                )
              }
            >
              Cancel proposal
            </button>
          </div>
        </article>
      ))}
      <Feedback error={op.error} />
    </section>
  );
}
