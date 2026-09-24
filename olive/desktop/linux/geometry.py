"""Portal compositor coordinates; no assumed pixel/logical scale equivalence."""
import math


def rectangle(value):
    if not isinstance(value, (tuple, list)) or len(value) != 4 or any(
            type(v) not in (int, float) or not math.isfinite(v) for v in value):
        raise ValueError('Invalid compositor rectangle')
    x, y, width, height = value
    if width <= 0 or height <= 0:
        raise ValueError('Empty compositor rectangle')
    return x, y, width, height


def approved_region(metadata):
    origin, size = metadata.get('position'), metadata.get('size')
    if not isinstance(origin, (tuple, list)) or not isinstance(size, (tuple, list)):
        raise PermissionError('Approved display geometry is unavailable')
    return rectangle([*origin, *size])


def contains(region, bounds):
    x, y, width, height = rectangle(region)
    try:
        bx, by, bw, bh = rectangle(bounds)
    except ValueError:
        return False
    return x <= bx and y <= by and bx + bw <= x + width and by + bh <= y + height


def pixel_point(region, image_size, point):
    """Map a full approved frame point, including negative display origins."""
    x, y, width, height = rectangle(region)
    iw, ih = image_size
    px, py = point
    rectangle([0, 0, iw, ih])
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in point) or not (0 <= px < iw and 0 <= py < ih):
        raise ValueError('Point is outside the captured frame')
    return x + px * width / iw, y + py * height / ih


def intersection(left, right):
    """Visible intersection of two logical compositor rectangles."""
    if not left or not right or len(left) != 4 or len(right) != 4:
        return None
    left, right = rectangle(left), rectangle(right)
    x, y = max(left[0], right[0]), max(left[1], right[1])
    end_x, end_y = min(left[0]+left[2], right[0]+right[2]), min(left[1]+left[3], right[1]+right[3])
    return [x,y,end_x-x,end_y-y] if end_x > x and end_y > y else None
