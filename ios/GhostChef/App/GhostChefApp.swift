import SwiftUI

@main
struct GhostChefApp: App {
    @State private var environment: AppEnvironment

    init() {
        #if DEBUG
            // `-cookFixture` uses the bundled fixture (and the still image in the simulator)
            // through the argument domain, so the user's saved Settings stay untouched.
            if ProcessInfo.processInfo.arguments.contains("-cookFixture") {
                var args = UserDefaults.standard.volatileDomain(forName: UserDefaults.argumentDomain)
                args[Settings.Key.dataSource] = Settings.DataSource.fixture.rawValue
                #if targetEnvironment(simulator)
                    args[Settings.Key.frameSource] = FrameSourceKind.stillImage.rawValue
                #endif
                UserDefaults.standard.setVolatileDomain(args, forName: UserDefaults.argumentDomain)
            }
        #endif
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

    #if DEBUG
        private static func argument(after flag: String) -> String? {
            let args = ProcessInfo.processInfo.arguments
            guard let i = args.firstIndex(of: flag), args.indices.contains(i + 1) else { return nil }
            return args[i + 1]
        }

        private static var galleryScreens: [(String, LensScreen)] {
            let args = ProcessInfo.processInfo.arguments
            let all = LensPreviewData.allScreens
            guard let i = args.firstIndex(of: "-lensGallery"), args.indices.contains(i + 1),
                let n = Int(args[i + 1]), all.indices.contains(n)
            else { return all }
            return [all[n]]
        }
    #endif

    @ViewBuilder
    private var root: some View {
        #if DEBUG
            // `-glassesLabMock` opens the Glasses Lab and runs every proof on MockDeviceKit,
            // so the simulator can be checked from the command line.
            if ProcessInfo.processInfo.arguments.contains("-glassesLabMock") {
                NavigationStack { GlassesLabView(outputFirst: true) }
                    .task { await environment.glasses.runAllOnMock() }
            } else if ProcessInfo.processInfo.arguments.contains("-lensGallery") {
                // Every LensScreen case rendered, for screenshots; `-lensGallery <n>` shows only case n.
                ScrollView {
                    VStack(spacing: 12) {
                        ForEach(Self.galleryScreens, id: \.0) { name, screen in
                            VStack(alignment: .leading, spacing: 4) {
                                Text(name).font(.caption)
                                PhoneLensView(screen: screen)
                            }
                        }
                    }
                    .padding()
                }
            } else if let id = Self.argument(after: "-cookRecipe") {
                // Opens the cook-along on a recipe id from the current data source (Settings).
                NavigationStack {
                    CookView(summary: RecipeSummary(id: id, title: "Recipe", status: .published, stepCount: 0))
                }
            } else if ProcessInfo.processInfo.arguments.contains("-cookFixture") {
                // Opens the cook-along on the bundled fixture with the still test image.
                NavigationStack {
                    CookView(summary: (try? FixtureRecipe.load())?.summary
                        ?? RecipeSummary(id: "", title: "?", status: .failed, stepCount: 0))
                }
            } else {
                RootView()
            }
        #else
            RootView()
        #endif
    }
}
