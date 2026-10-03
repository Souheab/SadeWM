use crate::config::TitleColors;
use anyhow::{Result, anyhow};
use cosmic_text::{Attrs, Buffer, Color, Family, FontSystem, Metrics, Shaping, SwashCache, Wrap};
use std::collections::VecDeque;
use tiny_skia::{Paint, PathBuilder, Pixmap, Stroke, Transform};
pub const TITLE_HEIGHT: i32 = 28;
pub fn rgb(hex: &str) -> [u8; 3] {
    let n = u32::from_str_radix(hex.trim_start_matches('#'), 16).unwrap_or(0);
    [(n >> 16) as u8, (n >> 8) as u8, n as u8]
}
pub fn hit_button(x: i32, y: i32) -> u8 {
    if !(0..TITLE_HEIGHT).contains(&y) {
        return 0;
    }
    for (i, cx) in [16, 36, 56].iter().enumerate() {
        if (x - cx).pow(2) + (y - 14).pow(2) <= 100 {
            return i as u8 + 1;
        }
    }
    4
}
pub struct Renderer {
    fonts: FontSystem,
    cache: SwashCache,
    titles: VecDeque<(String, Buffer)>,
}
impl Default for Renderer {
    fn default() -> Self {
        Self::new()
    }
}
impl Renderer {
    pub fn new() -> Self {
        let mut fonts = FontSystem::new();
        fonts
            .db_mut()
            .load_font_data(include_bytes!("../assets/DejaVuSans.ttf").to_vec());
        if fonts
            .db()
            .query(&cosmic_text::fontdb::Query {
                families: &[cosmic_text::fontdb::Family::SansSerif],
                ..Default::default()
            })
            .is_none()
        {
            fonts.db_mut().set_sans_serif_family("DejaVu Sans");
        }
        Self {
            fonts,
            cache: SwashCache::new(),
            titles: VecDeque::new(),
        }
    }
    pub fn titlebar(
        &mut self,
        width: u32,
        title: &str,
        focused: bool,
        above: bool,
        hover: u8,
        colors: &TitleColors,
    ) -> Result<Pixmap> {
        if self.cache.image_cache.len() > 4096 {
            self.cache = SwashCache::new();
        }
        let mut image = Pixmap::new(width.max(1), TITLE_HEIGHT as u32)
            .ok_or_else(|| anyhow!("titlebar dimensions too large"))?;
        let bg = if focused {
            &colors.bg_focused
        } else {
            &colors.bg
        };
        let [r, g, b] = rgb(bg);
        image.fill(tiny_skia::Color::from_rgba8(r, g, b, 255));
        let mut paint = Paint {
            anti_alias: true,
            ..Paint::default()
        };
        let set = |paint: &mut Paint, hex: &str, alpha: u8| {
            let [r, g, b] = rgb(hex);
            paint.set_color_rgba8(r, g, b, alpha);
        };
        set(&mut paint, &colors.sep, 255);
        let mut p = PathBuilder::new();
        p.move_to(0., 27.5);
        p.line_to(width as f32, 27.5);
        if let Some(p) = p.finish() {
            image.stroke_path(
                &p,
                &paint,
                &Stroke {
                    width: 1.,
                    ..Stroke::default()
                },
                Transform::identity(),
                None,
            );
        }
        for (index, color) in [&colors.close, &colors.above, &colors.minimize]
            .iter()
            .enumerate()
        {
            let x = 16. + index as f32 * 20.;
            set(
                &mut paint,
                color,
                if index == 1 && !above { 97 } else { 255 },
            );
            if let Some(path) = PathBuilder::from_circle(x, 14., 6.) {
                image.fill_path(
                    &path,
                    &paint,
                    tiny_skia::FillRule::Winding,
                    Transform::identity(),
                    None,
                );
            }
            if hover == index as u8 + 1 {
                let mut p = PathBuilder::new();
                match index {
                    0 => {
                        p.move_to(x - 3., 11.);
                        p.line_to(x + 3., 17.);
                        p.move_to(x + 3., 11.);
                        p.line_to(x - 3., 17.);
                    }
                    1 => {
                        p.move_to(x - 3.3, 15.2);
                        p.line_to(x, 11.6);
                        p.line_to(x + 3.3, 15.2);
                    }
                    _ => {
                        p.move_to(x - 3.3, 14.);
                        p.line_to(x + 3.3, 14.);
                    }
                }
                paint.set_color_rgba8(255, 255, 255, 230);
                if let Some(p) = p.finish() {
                    image.stroke_path(
                        &p,
                        &paint,
                        &Stroke {
                            width: 1.5,
                            ..Stroke::default()
                        },
                        Transform::identity(),
                        None,
                    );
                }
            }
        }
        if !title.is_empty() && width > 70 {
            let title = title.replace(['\n', '\r'], " ");
            // Shaping/fallback discovery is expensive for long Unicode titles.
            // Width only affects clipping/placement, so reuse shaped glyphs for
            // resize, focus and hover, with a bounded least-recently-used cache.
            let buffer = if let Some(index) = self.titles.iter().position(|(key, _)| key == &title)
            {
                self.titles.remove(index).unwrap().1
            } else {
                let mut buffer = Buffer::new(&mut self.fonts, Metrics::new(12., 28.));
                buffer.set_wrap(&mut self.fonts, Wrap::None);
                buffer.set_size(&mut self.fonts, None, Some(28.));
                buffer.set_text(
                    &mut self.fonts,
                    &title,
                    &Attrs::new().family(Family::SansSerif),
                    Shaping::Advanced,
                );
                buffer.shape_until_scroll(&mut self.fonts, false);
                buffer
            };
            let text_width = buffer
                .layout_runs()
                .map(|r| r.line_w)
                .fold(0.0_f32, f32::max);
            let offset = ((width as f32 - text_width) / 2.).max(70.) as i32;
            let [r, g, b] = rgb(&colors.text);
            buffer.draw(
                &mut self.fonts,
                &mut self.cache,
                Color::rgb(r, g, b),
                |x, y, w, h, c| {
                    let [r, g, b, a] = c.as_rgba();
                    for yy in y..y + h as i32 {
                        for xx in x + offset..x + offset + w as i32 {
                            if xx < 70 || xx >= width as i32 || !(0..28).contains(&yy) {
                                continue;
                            }
                            let i = (yy as usize * width as usize + xx as usize) * 4;
                            let pixels = image.data_mut();
                            for (channel, v) in [r, g, b].iter().enumerate() {
                                pixels[i + channel] = ((u32::from(*v) * u32::from(a)
                                    + u32::from(pixels[i + channel]) * (255 - u32::from(a)))
                                    / 255)
                                    as u8;
                            }
                        }
                    }
                },
            );
            self.titles.push_back((title, buffer));
            while self.titles.len() > 64
                || self
                    .titles
                    .iter()
                    .map(|(title, _)| title.len())
                    .sum::<usize>()
                    > 65536
            {
                self.titles.pop_front();
            }
        }
        Ok(image)
    }
}
/// Center-cropped nearest-neighbor cover sampling matches Go's coverImage.
pub fn cover_image(source: &image::RgbaImage, w: u32, h: u32) -> image::RgbaImage {
    let (sw, sh) = source.dimensions();
    let mut out = image::RgbaImage::new(w, h);
    if sw == 0 || sh == 0 || w == 0 || h == 0 {
        return out;
    }
    let scale = (sw as f64 / w as f64).min(sh as f64 / h as f64);
    let ox = (sw as f64 - w as f64 * scale) / 2.;
    let oy = (sh as f64 - h as f64 * scale) / 2.;
    for (x, y, pixel) in out.enumerate_pixels_mut() {
        let sx = ((ox + (x as f64 + 0.5) * scale) as u32).min(sw - 1);
        let sy = ((oy + (y as f64 + 0.5) * scale) as u32).min(sh - 1);
        *pixel = *source.get_pixel(sx, sy);
    }
    out
}
/// Encode straight RGB pixels for the server's native TrueColor visual.
pub fn encode_pixels(
    rgba: &[u8],
    w: usize,
    h: usize,
    bpp: u8,
    pad: u8,
    lsb: bool,
    masks: [u32; 3],
) -> Result<(Vec<u8>, usize)> {
    anyhow::ensure!(
        matches!(bpp, 16 | 24 | 32) && pad > 0,
        "unsupported X11 pixel format"
    );
    let bytes = usize::from(bpp) / 8;
    let stride = (w * usize::from(bpp)).div_ceil(usize::from(pad)) * usize::from(pad) / 8;
    anyhow::ensure!(rgba.len() >= w * h * 4, "short RGBA image");
    let mut out = vec![0; stride * h];
    for y in 0..h {
        for x in 0..w {
            let src = (y * w + x) * 4;
            let mut value = 0;
            for (c, mask) in masks.into_iter().enumerate() {
                if mask == 0 {
                    continue;
                }
                let max = mask >> mask.trailing_zeros();
                value |= ((u32::from(rgba[src + c]) * max + 127) / 255) << mask.trailing_zeros();
            }
            let data = if lsb {
                value.to_le_bytes()
            } else {
                value.to_be_bytes()
            };
            let slice = if lsb {
                &data[..bytes]
            } else {
                &data[4 - bytes..]
            };
            out[y * stride + x * bytes..y * stride + (x + 1) * bytes].copy_from_slice(slice);
        }
    }
    Ok((out, stride))
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn wallpaper_uses_center_crop_without_stretching() {
        let src = image::RgbaImage::from_fn(4, 2, |x, y| image::Rgba([x as u8, y as u8, 0, 255]));
        let out = cover_image(&src, 2, 2);
        assert_eq!(out.get_pixel(0, 0).0, [1, 0, 0, 255]);
        assert_eq!(out.get_pixel(1, 1).0, [2, 1, 0, 255]);
    }
    #[test]
    fn visual_formats() {
        let (bytes, stride) = encode_pixels(
            &[255, 0, 0, 255, 0, 255, 0, 255],
            2,
            1,
            16,
            32,
            true,
            [0xf800, 0x7e0, 31],
        )
        .unwrap();
        assert_eq!(stride, 4);
        assert_eq!(bytes, [0, 248, 224, 7]);
        let (bytes, _) = encode_pixels(
            &[255, 0, 0, 255],
            1,
            1,
            32,
            32,
            false,
            [0xff0000, 0xff00, 255],
        )
        .unwrap();
        assert_eq!(bytes, [0, 255, 0, 0]);
    }
    #[test]
    fn controls_and_unicode() {
        assert_eq!(hit_button(16, 14), 1);
        assert_eq!(hit_button(100, 14), 4);
        let mut r = Renderer::new();
        for width in [1, 60, 640] {
            let p = r
                .titlebar(
                    width,
                    "SADE — 日本語",
                    true,
                    false,
                    1,
                    &TitleColors::default(),
                )
                .unwrap();
            assert_eq!(p.height(), 28);
            assert_eq!(p.width(), width);
        }
    }
}
