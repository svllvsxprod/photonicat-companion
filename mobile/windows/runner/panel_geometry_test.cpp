#include "panel_geometry.h"
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <cassert>

using photonicat::PanelRect;
using photonicat::PlacePanel;

int main() {
  // RDP laptop at 200%: 780 logical pixels is taller than the work area.
  auto panel = PlacePanel({0, 96, 1920, 1080}, {1600, 0, 1648, 96}, 192);
  assert(panel.top >= 96 && panel.bottom <= 1080);
  assert(panel.right - panel.left == 860);
  assert(panel.top == 120);
  // Bottom taskbar, ordinary scale; retain normal size.
  panel = PlacePanel({0, 0, 1920, 1040}, {1780, 1040, 1804, 1080}, 96);
  assert(panel.right - panel.left == 430 && panel.bottom - panel.top == 780);
  assert(panel.bottom <= 1032 && panel.right <= 1920);
  // Pointer aims at the chevron center, including a top taskbar and screen-edge clamp.
  auto popover = photonicat::PlacePopover({0,48,1645,980}, {1390,0,1426,48}, 96);
  assert(popover.edge == photonicat::PanelEdge::top);
  assert(popover.body.left + popover.arrow_offset == 1408);
  assert(popover.body.top - popover.arrow_depth == 50);
  popover = photonicat::PlacePopover({0,0,1920,1040}, {1700,1040,1740,1080}, 144);
  assert(popover.edge == photonicat::PanelEdge::bottom);
  assert(popover.body.left + popover.arrow_offset == 1720);
  assert(popover.body.bottom + popover.arrow_depth == 1037);
  // A side-taskbar chevron near a screen corner must not be mistaken for the top edge.
  popover = photonicat::PlacePopover({48,0,1920,1080}, {0,0,48,40}, 96);
  assert(popover.edge == photonicat::PanelEdge::left);
  popover = photonicat::PlacePopover({0,0,1872,1080}, {1872,0,1920,40}, 96);
  assert(popover.edge == photonicat::PanelEdge::right);
  // Different DPI, negative monitor coordinates and all taskbar edges.
  for (unsigned dpi : {96u, 120u, 144u, 192u, 288u}) {
    for (auto work : {PanelRect{-1280, 0, 0, 720}, PanelRect{0, 80, 800, 600},
                      PanelRect{40, 0, 1024, 720}, PanelRect{0, 0, 280, 300}}) {
      for (auto icon : {PanelRect{work.right-40,work.top-40,work.right,work.top},
                       PanelRect{work.right-40,work.bottom,work.right,work.bottom+40},
                       PanelRect{work.left-40,work.top,work.left,work.top+40},
                       PanelRect{work.right,work.top,work.right+40,work.top+40}}) {
        panel = PlacePanel(work, icon, dpi);
        assert(panel.left >= work.left && panel.top >= work.top);
        assert(panel.right <= work.right && panel.bottom <= work.bottom);
        assert(panel.right > panel.left && panel.bottom > panel.top);
      }
    }
  }
}
