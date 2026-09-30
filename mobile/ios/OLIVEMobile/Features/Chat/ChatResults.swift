import SwiftUI
import AVFoundation
import AVKit
import Combine
import Photos
import UniformTypeIdentifiers

// MARK: - Sources (NOW / DEEP)

/// Evidence exactly as the computer structured it: titles, providers, dates, links.
struct SourcesView: View {
    let sources: [ChatSource]
    @State private var expanded = false
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Button { withAnimation(OliveTheme.Motion.settle) { expanded.toggle() } } label: {
                HStack(spacing: 6) {
                    Image(systemName: "text.book.closed").font(.caption)
                    Text(sources.count == 1 ? "1 source" : "\(sources.count) sources").font(.caption.weight(.semibold))
                    Image(systemName: expanded ? "chevron.up" : "chevron.down").font(.caption2)
                }.foregroundStyle(OliveTheme.accent).frame(minHeight: 32)
            }
            .accessibilityLabel(expanded ? "Hide sources" : "Show \(sources.count) sources")
            .accessibilityIdentifier("chat.sources")
            if expanded {
                ForEach(Array(sources.enumerated()), id: \.offset) { _, source in SourceCard(source: source) }
            }
        }
    }
}

struct SourceCard: View {
    let source: ChatSource
    @Environment(\.openURL) private var openURL
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text(source.id).font(.caption2.weight(.bold).monospaced()).foregroundStyle(OliveTheme.accentInk)
                    .padding(.horizontal, 5).padding(.vertical, 1).background(OliveTheme.accent, in: RoundedRectangle(cornerRadius: 4))
                    .accessibilityHidden(source.id.isEmpty)
                Text(source.title).font(.subheadline.weight(.semibold)).fixedSize(horizontal: false, vertical: true)
            }
            if let provider = source.provider { Text(provider).font(.caption).foregroundStyle(OliveTheme.secondary) }
            ForEach(facts, id: \.self) { Text($0).font(.caption2).foregroundStyle(OliveTheme.muted) }
            if let excerpt = source.excerpt, !excerpt.isEmpty {
                Text(excerpt).font(.caption).foregroundStyle(OliveTheme.secondary).lineLimit(4)
            }
            // Only validated http(s) links open, in the system browser; no link is invented.
            if let url = source.url {
                Button { openURL(url) } label: {
                    Label(url.host ?? "Open", systemImage: "arrow.up.right.square").font(.caption.weight(.semibold))
                }
                .foregroundStyle(OliveTheme.information).frame(minHeight: 32)
                .accessibilityLabel("Open source " + source.title)
                .accessibilityIdentifier("chat.source.open")
            }
        }
        .padding(10).frame(maxWidth: .infinity, alignment: .leading)
        .background(OliveTheme.raised, in: RoundedRectangle(cornerRadius: OliveTheme.Radius.control, style: .continuous))
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("chat.source")
    }
    private var facts: [String] {
        var values: [String] = []
        if source.kind == "document" || source.kind == "note" { values.append(source.page.map { "Your document · page \($0)" } ?? "Your document") }
        if let date = source.publishedAt { values.append("Published " + Self.date(date)) }
        else if source.kind == "web" || source.kind == "weather" { values.append(source.snapshot ? "Current page snapshot · publication date unknown" : "Publication date unknown") }
        if let date = source.updatedAt { values.append("Updated " + Self.date(date)) }
        if let date = source.retrievedAt, source.kind != "document" { values.append("Retrieved " + Self.date(date)) }
        return values
    }
    static func date(_ value: String) -> String {
        let parser = ISO8601DateFormatter()
        for options: ISO8601DateFormatter.Options in [[.withInternetDateTime], [.withInternetDateTime, .withFractionalSeconds], [.withFullDate]] {
            parser.formatOptions = options
            if let date = parser.date(from: value) { return date.formatted(date: .abbreviated, time: options == [.withFullDate] ? .omitted : .shortened) }
        }
        return value
    }
}

// MARK: - Media results

