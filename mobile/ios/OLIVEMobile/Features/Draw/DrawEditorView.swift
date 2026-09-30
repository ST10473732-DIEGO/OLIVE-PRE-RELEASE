import SwiftUI
import PhotosUI
import UniformTypeIdentifiers

/// The Draw editor: canvas, tools and actions. No Save button: every completed
/// stroke is saved on this phone at touch-up.
struct DrawEditorView: View {
    @Environment(AppState.self) private var state
    @Environment(\.dismiss) private var dismiss
    let drawingID: String
    @State private var editor: DrawEditorModel?
    @State private var showBrush = false
    @State private var confirmClear = false
    @State private var confirmDelete = false
    @State private var renaming = false
    @State private var photos = false
    @State private var photoItem: PhotosPickerItem?
    @State private var files = false
    @State private var camera = false
    @State private var share: ShareItem?

    private var model: DrawModel { state.draw }

    var body: some View {
        Group {
            if let editor {
                content(editor)
            } else {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .background(OliveTheme.ground)
        .navigationBarTitleDisplayMode(.inline)
        .onAppear {
            guard editor == nil, let engine = model.engine else { return }
            let made = DrawEditorModel(drawingID: drawingID, engine: engine, defaults: model.defaults)
            made.library = model
            model.editor = made
            editor = made
            Task { await made.load() }
        }
        .onDisappear { editor?.close(); if model.editor === editor { model.editor = nil } }
    }

    @ViewBuilder
    private func content(_ editor: DrawEditorModel) -> some View {
        @Bindable var editor = editor
        let trashed = model.summary(drawingID)?.trashed == true
        VStack(spacing: 0) {
            if let error = editor.loadError {
                OliveNotice(text: error, symbol: "exclamationmark.triangle", tint: OliveTheme.attention).padding()
                Spacer()
            } else {
                if let notice = editor.notice {
                    OliveNotice(text: notice, symbol: "info.circle", tint: OliveTheme.information, identifier: "draw.notice")
                        .padding(.horizontal, 12).padding(.vertical, 6)
                        .onTapGesture { editor.notice = nil }
                }
                if trashed {
                    OliveNotice(text: "This drawing is in Recently Deleted. Restore it to edit it.", symbol: "trash", tint: OliveTheme.attention)
                        .padding(.horizontal, 12).padding(.vertical, 6)
                }
                DrawCanvasRepresentable(editor: editor)
                    .allowsHitTesting(!trashed)
                    .overlay(alignment: .top) {
                        if let busy = editor.busy { OliveNotice(text: busy, busy: true).padding(8).fixedSize(horizontal: false, vertical: true) }
                    }
                statusLine(editor)
                toolbar(editor)
            }
        }
        .navigationTitle(model.summary(drawingID)?.title ?? editor.summary?.title ?? "Drawing")
        .toolbar {
            ToolbarItemGroup(placement: .topBarTrailing) {
                Button { editor.undo() } label: { Image(systemName: "arrow.uturn.backward") }
                    .disabled(editor.undoCount == 0 || trashed).accessibilityLabel("Undo my last edit").accessibilityIdentifier("draw.undo")
                Button { editor.redo() } label: { Image(systemName: "arrow.uturn.forward") }
                    .disabled(editor.redoCount == 0 || trashed).accessibilityLabel("Redo").accessibilityIdentifier("draw.redo")
                moreMenu(editor, trashed: trashed)
            }
        }
        .sheet(isPresented: $showBrush) { BrushSheet(editor: editor).presentationDetents([.height(300), .medium]).presentationDragIndicator(.visible) }
        .confirmationDialog("Clear the drawing?", isPresented: $confirmClear, titleVisibility: .visible) {
            Button("Clear", role: .destructive) { editor.clear() }
        } message: { Text("Clear is an edit: Undo brings everything back.") }
        .confirmationDialog("Move this drawing to Recently Deleted?", isPresented: $confirmDelete, titleVisibility: .visible) {
            Button("Delete", role: .destructive) { Task { await model.moveToTrash(drawingID); dismiss() } }
        } message: { Text("You can restore it from Recently Deleted. The change syncs to your computer.") }
        .sheet(isPresented: $renaming) {
            DrawRenameSheet(title: model.summary(drawingID)?.title ?? "") { title in Task { await model.rename(drawingID, title) } }
        }
        .photosPicker(isPresented: $photos, selection: $photoItem, matching: .images, preferredItemEncoding: .compatible)
        .onChange(of: photoItem) { _, item in
            guard let item else { return }
            photoItem = nil
            Task { if let data = try? await item.loadTransferable(type: Data.self) { await editor.importImage(data) } }
        }
        .fileImporter(isPresented: $files, allowedContentTypes: [.png, .jpeg, .heic, .heif]) { result in
            guard case .success(let url) = result else { return }
            let scoped = url.startAccessingSecurityScopedResource()
            defer { if scoped { url.stopAccessingSecurityScopedResource() } }
            // Bounded read; the file itself is never kept or referenced.
            guard let size = try? url.resourceValues(forKeys: [.fileSizeKey]).fileSize, size <= DrawSpec.Limit.maxImportBytes,
                  let data = try? Data(contentsOf: url, options: .mappedIfSafe) else {
                editor.notice = DrawError("image_too_large").errorDescription; return
            }
            Task { await editor.importImage(data) }
        }
        .fullScreenCover(isPresented: $camera) {
            CameraPicker { data in Task { await editor.importImage(data) } }.ignoresSafeArea()
        }
        .sheet(item: $share) { item in ShareSheet(url: item.url) }
    }

    private func statusLine(_ editor: DrawEditorModel) -> some View {
        HStack(spacing: 8) {
            switch editor.saveState {
            case .saving: Text("Saving…")
            case .saved: Text("Saved on this phone")
            case .failed(let message): Text(message).foregroundStyle(OliveTheme.attention)
            }
            Text("·").foregroundStyle(OliveTheme.muted)
            Text(shortSync).lineLimit(1)
            Spacer(minLength: 0)
            Text("\(editor.visibleCount) edit\(editor.visibleCount == 1 ? "" : "s")").monospacedDigit()
        }
        .font(.caption).foregroundStyle(OliveTheme.secondary)
        .padding(.horizontal, 12).padding(.vertical, 5)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("draw.status")
    }

    private var shortSync: String {
        let sync = model.sync
        switch sync.state {
        case .off: return "Sync off"
        case .checking: return "Checking computer…"
        case .unsupported: return "Computer doesn’t support Draw yet"
        case .notAllowed: return "Computer does not allow Draw sync"
        case .offline: return sync.pending > 0 ? "Offline — \(sync.pending) waiting" : "Offline"
        case .syncing: return sync.pendingAssets > 0 ? "\(sync.pendingAssets) image\(sync.pendingAssets == 1 ? "" : "s") arriving" : "Syncing…"
        case .synced: return "Synced"
        case .error: return "Sync issue"
        }
    }

    private func toolbar(_ editor: DrawEditorModel) -> some View {
        HStack(spacing: 6) {
            toolButton("Pen", symbol: "pencil.tip", selected: editor.tool == .pen, id: "draw.pen") { editor.tool = .pen }
            toolButton("Eraser", symbol: "eraser", selected: editor.tool == .erase, id: "draw.eraser") { editor.tool = .erase }
            Button { showBrush = true } label: {
                HStack(spacing: 6) {
                    Circle().fill(Color(hexString: editor.color).opacity(editor.opacity)).frame(width: 22, height: 22)
                        .overlay(Circle().stroke(OliveTheme.border))
                    Text(sizeLabel(editor.width)).font(.caption.monospacedDigit())
                }
                .frame(minWidth: 72, minHeight: OliveTheme.minimumTouchTarget)
            }
            .accessibilityLabel("Brush: colour, size and opacity")
            .accessibilityValue("\(DrawBrush.swatches.first { $0.hex == editor.color }?.name ?? editor.color), \(sizeLabel(editor.width)), \(Int((editor.opacity * 100).rounded())) percent opacity")
            .accessibilityIdentifier("draw.brush")
            Spacer(minLength: 0)
            Menu {
                Button("Fit") { editor.fit() }
                Button("50 %") { editor.setZoom(0.5) }
                Button("100 %") { editor.setZoom(1) }
                Button("200 %") { editor.setZoom(2) }
                Button("400 %") { editor.setZoom(4) }
            } label: {
                Text(editor.zoomLabel).font(.callout.monospacedDigit()).frame(minWidth: 60, minHeight: OliveTheme.minimumTouchTarget)
            } primaryAction: { editor.fit() }
            .accessibilityLabel("Zoom \(editor.zoomLabel). Tap to fit")
            .accessibilityIdentifier("draw.zoom")
        }
        .padding(.horizontal, 10)
        .padding(.bottom, 4)
        .background(OliveTheme.surface)
    }

    private func toolButton(_ label: String, symbol: String, selected: Bool, id: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: symbol).font(.title3)
                .frame(width: OliveTheme.minimumTouchTarget, height: OliveTheme.minimumTouchTarget)
                .background(selected ? OliveTheme.accent.opacity(0.22) : .clear, in: RoundedRectangle(cornerRadius: 10))
                .foregroundStyle(selected ? OliveTheme.accent : OliveTheme.text)
        }
        .accessibilityLabel(label)
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier(id)
    }

