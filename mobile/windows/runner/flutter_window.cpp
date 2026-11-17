#include "flutter_window.h"

#include <optional>
#include <dwmapi.h>
#include <flutter_windows.h>
#include "panel_geometry.h"
#include "tray_anchor.h"
#include <chrono>
#include <shellapi.h>
#include <flutter/standard_method_codec.h>

namespace {
constexpr UINT kTrayMessage = WM_APP + 61;
constexpr UINT kPositionPanel = WM_APP + 62;
constexpr UINT_PTR kAnchorTimer = 0x5043;

void ArrowPoints(int edge, int width, int height, POINT (&points)[3]) {
  switch (static_cast<photonicat::PanelEdge>(edge)) {
    case photonicat::PanelEdge::top:
      points[0] = {0,height}; points[1] = {width/2,0}; points[2] = {width,height}; break;
    case photonicat::PanelEdge::bottom:
      points[0] = {0,0}; points[1] = {width/2,height}; points[2] = {width,0}; break;
    case photonicat::PanelEdge::left:
      points[0] = {width,0}; points[1] = {0,height/2}; points[2] = {width,height}; break;
    case photonicat::PanelEdge::right:
      points[0] = {0,0}; points[1] = {width,height/2}; points[2] = {0,height}; break;
  }
}
LRESULT CALLBACK PointerWindowProc(HWND window, UINT message, WPARAM wparam, LPARAM lparam) {
  if (message == WM_NCHITTEST) return HTTRANSPARENT;
  if (message == WM_MOUSEACTIVATE) return MA_NOACTIVATE;
  if (message == WM_PAINT) {
    PAINTSTRUCT paint{}; HDC dc = BeginPaint(window, &paint);
    RECT rect{}; GetClientRect(window, &rect);
    FillRect(dc, &rect, static_cast<HBRUSH>(GetStockObject(BLACK_BRUSH)));
    POINT points[3]{};
    const int edge = static_cast<int>(GetWindowLongPtrW(window, GWLP_USERDATA));
    ArrowPoints(edge, static_cast<int>(rect.right), static_cast<int>(rect.bottom), points);
    HPEN pen = CreatePen(PS_SOLID, 1, RGB(65,65,52));
    auto old = SelectObject(dc, pen);
    Polyline(dc, points, 3);  // Leave the base open where it meets the panel.
    SelectObject(dc, old); DeleteObject(pen);
    EndPaint(window, &paint); return 0;
  }
  return DefWindowProcW(window, message, wparam, lparam);
}
HWND CreatePointerWindow(HWND owner) {
  WNDCLASSW type{};
  type.hInstance = GetModuleHandle(nullptr); type.lpfnWndProc = PointerWindowProc;
  type.lpszClassName = L"PhotonicatPopoverPointer";
  type.hCursor = LoadCursor(nullptr, IDC_ARROW);
  RegisterClassW(&type);
  return CreateWindowExW(WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE, type.lpszClassName,
      L"", WS_POPUP, 0,0,1,1,owner,nullptr,type.hInstance,nullptr);
}

constexpr wchar_t kRunKey[] = L"Software\\Microsoft\\Windows\\CurrentVersion\\Run";
constexpr wchar_t kRunValue[] = L"Photonicat";
std::wstring StartupCommand() {
  wchar_t path[32768];
  DWORD size = GetModuleFileNameW(nullptr, path, 32768);
  if (size == 0 || size >= 32768) return L"";
  return L"\"" + std::wstring(path, size) + L"\" --autostart";
}
flutter::EncodableValue StartupState() {
  wchar_t value[32768]{}; DWORD bytes = sizeof(value);
  LSTATUS read = RegGetValueW(HKEY_CURRENT_USER, kRunKey, kRunValue,
                             RRF_RT_REG_SZ, nullptr, value, &bytes);
  std::string state = "disabled";
  if (read == ERROR_SUCCESS && std::wstring(value) == StartupCommand()) {
    state = "enabled";
    BYTE approved[32]{}; DWORD length = sizeof(approved);
    if (RegGetValueW(HKEY_CURRENT_USER,
        L"Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\StartupApproved\\Run",
        kRunValue, RRF_RT_REG_BINARY, nullptr, approved, &length) == ERROR_SUCCESS && length > 0) {
      // Respect the user's OS-level disable; never rewrite StartupApproved.
      if (approved[0] != 2 && approved[0] != 6) state = "approval";
    }
  } else if (read != ERROR_SUCCESS && read != ERROR_FILE_NOT_FOUND) {
    state = "error";
  }
  return flutter::EncodableValue(flutter::EncodableMap{
      {flutter::EncodableValue("status"), flutter::EncodableValue(state)}});
}
void DrawTrayMenuItem(const DRAWITEMSTRUCT& item, UINT dpi) {
  const auto px = [dpi](int value) { return MulDiv(value, static_cast<int>(dpi), 96); };
  const bool selected = (item.itemState & ODS_SELECTED) != 0;
  HBRUSH background = CreateSolidBrush(RGB(15, 15, 13));
  FillRect(item.hDC, &item.rcItem, background);
  DeleteObject(background);
  RECT area = item.rcItem;
  InflateRect(&area, -px(6), -px(3));
  if (selected) {
    HBRUSH accent = CreateSolidBrush(RGB(255, 235, 0));
    auto oldBrush = SelectObject(item.hDC, accent);
    auto oldPen = SelectObject(item.hDC, GetStockObject(NULL_PEN));
    RoundRect(item.hDC, area.left, area.top, area.right, area.bottom, px(12), px(12));
    SelectObject(item.hDC, oldPen); SelectObject(item.hDC, oldBrush);
    DeleteObject(accent);
  }
  const auto oldColor = SetTextColor(item.hDC, selected ? RGB(0, 0, 0) : RGB(230, 230, 218));
  const int oldMode = SetBkMode(item.hDC, TRANSPARENT);
  HFONT font = CreateFontW(-px(14), 0, 0, 0, FW_MEDIUM, FALSE, FALSE, FALSE,
      DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY,
      DEFAULT_PITCH, L"Segoe UI");
  auto oldFont = SelectObject(item.hDC, font);
  RECT text = area; text.left += px(42); text.right -= px(12);
  DrawTextW(item.hDC, item.itemID == 1 ? L"Открыть Photonicat" : L"Завершить", -1,
            &text, DT_LEFT | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX);
  HFONT icons = CreateFontW(-px(18), 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE,
      DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY,
      DEFAULT_PITCH, L"Segoe MDL2 Assets");
  SelectObject(item.hDC, icons);
  if (!selected) SetTextColor(item.hDC, RGB(255, 235, 0));
  RECT icon = area; icon.left += px(12); icon.right = icon.left + px(22);
  DrawTextW(item.hDC, item.itemID == 1 ? L"\uE8A7" : L"\uE7E8", -1,
            &icon, DT_CENTER | DT_VCENTER | DT_SINGLELINE | DT_NOPREFIX);
  SelectObject(item.hDC, oldFont); SetTextColor(item.hDC, oldColor);
  SetBkMode(item.hDC, oldMode); DeleteObject(font); DeleteObject(icons);
}
HICON CatIcon() {
  HDC dc = GetDC(nullptr); HDC mem = CreateCompatibleDC(dc);
  HBITMAP color = CreateCompatibleBitmap(dc, 32, 32);
  HBITMAP mask = CreateBitmap(32, 32, 1, 1, nullptr);
  auto old = SelectObject(mem, color);
  RECT rect{0,0,32,32}; FillRect(mem, &rect, static_cast<HBRUSH>(GetStockObject(BLACK_BRUSH)));
  HBRUSH yellow = CreateSolidBrush(RGB(255,235,0)); auto brush = SelectObject(mem,yellow);
  auto pen = SelectObject(mem, GetStockObject(NULL_PEN));
  POINT cat[]={{3,3},{11,8},{21,8},{29,3},{27,23},{21,28},{11,28},{5,23}};
  Polygon(mem,cat,8); SelectObject(mem, GetStockObject(BLACK_BRUSH));
  Rectangle(mem,8,15,13,19); Rectangle(mem,19,15,24,19);
  SelectObject(mem,pen); SelectObject(mem,brush); DeleteObject(yellow);
  SelectObject(mem, mask); PatBlt(mem,0,0,32,32,BLACKNESS);
  SelectObject(mem, old); ICONINFO info{TRUE,0,0,mask,color};
  HICON icon=CreateIconIndirect(&info);
  DeleteObject(color); DeleteObject(mask); DeleteDC(mem); ReleaseDC(nullptr,dc); return icon;
}
}


