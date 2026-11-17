#ifndef PHOTONICAT_TRAY_ANCHOR_H_
#define PHOTONICAT_TRAY_ANCHOR_H_
#include <windows.h>
#include <optional>

HWND FindTaskbar(HMONITOR monitor);
std::optional<RECT> FindLegacyChevron(HWND taskbar);
// Call on a worker thread; only reads Explorer's accessibility tree.
std::optional<RECT> FindAccessibleChevron(HWND taskbar);
#endif