    private func sizeLabel(_ width: Double) -> String { width < 1 ? "0.5 px" : "\(Int(width)) px" }

    private func moreMenu(_ editor: DrawEditorModel, trashed: Bool) -> some View {
        Menu {
            if trashed {
                Button { Task { await model.restore(drawingID) } } label: { Label("Restore", systemImage: "arrow.uturn.backward") }
            } else {
                Section {
                    Button { renaming = true } label: { Label("Rename", systemImage: "pencil") }
                    Button { Task { _ = await model.duplicate(drawingID) } } label: { Label("Duplicate", systemImage: "plus.square.on.square") }
                }
                Section("Background") {
                    Button { editor.setBackground("#ffffff") } label: { Label("White", systemImage: editor.background == "#ffffff" ? "checkmark" : "square") }
                    Button { editor.setBackground("transparent") } label: {
                        Label("Transparent", systemImage: editor.background == "transparent" ? "checkmark" : "square.dashed")
                    }
                }
                Section("Import image") {
                    Button { photos = true } label: { Label("Photo Library", systemImage: "photo.on.rectangle") }
                    Button { files = true } label: { Label("Files", systemImage: "folder") }
                    if UIImagePickerController.isSourceTypeAvailable(.camera) {
                        Button { camera = true } label: { Label("Camera", systemImage: "camera") }
                    }
                    #if DEBUG
                    if ProcessInfo.processInfo.arguments.contains("--ui-test-draw-fixture") {
                        Button { Task { await editor.importImage(DrawTestFixtures.syntheticPNG()) } } label: { Label("Synthetic test image", systemImage: "testtube.2") }
                    }
                    #endif
                }
                Section("Export") {
                    Button { export(editor, jpeg: false) } label: { Label("Share PNG", systemImage: "square.and.arrow.up") }
                    Button { export(editor, jpeg: true) } label: { Label("Share JPEG", systemImage: "square.and.arrow.up") }
                }
                Section {
                    Button(role: .destructive) { confirmClear = true } label: { Label("Clear", systemImage: "clear") }
                    Button(role: .destructive) { confirmDelete = true } label: { Label("Delete drawing", systemImage: "trash") }
                }
            }
        } label: { Image(systemName: "ellipsis.circle") }
        .accessibilityLabel("Drawing actions")
        .accessibilityIdentifier("draw.more")
    }

