import Cocoa
import FlutterMacOS
import ServiceManagement

@main
class AppDelegate: FlutterAppDelegate, NSWindowDelegate {
  private var statusItem: NSStatusItem?
  private let popover = NSPopover()
  private var blinkTimer: Timer?
  private var startupChannel: FlutterMethodChannel?
  private lazy var openEyesIcon = statusIcon(eyesClosed: false)
  private lazy var closedEyesIcon = statusIcon(eyesClosed: true)

  override func applicationDidFinishLaunching(_ notification: Notification) {
    NSApp.setActivationPolicy(.accessory)
    if let flutter = mainFlutterWindow?.contentViewController as? FlutterViewController {
      startupChannel = FlutterMethodChannel(name: "photonicat/startup", binaryMessenger: flutter.engine.binaryMessenger)
      startupChannel?.setMethodCallHandler { [weak self] call, result in
        guard let self else { return }
        guard #available(macOS 13.0, *) else {
          result(["status": "unsupported", "message": "Автозапуск из приложения доступен с macOS 13."])
          return
        }
        if call.method == "get" { result(self.startupState()); return }
        if call.method == "settings" {
          SMAppService.openSystemSettingsLoginItems()
          result(nil); return
        }
        guard call.method == "set", let enabled = call.arguments as? Bool else {
          result(FlutterMethodNotImplemented); return
        }
        let path = Bundle.main.bundleURL.standardizedFileURL.path
        let userApps = NSHomeDirectory() + "/Applications/"
        if enabled && !path.hasPrefix("/Applications/") && !path.hasPrefix(userApps) {
          result(FlutterError(code: "install_first", message: "Сначала перенеси Photonicat в папку «Программы» и запусти оттуда.", details: nil)); return
        }
        do {
          if enabled {
            if SMAppService.mainApp.status != .enabled && SMAppService.mainApp.status != .requiresApproval {
              try SMAppService.mainApp.register()
            }
          } else if SMAppService.mainApp.status != .notRegistered {
            try SMAppService.mainApp.unregister()
          }
          result(self.startupState())
        } catch {
          result(FlutterError(code: "startup_failed", message: "Не удалось изменить автозапуск. Проверь настройки входа macOS.", details: nil))
        }
      }
    }
    if let controller = mainFlutterWindow?.contentViewController {
      mainFlutterWindow?.contentViewController = nil
      // Keep Flutter's responder chain inside a normal child controller.
      // AppKit can consume mouse events when Flutter is the popover's root view.
      let host = NSViewController()
      host.view = NSView(frame: NSRect(x: 0, y: 0, width: 430, height: 780))
      host.addChild(controller)
      controller.view.frame = host.view.bounds
      controller.view.autoresizingMask = [.width, .height]
      host.view.addSubview(controller.view)
      popover.contentViewController = host
    }
    popover.contentSize = NSSize(width: 430, height: 780)
    popover.behavior = .transient
    popover.animates = true
    mainFlutterWindow?.delegate = self
    mainFlutterWindow?.title = "Photonicat"
    mainFlutterWindow?.setContentSize(NSSize(width: 430, height: 780))
    mainFlutterWindow?.minSize = NSSize(width: 390, height: 600)
    let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
    statusItem = item
    if let button = item.button {
      button.image = openEyesIcon
      button.toolTip = "Photonicat"
      button.setAccessibilityLabel("Photonicat")
      button.target = self
      button.action = #selector(togglePanel)
      button.sendAction(on: [.leftMouseUp, .rightMouseUp])
    }
    mainFlutterWindow?.orderOut(nil)
    scheduleBlink()
  }

  @available(macOS 13.0, *)
  private func startupState() -> [String: String] {
    switch SMAppService.mainApp.status {
    case .enabled: return ["status": "enabled"]
    case .requiresApproval: return ["status": "approval"]
    case .notRegistered: return ["status": "disabled"]
    case .notFound: return ["status": "disabled"]
    @unknown default: return ["status": "unsupported"]
    }
  }

  private func statusIcon(eyesClosed: Bool) -> NSImage {
    NSImage(size: NSSize(width: 20, height: 20), flipped: false) { _ in
        let p = NSBezierPath()
        p.move(to: NSPoint(x: 2, y: 17)); p.line(to: NSPoint(x: 7, y: 14))
        p.line(to: NSPoint(x: 13, y: 14)); p.line(to: NSPoint(x: 18, y: 17))
        p.line(to: NSPoint(x: 17, y: 6)); p.line(to: NSPoint(x: 13, y: 3))
        p.line(to: NSPoint(x: 7, y: 3)); p.line(to: NSPoint(x: 3, y: 6)); p.close()
        NSColor(calibratedRed: 1, green: 0.92, blue: 0, alpha: 1).setFill(); p.fill()
        NSColor.black.setFill()
        let eyeHeight: CGFloat = eyesClosed ? 0.65 : 2
        let eyeY: CGFloat = 9 - eyeHeight / 2
        NSBezierPath(rect: NSRect(x: 5, y: eyeY, width: 3, height: eyeHeight)).fill()
        NSBezierPath(rect: NSRect(x: 12, y: eyeY, width: 3, height: eyeHeight)).fill()
        return true
    }
  }

  private func scheduleBlink() {
    blinkTimer?.invalidate()
    let timer = Timer(timeInterval: Double.random(in: 5...9), repeats: false) { [weak self] _ in
      guard let self else { return }
      self.statusItem?.button?.image = self.closedEyesIcon
      DispatchQueue.main.asyncAfter(deadline: .now() + 0.14) { [weak self] in
        guard let self else { return }
        self.statusItem?.button?.image = self.openEyesIcon
        self.scheduleBlink()
      }
    }
    blinkTimer = timer
    RunLoop.main.add(timer, forMode: .common)
  }

  @objc private func togglePanel() {
    if NSApp.currentEvent?.type == .rightMouseUp {
      let menu = NSMenu()
      menu.addItem(withTitle: "Открыть Photonicat", action: #selector(showPanel), keyEquivalent: "")
      menu.addItem(.separator())
      menu.addItem(withTitle: "Завершить", action: #selector(quit), keyEquivalent: "q")
      for item in menu.items { item.target = self }
      statusItem?.menu = menu
      statusItem?.button?.performClick(nil)
      statusItem?.menu = nil
      return
    }
    if popover.isShown { popover.performClose(nil) } else { showPanel() }
  }

  @objc private func showPanel() {
    guard let button = statusItem?.button else { return }
    let availableHeight = (button.window?.screen?.visibleFrame.height ?? 900) - 28
    popover.contentSize = NSSize(width: 430, height: min(780, availableHeight))
    NSApp.activate(ignoringOtherApps: true)
    popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
    popover.contentViewController?.view.window?.makeKey()
  }

  @objc private func quit() { NSApp.terminate(nil) }
  func windowShouldClose(_ sender: NSWindow) -> Bool { sender.orderOut(nil); return false }
  override func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool { false }
  override func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool { showPanel(); return true }
  override func applicationSupportsSecureRestorableState(_ app: NSApplication) -> Bool { true }
}
