import SwiftUI
import PhotosUI
import UniformTypeIdentifiers

/// The sources behind the composer's + button. One compact menu, no extra buttons.
enum AttachmentSource: String, Identifiable, CaseIterable {
    case photos, camera, files, notes, drawings
    var id: String { rawValue }
    var title: String {
        switch self {
        case .photos: "Photo Library"
        case .camera: "Take Photo"
        case .files: "Files"
        case .notes: "OLIVE Notes"
        case .drawings: "OLIVE Draw"
        }
    }
    var symbol: String {
        switch self {
        case .photos: "photo.on.rectangle"
        case .camera: "camera"
        case .files: "folder"
        case .notes: "note.text"
        case .drawings: "scribble.variable"
        }
    }
}

struct AttachMenuButton: View {
    let disabled: Bool
    let choose: (AttachmentSource) -> Void
    var body: some View {
        Menu {
            ForEach(AttachmentSource.allCases) { source in
                if source != .camera || UIImagePickerController.isSourceTypeAvailable(.camera) {
                    Button { choose(source) } label: { Label(source.title, systemImage: source.symbol) }
                        .accessibilityIdentifier("chat.attach." + source.rawValue)
                }
            }
        } label: {
            Image(systemName: "plus").font(.system(size: 17, weight: .semibold)).foregroundStyle(disabled ? OliveTheme.muted : OliveTheme.accent)
                .frame(width: 40, height: 40).background(OliveTheme.surface, in: Circle())
                .frame(width: 44, height: 44).contentShape(Circle())
        }
        .disabled(disabled)
        .accessibilityLabel("Add attachment")
        .accessibilityHint("Photo Library, Take Photo, Files, OLIVE Notes or OLIVE Draw")
        .accessibilityIdentifier("chat.attach")
    }
}

/// Compact chips above the composer: thumbnail or icon, name, type and size, remove.
struct AttachmentChips: View {
    @Environment(AppState.self) private var state
    var body: some View {
        if !state.draftAttachments.isEmpty || state.preparing > 0 {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(state.draftAttachments) { item in
                        AttachmentChip(item: item, accepted: state.selectedCapability == nil ? true : state.attachmentAccepted(item)) {
                            withAnimation(OliveTheme.Motion.press) { state.removeAttachment(item.id) }
                        }
                    }
                    if state.preparing > 0 {
                        HStack(spacing: 8) { ProgressView().controlSize(.small); Text("Preparing…").font(.caption) }
                            .padding(.horizontal, 12).frame(height: 52)
                            .background(OliveTheme.raised, in: RoundedRectangle(cornerRadius: OliveTheme.Radius.control, style: .continuous))
                            .accessibilityElement(children: .combine).accessibilityLabel("Preparing attachment")
                    }
                }.padding(.horizontal, 6)
            }.accessibilityIdentifier("chat.attachments")
        }
    }
}

struct AttachmentChip: View {
    let item: StoredChatAttachment
    var accepted = true
    var onRemove: (() -> Void)?
    @Environment(AppState.self) private var state
    var body: some View {
        HStack(spacing: 8) {
            AttachmentThumbnail(item: item, url: state.attachmentStore.url(item.descriptor))
            VStack(alignment: .leading, spacing: 2) {
                Text(item.provenance.title ?? item.descriptor.name).font(.caption.weight(.semibold)).lineLimit(1)
                Text(detail).font(.caption2).foregroundStyle(accepted ? OliveTheme.muted : OliveTheme.attention).lineLimit(1)
            }.frame(maxWidth: 150, alignment: .leading)
            if let onRemove {
                Button(action: onRemove) {
                    Image(systemName: "xmark").font(.caption.weight(.bold)).foregroundStyle(OliveTheme.secondary)
                        .frame(width: 28, height: 28).background(OliveTheme.surface, in: Circle())
                        .frame(width: 44, height: 44).contentShape(Circle())
                }.buttonStyle(.plain)
                    .accessibilityLabel("Remove " + (item.provenance.title ?? item.descriptor.name))
                    .accessibilityIdentifier("chat.attachment.remove")
            }
        }
        .padding(.leading, 6).padding(.trailing, onRemove == nil ? 10 : 0).frame(minHeight: 52)
        .background(OliveTheme.raised, in: RoundedRectangle(cornerRadius: OliveTheme.Radius.control, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: OliveTheme.Radius.control, style: .continuous)
            .stroke(accepted ? OliveTheme.border : OliveTheme.attention.opacity(0.7)))
        .accessibilityElement(children: .contain)
        .accessibilityLabel(item.typeLabel + ", " + (item.provenance.title ?? item.descriptor.name) + (accepted ? "" : ", not accepted by this mode"))
        .accessibilityIdentifier("chat.attachment." + item.provenance.source)
    }
    private var detail: String {
        var parts = [item.typeLabel]
        if let pages = item.pageCount { parts.append("\(pages) page" + (pages == 1 ? "" : "s")) }
        if let w = item.pixelWidth, let h = item.pixelHeight { parts.append("\(w)×\(h)") }
        parts.append(ByteCountFormatter.string(fromByteCount: item.descriptor.size, countStyle: .file))
        return parts.joined(separator: " · ")
    }
}