    private func export(_ editor: DrawEditorModel, jpeg: Bool) {
        Task { if let url = await editor.export(jpeg: jpeg) { share = ShareItem(url: url) } }
    }
}

/// Colour, size and opacity. Colours are exact #rrggbb values. Compact so every
/// control is on screen at once, even on a small phone in landscape.
private struct BrushSheet: View {
    @Bindable var editor: DrawEditorModel
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text("Brush").font(.headline).frame(maxWidth: .infinity).accessibilityAddTraits(.isHeader)
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 10) {
                        ForEach(DrawBrush.swatches, id: \.hex) { swatch in
                            Button { editor.color = swatch.hex } label: {
                                Circle().fill(Color(hexString: swatch.hex)).frame(width: 34, height: 34)
                                    .overlay(Circle().stroke(editor.color == swatch.hex ? OliveTheme.accent : OliveTheme.border,
                                                             lineWidth: editor.color == swatch.hex ? 3 : 1))
                                    .frame(width: OliveTheme.minimumTouchTarget, height: OliveTheme.minimumTouchTarget)
                            }
                            .buttonStyle(.plain)
                            .accessibilityLabel("Colour \(swatch.name)")
                            .accessibilityAddTraits(editor.color == swatch.hex ? .isSelected : [])
                        }
                    }
                }
                ColorPicker("Any colour", selection: Binding(get: { Color(hexString: editor.color) }, set: { value in
                    let resolved = UIColor(value).resolvedColor(with: .current)
                    var r: CGFloat = 0, g: CGFloat = 0, b: CGFloat = 0, a: CGFloat = 0
                    guard resolved.getRed(&r, green: &g, blue: &b, alpha: &a) else { return }
                    editor.color = DrawBrush.hex(red: r, green: g, blue: b)
                }), supportsOpacity: false)
                HStack {
                    Text("Size").frame(width: 64, alignment: .leading)
                    Slider(value: Binding(get: { DrawBrush.slider(size: editor.width) }, set: { editor.width = DrawBrush.size(slider: $0) }), in: 0...1000)
                        .accessibilityLabel("Size").accessibilityValue(editor.width < 1 ? "0.5 pixels" : "\(Int(editor.width)) pixels")
                        .accessibilityIdentifier("draw.size")
                    Text(editor.width < 1 ? "0.5 px" : "\(Int(editor.width)) px").monospacedDigit().frame(width: 60, alignment: .trailing)
                }
                HStack {
                    Text("Opacity").frame(width: 64, alignment: .leading)
                    Slider(value: $editor.opacity, in: 0.05...1, step: 0.05)
                        .accessibilityLabel("Opacity").accessibilityValue("\(Int((editor.opacity * 100).rounded())) percent")
                        .accessibilityIdentifier("draw.opacity")
                    Text("\(Int((editor.opacity * 100).rounded())) %").monospacedDigit().frame(width: 60, alignment: .trailing)
                }
            }
            .padding(OliveTheme.Space.medium)
        }
        .background(OliveTheme.surface)
    }
}