#include "flutter/generated_plugin_registrant.h"

FlutterWindow::FlutterWindow(const flutter::DartProject& project)
    : project_(project) {}

FlutterWindow::~FlutterWindow() {}

bool FlutterWindow::OnCreate() {
  if (!Win32Window::OnCreate()) {
    return false;
  }

  RECT frame = GetClientArea();

  // The size here must match the window dimensions to avoid unnecessary surface
  // creation / destruction in the startup path.
  flutter_controller_ = std::make_unique<flutter::FlutterViewController>(
      frame.right - frame.left, frame.bottom - frame.top, project_);
  // Ensure that basic setup of the controller was successful.
  if (!flutter_controller_->engine() || !flutter_controller_->view()) {
    return false;
  }
  RegisterPlugins(flutter_controller_->engine());
  startup_channel_ = std::make_unique<flutter::MethodChannel<flutter::EncodableValue>>(
      flutter_controller_->engine()->messenger(), "photonicat/startup",
      &flutter::StandardMethodCodec::GetInstance());
  startup_channel_->SetMethodCallHandler([](const auto& call, auto result) {
    if (call.method_name() == "get") { result->Success(StartupState()); return; }
    if (call.method_name() == "settings") {
      ShellExecuteW(nullptr, L"open", L"ms-settings:startupapps", nullptr, nullptr, SW_SHOWNORMAL);
      result->Success(); return;
    }
    if (call.method_name() != "set" || !call.arguments() || !std::holds_alternative<bool>(*call.arguments())) {
      result->NotImplemented(); return;
    }
    const bool enabled = std::get<bool>(*call.arguments());
    const auto command = StartupCommand();
    if (command.empty()) { result->Error("startup_failed", "Unable to locate application"); return; }
    LSTATUS status;
    if (enabled) {
      status = RegSetKeyValueW(HKEY_CURRENT_USER, kRunKey, kRunValue, REG_SZ,
          command.c_str(), static_cast<DWORD>((command.size()+1)*sizeof(wchar_t)));
    } else {
      status = RegDeleteKeyValueW(HKEY_CURRENT_USER, kRunKey, kRunValue);
      if (status == ERROR_FILE_NOT_FOUND) status = ERROR_SUCCESS;
    }
    if (status != ERROR_SUCCESS) { result->Error("startup_failed", "Unable to update startup setting"); return; }
    result->Success(StartupState());
  });
  SetChildContent(flutter_controller_->view()->GetNativeWindow());

  tray_icon_ = CatIcon();
  tray_.cbSize = sizeof(tray_); tray_.hWnd = GetHandle(); tray_.uID = 1;
  tray_.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP;
  tray_.uCallbackMessage = kTrayMessage; tray_.hIcon = tray_icon_;
  wcscpy_s(tray_.szTip, L"Photonicat");
  tray_available_ = Shell_NotifyIconW(NIM_ADD, &tray_) != FALSE;
  SetWindowTextW(GetHandle(), L"Photonicat");
  if (tray_available_) {
    SetWindowLongPtrW(GetHandle(), GWL_STYLE, WS_POPUP | WS_CLIPCHILDREN);
    SetWindowLongPtrW(GetHandle(), GWL_EXSTYLE, WS_EX_TOOLWINDOW);
    SetWindowPos(GetHandle(), nullptr, 0, 0, 0, 0,
                 SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED);
    // Native Windows 11 rounded outline; older systems safely ignore it.
    pointer_window_ = CreatePointerWindow(GetHandle());
    const DWORD round = 2;
    DwmSetWindowAttribute(GetHandle(), 33, &round, sizeof(round));
    const COLORREF border = RGB(65, 65, 52);
    DwmSetWindowAttribute(GetHandle(), 34, &border, sizeof(border));
  } else {
    // If Explorer has no tray, keep a normal closable/resizable window.
    flutter_controller_->engine()->SetNextFrameCallback([this]() { Show(); });
  }

  // Flutter can complete the first frame before the "show window" callback is
  // registered. The following call ensures a frame is pending to ensure the
  // window is shown. It is a no-op if the first frame hasn't completed yet.
  flutter_controller_->ForceRedraw();

  return true;
}

