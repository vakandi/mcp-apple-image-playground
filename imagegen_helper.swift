import Foundation
import ImagePlayground
import AppKit
import Vision
import CoreImage
import Combine

struct Request: Codable {
    let mode: String
    let prompt: String?
    let style: String?
    let count: Int?
    let outputDir: String?
    let prefix: String?
    let inputPath: String?
    let inputImage: String?
    let targetWidth: Int?
    let targetHeight: Int?
    let outputPath: String?
    let filter: String?
    let intensity: Double?
}

struct ResultImage: Codable {
    let path: String
    let index: Int
}

struct FaceInfo: Codable {
    let x: Double
    let y: Double
    let width: Double
    let height: Double
}

struct ImageInfo: Codable {
    let width: Int
    let height: Int
    let faces: [FaceInfo]
    let hasTransparency: Bool
}

struct Response: Codable {
    let success: Bool
    let images: [ResultImage]?
    let availableStyles: [String]?
    let imageInfo: ImageInfo?
    let error: String?
}

func writeResponse(_ r: Response, to path: String) {
    if let data = try? JSONEncoder().encode(r) {
        try? data.write(to: URL(fileURLWithPath: path))
    }
}

func printResponse(_ r: Response, exitCode: Int32 = 0) -> Never {
    if let data = try? JSONEncoder().encode(r),
       let str = String(data: data, encoding: .utf8) {
        print(str)
    }
    exit(exitCode)
}

// MARK: - Image Generation

func generateImages(prompt: String, style: String, count: Int, outputDir: String, prefix: String, inputImage: String?) async -> Response {
    do {
        setenv("LANG", "en_US.UTF-8", 1)
        setenv("LC_ALL", "en_US.UTF-8", 1)
        setenv("LC_CTYPE", "en_US.UTF-8", 1)
        setlocale(LC_ALL, "en_US.UTF-8")
        let creator = try await ImageCreator()
        let available = creator.availableStyles
        guard let matchedStyle = available.first(where: { $0.id == style }) else {
            return Response(success: false, images: nil, availableStyles: available.map { $0.id },
                            imageInfo: nil,
                            error: "Style '\(style)' unavailable. Available: \(available.map { $0.id })")
        }
        try FileManager.default.createDirectory(atPath: outputDir, withIntermediateDirectories: true)

        // Build concepts: text prompt + optional photo input
        var concepts: [ImagePlaygroundConcept] = [.text(prompt)]
        if let imgPath = inputImage, !imgPath.isEmpty {
            if let nsImage = NSImage(contentsOfFile: imgPath),
               let tiff = nsImage.tiffRepresentation,
               let bitmap = NSBitmapImageRep(data: tiff),
               let cgImg = bitmap.cgImage(forProposedRect: nil, context: nil, hints: nil) {
                concepts.append(.image(cgImg))
            }
        }

        let stream = creator.images(for: concepts, style: matchedStyle, limit: count)
        var results: [ResultImage] = []
        var idx = 0
        for try await generated in stream {
            let rep = NSBitmapImageRep(cgImage: generated.cgImage)
            guard let pngData = rep.representation(using: .png, properties: [:]) else { continue }
            let filename = "\(prefix)_\(idx).png"
            let path = (outputDir as NSString).appendingPathComponent(filename)
            try pngData.write(to: URL(fileURLWithPath: path))
            results.append(ResultImage(path: path, index: idx))
            idx += 1
        }
        return Response(success: true, images: results, availableStyles: available.map { $0.id },
                        imageInfo: nil, error: nil)
    } catch {
        return Response(success: false, images: nil, availableStyles: nil, imageInfo: nil,
                        error: "\(error)")
    }
}

// MARK: - ChatGPT External Provider Generation (via ImagePlaygroundViewController)

