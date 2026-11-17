#ifndef PHOTONICAT_PANEL_GEOMETRY_H_
#define PHOTONICAT_PANEL_GEOMETRY_H_
#include <algorithm>
#include <cstdlib>

namespace photonicat {
struct PanelRect { int left, top, right, bottom; };
enum class PanelEdge { top, bottom, left, right };
struct PanelPlacement { PanelRect body; PanelEdge edge; int arrow_offset; int arrow_depth; };
// Physical pixels throughout; content size and arrow dimensions respect monitor DPI.
inline PanelPlacement PlacePopover(PanelRect work, PanelRect anchor, unsigned dpi) {
  const auto px = [dpi](int value) { return static_cast<int>((value * dpi + 48) / 96); };
  const int cx = (anchor.left + anchor.right) / 2, cy = (anchor.top + anchor.bottom) / 2;
  const int distances[] = {std::abs(cy - work.top), std::abs(cy - work.bottom),
                           std::abs(cx - work.left), std::abs(cx - work.right)};
  int closest = static_cast<int>(std::min_element(distances, distances + 4) - distances);
  if (anchor.bottom <= work.top) closest = 0;
  else if (anchor.top >= work.bottom) closest = 1;
  else if (anchor.right <= work.left) closest = 2;
  else if (anchor.left >= work.right) closest = 3;
  const auto edge = static_cast<PanelEdge>(closest);
  const bool vertical = edge == PanelEdge::top || edge == PanelEdge::bottom;
  const int margin = std::min(px(8), std::min(work.right-work.left, work.bottom-work.top) / 8);
  const int depth = std::min(px(10), std::min(work.right-work.left, work.bottom-work.top) / 8);
  const int gap = std::max(1, px(2));
  const int width = std::max(1, std::min(px(430), work.right-work.left-2*margin-(vertical?0:depth+gap)));
  const int height = std::max(1, std::min(px(780), work.bottom-work.top-2*margin-(vertical?depth+gap:0)));
  int x = cx - width/2, y = cy - height/2;
  if (edge == PanelEdge::top) y = work.top + gap + depth;
  if (edge == PanelEdge::bottom) y = work.bottom - gap - depth - height;
  if (edge == PanelEdge::left) x = work.left + gap + depth;
  if (edge == PanelEdge::right) x = work.right - gap - depth - width;
  x = std::clamp(x, work.left + margin, work.right - margin - width);
  y = std::clamp(y, work.top + margin, work.bottom - margin - height);
  const int length = vertical ? width : height;
  const int inset = std::min(px(24), length / 2);
  const int offset = std::clamp(vertical ? cx-x : cy-y, inset, length-inset);
  return {{x,y,x+width,y+height},edge,offset,depth};
}
inline PanelRect PlacePanel(PanelRect work, PanelRect anchor, unsigned dpi) {
  return PlacePopover(work,anchor,dpi).body;
}
}
#endif
