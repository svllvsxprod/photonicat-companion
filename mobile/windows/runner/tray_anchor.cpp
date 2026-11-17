#include "tray_anchor.h"
#include <UIAutomation.h>
#include <wrl/client.h>
#include <string>

namespace {
using Microsoft::WRL::ComPtr;
struct TaskbarSearch { HMONITOR monitor; HWND result = nullptr; };
BOOL CALLBACK FindTaskbarWindow(HWND window, LPARAM data) {
  auto& search = *reinterpret_cast<TaskbarSearch*>(data);
  wchar_t name[128]{}; GetClassNameW(window, name, 128);
  if ((wcscmp(name, L"Shell_TrayWnd") == 0 || wcscmp(name, L"Shell_SecondaryTrayWnd") == 0) &&
      MonitorFromWindow(window, MONITOR_DEFAULTTONEAREST) == search.monitor) {
    search.result = window; return FALSE;
  }
  return TRUE;
}
bool ValidAnchor(const RECT& button, HWND taskbar) {
  RECT bar{}, overlap{};
  return GetWindowRect(taskbar, &bar) && button.right > button.left &&
      button.bottom > button.top && IntersectRect(&overlap, &button, &bar) &&
      EqualRect(&overlap, &button);
}
struct ButtonSearch { HWND taskbar; std::optional<RECT> result; unsigned count = 0; };
BOOL CALLBACK FindButton(HWND window, LPARAM data) {
  auto& search = *reinterpret_cast<ButtonSearch*>(data);
  wchar_t name[128]{}; GetClassNameW(window, name, 128);
  RECT rect{};
  if (wcscmp(name, L"Button") == 0 && IsWindowVisible(window) &&
      GetWindowRect(window, &rect) && ValidAnchor(rect, search.taskbar)) {
    search.result = rect; ++search.count;
  }
  return TRUE;
}
}
HWND FindTaskbar(HMONITOR monitor) {
  TaskbarSearch search{monitor};
  EnumWindows(FindTaskbarWindow, reinterpret_cast<LPARAM>(&search));
  return search.result;
}
std::optional<RECT> FindLegacyChevron(HWND taskbar) {
  if (!taskbar) return std::nullopt;
  HWND notify = FindWindowExW(taskbar, nullptr, L"TrayNotifyWnd", nullptr);
  if (!notify) return std::nullopt;
  ButtonSearch search{taskbar, std::nullopt, 0};
  EnumChildWindows(notify, FindButton, reinterpret_cast<LPARAM>(&search));
  // The classic overflow chevron is the sole Button in TrayNotifyWnd.
  return search.count == 1 ? search.result : std::nullopt;
}
std::optional<RECT> FindAccessibleChevron(HWND taskbar) {
  if (!taskbar) return std::nullopt;
  if (FAILED(CoInitializeEx(nullptr, COINIT_MULTITHREADED))) return std::nullopt;
  std::optional<RECT> found;
  {
    ComPtr<IUIAutomation> automation;
    if (SUCCEEDED(CoCreateInstance(CLSID_CUIAutomation8, nullptr, CLSCTX_INPROC_SERVER,
                                  IID_PPV_ARGS(&automation)))) {
      ComPtr<IUIAutomation2> options;
      if (SUCCEEDED(automation.As(&options))) {
        options->put_ConnectionTimeout(700);
        options->put_TransactionTimeout(700);
      }
      ComPtr<IUIAutomationElement> root;
      if (SUCCEEDED(automation->ElementFromHandle(taskbar, &root))) {
        struct Match { PROPERTYID property; const wchar_t* value; };
        const Match matches[] = {
          {UIA_ClassNamePropertyId, L"SystemTray.ChevronIconView"},
          {UIA_AutomationIdPropertyId, L"SystemTrayChevron"},
          {UIA_NamePropertyId, L"Show hidden icons"},
          {UIA_NamePropertyId, L"Hidden icon menu"},
          {UIA_NamePropertyId, L"Показать скрытые значки"},
          {UIA_NamePropertyId, L"Меню скрытых значков"},
          {UIA_NamePropertyId, L"Ausgeblendete Symbole einblenden"}
        };
        ComPtr<IUIAutomationCondition> combined;
        for (const auto& match : matches) {
          VARIANT value{}; value.vt = VT_BSTR; value.bstrVal = SysAllocString(match.value);
          ComPtr<IUIAutomationCondition> condition;
          HRESULT result = automation->CreatePropertyCondition(match.property, value, &condition);
          VariantClear(&value);
          if (FAILED(result)) continue;
          if (!combined) { combined = condition; continue; }
          ComPtr<IUIAutomationCondition> either;
          if (SUCCEEDED(automation->CreateOrCondition(combined.Get(), condition.Get(), &either)))
            combined = either;
        }
        ComPtr<IUIAutomationElement> element;
        if (combined && SUCCEEDED(root->FindFirst(TreeScope_Descendants, combined.Get(), &element)) && element) {
          RECT rect{}; BOOL offscreen = TRUE;
          if (SUCCEEDED(element->get_CurrentBoundingRectangle(&rect)) &&
              SUCCEEDED(element->get_CurrentIsOffscreen(&offscreen)) && !offscreen && ValidAnchor(rect, taskbar))
            found = rect;
        }
      }
    }
  }
  CoUninitialize();
  return found;
}