func generateChatGPT(prompt: String, outputDir: String, prefix: String) async -> Response {
    let semaphore = DispatchSemaphore(value: 0)
    var resultResponse: Response = Response(success: false, images: nil, availableStyles: nil,
                                            imageInfo: nil, error: "Generation did not complete")
    
    await MainActor.run {
        let vc = ImagePlaygroundViewController()
        vc.concepts = [.text(prompt)]
        if #available(macOS 26.0, *) {
            vc.allowedGenerationStyles = [.externalProvider]
        }
        
        class DelegateHandler: NSObject, ImagePlaygroundViewController.Delegate {
            let outputDir: String
            let prefix: String
            let semaphore: DispatchSemaphore
            var result: Response
            
            init(outputDir: String, prefix: String, semaphore: DispatchSemaphore) {
                self.outputDir = outputDir
                self.prefix = prefix
                self.semaphore = semaphore
                self.result = Response(success: false, images: nil, availableStyles: nil,
                                       imageInfo: nil, error: "Generation did not complete")
            }
            
            func imagePlaygroundViewController(_ controller: ImagePlaygroundViewController,
                                               didCreateImageAt imageURL: URL) {
                do {
                    try FileManager.default.createDirectory(atPath: outputDir, withIntermediateDirectories: true)
                    let filename = "\(prefix)_chatgpt_0.png"
                    let destPath = "\(outputDir)/\(filename)"
                    if FileManager.default.fileExists(atPath: destPath) {
                        try FileManager.default.removeItem(atPath: destPath)
                    }
                    try FileManager.default.copyItem(at: imageURL, to: URL(fileURLWithPath: destPath))
                    result = Response(success: true,
                                      images: [ResultImage(path: destPath, index: 0)],
                                      availableStyles: nil, imageInfo: nil, error: nil)
                } catch {
                    result = Response(success: false, images: nil, availableStyles: nil,
                                      imageInfo: nil, error: "Failed to copy generated image: \(error)")
                }
                semaphore.signal()
            }
            
            func imagePlaygroundViewControllerDidCancel(_ controller: ImagePlaygroundViewController) {
                result = Response(success: false, images: nil, availableStyles: nil,
                                  imageInfo: nil, error: "User cancelled generation")
                semaphore.signal()
            }
        }
        
        let handler = DelegateHandler(outputDir: outputDir, prefix: prefix, semaphore: semaphore)
        vc.delegate = handler
        
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 600, height: 600),
                              styleMask: [.titled, .closable],
                              backing: .buffered, defer: false)
        window.title = "Image Playground — ChatGPT"
        window.contentViewController = vc
        window.center()
        window.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
        
        objc_setAssociatedObject(window, "handler", handler, .OBJC_ASSOCIATION_RETAIN)
        objc_setAssociatedObject(vc, "window", window, .OBJC_ASSOCIATION_RETAIN)
        
        DispatchQueue.main.asyncAfter(deadline: .now() + 5) {
            let script = """
            tell application "System Events"
                tell process "ImageGenHelper"
                    try
                        click button 1 of window 1
                    end try
                end tell
            end tell
            """
            if let appleScript = NSAppleScript(source: script) {
                var error: NSDictionary?
                appleScript.executeAndReturnError(&error)
            }
        }
        
        DispatchQueue.main.asyncAfter(deadline: .now() + 90) {
            if semaphore.wait(timeout: .now()) == .timedOut {
                resultResponse = Response(success: false, images: nil, availableStyles: nil,
                                          imageInfo: nil, error: "ChatGPT generation timed out (90s)")
                window.close()
                semaphore.signal()
            }
        }
    }
    
    semaphore.wait()
    return resultResponse
}

// MARK: - Vision: Face Detection

func detectFaces(inputPath: String) -> Response {
    guard let img = NSImage(contentsOfFile: inputPath),
          let tiff = img.tiffRepresentation,
          let bitmap = NSBitmapImageRep(data: tiff),
          let cgImg = bitmap.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        return Response(success: false, images: nil, availableStyles: nil, imageInfo: nil,
                        error: "Could not load image at \(inputPath)")
    }
    let w = cgImg.width
    let h = cgImg.height
    var faces: [FaceInfo] = []
    let semaphore = DispatchSemaphore(value: 0)
    let request = VNDetectFaceRectanglesRequest { req, _ in
        if let results = req.results as? [VNFaceObservation] {
            faces = results.map { obs in
                FaceInfo(
                    x: Double(obs.boundingBox.origin.x) * Double(w),
                    y: Double((1.0 - obs.boundingBox.origin.y - obs.boundingBox.size.height)) * Double(h),
                    width: Double(obs.boundingBox.size.width) * Double(w),
                    height: Double(obs.boundingBox.size.height) * Double(h)
                )
            }
        }
        semaphore.signal()
    }
    try? VNImageRequestHandler(cgImage: cgImg, options: [:]).perform([request])
    semaphore.wait()
    return Response(success: true, images: nil, availableStyles: nil,
                    imageInfo: ImageInfo(width: w, height: h, faces: faces, hasTransparency: bitmap.hasAlpha),
                    error: nil)
}