struct AttachmentThumbnail: View {
    let item: StoredChatAttachment
    let url: URL
    @State private var image: UIImage?
    var body: some View {
        Group {
            if let image {
                Image(uiImage: image).resizable().scaledToFill()
            } else {
                Image(systemName: item.symbol).font(.system(size: 18)).foregroundStyle(OliveTheme.accent)
            }
        }
        .frame(width: 40, height: 40).background(OliveTheme.surface)
        .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
        .accessibilityHidden(true)
        .task(id: item.id) {
            guard item.descriptor.kind == "image" else { return }
            let url = self.url
            // Downsampled on a background thread; the full image is never decoded for a chip.
            image = await Task.detached(priority: .utility) { () -> UIImage? in
                guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
                      let cg = CGImageSourceCreateThumbnailAtIndex(source, 0, [kCGImageSourceCreateThumbnailFromImageAlways: true,
                        kCGImageSourceThumbnailMaxPixelSize: 120, kCGImageSourceCreateThumbnailWithTransform: true] as CFDictionary) else { return nil }
                return UIImage(cgImage: cg)
            }.value
        }
    }
}

// MARK: - Mode selection

struct ModeButton: View {
    @Environment(AppState.self) private var state
    @Binding var presented: Bool
    var body: some View {
        let mode = state.selectedMode
        Button { presented = true } label: {
            HStack(spacing: 4) {
                Image(systemName: mode.symbol).font(.caption2)
                Text(mode.short)
                Image(systemName: "chevron.up.chevron.down").font(.caption2)
            }
            .font(.caption.weight(.semibold)).foregroundStyle(OliveTheme.accent)
            .padding(.horizontal, 10).padding(.vertical, 5)
            .background(OliveTheme.accent.opacity(0.12), in: Capsule())
            .frame(minHeight: 44).contentShape(Rectangle())
        }
        .disabled(state.active)
        .accessibilityLabel("Mode, " + mode.name)
        .accessibilityHint("Choose how your computer answers")
        .accessibilityIdentifier("chat.mode")
    }
}

