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
        .toolbarBackground(OliveTheme.ground, for: .tabBar)
        .toolbarBackground(.visible, for: .tabBar)
        .sheet(isPresented: $state.isSettingsPresented) { NavigationStack { SettingsView() } }
        .onChange(of: scenePhase) { _, phase in
            if phase == .inactive { state.saveDraft() }
        }
    }
}
