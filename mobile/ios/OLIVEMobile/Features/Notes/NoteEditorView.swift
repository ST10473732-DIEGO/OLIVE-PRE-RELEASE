import SwiftUI
import UIKit

/// Full-screen plain-text note editor. Saves as you type (no Save button).
struct NoteEditorView: View {
    @Environment(AppState.self) private var state
    @Environment(\.dismiss) private var dismiss
    let noteID: String
    @State private var title = ""
    @State private var loaded: String?
    @State private var confirmDelete = false
    @State private var confirmPurge = false
    @FocusState private var titleFocused: Bool

    private var model: NotesModel { state.notes }
    private var row: NoteRow? { model.row(noteID) }

    var body: some View {
        VStack(spacing: 0) {
            if let notice = model.notice {
                OliveNotice(text: notice, symbol: "exclamationmark.triangle", tint: OliveTheme.attention)
                    .padding(.horizontal, OliveTheme.Space.medium).padding(.top, 8)
                    .onTapGesture { model.notice = nil }
            }
            TextField(row?.displayTitle ?? "Title", text: $title)
                .font(OliveTheme.TypeStyle.heading)
                .focused($titleFocused)
                .submitLabel(.done)
                .disabled(row?.trashed == true)
                .onSubmit { commitTitle() }
                .onChange(of: titleFocused) { _, focused in if !focused { commitTitle() } }
                .padding(.horizontal, OliveTheme.Space.medium).padding(.top, 12)
                .accessibilityLabel("Note title")
            if let loaded {
                NoteTextView(model: model, noteID: noteID, initial: loaded, editable: row?.trashed != true && row?.status == "ok")
                    .padding(.horizontal, 10)
            } else {
                Spacer()
            }
        }
        .background(OliveTheme.surface)
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItemGroup(placement: .topBarTrailing) {
                if row?.trashed == true {
                    Button("Restore") { model.restore(noteID) }
                    Button("Delete permanently", role: .destructive) { confirmPurge = true }
                } else {
                    Button { model.pin(noteID, !(row?.pinned ?? false)) } label: {
                        Image(systemName: row?.pinned == true ? "pin.slash" : "pin")
                    }.accessibilityLabel(row?.pinned == true ? "Unpin note" : "Pin note")
                    Menu {
                        Button { model.undo(noteID) } label: { Label("Undo my last edit", systemImage: "arrow.uturn.backward") }
                        Button { model.undo(noteID, redo: true) } label: { Label("Redo", systemImage: "arrow.uturn.forward") }
                        ShareLink(item: model.text(of: noteID) ?? "", subject: Text(row?.displayTitle ?? "Note")) {
                            Label("Share as text", systemImage: "square.and.arrow.up")
                        }
                        Button(role: .destructive) { confirmDelete = true } label: { Label("Delete", systemImage: "trash") }
                    } label: { Image(systemName: "ellipsis.circle") }.accessibilityLabel("Note actions")
                }
            }
        }
        .confirmationDialog("Move this note to Recently Deleted?", isPresented: $confirmDelete, titleVisibility: .visible) {
            Button("Delete", role: .destructive) { model.moveToTrash(noteID); dismiss() }
        } message: { Text("You can restore it from Recently Deleted. The change syncs to your computer.") }
        .confirmationDialog("Delete permanently?", isPresented: $confirmPurge, titleVisibility: .visible) {
            Button("Delete permanently", role: .destructive) { model.purge(noteID); dismiss() }
        } message: { Text("It is removed here and from your computer when they sync. This cannot be undone.") }
        .onAppear {
            loaded = model.open(noteID)
            title = row?.title ?? ""
        }
        .onDisappear { commitTitle(); model.close(noteID) }
    }

    private func commitTitle() {
        guard let row, !row.trashed, title.trimmingCharacters(in: .whitespaces) != row.title else { return }
        model.rename(noteID, title)
    }
}

/// UITextView bridge. Local typing becomes one engine edit per change; remote
/// and undo edits arrive as UTF-16 deltas applied to the text storage, so the
/// caret and selection stay on the same text. Marked (IME) text is never
/// interrupted: remote edits wait until composition ends.
struct NoteTextView: UIViewRepresentable {
    let model: NotesModel
    let noteID: String
    let initial: String
    let editable: Bool

    func makeCoordinator() -> Coordinator { Coordinator(model: model, noteID: noteID) }

    func makeUIView(context: Context) -> UITextView {
        let view = NoteUITextView()
        view.delegate = context.coordinator
        view.font = UIFont.preferredFont(forTextStyle: .body)
        view.adjustsFontForContentSizeCategory = true
        view.backgroundColor = .clear
        view.textColor = UIColor(OliveTheme.text)
        view.tintColor = UIColor(OliveTheme.accent)
        view.keyboardDismissMode = .interactive
        view.alwaysBounceVertical = true
        view.smartInsertDeleteType = .no
        view.text = initial
        view.isEditable = editable
        view.accessibilityLabel = "Note text"
        context.coordinator.view = view
        context.coordinator.shadow = initial
        model.editor = context.coordinator
        return view
    }

