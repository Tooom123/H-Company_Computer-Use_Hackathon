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
            // With panel/overlay hidden and no tracker, there may be no own
            // shareable window at all. Explicitly requested visible IDs still
            // must all be found; an intentionally empty list is valid.
            guard !excludedWindows.isEmpty || requestedWindowIDs.isEmpty else {
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
            // CGWindowList supplies front-to-back ordering. SCWindow's layer
            // alone is not a stacking order. Keep only shareable application
            // windows and never export window titles or the images behind them.
            let shareableByID = Dictionary(content.windows.map { ($0.windowID, $0) }, uniquingKeysWith: { first, _ in first })
            let orderedInfo = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]] ?? []
            let windowMetadataCapturedAt = formatter.string(from: Date())
            let windows: [[String: Any]] = orderedInfo.compactMap { info in
                guard let idNumber = info[kCGWindowNumber as String] as? NSNumber else { return nil }
                let id = idNumber.uint32Value
                guard let window = shareableByID[id], let owner = window.owningApplication,
                      !requestedWindowIDs.contains(id), owner.processID != excludedPID,
                      window.isOnScreen,
                      let layer = info[kCGWindowLayer as String] as? NSNumber, layer.intValue >= 0,
                      let rect = info[kCGWindowBounds as String] as? [String: Any],
                      let x = rect["X"] as? NSNumber, let y = rect["Y"] as? NSNumber,
                      let width = rect["Width"] as? NSNumber, let height = rect["Height"] as? NSNumber,
                      x.doubleValue.isFinite, y.doubleValue.isFinite,
                      width.doubleValue.isFinite, height.doubleValue.isFinite,
                      width.doubleValue >= 48, height.doubleValue >= 32 else { return nil }
                if let alpha = info[kCGWindowAlpha as String] as? NSNumber, alpha.doubleValue <= 0.05 { return nil }
                let bounds = CGRect(x: x.doubleValue, y: y.doubleValue, width: width.doubleValue, height: height.doubleValue)
                guard bounds.intersects(display.frame) else { return nil }
                return ["id": id, "appName": owner.applicationName,
                        "bounds": ["x": bounds.minX, "y": bounds.minY, "width": bounds.width, "height": bounds.height]]
            }
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
                "windowMetadataCapturedAt": windowMetadataCapturedAt, "windows": windows,
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