// MARK: - Smart Crop

func smartCrop(inputPath: String, targetW: Int, targetH: Int, outputPath: String) -> Response {
    guard let img = NSImage(contentsOfFile: inputPath),
          let tiff = img.tiffRepresentation,
          let bitmap = NSBitmapImageRep(data: tiff),
          let cgImg = bitmap.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        return Response(success: false, images: nil, availableStyles: nil, imageInfo: nil,
                        error: "Could not load image at \(inputPath)")
    }
    let srcW = Double(cgImg.width)
    let srcH = Double(cgImg.height)
    let targetRatio = Double(targetW) / Double(targetH)
    var faces: [FaceInfo] = []
    let sem = DispatchSemaphore(value: 0)
    let faceReq = VNDetectFaceRectanglesRequest { req, _ in
        if let results = req.results as? [VNFaceObservation] {
            faces = results.map { obs in
                FaceInfo(x: Double(obs.boundingBox.origin.x),
                         y: Double(1.0 - obs.boundingBox.origin.y - obs.boundingBox.size.height),
                         width: Double(obs.boundingBox.size.width),
                         height: Double(obs.boundingBox.size.height))
            }
        }
        sem.signal()
    }
    try? VNImageRequestHandler(cgImage: cgImg, options: [:]).perform([faceReq])
    sem.wait()

    var cropCenterX = srcW / 2.0
    var cropCenterY = srcH / 2.0
    if !faces.isEmpty {
        cropCenterX = faces.map { $0.x + $0.width / 2.0 }.reduce(0, +) / Double(faces.count) * srcW
        cropCenterY = faces.map { $0.y + $0.height / 2.0 }.reduce(0, +) / Double(faces.count) * srcH
    }
    var cropW: Double
    var cropH: Double
    if targetRatio > srcW / srcH {
        cropW = srcW
        cropH = srcW / targetRatio
    } else {
        cropH = srcH
        cropW = srcH * targetRatio
    }
    let cropX = max(0, min(cropCenterX - cropW / 2.0, srcW - cropW))
    let cropY = max(0, min(cropCenterY - cropH / 2.0, srcH - cropH))

    let ciImage = CIImage(cgImage: cgImg)
    let cropped = ciImage.cropped(to: CGRect(x: cropX, y: cropY, width: cropW, height: cropH))
        .transformed(by: CGAffineTransform(translationX: -cropX, y: -cropY))

    let scaleFilter = CIFilter(name: "CILanczosScaleTransform")!
    scaleFilter.setValue(cropped, forKey: kCIInputImageKey)
    scaleFilter.setValue(Float(targetH) / Float(cropH), forKey: kCIInputScaleKey)
    scaleFilter.setValue(1.0, forKey: kCIInputAspectRatioKey)

    guard let output = scaleFilter.outputImage else {
        return Response(success: false, images: nil, availableStyles: nil, imageInfo: nil,
                        error: "Scale filter produced no output")
    }
    let ciCtx = CIContext(options: [.useSoftwareRenderer: false])
    guard let cgResult = ciCtx.createCGImage(output, from: output.extent) else {
        return Response(success: false, images: nil, availableStyles: nil, imageInfo: nil,
                        error: "Failed to render cropped image")
    }
    let rep = NSBitmapImageRep(cgImage: cgResult)
    if let pngData = rep.representation(using: .png, properties: [:]) {
        try? pngData.write(to: URL(fileURLWithPath: outputPath))
        return Response(success: true, images: [ResultImage(path: outputPath, index: 0)],
                        availableStyles: nil, imageInfo: nil, error: nil)
    }
    return Response(success: false, images: nil, availableStyles: nil, imageInfo: nil,
                    error: "Failed to encode PNG")
}

