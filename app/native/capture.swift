import Foundation
import ScreenCaptureKit
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers

// Capture only after an explicit request. Every window owned by Electron is
// excluded by ScreenCaptureKit, including the tracker, overlay and inspector.
@main
struct Capture {
    static func main() async {
        do {
            guard #available(macOS 14.0, *) else {
                throw CaptureError.message("La capture sans overlay nécessite macOS 14 ou ultérieur.")
            }
            let args = CommandLine.arguments
            func argument(_ flag: String) throws -> String {
                guard let index = args.firstIndex(of: flag), index + 1 < args.count else {
                    throw CaptureError.message("Argument manquant : \(flag)")
                }
                return args[index + 1]
            }
            guard let displayID = UInt32(try argument("--display")),
                  let excludedPID = Int32(try argument("--exclude-pid")) else {
                throw CaptureError.message("Écran ou processus invalide.")
            }
            let output = try argument("--output")
            guard CGPreflightScreenCaptureAccess() || CGRequestScreenCaptureAccess() else {
                throw CaptureError.message("Autorisez l’enregistrement de l’écran dans Réglages Système → Confidentialité et sécurité, puis relancez l’app.")
            }
            let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
            guard let display = content.displays.first(where: { $0.displayID == displayID }) else {
                throw CaptureError.message("L’écran sélectionné n’est plus disponible.")
            }
            let ownApplications = content.applications.filter { $0.processID == excludedPID }
            guard !ownApplications.isEmpty else {
                throw CaptureError.message("Impossible d’identifier les fenêtres H-Companion à exclure. Capture annulée.")
            }
            let filter = SCContentFilter(display: display, excludingApplications: ownApplications, exceptingWindows: [])
            let configuration = SCStreamConfiguration()
            configuration.width = CGDisplayPixelsWide(displayID)
            configuration.height = CGDisplayPixelsHigh(displayID)
            configuration.showsCursor = false
            configuration.capturesAudio = false
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            let captureStartedAt = formatter.string(from: Date())
            let image = try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: configuration)
            let captureCompletedAt = formatter.string(from: Date())
            guard let destination = CGImageDestinationCreateWithURL(URL(fileURLWithPath: output) as CFURL, UTType.png.identifier as CFString, 1, nil) else {
                throw CaptureError.message("Impossible de préparer l’image de capture.")
            }
            CGImageDestinationAddImage(destination, image, nil)
            guard CGImageDestinationFinalize(destination) else {
                throw CaptureError.message("Impossible d’encoder la capture.")
            }
            let metadata: [String: Any] = [
                "width": image.width, "height": image.height,
                "captureStartedAt": captureStartedAt, "captureCompletedAt": captureCompletedAt,
                "excludedApplicationCount": ownApplications.count,
                "excludedWindowCount": content.windows.filter { $0.owningApplication?.processID == excludedPID }.count
            ]
            let json = try JSONSerialization.data(withJSONObject: metadata)
            print(String(decoding: json, as: UTF8.self))
        } catch {
            FileHandle.standardError.write(Data("\(error.localizedDescription)\n".utf8))
            exit(1)
        }
    }
}

enum CaptureError: LocalizedError {
    case message(String)
    var errorDescription: String? { if case let .message(text) = self { return text }; return nil }
}