/// Grouped CHAT / RESEARCH / CREATE. Availability comes from the connected computer.
struct ModePickerSheet: View {
    @Environment(AppState.self) private var state
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        @Bindable var state = state
        NavigationStack {
            List {
                ForEach(ChatMode.Group.allCases, id: \.self) { group in
                    Section(group.rawValue) {
                        ForEach(ChatMode.all.filter { $0.group == group }) { mode in row(mode) }
                    }.listRowBackground(OliveTheme.raised)
                }
                if state.preset == "audio", let voices = state.selectedCapability?.voices, voices.count > 1 {
                    Section {
                        Picker("Voice", selection: $state.voice) {
                            Text("Computer default").tag(String?.none)
                            ForEach(voices) { Text($0.name).tag(Optional($0.id)) }
                        }.accessibilityIdentifier("chat.voice")
                    } header: { Text("AUDIO voice") } footer: { Text("Applies to your next AUDIO request.") }
                        .listRowBackground(OliveTheme.raised)
                }
            }
            .oliveListStyle()
            .navigationTitle("Mode").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() }.accessibilityIdentifier("chat.mode.done") } }
            .task { await state.chatConnection?.refreshChatCapabilities() }
            .onChange(of: state.voice) { _, _ in state.saveSession() }
        }
        .presentationDetents([.large])
    }

    private func row(_ mode: ChatMode) -> some View {
        let availability = state.availability(mode)
        let selected = state.preset == mode.id
        let capability = state.chatCapabilities?.mode(mode.id)
        let notes = (capability?.limitations ?? []).compactMap { ChatText.limitation($0, mode: mode) }
        return Button {
            state.preset = mode.id
            dismiss()
        } label: {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: mode.symbol).frame(width: 24).foregroundStyle(availability == .available ? OliveTheme.accent : OliveTheme.muted)
                VStack(alignment: .leading, spacing: 3) {
                    Text(mode.name).font(.body.weight(.semibold)).foregroundStyle(availability == .available ? OliveTheme.text : OliveTheme.muted)
                    Text(availability == .available ? mode.summary : availability.explanation)
                        .font(.footnote).foregroundStyle(availability == .available ? OliveTheme.secondary : OliveTheme.attention)
                        .fixedSize(horizontal: false, vertical: true)
                    if availability == .available, let note = notes.first {
                        Text(note).font(.caption).foregroundStyle(OliveTheme.muted).fixedSize(horizontal: false, vertical: true)
                    }
                }
                Spacer(minLength: 8)
                if selected { Image(systemName: "checkmark").foregroundStyle(OliveTheme.accent).accessibilityHidden(true) }
            }.padding(.vertical, 4).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        // Unavailable modes stay selectable so their explanation is visible; Send explains again.
        .accessibilityLabel(mode.name)
        .accessibilityValue(selected ? "Selected" : availability == .available ? "" : availability.explanation)
        .accessibilityHint(mode.summary)
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier("chat.mode." + mode.id)
    }
}

// MARK: - VIDEO length

/// Compact "Duration · Auto" control, shown only when the computer plans VIDEO length.
struct VideoDurationButton: View {
    @Environment(AppState.self) private var state
    @Binding var presented: Bool
    var body: some View {
        let label = state.videoDurationLabel
        Button { presented = true } label: {
            HStack(spacing: 4) {
                Image(systemName: "timer").font(.caption2)
                Text(label)
            }
            .font(.caption.weight(.semibold)).foregroundStyle(OliveTheme.accent)
            .padding(.horizontal, 10).padding(.vertical, 5)
            .background(OliveTheme.accent.opacity(0.12), in: Capsule())
            .frame(minHeight: 44).contentShape(Rectangle())
        }
        .disabled(state.active)
        .accessibilityLabel("Video length, " + label)
        .accessibilityHint("Choose how long the video should be")
        .accessibilityIdentifier("chat.videoDuration")
    }
}

/// Auto, the computer's presets, or a custom length in seconds or minutes.
struct VideoDurationSheet: View {
    @Environment(AppState.self) private var state
    @Environment(\.dismiss) private var dismiss
    @State private var custom = ""
    @State private var minutes = false
    @FocusState private var typing: Bool