// MARK: - Core Image Filters

func applyFilter(inputPath: String, filterName: String, intensity: Double, outputPath: String) -> Response {
    guard let img = NSImage(contentsOfFile: inputPath),
          let tiff = img.tiffRepresentation,
          let bitmap = NSBitmapImageRep(data: tiff),
          let cgImg = bitmap.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        return Response(success: false, images: nil, availableStyles: nil, imageInfo: nil,
                        error: "Could not load image at \(inputPath)")
    }
    let ciImage = CIImage(cgImage: cgImg)
    var output: CIImage?
    switch filterName {
    case "blur":
        let f = CIFilter(name: "CIGaussianBlur")!
        f.setValue(ciImage, forKey: kCIInputImageKey)
        f.setValue(Float(intensity * 20.0), forKey: kCIInputRadiusKey)
        output = f.outputImage
    case "sharpen":
        let f = CIFilter(name: "CISharpenLuminance")!
        f.setValue(ciImage, forKey: kCIInputImageKey)
        f.setValue(Float(intensity * 2.0), forKey: "inputSharpness")
        output = f.outputImage
    case "brightness":
        let f = CIFilter(name: "CIColorControls")!
        f.setValue(ciImage, forKey: kCIInputImageKey)
        f.setValue(Float(intensity), forKey: kCIInputBrightnessKey)
        output = f.outputImage
    case "contrast":
        let f = CIFilter(name: "CIColorControls")!
        f.setValue(ciImage, forKey: kCIInputImageKey)
        f.setValue(1.0 + Float(intensity), forKey: kCIInputContrastKey)
        output = f.outputImage
    case "saturation":
        let f = CIFilter(name: "CIColorControls")!
        f.setValue(ciImage, forKey: kCIInputImageKey)
        f.setValue(1.0 + Float(intensity), forKey: kCIInputSaturationKey)
        output = f.outputImage
    case "vignette":
        let f = CIFilter(name: "CIVignette")!
        f.setValue(ciImage, forKey: kCIInputImageKey)
        f.setValue(Float(intensity * 5.0), forKey: kCIInputIntensityKey)
        output = f.outputImage
    case "sepia":
        let f = CIFilter(name: "CISepiaTone")!
        f.setValue(ciImage, forKey: kCIInputImageKey)
        f.setValue(Float(intensity), forKey: kCIInputIntensityKey)
        output = f.outputImage
    case "noir":
        let f = CIFilter(name: "CIPhotoEffectNoir")!
        f.setValue(ciImage, forKey: kCIInputImageKey)
        output = f.outputImage
    case "instant":
        let f = CIFilter(name: "CIPhotoEffectInstant")!
        f.setValue(ciImage, forKey: kCIInputImageKey)
        output = f.outputImage
    case "chrome":
        let f = CIFilter(name: "CIPhotoEffectChrome")!
        f.setValue(ciImage, forKey: kCIInputImageKey)
        output = f.outputImage
    default:
        return Response(success: false, images: nil, availableStyles: nil, imageInfo: nil,
                        error: "Unknown filter '\(filterName)'. Available: blur, sharpen, brightness, contrast, saturation, vignette, sepia, noir, instant, chrome")
    }
    guard let result = output else {
        return Response(success: false, images: nil, availableStyles: nil, imageInfo: nil,
                        error: "Filter produced no output")
    }
    let ciCtx = CIContext(options: [.useSoftwareRenderer: false])
    guard let cgResult = ciCtx.createCGImage(result, from: result.extent) else {
        return Response(success: false, images: nil, availableStyles: nil, imageInfo: nil,
                        error: "Failed to render filter output")
    }
    let rep = NSBitmapImageRep(cgImage: cgResult)
    if let pngData = rep.representation(using: .png, properties: [:]) {
        try? pngData.write(to: URL(fileURLWithPath: outputPath))
        return Response(success: true, images: [ResultImage(path: outputPath, index: 0)],
                        availableStyles: nil, imageInfo: nil, error: nil)
    }
    return Response(success: false, images: nil, availableStyles: nil, imageInfo: nil,
                    error: "Failed to encode PNG")
}

// MARK: - Image Info

