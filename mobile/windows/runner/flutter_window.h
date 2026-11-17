#ifndef RUNNER_FLUTTER_WINDOW_H_
#define RUNNER_FLUTTER_WINDOW_H_

#include <flutter/dart_project.h>
#include <flutter/flutter_view_controller.h>

#include <memory>
#include <future>
#include <optional>
#include <flutter/method_channel.h>
#include <flutter/encodable_value.h>
#include <shellapi.h>

#include "win32_window.h"

// A window that does nothing but host a Flutter view.
class FlutterWindow : public Win32Window {
 public:
  // Creates a new FlutterWindow hosting a Flutter view running |project|.
  explicit FlutterWindow(const flutter::DartProject& project);
  virtual ~FlutterWindow();

 protected:
  // Win32Window:
  bool OnCreate() override;
  void OnDestroy() override;
  LRESULT MessageHandler(HWND window, UINT const message, WPARAM const wparam,
                         LPARAM const lparam) noexcept override;

 private:
  NOTIFYICONDATAW tray_{};
  HICON tray_icon_ = nullptr;
  HWND pointer_window_ = nullptr;
  bool pointer_visible_ = false;
  bool panel_requested_ = false;
  std::optional<RECT> resolved_anchor_;
  std::future<std::optional<RECT>> anchor_query_;
  UINT menu_dpi_ = 96;
  bool tray_available_ = false;
  bool positioning_panel_ = false;
  ULONGLONG tray_dismissed_at_ = 0;
  void TogglePanel();
  void ShowPanel();
  void ShowResolvedPanel();
  void PositionPanel();
  bool GetTrayRect(RECT* rect) const;
  std::unique_ptr<flutter::MethodChannel<flutter::EncodableValue>> startup_channel_;

  // The project to run.
  flutter::DartProject project_;

  // The Flutter instance hosted by this window.
  std::unique_ptr<flutter::FlutterViewController> flutter_controller_;
};

#endif  // RUNNER_FLUTTER_WINDOW_H_
