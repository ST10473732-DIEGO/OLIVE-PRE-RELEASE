import { useState } from "react";
import { call, type Chat } from "../../services/api";
import { useResource } from "../../services/useResource";
import { Sheet } from "../../components/Sheet";
import { Details } from "../../components/WorkspacePage";
import { Markdown } from "../../components/Markdown";
export function ConversationOptions({
  chat,
  open,
  onOpenChange,
  busy,
  setChat,
  report,
  beforeDelete,
}: {
  chat: Chat;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  busy: boolean;
  setChat: (chat: Chat) => void;
  report: (error: unknown) => void;
  beforeDelete: (deleting: boolean) => void;
}) {
  const resource = useResource(
    async () => ({
      projects: await call<{ id: string; title: string }[]>(
        "data.projects",
        {},
      ),
      summary: await call<{ active: boolean }>("chat.summary_state", {
        chat_id: chat.id,
      }),
    }),
    ["projects", "runtime.activity"],
  );
  const [title, setTitle] = useState(chat.title);
  const [notes, setNotes] = useState(chat.notes || "");
  const [project, setProject] = useState(chat.project_id || "");
  const [summary, setSummary] = useState(chat.summary || "");
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState("");
  const [inspection, setInspection] = useState<unknown>();
  const working = busy || pending || resource.data?.summary.active;
  const operation = async (fn: () => Promise<unknown>, message: string) => {
    setPending(true);
    try {
      const result = await fn();
      setNotice(result === null ? "Cancelled." : message);
    } catch (error) {
      report(error);
    } finally {
      setPending(false);
      void resource.refresh();
    }
  };
  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
      title="Conversation options"
      description="Manage this conversation and its local context."
    >
      <p role="status">{notice}</p>
      <label className="field">
        Title
        <input
          aria-label="Conversation title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={200}
        />
      </label>
      <label className="field">
        Project
        <select
          aria-label="Conversation project"
          value={project}
          onChange={(e) => setProject(e.target.value)}
        >
          <option value="">No project</option>
          {resource.data?.projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.title}
            </option>
          ))}
        </select>
      </label>
      <label className="field">
        Conversation notes
        <textarea
          aria-label="Conversation notes"
          rows={4}
          maxLength={32000}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </label>
      <button
        className="primary"
        disabled={working || !title.trim()}
        onClick={() =>
          void operation(
            async () =>
              setChat(
                await call<Chat>("chat.metadata", {
                  chat_id: chat.id,
                  title,
                  notes,
                  project_id: project,
                }),
              ),
            "Conversation details saved.",
          )
        }
      >
        Save conversation details
      </button>
      <details>
        <summary>Conversation summary</summary>
        {summary ? <Markdown text={summary} /> : <p>No summary saved yet.</p>}
        <button
          disabled={working}
          onClick={() =>
            void operation(
              async () =>
                setSummary(
                  await call<string>("chat.summarize", { chat_id: chat.id }),
                ),
              "Summary saved.",
            )
          }
        >
          Generate summary
        </button>
        {resource.data?.summary.active && (
          <button
            onClick={() =>
              void call("chat.cancel_summary", { chat_id: chat.id }).catch(
                report,
              )
            }
          >
            Cancel summary
          </button>
        )}
      </details>
      <button
        disabled={pending}
        onClick={() =>
          void operation(
            () =>
              window.olive.fileAction({
                action: "export-chat",
                chat_id: chat.id,
              }),
            "Conversation exported.",
          )
        }
      >
        Export conversation
      </button>
      <details>
        <summary>Developer interaction details</summary>
        <button
          onClick={() =>
            void operation(
              async () =>
                setInspection(
                  await call("interaction.inspect", { chat_id: chat.id }),
                ),
              "Interaction state loaded.",
            )
          }
        >
          Inspect language context
        </button>
        {inspection !== undefined && <Details value={inspection} />}
      </details>
      <details>
        <summary>Delete this conversation</summary>
        <p>
          This removes the conversation and its document indexes. Original
          attached files are kept. Keep at least one conversation.
        </p>
        <button
          disabled={working}
          onClick={() =>
            void operation(async () => {
              beforeDelete(true);
              try {
                const next = await call<Chat>("chat.delete", {
                  chat_id: chat.id,
                });
                onOpenChange(false);
                setChat(next);
              } catch (error) {
                beforeDelete(false);
                throw error;
              }
            }, "Conversation deleted.")
          }
        >
          Delete conversation and indexes
        </button>
      </details>
    </Sheet>
  );
}
