"""Independent control evidence. Coordinates alone never establish existence.

Semantic bounds are compositor coordinates. Visual bounds are frame pixels.
The raster fallback supports closed, filled controls with one readable label;
transparent controls, unlabeled icons and uncertain boundaries abstain.
"""
from dataclasses import dataclass
from enum import StrEnum
import math


class TargetState(StrEnum):
    FOUND = 'FOUND'
    NOT_VISIBLE_HERE = 'NOT_VISIBLE_HERE'
    AMBIGUOUS = 'AMBIGUOUS'
    NOT_ACTIONABLE = 'NOT_ACTIONABLE'
    STALE = 'STALE'
    UNSUPPORTED = 'UNSUPPORTED'


@dataclass(frozen=True)
class TargetEvidence:
    state: TargetState
    bounds: tuple | None = None
    identity: str = ''
    source: str = ''

    def require(self):
        if self.state != TargetState.FOUND:
            raise ValueError(f'{self.state}: no verified actionable target; no input')
        return self.bounds


def semantic_target(observation, label, revision=None):
    from .visual_targets import normalize
    if revision is not None and observation.get('revision') != revision:
        return TargetEvidence(TargetState.STALE)
    candidates = [c for c in observation.get('controls', [])
                  if normalize(c.get('name', '')) == normalize(label)]
    if not candidates:
        return TargetEvidence(TargetState.UNSUPPORTED if observation.get('incomplete') else TargetState.NOT_VISIBLE_HERE)
    if len(candidates) != 1:
        return TargetEvidence(TargetState.AMBIGUOUS)
    c = candidates[0]
    if not c.get('enabled') or c.get('visible') is False or c.get('occluded'):
        return TargetEvidence(TargetState.NOT_ACTIONABLE)
    if c.get('role') not in {'button', 'push button', 'toggle button', 'check box', 'radio button', 'menu item', 'page tab', 'link'}:
        return TargetEvidence(TargetState.UNSUPPORTED)
    bounds = c.get('bounds')
    if not isinstance(bounds, (list,tuple)) or len(bounds) != 4 or not all(type(n) in {int,float} and math.isfinite(n) for n in bounds) or min(bounds[2:]) <= 0:
        return TargetEvidence(TargetState.UNSUPPORTED)
    x,y,w,h = bounds
    return TargetEvidence(TargetState.FOUND, (x,y,x+w,y+h), c['id'], 'at-spi')


def filled_region(image, text_box, other_boxes):
    """Find a connected fill surrounding text, bounded by observed color edges.

    Seeds probe glyph surroundings, not possible click coordinates. Flood-fill
    boundaries supply the admitted area. Backgrounds, merged panels, fragments,
    and regions containing another label are rejected.
    """
    from PIL import ImageChops, ImageDraw
    pixels = image.convert('RGB')
    left,top,right,bottom = map(int, text_box)
    seeds = [(left-3,(top+bottom)//2),(right+3,(top+bottom)//2),((left+right)//2,top-3),((left+right)//2,bottom+3)]
    found = set()
    for x,y in seeds:
        if not (0 < x < pixels.width-1 and 0 < y < pixels.height-1):
            continue
        flood = pixels.copy()
        color = pixels.getpixel((x,y))
        # A grey fill alone cannot distinguish enabled from disabled styling.
        # Those controls require semantic state, rather than a visual guess.
        if max(color)-min(color) < 18:
            continue
        marker = tuple(255-v for v in color)
        ImageDraw.floodfill(flood, (x,y), marker, thresh=18)
        difference = ImageChops.difference(pixels, flood).convert('L').point(lambda p: 255 if p else 0)
        box = difference.getbbox()
        if box is None:
            continue
        l,t,r,b = box
        if l <= 0 or t <= 0 or r >= pixels.width or b >= pixels.height:
            continue
        if not (l < left < right < r and t < top < bottom < b):
            continue
        width,height = r-l,b-t
        if height < bottom-top+4 or height > max(100, (bottom-top)*5) or width/height > 18 or width*height > pixels.width*pixels.height*.22:
            continue
        occupied = difference.histogram()[255]
        if occupied/(width*height) < .72:
            continue
        if any(box2 != text_box and max(l,box2[0]) < min(r,box2[2]) and max(t,box2[1]) < min(b,box2[3]) for box2 in other_boxes):
            continue
        found.add(box)
    return next(iter(found)) if len(found) == 1 else None