    func updateUIView(_ view: UITextView, context: Context) {
        view.isEditable = editable
        model.editor = context.coordinator
    }

    static func dismantleUIView(_ view: UITextView, coordinator: Coordinator) {
        if coordinator.model.editor === coordinator { coordinator.model.editor = nil }
    }

    @MainActor
    final class Coordinator: NSObject, UITextViewDelegate, NoteEditorBridge {
        let model: NotesModel
        let noteID: String
        weak var view: UITextView?
        var shadow = ""
        private var queued: [[ConnectJSON]] = []

        init(model: NotesModel, noteID: String) { self.model = model; self.noteID = noteID }

        func textView(_ textView: UITextView, shouldChangeTextIn range: NSRange, replacementText text: String) -> Bool {
            // Pasted rich content arrives here as plain text only (no attributes are kept).
            let current = (textView.text ?? "") as NSString
            let next = current.replacingCharacters(in: range, with: text)
            if next.utf8.count > 1_500_000 {
                model.notice = NotesModel.message("note_too_large")
                return false
            }
            return true
        }

        func textViewDidChange(_ textView: UITextView) {
            guard textView.markedTextRange == nil else { return } // Composing: wait for the final text.
            guard !queued.isEmpty else { commit(textView); return }
            // Remote edits arrived while composing. They are already in the engine's
            // document, so map the composed change through them before sending it.
            let pending = queued
            queued.removeAll()
            let value = NotesText.normalize(textView.text ?? "")
            var caret = textView.selectedRange.location
            if let change = NotesText.diff(shadow, value) {
                var start = change.index, end = change.index + change.remove
                for delta in pending { start = NotesText.transform(start, delta); end = NotesText.transform(end, delta) }
                _ = model.edit(noteID, index: start, remove: max(0, end - start), insert: change.insert)
                caret = start + change.insert.utf16.count
            } else {
                for delta in pending { caret = NotesText.transform(caret, delta) }
            }
            if let text = model.text(of: noteID) { replaceAll(textView, text: text, caret: caret) }
        }

        private func commit(_ textView: UITextView) {
            let value = NotesText.normalize(textView.text ?? "")
            guard let change = NotesText.diff(shadow, value) else { return }
            if model.edit(noteID, index: change.index, remove: change.remove, insert: change.insert) {
                shadow = value
                if value != textView.text { textView.text = value }
            } else if let text = model.text(of: noteID) {
                reload(text: text) // Not saved: show what is actually stored.
            }
        }

        func apply(delta: [ConnectJSON]) {
            guard let view else { return }
            if view.markedTextRange != nil { queued.append(delta); return }
            let storage = view.textStorage
            let selection = view.selectedRange
            let start = NotesText.transform(selection.location, delta)
            let end = NotesText.transform(selection.location + selection.length, delta)
            let offset = view.contentOffset
            storage.beginEditing()
            var position = 0
            for op in delta {
                if let retain = op["retain"].integer { position += Int(retain) }
                else if let insert = op["insert"].string {
                    storage.replaceCharacters(in: NSRange(location: position, length: 0),
                        with: NSAttributedString(string: insert, attributes: view.typingAttributes))
                    position += insert.utf16.count
                } else if let remove = op["delete"].integer {
                    storage.replaceCharacters(in: NSRange(location: position, length: Int(remove)), with: "")
                }
            }
            storage.endEditing()
            shadow = view.text ?? ""
            // Defensive check on ordinary sizes: never leave the view diverged from storage.
            if (shadow as NSString).length < 200_000, let stored = model.text(of: noteID), stored != shadow {
                replaceAll(view, text: stored, caret: start); return
            }
            view.selectedRange = NSRange(location: start, length: max(0, end - start))
            view.setContentOffset(offset, animated: false)
        }

        func reload(text: String) {
            guard let view else { return }
            replaceAll(view, text: text, caret: view.selectedRange.location)
        }

        private func replaceAll(_ view: UITextView, text: String, caret: Int) {
            let offset = view.contentOffset
            view.text = text
            shadow = text
            view.selectedRange = NSRange(location: min(caret, (text as NSString).length), length: 0)
            view.setContentOffset(offset, animated: false)
        }
    }
}

/// System shake-to-undo would fight the CRDT: undo uses the engine's
/// local-only undo (menu), so this text view registers no UIKit undo.
final class NoteUITextView: UITextView {
    private let quietUndo: UndoManager = { let manager = UndoManager(); manager.disableUndoRegistration(); return manager }()
    override var undoManager: UndoManager? { quietUndo }
}