private struct ShareItem: Identifiable { let url: URL; var id: String { url.path } }

/// The standard iOS share sheet (save to Files/Photos, AirDrop…). Nothing is uploaded by OLIVE.
private struct ShareSheet: UIViewControllerRepresentable {
    let url: URL
    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: [url], applicationActivities: nil)
    }
    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}

/// Native camera capture. The photo is canonicalized straight into a Draw
/// asset (no metadata); nothing is saved to the Photo Library.
private struct CameraPicker: UIViewControllerRepresentable {
    let onImage: (Data) -> Void
    @Environment(\.dismiss) private var dismiss
    func makeCoordinator() -> Coordinator { Coordinator(self) }
    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.delegate = context.coordinator
        return picker
    }
    func updateUIViewController(_ controller: UIImagePickerController, context: Context) {}
    final class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let parent: CameraPicker
        init(_ parent: CameraPicker) { self.parent = parent }
        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            if let image = info[.originalImage] as? UIImage, let data = image.jpegData(compressionQuality: 0.95) { parent.onImage(data) }
            parent.dismiss()
        }
        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) { parent.dismiss() }
    }
}

extension Color {
    /// #rrggbb → sRGB colour (exact component values).
    init(hexString: String) {
        let color = DrawColor(hex: DrawText.isColor(hexString) ? hexString : "#000000")
        self.init(.sRGB, red: color.red, green: color.green, blue: color.blue, opacity: 1)
    }
}

#if DEBUG
/// Synthetic images for isolated UI tests (never personal photos).
enum DrawTestFixtures {
    static func syntheticPNG() -> Data {
        let size = CGSize(width: 480, height: 320)
        let image = UIGraphicsImageRenderer(size: size, format: { let f = UIGraphicsImageRendererFormat(); f.scale = 1; f.opaque = false; return f }()).image { context in
            UIColor(red: 0.12, green: 0.39, blue: 0.91, alpha: 1).setFill()
            context.fill(CGRect(x: 0, y: 0, width: 240, height: 320))
            UIColor(red: 0.26, green: 0.63, blue: 0.28, alpha: 1).setFill()
            context.fill(CGRect(x: 240, y: 0, width: 240, height: 160))
            // Bottom-right quarter stays transparent.
        }
        return image.pngData() ?? Data()
    }
}
#endif
