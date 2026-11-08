import AppKit
import Foundation

// Small Finder entry point for the local development checkout. No credentials in this bundle.
final class LauncherDelegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ notification: Notification) {
        guard let configURL = Bundle.main.url(forResource: "launcher", withExtension: "json"),
              let data = try? Data(contentsOf: configURL),
              let config = (try? JSONSerialization.jsonObject(with: data)) as? [String: String],
              let root = config["repository"] else {
            fail("The local launcher configuration is missing. Reinstall the H Companion shortcut.")
            return
        }
        let script = URL(fileURLWithPath: root).appendingPathComponent("scripts/start-devin-companion.py")
        guard FileManager.default.fileExists(atPath: script.path) else {
            fail("The project has moved. Reinstall the H Companion shortcut from its new location.")
            return
        }
        DispatchQueue.global(qos: .userInitiated).async {
            let process = Process()
            let output = Pipe()
            process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
            process.arguments = [script.path]
            process.currentDirectoryURL = URL(fileURLWithPath: root)
            process.standardInput = FileHandle.nullDevice
            process.standardOutput = output
            process.standardError = output
            do {
                try process.run()
                let result = output.fileHandleForReading.readDataToEndOfFile()
                process.waitUntilExit()
                let message = String(data: result, encoding: .utf8) ?? "The local coach could not start."
                DispatchQueue.main.async {
                    if process.terminationStatus == 0 {
                        NSApp.terminate(nil)
                    } else {
                        self.fail(String(message.prefix(3000)))
                    }
                }
            } catch {
                DispatchQueue.main.async {
                    self.fail("The local Python launcher could not be opened. Check the H Companion installation.")
                }
            }
        }
    }

    private func fail(_ explanation: String) {
        NSApp.activate(ignoringOtherApps: true)
        let alert = NSAlert()
        alert.messageText = "H Companion could not start"
        alert.informativeText = explanation
        alert.alertStyle = .warning
        alert.addButton(withTitle: "OK")
        alert.runModal()
        NSApp.terminate(nil)
    }
}

let app = NSApplication.shared
let delegate = LauncherDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