func getImageInfo(inputPath: String) -> Response {
    guard let img = NSImage(contentsOfFile: inputPath),
          let tiff = img.tiffRepresentation,
          let bitmap = NSBitmapImageRep(data: tiff) else {
        return Response(success: false, images: nil, availableStyles: nil, imageInfo: nil,
                        error: "Could not load image at \(inputPath)")
    }
    return Response(success: true, images: nil, availableStyles: nil,
                    imageInfo: ImageInfo(width: bitmap.pixelsWide, height: bitmap.pixelsHigh,
                                         faces: [], hasTransparency: bitmap.hasAlpha),
                    error: nil)
}

// MARK: - Request Router

func handleRequest(_ request: Request) async -> Response {
    switch request.mode {
    case "list-styles":
        do {
            let creator = try await ImageCreator()
            return Response(success: true, images: nil,
                            availableStyles: creator.availableStyles.map { $0.id },
                            imageInfo: nil, error: nil)
        } catch {
            return Response(success: false, images: nil, availableStyles: nil,
                            imageInfo: nil, error: "\(error)")
        }
    case "generate":
        guard let prompt = request.prompt, !prompt.isEmpty else {
            return Response(success: false, images: nil, availableStyles: nil,
                            imageInfo: nil, error: "Missing 'prompt'.")
        }
        return await generateImages(prompt: prompt, style: request.style ?? "illustration",
                                     count: max(1, min(request.count ?? 1, 4)),
                                     outputDir: request.outputDir ?? NSTemporaryDirectory(),
                                     prefix: request.prefix ?? "aigen",
                                     inputImage: request.inputImage)
    case "generate-chatgpt":
        guard let prompt = request.prompt, !prompt.isEmpty else {
            return Response(success: false, images: nil, availableStyles: nil,
                            imageInfo: nil, error: "Missing 'prompt'.")
        }
        return await generateChatGPT(prompt: prompt,
                                     outputDir: request.outputDir ?? NSTemporaryDirectory(),
                                     prefix: request.prefix ?? "aigen")
    case "detect-faces":
        guard let path = request.inputPath else {
            return Response(success: false, images: nil, availableStyles: nil,
                            imageInfo: nil, error: "Missing 'inputPath'.")
        }
        return detectFaces(inputPath: path)
    case "smart-crop":
        guard let path = request.inputPath, let tw = request.targetWidth, let th = request.targetHeight else {
            return Response(success: false, images: nil, availableStyles: nil,
                            imageInfo: nil, error: "Missing 'inputPath', 'targetWidth', or 'targetHeight'.")
        }
        let out = request.outputPath ?? {
            let dir = (path as NSString).deletingLastPathComponent
            let name = ((path as NSString).lastPathComponent as NSString).deletingPathExtension
            return "\(dir)/\(name)_smartcrop_\(tw)x\(th).png"
        }()
        return smartCrop(inputPath: path, targetW: tw, targetH: th, outputPath: out)
    case "apply-filter":
        guard let path = request.inputPath, let filterName = request.filter else {
            return Response(success: false, images: nil, availableStyles: nil,
                            imageInfo: nil, error: "Missing 'inputPath' or 'filter'.")
        }
        let out = request.outputPath ?? {
            let dir = (path as NSString).deletingLastPathComponent
            let name = ((path as NSString).lastPathComponent as NSString).deletingPathExtension
            return "\(dir)/\(name)_\(filterName).png"
        }()
        return applyFilter(inputPath: path, filterName: filterName,
                           intensity: request.intensity ?? 0.5, outputPath: out)
    case "info":
        guard let path = request.inputPath else {
            return Response(success: false, images: nil, availableStyles: nil,
                            imageInfo: nil, error: "Missing 'inputPath'.")
        }
        return getImageInfo(inputPath: path)
    default:
        return Response(success: false, images: nil, availableStyles: nil, imageInfo: nil,
                        error: "Unknown mode '\(request.mode)'.")
    }
}

// MARK: - Entry Point