    var body: some View {
        let capability = state.videoCapability
        let maximum = Double(capability?.maximumMS ?? 0) / 1000
        let presets = (capability?.presetsMS ?? []).map { Double($0) / 1000 }.filter { maximum == 0 || $0 <= maximum }
        let typed = VideoDuration.custom(custom, minutes: minutes)
        NavigationStack {
            List {
                Section {
                    choice(nil, title: "Auto", detail: autoDetail)
                    ForEach(presets, id: \.self) { seconds in choice(seconds, title: VideoDuration.label(seconds), detail: nil) }
                } footer: {
                    Text("Longer videos are made on your computer from about 2-second segments, one after another"
                         + (maximum > 0 ? ", up to \(VideoDuration.label(maximum))." : "."))
                }.listRowBackground(OliveTheme.raised)
                Section {
                    HStack(spacing: 10) {
                        TextField("Length", text: $custom).keyboardType(.decimalPad).focused($typing)
                            .accessibilityLabel("Custom length").accessibilityIdentifier("chat.videoDuration.custom")
                        Picker("Unit", selection: $minutes) {
                            Text("sec").tag(false)
                            Text("min").tag(true)
                        }.pickerStyle(.segmented).frame(maxWidth: 150).accessibilityIdentifier("chat.videoDuration.unit")
                    }
                    Button("Use \(typed.map(VideoDuration.label) ?? "custom length")") {
                        guard let typed else { return }
                        state.videoDuration = typed; dismiss()
                    }
                    .disabled(typed == nil || (maximum > 0 && (typed ?? 0) > maximum))
                    .accessibilityIdentifier("chat.videoDuration.apply")
                } header: { Text("Custom") } footer: {
                    if let typed, maximum > 0, typed > maximum {
                        Text("This computer allows up to \(VideoDuration.label(maximum)) per video.").foregroundStyle(OliveTheme.attention)
                    }
                }.listRowBackground(OliveTheme.raised)
            }
            .oliveListStyle()
            .navigationTitle("Video length").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() }.accessibilityIdentifier("chat.videoDuration.done") } }
            .onAppear {
                if let chosen = state.videoDuration, !presets.contains(chosen) { custom = String(format: chosen == chosen.rounded() ? "%.0f" : "%.1f", chosen) }
            }
        }
        .presentationDetents([.medium, .large])
    }

    private var autoDetail: String {
        if let stated = VideoDuration.parse(state.draft) { return "From your message · " + VideoDuration.label(stated.seconds) }
        let fallback = state.videoCapability.map { VideoDuration.label(Double($0.defaultMS) / 1000) } ?? ""
        return "Uses a length in your message, else " + (fallback.isEmpty ? "your computer’s default" : fallback)
    }

    private func choice(_ seconds: Double?, title: String, detail: String?) -> some View {
        let selected = state.videoDuration == seconds
        return Button {
            state.videoDuration = seconds; dismiss()
        } label: {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).foregroundStyle(OliveTheme.text)
                    if let detail { Text(detail).font(.footnote).foregroundStyle(OliveTheme.secondary).fixedSize(horizontal: false, vertical: true) }
                }
                Spacer(minLength: 8)
                if selected { Image(systemName: "checkmark").foregroundStyle(OliveTheme.accent).accessibilityHidden(true) }
            }.contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier("chat.videoDuration.option." + (seconds.map { String(Int($0)) } ?? "auto"))
    }
}

// MARK: - OLIVE Notes and OLIVE Draw pickers

struct NotePickerSheet: View {
    @Environment(AppState.self) private var state
    @Environment(\.dismiss) private var dismiss
    @State private var query = ""
    var body: some View {
        let rows = state.notes.notes.filter { row in
            query.isEmpty || row.displayTitle.localizedCaseInsensitiveContains(query) || row.preview.localizedCaseInsensitiveContains(query)
        }
        NavigationStack {
            List {
                if state.notes.notes.isEmpty {
                    OliveEmptyState(symbol: "note.text", title: "No notes", detail: "Notes you write in OLIVE DrawNote appear here.")
                        .listRowBackground(Color.clear)
                }
                ForEach(rows) { row in
                    Button {
                        state.attachNote(row); dismiss()
                    } label: {
                        VStack(alignment: .leading, spacing: 3) {
                            Text(row.displayTitle).font(.body.weight(.semibold)).foregroundStyle(OliveTheme.text)
                            if !row.preview.isEmpty { Text(row.preview).font(.footnote).foregroundStyle(OliveTheme.secondary).lineLimit(2) }
                        }.padding(.vertical, 2)
                    }
                    .accessibilityLabel("Attach note " + row.displayTitle)
                    .accessibilityIdentifier("chat.pick.note")
                }.listRowBackground(OliveTheme.raised)
            }
            .oliveListStyle()
            .searchable(text: $query, placement: .navigationBarDrawer(displayMode: .always), prompt: "Search notes")
            .navigationTitle("OLIVE Notes").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } } }
            .safeAreaInset(edge: .bottom) {
                Text("A snapshot of the note as it is now is sent to your computer. Later edits don't change this message.")
                    .font(.caption).foregroundStyle(OliveTheme.muted).padding().frame(maxWidth: .infinity).background(OliveTheme.surface)
            }
        }
    }
}