struct ArtifactView: View {
    let artifact: ChatArtifact
    @Environment(AppState.self) private var state
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if !artifact.known {
                OliveNotice(text: "This result type needs a newer OLIVE on this iPhone.", symbol: "questionmark.square.dashed", tint: OliveTheme.muted)
            } else if let url = state.mediaFiles[artifact.id] {
                switch artifact.kind {
                case "image": ImageArtifactView(artifact: artifact, url: url)
                case "audio": AudioArtifactView(artifact: artifact, url: url)
                default: VideoArtifactView(artifact: artifact, url: url)
                }
            } else {
                transfer
            }
        }
        // Visible results that are not on this iPhone (cleared, or interrupted) resume downloading.
        .task(id: artifact.id) { if state.mediaFiles[artifact.id] == nil && state.mediaFailures[artifact.id] == nil { state.ensureMedia([artifact]) } }
        // A container: the player controls keep their own labels and identifiers.
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("chat.artifact." + artifact.kind)
    }

    private var transfer: some View {
        let received = state.mediaProgress[artifact.id]
        return HStack(spacing: 12) {
            Image(systemName: artifact.kind == "image" ? "photo" : artifact.kind == "audio" ? "waveform" : "film")
                .font(.title3).foregroundStyle(OliveTheme.accent).frame(width: 36)
            VStack(alignment: .leading, spacing: 4) {
                if let failure = state.mediaFailures[artifact.id] {
                    Text(failure).font(.caption).foregroundStyle(OliveTheme.attention).fixedSize(horizontal: false, vertical: true)
                    Button("Retry download") { state.retryMedia(artifact) }.font(.caption.weight(.semibold))
                        .accessibilityIdentifier("chat.artifact.retry")
                } else if let received {
                    // Real byte progress: the size is known exactly.
                    ProgressView(value: Double(received), total: Double(artifact.size))
                    Text("Transferring result… " + ByteCountFormatter.string(fromByteCount: received, countStyle: .file) + " of "
                         + ByteCountFormatter.string(fromByteCount: artifact.size, countStyle: .file)).font(.caption).foregroundStyle(OliveTheme.muted)
                } else {
                    Text(state.chatConnection?.connected == true ? "Waiting to transfer…" : "Connect to your computer to download this result.")
                        .font(.caption).foregroundStyle(OliveTheme.muted)
                }
            }
        }
        .padding(12).frame(maxWidth: .infinity, alignment: .leading)
        .background(OliveTheme.raised, in: RoundedRectangle(cornerRadius: OliveTheme.Radius.card, style: .continuous))
        .accessibilityElement(children: .combine)
    }
}

/// A copy with a safe, descriptive name for sharing or saving. The peer's
/// filename is never used as a path; results stay app-owned until the user shares.
enum MediaExport {
    static func copy(_ url: URL, artifact: ChatArtifact) -> URL? {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("ChatShare", isDirectory: true)
            .appendingPathComponent(artifact.artifactID, isDirectory: true)
        try? FileManager.default.removeItem(at: folder)  // Only this artifact's previous share copy.
        do {
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            let stamp = Date().formatted(.iso8601.year().month().day())
            let name = "OLIVE \(ChatMode.named(artifact.mode).short) \(stamp) \(artifact.artifactID.prefix(6)).\(artifact.fileExtension)"
            let target = folder.appendingPathComponent(name)
            try FileManager.default.copyItem(at: url, to: target)
            return target
        } catch { return nil }
    }
}

struct MediaActions: View {
    let artifact: ChatArtifact
    let url: URL
    @State private var exporting = false
    @State private var notice: String?
    @State private var shareable: URL?
    var body: some View {
        HStack(spacing: 16) {
            if let shareable {
                ShareLink(item: shareable) { Label("Share", systemImage: "square.and.arrow.up") }
                    .accessibilityIdentifier("chat.artifact.share")
            }
            if artifact.kind != "audio" {
                Button { saveToPhotos() } label: { Label("Save to Photos", systemImage: "photo.badge.plus") }
                    .accessibilityIdentifier("chat.artifact.savePhotos")
            }
            Button { exporting = true } label: { Label("Save to Files", systemImage: "folder.badge.plus") }
                .accessibilityIdentifier("chat.artifact.saveFiles")
        }
        .font(.caption.weight(.semibold)).labelStyle(.iconOnly).foregroundStyle(OliveTheme.accent)
        .frame(minHeight: 44)
        .task(id: url) { shareable = MediaExport.copy(url, artifact: artifact) }
        .fileExporter(isPresented: $exporting, item: shareable ?? url, contentTypes: [UTType(filenameExtension: artifact.fileExtension) ?? .data],
                      defaultFilename: shareable?.lastPathComponent) { result in
            if case .success = result { notice = "Saved to Files" }
        }
        .overlay(alignment: .top) {
            if let notice { Text(notice).font(.caption2).foregroundStyle(OliveTheme.secondary).offset(y: -18).transition(.opacity) }
        }
    }