if CommandLine.arguments.count <= 1 {
    guard let mode = ProcessInfo.processInfo.environment["IMAGE_HELPER_MODE"],
          let outputPath = ProcessInfo.processInfo.environment["IMAGE_HELPER_OUTPUT"] else {
        print("{\"success\":false,\"error\":\"No CLI args and no IMAGE_HELPER_MODE env var.\"}")
        exit(1)
    }

    let app = NSApplication.shared
    app.setActivationPolicy(.regular)

    let window = NSWindow(
        contentRect: NSRect(x: 0, y: 0, width: 400, height: 300),
        styleMask: [.titled, .closable],
        backing: .buffered,
        defer: false
    )
    window.title = "ImageGenHelper"
    window.contentView = NSView(frame: NSRect(x: 0, y: 0, width: 400, height: 300))
    window.center()

    class AppDelegate: NSObject, NSApplicationDelegate {
        let mode: String
        let outputPath: String
        init(mode: String, outputPath: String) {
            self.mode = mode
            self.outputPath = outputPath
        }
        func applicationDidFinishLaunching(_ notification: Notification) {
            NSApplication.shared.activate(ignoringOtherApps: true)
            if let w = NSApplication.shared.windows.first {
                w.makeKeyAndOrderFront(nil)
            }

            UserDefaults.standard.set(["en"], forKey: "AppleLanguages")
            UserDefaults.standard.set("en-US", forKey: "AppleLocale")

            if let globalDomain = UserDefaults(suiteName: ".GlobalPreferences") {
                globalDomain.set(["en"], forKey: "AppleLanguages")
                globalDomain.set("en-US", forKey: "AppleLocale")
            }

            Task { @MainActor [self] in
                try? await Task.sleep(for: .seconds(3))
                NSApplication.shared.activate(ignoringOtherApps: true)

                let request: Request
                if self.mode == "list-styles" {
                    request = Request(mode: "list-styles", prompt: nil, style: nil, count: nil,
                                      outputDir: nil, prefix: nil, inputPath: nil, inputImage: nil,
                                      targetWidth: nil, targetHeight: nil, outputPath: nil,
                                      filter: nil, intensity: nil)
                } else if self.mode == "generate-chatgpt" {
                    let prompt = ProcessInfo.processInfo.environment["IMAGE_HELPER_PROMPT"] ?? ""
                    let outputDir = ProcessInfo.processInfo.environment["IMAGE_HELPER_DIR"] ?? NSTemporaryDirectory()
                    let prefix = ProcessInfo.processInfo.environment["IMAGE_HELPER_PREFIX"] ?? "chatgpt"
                    request = Request(mode: "generate-chatgpt", prompt: prompt, style: nil, count: nil,
                                      outputDir: outputDir, prefix: prefix,
                                      inputPath: nil, inputImage: nil,
                                      targetWidth: nil, targetHeight: nil,
                                      outputPath: nil, filter: nil, intensity: nil)
                } else {
                    let style = ProcessInfo.processInfo.environment["IMAGE_HELPER_STYLE"] ?? "illustration"
                    let count = Int(ProcessInfo.processInfo.environment["IMAGE_HELPER_COUNT"] ?? "1") ?? 1
                    let outputDir = ProcessInfo.processInfo.environment["IMAGE_HELPER_DIR"] ?? NSTemporaryDirectory()
                    let prefix = ProcessInfo.processInfo.environment["IMAGE_HELPER_PREFIX"] ?? "aigen"
                    let prompt = ProcessInfo.processInfo.environment["IMAGE_HELPER_PROMPT"] ?? ""
                    let inputImg = ProcessInfo.processInfo.environment["IMAGE_HELPER_INPUT_IMAGE"] ?? ""
                    request = Request(mode: "generate", prompt: prompt, style: style, count: count,
                                      outputDir: outputDir, prefix: prefix,
                                      inputPath: nil, inputImage: inputImg.isEmpty ? nil : inputImg,
                                      targetWidth: nil, targetHeight: nil,
                                      outputPath: nil, filter: nil, intensity: nil)
                }
                let result = await handleRequest(request)
                writeResponse(result, to: self.outputPath)
                NSApplication.shared.terminate(nil)
            }
        }
    }

    let delegate = AppDelegate(mode: mode, outputPath: outputPath)
    app.delegate = delegate
    app.run()
} else {
    let semaphore = DispatchSemaphore(value: 0)
    Task {
        let args = CommandLine.arguments
        guard let argData = args[1].data(using: .utf8),
              let request = try? JSONDecoder().decode(Request.self, from: argData) else {
            printResponse(Response(success: false, images: nil, availableStyles: nil, imageInfo: nil,
                                    error: "First argument must be a JSON string."),
                          exitCode: 1)
        }
        let needsForeground = (request.mode == "generate" || request.mode == "list-styles")
        if needsForeground {
            let result = await launchViaOpen(request: request, args: args[1])
            printResponse(result)
        } else {
            let result = await handleRequest(request)
            printResponse(result)
        }
        semaphore.signal()
    }
    semaphore.wait()
}