void FlutterWindow::OnDestroy() {
  KillTimer(GetHandle(), kAnchorTimer);
  panel_requested_ = false;
  if (pointer_window_) { DestroyWindow(pointer_window_); pointer_window_ = nullptr; }
  startup_channel_.reset();
  Shell_NotifyIconW(NIM_DELETE, &tray_);
  if (tray_icon_) { DestroyIcon(tray_icon_); tray_icon_ = nullptr; }
  if (flutter_controller_) {
    flutter_controller_ = nullptr;
  }

  Win32Window::OnDestroy();
}

LRESULT
FlutterWindow::MessageHandler(HWND hwnd, UINT const message,
                              WPARAM const wparam,
                              LPARAM const lparam) noexcept {
  if (message == WM_SHOWWINDOW && !wparam && pointer_window_) {
    ShowWindow(pointer_window_, SW_HIDE);
  }
  if (message == WM_TIMER && wparam == kAnchorTimer) {
    if (anchor_query_.valid() && anchor_query_.wait_for(std::chrono::milliseconds(0)) == std::future_status::ready) {
      KillTimer(hwnd, kAnchorTimer);
      auto anchor = anchor_query_.get();
      if (panel_requested_) {
        panel_requested_ = false; resolved_anchor_ = anchor; ShowResolvedPanel();
      }
    }
    return 0;
  }
  if (message == RegisterWindowMessageW(L"TaskbarCreated")) {
    tray_available_ = Shell_NotifyIconW(NIM_ADD, &tray_) != FALSE;
    if (!tray_available_) {
      SetWindowLongPtrW(hwnd, GWL_STYLE, WS_OVERLAPPEDWINDOW | WS_CLIPCHILDREN);
      SetWindowLongPtrW(hwnd, GWL_EXSTYLE, WS_EX_APPWINDOW);
      SetWindowPos(hwnd, nullptr, 0, 0, 0, 0,
          SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED);
      Show();
    }
    return 0;
  }
  if (message == WM_MEASUREITEM && lparam) {
    auto item = reinterpret_cast<MEASUREITEMSTRUCT*>(lparam);
    if (item->CtlType == ODT_MENU && (item->itemID == 1 || item->itemID == 2)) {
      item->itemWidth = MulDiv(236, static_cast<int>(menu_dpi_), 96);
      item->itemHeight = MulDiv(44, static_cast<int>(menu_dpi_), 96);
      return TRUE;
    }
  }
  if (message == WM_DRAWITEM && lparam) {
    auto item = reinterpret_cast<DRAWITEMSTRUCT*>(lparam);
    if (item->CtlType == ODT_MENU && (item->itemID == 1 || item->itemID == 2)) {
      DrawTrayMenuItem(*item, menu_dpi_); return TRUE;
    }
  }
  if (message == kPositionPanel) {
    if (IsWindowVisible(hwnd)) ShowPanel();
    else resolved_anchor_.reset();
    return 0;
  }
  if (tray_available_ && message == WM_ACTIVATE && LOWORD(wparam) == WA_INACTIVE) {
    DWORD owner = 0;
    if (lparam) GetWindowThreadProcessId(reinterpret_cast<HWND>(lparam), &owner);
    // Native file pickers belong to this process and must remain usable.
    if (owner != GetCurrentProcessId()) {
      panel_requested_ = false;
      POINT point{}; RECT icon{}; GetCursorPos(&point);
      tray_dismissed_at_ = GetTrayRect(&icon) && PtInRect(&icon, point)
                              ? GetTickCount64() : 0;
      ShowWindow(hwnd, SW_HIDE);
    }
    // Do not let the base WM_ACTIVATE handler refocus a deactivated Flutter view.
    return 0;
  }
  if (tray_available_ && message == WM_CLOSE) {
    panel_requested_ = false;
    ShowWindow(hwnd, SW_HIDE); return 0;
  }
  if (message == kTrayMessage) {
    if (lparam == WM_LBUTTONUP || lparam == NIN_KEYSELECT) { TogglePanel(); return 0; }
    if (lparam == WM_RBUTTONUP || lparam == WM_CONTEXTMENU) {
      POINT point; GetCursorPos(&point);
      menu_dpi_ = FlutterDesktopGetDpiForMonitor(MonitorFromPoint(point, MONITOR_DEFAULTTONEAREST));
      HMENU menu = CreatePopupMenu();
      HBRUSH menu_background = CreateSolidBrush(RGB(15, 15, 13));
      MENUINFO info{sizeof(MENUINFO)};
      info.fMask = MIM_BACKGROUND | MIM_STYLE;
      info.hbrBack = menu_background; info.dwStyle = MNS_NOCHECK;
      SetMenuInfo(menu, &info);
      AppendMenuW(menu, MF_OWNERDRAW, 1, L"Открыть Photonicat");
      AppendMenuW(menu, MF_OWNERDRAW, 2, L"Завершить");
      SetForegroundWindow(hwnd);
      UINT action = TrackPopupMenu(menu, TPM_RETURNCMD | TPM_RIGHTBUTTON,
                                  point.x, point.y, 0, hwnd, nullptr);
      DestroyMenu(menu);
      DeleteObject(menu_background);
      PostMessage(hwnd, WM_NULL, 0, 0);
      if (action == 1) ShowPanel();
      if (action == 2) DestroyWindow(hwnd);
      return 0;
    }
  }
  if (tray_available_ && (message == WM_DPICHANGED || message == WM_DISPLAYCHANGE ||
      (message == WM_SETTINGCHANGE && wparam == SPI_SETWORKAREA))) {
    // Apply after Flutter has processed its DPI update, including RDP resizing.
    if (!positioning_panel_) PostMessage(hwnd, kPositionPanel, 0, 0);
  }
  // Give Flutter, including plugins, an opportunity to handle window messages.
  if (flutter_controller_) {
    std::optional<LRESULT> result =
        flutter_controller_->HandleTopLevelWindowProc(hwnd, message, wparam,
                                                      lparam);
    if (result) {
      return *result;
    }
  }

  switch (message) {
    case WM_FONTCHANGE:
      flutter_controller_->engine()->ReloadSystemFonts();
      break;
  }

  return Win32Window::MessageHandler(hwnd, message, wparam, lparam);
}

