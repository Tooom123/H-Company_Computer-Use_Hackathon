import Foundation
import ScreenCaptureKit
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers

// Capture only after an explicit request. Electron passes its native window IDs:
// ScreenCaptureKit does not always attribute these windows to Electron's main PID.
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
            var requestedWindowIDs = Set<CGWindowID>()
            if args.contains("--exclude-window-ids") {
                let values = try argument("--exclude-window-ids")
                if !values.isEmpty {
                    for value in values.split(separator: ",", omittingEmptySubsequences: false) {
                        guard let id = UInt32(value), id > 0 else {
                            throw CaptureError.message("Liste d’identifiants de fenêtres invalide.")
                        }
                        requestedWindowIDs.insert(id)
                    }
                }
            }
            let output = try argument("--output")
            guard CGPreflightScreenCaptureAccess() || CGRequestScreenCaptureAccess() else {
                throw CaptureError.message("Autorisez l’enregistrement de l’écran dans Réglages Système → Confidentialité et sécurité, puis relancez l’app.")
            }
            // Include occluded/offscreen windows so an overlay or inspector can
            // still be matched. The caller lists visible, live windows; if one
            // disappears during capture, fail below and let the user retry.
            let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)
            guard let display = content.displays.first(where: { $0.displayID == displayID }) else {
                throw CaptureError.message("L’écran sélectionné n’est plus disponible.")
            }
            let ownApplications = content.applications.filter { $0.processID == excludedPID }
            let explicitMatches = content.windows.filter { requestedWindowIDs.contains($0.windowID) }
            let pidMatches = content.windows.filter { $0.owningApplication?.processID == excludedPID }
            let excludedWindows = content.windows.filter {
                requestedWindowIDs.contains($0.windowID) || $0.owningApplication?.processID == excludedPID
            }
            guard !excludedWindows.isEmpty else {
                // Diagnostics contain only our requested IDs and aggregate counts,
                // never other applications' names, titles or window identifiers.
                let requested = requestedWindowIDs.sorted().map(String.init).joined(separator: ",")
                throw CaptureError.message("Impossible d’identifier les fenêtres H-Companion à exclure (IDs demandés : [\(requested)], correspondances ID : 0, correspondances PID : 0, fenêtres disponibles : \(content.windows.count)). Capture annulée.")
            }
            let matchedIDs = Set(explicitMatches.map { $0.windowID })
            let missingIDs = requestedWindowIDs.subtracting(matchedIDs)
            guard missingIDs.isEmpty else {
                let missing = missingIDs.sorted().map(String.init).joined(separator: ",")
                throw CaptureError.message("Certaines fenêtres H-Companion visibles ne peuvent pas être exclues (IDs : [\(missing)]). Capture annulée ; réessayez une fois les fenêtres stabilisées.")
            }
            let filter = SCContentFilter(display: display, excludingWindows: excludedWindows)
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
                "requestedWindowCount": requestedWindowIDs.count,
                "matchedExplicitWindowCount": explicitMatches.count,
                "pidMatchedWindowCount": pidMatches.count,
                "unmatchedWindowIDs": requestedWindowIDs.subtracting(matchedIDs).sorted(),
                "excludedWindowCount": excludedWindows.count
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