// MARK: - Launch via `open` command (the proven pattern)

let handshakeDir = "/tmp/com.communitymanager.imagegen-helper"

func launchViaOpen(request: Request, args: String) async -> Response {
    let fm = FileManager.default
    do { try fm.createDirectory(atPath: handshakeDir, withIntermediateDirectories: true) } catch {}

    let requestID = UUID().uuidString
    let outputPath = "\(handshakeDir)/resp_\(requestID).json"

    let appBundlePath = "\(handshakeDir)/ImageGenHelper.app"
    let contentsDir = "\(appBundlePath)/Contents"
    let macOSDir = "\(contentsDir)/MacOS"

    do {
        try fm.createDirectory(atPath: macOSDir, withIntermediateDirectories: true)
        let binaryDest = "\(macOSDir)/imagegen_helper"
        if fm.fileExists(atPath: binaryDest) { try fm.removeItem(atPath: binaryDest) }
        try fm.createSymbolicLink(atPath: binaryDest, withDestinationPath: CommandLine.arguments[0])

        let plist = """
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0">
        <dict>
            <key>CFBundleIdentifier</key>
            <string>com.communitymanager.imagegen-helper</string>
            <key>CFBundleName</key>
            <string>ImageGenHelper</string>
            <key>CFBundleExecutable</key>
            <string>imagegen_helper</string>
            <key>CFBundlePackageType</key>
            <string>APPL</string>
            <key>LSUIElement</key>
            <false/>
        </dict>
        </plist>
        """
        try plist.write(toFile: "\(contentsDir)/Info.plist", atomically: true, encoding: .utf8)
    } catch {
        return Response(success: false, images: nil, availableStyles: nil, imageInfo: nil,
                        error: "Failed to create .app bundle: \(error)")
    }

    var env = ProcessInfo.processInfo.environment
    env["IMAGE_HELPER_PROMPT"] = request.prompt ?? ""
    env["IMAGE_HELPER_STYLE"] = request.style ?? "illustration"
    env["IMAGE_HELPER_COUNT"] = "\(request.count ?? 1)"
    env["IMAGE_HELPER_DIR"] = request.outputDir ?? NSTemporaryDirectory()
    env["IMAGE_HELPER_PREFIX"] = request.prefix ?? "aigen"
    env["IMAGE_HELPER_OUTPUT"] = outputPath
    env["IMAGE_HELPER_INPUT_IMAGE"] = request.inputImage ?? ""
    env["LANG"] = "en_US.UTF-8"
    env["LC_ALL"] = "en_US.UTF-8"

    let proc = Process()
    proc.executableURL = URL(fileURLWithPath: "/usr/bin/open")
    proc.arguments = ["-a", appBundlePath]
    proc.environment = env

    do {
        try proc.run()
        proc.waitUntilExit()
    } catch {
        return Response(success: false, images: nil, availableStyles: nil, imageInfo: nil,
                        error: "Failed to launch via open: \(error)")
    }

    let deadline = Date().addingTimeInterval(120)
    while Date() < deadline {
        if fm.fileExists(atPath: outputPath),
           let data = try? Data(contentsOf: URL(fileURLWithPath: outputPath)),
           let resp = try? JSONDecoder().decode(Response.self, from: data) {
            try? fm.removeItem(atPath: outputPath)
            return resp
        }
        try? await Task.sleep(for: .milliseconds(300))
    }
    try? fm.removeItem(atPath: outputPath)
    return Response(success: false, images: nil, availableStyles: nil, imageInfo: nil,
                    error: "Timed out waiting for foreground generation (120s).")
}