    /// Only when the user taps Save: add-only access, nothing else in the library is read.
    private func saveToPhotos() {
        let source = url, kind = artifact.kind
        PHPhotoLibrary.requestAuthorization(for: .addOnly) { status in
            guard status == .authorized || status == .limited else {
                Task { @MainActor in notice = "Allow OLIVE to add to Photos in Settings." }
                return
            }
            PHPhotoLibrary.shared().performChanges({
                let request = PHAssetCreationRequest.forAsset()
                request.addResource(with: kind == "video" ? .video : .photo, fileURL: source, options: nil)
            }) { saved, _ in Task { @MainActor in notice = saved ? "Saved to Photos" : "Couldn't save to Photos." } }
        }
    }
}

struct ImageArtifactView: View {
    let artifact: ChatArtifact
    let url: URL
    @State private var image: UIImage?
    @State private var viewing = false
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Button { viewing = true } label: {
                Group {
                    if let image { Image(uiImage: image).resizable().scaledToFit() }
                    else { ProgressView().frame(height: 180) }
                }
                .frame(maxWidth: 360, maxHeight: 360)
                .clipShape(RoundedRectangle(cornerRadius: OliveTheme.Radius.card, style: .continuous))
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Generated image from OLIVE \(ChatMode.named(artifact.mode).short)")
            .accessibilityHint("Opens full screen")
            .accessibilityIdentifier("chat.artifact.image.open")
            MediaActions(artifact: artifact, url: url)
        }
        .task(id: url) {
            let url = url
            image = await Task.detached(priority: .userInitiated) { () -> UIImage? in
                guard let source = CGImageSourceCreateWithURL(url as CFURL, nil),
                      let cg = CGImageSourceCreateThumbnailAtIndex(source, 0, [kCGImageSourceCreateThumbnailFromImageAlways: true,
                        kCGImageSourceThumbnailMaxPixelSize: 1024, kCGImageSourceCreateThumbnailWithTransform: true] as CFDictionary) else { return nil }
                return UIImage(cgImage: cg)
            }.value
        }
        .fullScreenCover(isPresented: $viewing) { ImageViewer(artifact: artifact, url: url) }
    }
}

/// Full screen with pinch to zoom, double-tap, and Share. No WebView.
struct ImageViewer: View {
    let artifact: ChatArtifact
    let url: URL
    @Environment(\.dismiss) private var dismiss
    @State private var image: UIImage?
    @State private var scale: CGFloat = 1
    @State private var base: CGFloat = 1
    @State private var offset: CGSize = .zero
    @State private var drag: CGSize = .zero
    var body: some View {
        NavigationStack {
            GeometryReader { geometry in
                Group {
                    if let image {
                        Image(uiImage: image).resizable().scaledToFit()
                            .scaleEffect(scale).offset(x: offset.width + drag.width, y: offset.height + drag.height)
                            .frame(width: geometry.size.width, height: geometry.size.height)
                            .gesture(MagnifyGesture().onChanged { scale = min(8, max(1, base * $0.magnification)) }
                                .onEnded { _ in base = scale; if scale == 1 { offset = .zero } })
                            .simultaneousGesture(DragGesture().onChanged { if scale > 1 { drag = $0.translation } }
                                .onEnded { _ in offset.width += drag.width; offset.height += drag.height; drag = .zero })
                            .onTapGesture(count: 2) { withAnimation { scale = scale > 1 ? 1 : 2.5; base = scale; if scale == 1 { offset = .zero } } }
                            .accessibilityLabel("Generated image, zoom \(Int(scale * 100)) percent")
                            .accessibilityIdentifier("chat.viewer.image")
                    } else { ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity) }
                }
            }
            .background(Color.black.ignoresSafeArea())
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() }.accessibilityIdentifier("chat.viewer.done") }
                ToolbarItem(placement: .primaryAction) { MediaActions(artifact: artifact, url: url) }
            }
            .toolbarBackground(.visible, for: .navigationBar)
        }
        .task { let url = url; image = await Task.detached { UIImage(contentsOfFile: url.path) }.value }
    }
}

