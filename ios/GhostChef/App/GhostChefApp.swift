import SwiftUI

@main
struct GhostChefApp: App {
    @State private var environment: AppEnvironment

    init() {
        let environment = AppEnvironment()
        // DAT SDK rule: configure once at launch, before any other Wearables call.
        environment.glasses.configure()
        _environment = State(initialValue: environment)
    }

    var body: some Scene {
        WindowGroup {
            root
                .environment(environment)
                .environment(environment.glasses)
                // Meta AI returns here after registration and permission prompts.
                .onOpenURL { environment.glasses.handle(url: $0) }
        }
    }

    @ViewBuilder
    private var root: some View {
        #if DEBUG
            // `-glassesLabMock` opens the Glasses Lab and runs every proof on MockDeviceKit,
            // so the simulator can be checked from the command line.
            if ProcessInfo.processInfo.arguments.contains("-glassesLabMock") {
                NavigationStack { GlassesLabView(outputFirst: true) }
                    .task { await environment.glasses.runAllOnMock() }
            } else {
                RootView()
            }
        #else
            RootView()
        #endif
    }
}
