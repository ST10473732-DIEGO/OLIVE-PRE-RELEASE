"""One place for Linux desktop coordinate spaces (KDE/Wayland, multi-monitor).

Spaces used by desktop control:

* global logical: compositor coordinates. KWin window geometry, portal stream
  position/size and libei regions all use it. Monitor origins can be negative
  (a monitor placed left of or above the primary one) and never assume 0,0.
* monitor physical: device pixels, logical * scale (fractional KDE scaling).
* frame pixels: one captured (usually downscaled) image of one monitor stream.
* crop pixels: a frame cropped to one window's client rectangle.

AT-SPI extents are mapped to global logical coordinates by the accessibility
module (its window offset binding) before they reach any code here. Adapters
and executors must convert only through these functions; no scale factor is
applied anywhere else, so it can never be applied twice.
"""
from dataclasses import dataclass
import math


def _finite(*values):
    return all(type(v) in (int, float) and math.isfinite(v) for v in values)


def rect(value):
    """A validated (x, y, width, height) logical rectangle."""
    if not isinstance(value, (tuple, list)) or len(value) != 4 or not _finite(*value):
        raise ValueError('Invalid rectangle')
    x, y, width, height = value
    if width <= 0 or height <= 0:
        raise ValueError('Empty rectangle')
    return (x, y, width, height)


def inside(outer, inner):
    ox, oy, ow, oh = rect(outer)
    try:
        ix, iy, iw, ih = rect(inner)
    except ValueError:
        return False
    return ox <= ix and oy <= iy and ix + iw <= ox + ow and iy + ih <= oy + oh


def overlap(left, right):
    lx, ly, lw, lh = rect(left)
    rx, ry, rw, rh = rect(right)
    width = min(lx + lw, rx + rw) - max(lx, rx)
    height = min(ly + lh, ry + rh) - max(ly, ry)
    return width * height if width > 0 and height > 0 else 0


@dataclass(frozen=True)
class Monitor:
    name: str
    x: float
    y: float
    width: float    # logical
    height: float   # logical
    scale: float = 1.0

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name or len(self.name) > 80:
            raise ValueError('Invalid monitor name')
        rect((self.x, self.y, self.width, self.height))
        if not _finite(self.scale) or not .5 <= self.scale <= 4:
            raise ValueError('Unsupported monitor scale')

    @property
    def bounds(self):
        return (self.x, self.y, self.width, self.height)

    @property
    def physical_size(self):
        return (round(self.width * self.scale), round(self.height * self.scale))

    def contains(self, x, y):
        return _finite(x, y) and self.x <= x < self.x + self.width and self.y <= y < self.y + self.height

    def to_physical(self, x, y):
        """Global logical point -> device pixel inside this monitor."""
        if not self.contains(x, y):
            raise ValueError('Point is outside this monitor')
        return ((x - self.x) * self.scale, (y - self.y) * self.scale)

    def to_logical(self, px, py):
        """Device pixel inside this monitor -> global logical point."""
        width, height = self.physical_size
        if not _finite(px, py) or not (0 <= px < width and 0 <= py < height):
            raise ValueError('Pixel is outside this monitor')
        return (self.x + px / self.scale, self.y + py / self.scale)


@dataclass(frozen=True)
class Layout:
    monitors: tuple

    def __post_init__(self):
        names = [m.name for m in self.monitors]
        if not self.monitors or len(set(names)) != len(names):
            raise ValueError('Monitor layout needs unique named monitors')
        for index, first in enumerate(self.monitors):
            for second in self.monitors[index + 1:]:
                if overlap(first.bounds, second.bounds):
                    raise ValueError('Mirrored or overlapping monitors are not a supported input layout')

    @classmethod
    def from_rows(cls, rows):
        return cls(tuple(Monitor(r['name'], *rect(r['geometry']), float(r.get('scale', 1.0))) for r in rows))

    def monitor(self, name):
        found = [m for m in self.monitors if m.name == name]
        if len(found) != 1:
            raise LookupError('Monitor is not part of the current layout')
        return found[0]

    def at(self, x, y):
        found = [m for m in self.monitors if m.contains(x, y)]
        return found[0] if len(found) == 1 else None

    def containing(self, bounds):
        """The one monitor fully containing a window/control, or None (spanning windows fail closed)."""
        found = [m for m in self.monitors if inside(m.bounds, bounds)]
        return found[0] if len(found) == 1 else None

    def mostly(self, bounds):
        """Monitor showing most of a rectangle; for reporting, never for input."""
        scored = [(overlap(m.bounds, bounds), m) for m in self.monitors]
        best = max(score for score, _ in scored)
        winners = [m for score, m in scored if score == best]
        return winners[0] if best and len(winners) == 1 else None

    @property
    def bounds(self):
        left = min(m.x for m in self.monitors)
        top = min(m.y for m in self.monitors)
        right = max(m.x + m.width for m in self.monitors)
        bottom = max(m.y + m.height for m in self.monitors)
        return (left, top, right - left, bottom - top)