/// Native playback: play, pause, seek, duration, replay and Share. Plays under
/// the normal iOS audio rules; no background audio capability is requested.
struct AudioArtifactView: View {
    let artifact: ChatArtifact
    let url: URL
    @State private var player: AVAudioPlayer?
    @State private var playing = false
    @State private var position: Double = 0
    @State private var duration: Double = 0
    private let tick = Timer.publish(every: 0.2, on: .main, in: .common).autoconnect()
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 12) {
                Button { toggle() } label: {
                    Image(systemName: playing ? "pause.fill" : (position >= duration - 0.05 && duration > 0 ? "arrow.counterclockwise" : "play.fill"))
                        .font(.system(size: 18, weight: .bold)).foregroundStyle(OliveTheme.accentInk)
                        .frame(width: 44, height: 44).background(OliveTheme.accent, in: Circle())
                }
                .accessibilityLabel(playing ? "Pause" : "Play")
                .accessibilityIdentifier("chat.audio.play")
                VStack(alignment: .leading, spacing: 2) {
                    Slider(value: Binding(get: { position }, set: { position = $0; player?.currentTime = $0 }), in: 0...max(duration, 0.1))
                        .tint(OliveTheme.accent)
                        .accessibilityLabel("Seek")
                        .accessibilityValue(Self.time(position) + " of " + Self.time(duration))
                        .accessibilityIdentifier("chat.audio.seek")
                    Text(Self.time(position) + " / " + Self.time(duration)).font(.caption2.monospacedDigit()).foregroundStyle(OliveTheme.muted)
                        .accessibilityIdentifier("chat.audio.duration")
                }
            }
            MediaActions(artifact: artifact, url: url)
        }
        .padding(12).frame(maxWidth: 420, alignment: .leading)
        .background(OliveTheme.raised, in: RoundedRectangle(cornerRadius: OliveTheme.Radius.card, style: .continuous))
        .onAppear {
            player = try? AVAudioPlayer(contentsOf: url)
            player?.prepareToPlay()
            duration = player?.duration ?? Double(artifact.durationMS ?? 0) / 1000
        }
        .onDisappear { player?.stop(); playing = false }
        .onReceive(tick) { _ in
            guard let player else { return }
            position = player.currentTime
            if playing && !player.isPlaying { playing = false; position = duration }
        }
    }
    private func toggle() {
        guard let player else { return }
        if playing { player.pause(); playing = false; return }
        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .spokenAudio)
        try? AVAudioSession.sharedInstance().setActive(true)
        if player.currentTime >= player.duration - 0.05 { player.currentTime = 0 }
        playing = player.play()
    }
    static func time(_ seconds: Double) -> String {
        let total = Int(seconds.rounded()); return String(format: "%d:%02d", total / 60, total % 60)
    }
}

/// AVPlayer streams from the verified local file; the video is never decoded into memory.
struct VideoArtifactView: View {
    let artifact: ChatArtifact
    let url: URL
    @State private var player: AVPlayer?
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            VideoPlayer(player: player)
                .aspectRatio(CGFloat(artifact.width ?? 16) / CGFloat(artifact.height ?? 9), contentMode: .fit)
                .frame(maxWidth: 420)
                .clipShape(RoundedRectangle(cornerRadius: OliveTheme.Radius.card, style: .continuous))
                .accessibilityLabel("Generated video from OLIVE VIDEO")
                .accessibilityIdentifier("chat.video.player")
            HStack {
                Text([artifact.durationMS.map { AudioArtifactView.time(Double($0) / 1000) }, artifact.hasAudio == true ? "with sound" : nil,
                      ByteCountFormatter.string(fromByteCount: artifact.size, countStyle: .file)].compactMap { $0 }.joined(separator: " · "))
                    .font(.caption2).foregroundStyle(OliveTheme.muted)
                Spacer()
                MediaActions(artifact: artifact, url: url)
            }.frame(maxWidth: 420)
        }
        .onAppear { if player == nil { player = AVPlayer(url: url) } }
        .onDisappear { player?.pause() }
    }
}
