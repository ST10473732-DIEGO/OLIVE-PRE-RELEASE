import SwiftUI

/// The two sections of OLIVE DrawNote. The last-used section is remembered on
/// this phone only (never synced).
enum DrawNoteSection: String, CaseIterable, Identifiable {
    case notes, draw
    var id: String { rawValue }
    var title: String { self == .notes ? "Notes" : "Draw" }
}

/// OLIVE DrawNote: [ Notes ] [ Draw ]. Notes is the unchanged OLIVE Notes.
struct DrawNoteView: View {
    @Environment(AppState.self) private var state
    var body: some View {
        switch state.drawNoteSection {
        case .notes: NotesView()
        case .draw: DrawLibraryView()
        }
    }
}

/// The Notes | Draw switch shown at the top of each section's list.
struct DrawNoteSectionPicker: View {
    @Environment(AppState.self) private var state
    var body: some View {
        @Bindable var state = state
        Picker("OLIVE DrawNote section", selection: $state.drawNoteSection) {
            ForEach(DrawNoteSection.allCases) { Text($0.title).tag($0) }
        }
        .pickerStyle(.segmented)
        .accessibilityIdentifier("drawnote.section")
    }
}