bool FlutterWindow::GetTrayRect(RECT* rect) const {
  NOTIFYICONIDENTIFIER icon{};
  icon.cbSize = sizeof(icon); icon.hWnd = tray_.hWnd; icon.uID = tray_.uID;
  return SUCCEEDED(Shell_NotifyIconGetRect(&icon, rect));
}

void FlutterWindow::PositionPanel() {
  if (!tray_available_ || positioning_panel_) return;
  positioning_panel_ = true;
  RECT anchor{};
  POINT cursor{}; GetCursorPos(&cursor);
  if (!GetTrayRect(&anchor)) anchor = {cursor.x, cursor.y, cursor.x + 1, cursor.y + 1};
  if (resolved_anchor_) anchor = *resolved_anchor_;
  HMONITOR target = MonitorFromRect(&anchor, MONITOR_DEFAULTTONEAREST);
  MONITORINFO monitor{sizeof(MONITORINFO)};
  if (GetMonitorInfoW(target, &monitor)) {
    const auto& work = monitor.rcWork;
    const auto placement = photonicat::PlacePopover(
        {static_cast<int>(work.left), static_cast<int>(work.top),
         static_cast<int>(work.right), static_cast<int>(work.bottom)},
        {static_cast<int>(anchor.left), static_cast<int>(anchor.top),
         static_cast<int>(anchor.right), static_cast<int>(anchor.bottom)},
        FlutterDesktopGetDpiForMonitor(target));
    const auto& frame = placement.body;
    SetWindowPos(GetHandle(), nullptr, frame.left, frame.top,
                 frame.right - frame.left, frame.bottom - frame.top,
                 SWP_NOZORDER | SWP_NOACTIVATE);
    // Only point at an actual taskbar control, never at a guessed screen coordinate.
    pointer_visible_ = resolved_anchor_.has_value() || anchor.bottom <= work.top ||
        anchor.top >= work.bottom || anchor.right <= work.left || anchor.left >= work.right;
    if (pointer_window_) {
      const int depth = placement.arrow_depth;
      const int half = MulDiv(12, static_cast<int>(FlutterDesktopGetDpiForMonitor(target)), 96);
      const int overlap = 2;
      int x = 0, y = 0, width = half*2, height = depth+overlap;
      switch (placement.edge) {
        case photonicat::PanelEdge::top:
          x = frame.left + placement.arrow_offset-half; y = frame.top-depth; break;
        case photonicat::PanelEdge::bottom:
          x = frame.left + placement.arrow_offset-half; y = frame.bottom-overlap; break;
        case photonicat::PanelEdge::left:
          width = depth+overlap; height = half*2;
          x = frame.left-depth; y = frame.top+placement.arrow_offset-half; break;
        case photonicat::PanelEdge::right:
          width = depth+overlap; height = half*2;
          x = frame.right-overlap; y = frame.top+placement.arrow_offset-half; break;
      }
      POINT points[3]{}; ArrowPoints(static_cast<int>(placement.edge), width, height, points);
      SetWindowLongPtrW(pointer_window_, GWLP_USERDATA, static_cast<LONG_PTR>(placement.edge));
      HRGN region = CreatePolygonRgn(points, 3, WINDING);
      if (!SetWindowRgn(pointer_window_, region, FALSE)) DeleteObject(region);
      SetWindowPos(pointer_window_, HWND_TOP, x,y,width,height, SWP_NOACTIVATE);
      InvalidateRect(pointer_window_, nullptr, TRUE);
      ShowWindow(pointer_window_, pointer_visible_ && IsWindowVisible(GetHandle()) ? SW_SHOWNOACTIVATE : SW_HIDE);
    }
  }
  positioning_panel_ = false;
}

