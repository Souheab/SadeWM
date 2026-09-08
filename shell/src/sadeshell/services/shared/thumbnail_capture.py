"""Worker-owned XCB capture. Never redirects windows or owns the compositor."""
import threading
from array import array

from PIL import Image
import xcffib
import xcffib.xproto as x
import xcffib.render as render
import xcffib.composite as composite

RAW_LIMIT = 32 * 1024 * 1024
_fallback_lock = threading.Lock()


def thumbnail_size(width, height, maximum=(212, 136)):
    ratio = min(maximum[0] / width, maximum[1] / height, 1)
    return max(1, int(width * ratio)), max(1, int(height * ratio))


def decode_pixels(data, width, height, bpp, pad, byte_order, masks):
    stride = ((width * bpp + pad - 1) // pad) * (pad // 8)
    if len(data) < stride * height:
        raise ValueError("Short X image")
    red, green, blue = masks
    if masks == (0xff0000, 0xff00, 0xff) and bpp in (24, 32):
        mode = ("BGRX" if bpp == 32 else "BGR") if byte_order == 0 else ("XRGB" if bpp == 32 else "RGB")
        return Image.frombytes("RGB", (width, height), data, "raw", mode, stride)
    if bpp not in (16, 24, 32) or any(mask == 0 for mask in masks):
        raise ValueError("Unsupported X visual")
    shifts = [(mask & -mask).bit_length() - 1 for mask in masks]
    maxima = [mask >> shift for mask, shift in zip(masks, shifts)]
    output = bytearray(width * height * 3)
    size = bpp // 8
    order = "little" if byte_order == 0 else "big"
    for row in range(height):
        for col in range(width):
            offset = row * stride + col * size
            pixel = int.from_bytes(data[offset:offset + size], order)
            target = (row * width + col) * 3
            for channel, (mask, shift, maximum) in enumerate(zip(masks, shifts, maxima)):
                output[target + channel] = ((pixel & mask) >> shift) * 255 // maximum
    return Image.frombytes("RGB", (width, height), bytes(output))


class CaptureConnection:
    def __init__(self):
        self.connection = xcffib.connect()
        self.setup = self.connection.get_setup()
        self.screen = self.setup.roots[self.connection.pref_screen]
        self.formats = {f.depth: f for f in self.setup.pixmap_formats}
        self.visuals = {v.visual_id: v for depth in self.screen.allowed_depths for v in depth.visuals}
        self.render = None
        self.composite = None
        self.pict_formats = {}
        self._filter_available = True
        self._icon_atom = self.connection.core.InternAtom(False, 12, "_NET_WM_ICON").reply().atom
        self.visual_formats = {}
        try:
            self.render = self.connection(render.key)
            self.render.QueryVersion(0, 11).reply()
            reply = self.render.QueryPictFormats().reply()
            self.pict_formats = {f.id: f for f in reply.formats}
            self.visual_formats = {v.visual: v.format for s in reply.screens for d in s.depths for v in d.visuals}
        except Exception:
            self.render = None
        try:
            self.composite = self.connection(composite.key)
            self.composite.QueryVersion(0, 4).reply()
        except Exception:
            self.composite = None

    def close(self):
        self.connection.disconnect()

    def icon(self, window):
        # At most 1 MiB of icon property data enters Python.
        reply = self.connection.core.GetProperty(False, window, self._icon_atom,
                                                  x.Atom.CARDINAL, 0, 262144).reply()
        if reply.format != 32:
            return None
        values = array("I")
        values.frombytes(bytes(reply.value.buf()))
        candidates = []
        offset = 0
        while offset + 2 <= len(values):
            width, height = values[offset:offset + 2]
            offset += 2
            if not width or not height or width * height > len(values) - offset:
                break
            candidates.append((width, height, offset))
            offset += width * height
        if not candidates:
            return None
        width, height, start = min(candidates, key=lambda item: (max(item[:2]) < 64, abs(max(item[:2]) - 64)))
        data = values[start:start + width * height].tobytes()
        import sys
        raw_mode = "BGRA" if sys.byteorder == "little" else "ARGB"
        image = Image.frombytes("RGBA", (width, height), data, "raw", raw_mode)
        image.thumbnail((64, 64), Image.Resampling.LANCZOS)
        return image

    def _read(self, drawable, width, height, depth, masks):
        fmt = self.formats[depth]
        result = self.connection.core.GetImage(x.ImageFormat.ZPixmap, drawable, 0, 0, width, height, 0xffffffff).reply()
        return decode_pixels(bytes(result.data.buf()), width, height, fmt.bits_per_pixel,
                             fmt.scanline_pad, self.setup.image_byte_order, masks)

    def capture(self, window):
        conn = self.connection
        attrs = conn.core.GetWindowAttributes(window).reply()
        geometry = conn.core.GetGeometry(window).reply()
        if not geometry.width or not geometry.height:
            return None
        visual = self.visuals.get(attrs.visual)
        if visual is None:
            return None
        masks = (visual.red_mask, visual.green_mask, visual.blue_mask)
        if self.render is None or attrs.visual not in self.visual_formats:
            if attrs.map_state != x.MapState.Viewable:
                return None
            fmt = self.formats[geometry.depth]
            stride = ((geometry.width * fmt.bits_per_pixel + fmt.scanline_pad - 1) // fmt.scanline_pad) * (fmt.scanline_pad // 8)
            if stride * geometry.height > RAW_LIMIT or not _fallback_lock.acquire(blocking=False):
                return None
            try:
                image = self._read(window, geometry.width, geometry.height, geometry.depth, masks)
                image.thumbnail((212, 136), Image.Resampling.LANCZOS)
                return image
            finally:
                _fallback_lock.release()
        pixmaps = []
        pictures = []
        drawable = window
        try:
            if self.composite:
                named = conn.generate_id()
                try:
                    self.composite.NameWindowPixmap(window, named, is_checked=True).check()
                    pixmaps.append(named)
                    drawable = named
                except Exception:
                    pass
            if drawable == window and attrs.map_state != x.MapState.Viewable:
                return None
            width, height = thumbnail_size(geometry.width, geometry.height)
            fmt = self.visual_formats[attrs.visual]
            destination = conn.generate_id()
            conn.core.CreatePixmap(geometry.depth, destination, self.screen.root, width, height, is_checked=True).check()
            pixmaps.append(destination)
            source_picture, destination_picture = conn.generate_id(), conn.generate_id()
            for picture, image in ((source_picture, drawable), (destination_picture, destination)):
                self.render.CreatePicture(picture, image, fmt, 0, [], is_checked=True).check()
                pictures.append(picture)
            transform = render.TRANSFORM.synthetic(
                int(geometry.width / width * 65536), 0, 0,
                0, int(geometry.height / height * 65536), 0,
                0, 0, 65536)
            self.render.SetPictureTransform(source_picture, transform, is_checked=True).check()
            if self._filter_available:
                try:
                    self.render.SetPictureFilter(source_picture, 8, "bilinear", 0, [], is_checked=True).check()
                except x.MatchError:
                    # Probe once; retain the default filter thereafter.
                    self._filter_available = False
            self.render.Composite(render.PictOp.Src, source_picture, 0, destination_picture,
                                  0, 0, 0, 0, 0, 0, width, height, is_checked=True).check()
            return self._read(destination, width, height, geometry.depth, masks)
        finally:
            for picture in reversed(pictures):
                self.render.FreePicture(picture)
            for pixmap in reversed(pixmaps):
                conn.core.FreePixmap(pixmap)
            conn.flush()