struct DrawPickerSheet: View {
    @Environment(AppState.self) private var state
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            List {
                if state.draw.drawings.isEmpty {
                    OliveEmptyState(symbol: "scribble.variable", title: "No drawings", detail: "Drawings you make in OLIVE DrawNote appear here.")
                        .listRowBackground(Color.clear)
                }
                ForEach(state.draw.drawings.filter { $0.status == "ok" }) { summary in
                    Button {
                        state.attachDrawing(summary); dismiss()
                    } label: {
                        HStack(spacing: 12) {
                            Group {
                                if let image = state.draw.thumbnail(for: summary) { Image(uiImage: image).resizable().scaledToFit() }
                                else { Image(systemName: "scribble.variable").foregroundStyle(OliveTheme.accent) }
                            }.frame(width: 64, height: 44).background(OliveTheme.surface).clipShape(RoundedRectangle(cornerRadius: 6))
                            VStack(alignment: .leading, spacing: 2) {
                                Text(summary.title).font(.body.weight(.semibold)).foregroundStyle(OliveTheme.text)
                                Text("\(summary.width)×\(summary.height)").font(.caption).foregroundStyle(OliveTheme.muted)
                            }
                        }
                    }
                    .accessibilityLabel("Attach drawing " + summary.title)
                    .accessibilityIdentifier("chat.pick.drawing")
                }.listRowBackground(OliveTheme.raised)
            }
            .oliveListStyle()
            .navigationTitle("OLIVE Draw").navigationBarTitleDisplayMode(.inline)
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } } }
            .safeAreaInset(edge: .bottom) {
                Text("A PNG snapshot of the drawing is attached. The drawing itself isn't changed.")
                    .font(.caption).foregroundStyle(OliveTheme.muted).padding().frame(maxWidth: .infinity).background(OliveTheme.surface)
            }
            .task { await state.draw.refresh() }
        }
    }
}

/// The system camera. iOS asks for camera permission the first time it is shown.
/// Captures are not saved to Photos.
struct ChatCameraPicker: UIViewControllerRepresentable {
    let completion: (UIImage?) -> Void
    func makeCoordinator() -> Coordinator { Coordinator(completion: completion) }
    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.cameraCaptureMode = .photo
        picker.delegate = context.coordinator
        return picker
    }
    func updateUIViewController(_ controller: UIImagePickerController, context: Context) {}
    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let completion: (UIImage?) -> Void
        init(completion: @escaping (UIImage?) -> Void) { self.completion = completion }
        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            completion(info[.originalImage] as? UIImage)
        }
        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) { completion(nil) }
    }
}

extension AppState {
    /// Document types the computer's modes accept (from its advertisement), plus images.
    var importableTypes: [UTType] {
        var types: [UTType] = [.image]
        let mimes = Set(chatCapabilities?.modes.flatMap { $0.documentMax > 0 ? $0.documentMimes : [] } ?? [])
        if mimes.contains("application/pdf") { types.append(.pdf) }
        if mimes.contains("text/plain") { types += [.plainText, .text, .commaSeparatedText] }
        if mimes.contains("text/markdown"), let markdown = UTType("net.daringfireball.markdown") { types.append(markdown) }
        if mimes.contains("text/x-source") { types += [.sourceCode, .script, .json, .xml, .yaml] }
        if mimes.contains(where: { $0.hasSuffix("wordprocessingml.document") }), let docx = UTType("org.openxmlformats.wordprocessingml.document") { types.append(docx) }
        return types
    }

    func attachFile(_ url: URL) {
        let capabilities = chatCapabilities
        addAttachment { directory in
            try AttachmentPreparation.file(url, limit: { AppState.limit(capabilities, kind: $0, mime: $1) }, directory: directory)
        }
    }

    func attachPhotos(_ items: [PhotosPickerItem]) {
        for item in items {
            preparing += 1
            Task {
                // The user's explicit selection only; the library is never enumerated.
                let data = try? await item.loadTransferable(type: Data.self)
                preparing -= 1
                guard let data else { attachmentNotice = "The photo couldn't be loaded."; return }
                addAttachment { try AttachmentPreparation.photo(data, source: "photo", name: "Photo.jpg", directory: $0) }
            }
        }
    }

    func attachCamera(_ picture: UIImage) {
        addAttachment { try AttachmentPreparation.camera(picture, directory: $0) }
    }
}