void FlutterWindow::ShowPanel() {
  if (anchor_query_.valid()) { panel_requested_ = true; return; }
  RECT icon{}; POINT cursor{}; GetCursorPos(&cursor);
  HMONITOR monitor = GetTrayRect(&icon)
      ? MonitorFromRect(&icon, MONITOR_DEFAULTTONEAREST)
      : MonitorFromPoint(cursor, MONITOR_DEFAULTTONEAREST);
  HWND taskbar = FindTaskbar(monitor);
  resolved_anchor_ = FindLegacyChevron(taskbar);
  if (resolved_anchor_ || !taskbar) { ShowResolvedPanel(); return; }
  // Windows 11's XAML taskbar exposes the chevron through accessibility.
  // Read it off the UI thread so an unresponsive Explorer cannot freeze Flutter.
  panel_requested_ = true;
  anchor_query_ = std::async(std::launch::async, [taskbar]() { return FindAccessibleChevron(taskbar); });
  SetTimer(GetHandle(), kAnchorTimer, 30, nullptr);
}

void FlutterWindow::ShowResolvedPanel() {
  PositionPanel();
  ShowWindow(GetHandle(), SW_SHOWNORMAL);
  SetForegroundWindow(GetHandle());
  if (pointer_window_ && pointer_visible_) ShowWindow(pointer_window_, SW_SHOWNOACTIVATE);
}

void FlutterWindow::TogglePanel() {
  if (panel_requested_) { panel_requested_ = false; return; }
  HWND window = GetHandle();
  if ((IsWindowVisible(window) && GetForegroundWindow() == window) ||
      (tray_dismissed_at_ && GetTickCount64() - tray_dismissed_at_ < 500)) {
    tray_dismissed_at_ = 0;
    ShowWindow(window, SW_HIDE); return;
  }
  tray_dismissed_at_ = 0;
  ShowPanel();
}