@dataclass(frozen=True)
class FrameSpace:
    """A captured frame of one monitor stream: frame pixels <-> global logical."""
    region: tuple   # the stream's logical monitor rectangle
    width: int      # frame pixels
    height: int

    def __post_init__(self):
        rect(self.region)
        if type(self.width) is not int or type(self.height) is not int or self.width <= 0 or self.height <= 0:
            raise ValueError('Invalid frame size')

    @property
    def sx(self):
        return self.width / self.region[2]

    @property
    def sy(self):
        return self.height / self.region[3]

    def to_frame(self, x, y):
        if not _finite(x, y):
            raise ValueError('Invalid point')
        return ((x - self.region[0]) * self.sx, (y - self.region[1]) * self.sy)

    def to_logical(self, px, py):
        if not _finite(px, py) or not (0 <= px < self.width and 0 <= py < self.height):
            raise ValueError('Point is outside the captured frame')
        return (self.region[0] + px / self.sx, self.region[1] + py / self.sy)

    def crop(self, window):
        """The frame-pixel crop of a window that lies entirely on this monitor."""
        window = rect(window)
        if not inside(self.region, window):
            raise PermissionError('WINDOW_OFF_MONITOR: the target window is not entirely on the captured monitor')
        x, y, width, height = window
        left, top = self.to_frame(x, y)
        right, bottom = self.to_frame(x + width, y + height)
        box = (max(0, round(left)), max(0, round(top)), min(self.width, round(right)), min(self.height, round(bottom)))
        if box[2] - box[0] < 1 or box[3] - box[1] < 1:
            raise ValueError('Window crop is empty')
        return WindowCrop(self, window, box)


@dataclass(frozen=True)
class WindowCrop:
    space: FrameSpace
    window: tuple   # logical client rectangle the crop was made for
    box: tuple      # (left, top, right, bottom) frame pixels

    @property
    def size(self):
        return (self.box[2] - self.box[0], self.box[3] - self.box[1])

    def to_logical(self, px, py):
        """Crop pixel -> global logical point, required to stay inside the window."""
        width, height = self.size
        if not _finite(px, py) or not (0 <= px < width and 0 <= py < height):
            raise ValueError('Point is outside the captured window')
        x, y = self.space.to_logical(self.box[0] + px, self.box[1] + py)
        wx, wy, ww, wh = self.window
        # Rounding at the crop edge may land a hair outside; clamp only that.
        x, y = min(max(x, wx), wx + ww - .5), min(max(y, wy), wy + wh - .5)
        return (x, y)

    def to_crop(self, x, y):
        px, py = self.space.to_frame(x, y)
        return (px - self.box[0], py - self.box[1])

    def describe(self):
        return {'window': list(self.window), 'box': list(self.box), 'region': list(self.space.region),
                'frame': [self.space.width, self.space.height]}

    @classmethod
    def restore(cls, value):
        """Rebuild from `describe()` output kept with a visual observation."""
        space = FrameSpace(tuple(value['region']), *value['frame'])
        crop = space.crop(tuple(value['window']))
        if list(crop.box) != list(value['box']):
            raise ValueError('Stored crop does not match its geometry')
        return crop


def input_point(layout, mapped_region, point):
    """Validate a global logical input point against the consented monitor.

    `mapped_region` is the portal/libei region the input device is bound to.
    The point must be on exactly that monitor in the current layout.
    """
    x, y = point
    monitor = layout.at(x, y) if layout else None
    if layout is not None and (monitor is None or tuple(monitor.bounds) != tuple(rect(mapped_region))):
        raise PermissionError('INPUT_REFUSED: the point is not on the consented monitor')
    rx, ry, rw, rh = rect(mapped_region)
    if not (rx <= x < rx + rw and ry <= y < ry + rh):
        raise PermissionError('INPUT_REFUSED: the point is outside the consented monitor')
    return (x, y)
