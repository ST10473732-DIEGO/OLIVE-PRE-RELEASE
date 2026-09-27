import SwiftUI

struct RootView: View {
    @Environment(AppState.self) private var state
    @Environment(\.scenePhase) private var scenePhase
    var body: some View {
        @Bindable var state = state
        TabView(selection: $state.destination) {
            NavigationStack { HomeView() }
                .tabItem { Label("Home", systemImage: Destination.home.symbol) }.tag(Destination.home)
            NavigationStack { ChatView() }
                .tabItem { Label("Chat", systemImage: Destination.chat.symbol) }.tag(Destination.chat)
            NavigationStack { DevicesView() }
                .tabItem { Label("Devices", systemImage: Destination.devices.symbol) }.tag(Destination.devices)
        }
        .foregroundStyle(OliveTheme.text)
        .modifier(TabBarBackground())
        .sheet(isPresented: $state.isSettingsPresented) { NavigationStack { SettingsView() } }
        .task { state.activate() }
        .onChange(of: state.session?.selectedID) { _, _ in state.restoreCompletedChat() }
        .onChange(of: scenePhase) { _, phase in
            if phase == .inactive { state.saveDraft() }
            if phase == .background { state.suspend() }
            if phase == .active { state.activate() }
        }
    }
}

/// iOS 26+ floats a glass tab bar over content; forcing a solid bar there leaves a black band behind it.
private struct TabBarBackground: ViewModifier {
    func body(content: Content) -> some View {
        if #available(iOS 26, *) { content } else {
            content.toolbarBackground(OliveTheme.ground, for: .tabBar).toolbarBackground(.visible, for: .tabBar)
        }
    }
}
