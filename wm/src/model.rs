use crate::config::{Config, TAG_MASK};
use std::time::Instant;

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct ClientId(pub u32);
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct MonitorId(pub usize);
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Rect {
    pub x: i32,
    pub y: i32,
    pub w: i32,
    pub h: i32,
}
impl Rect {
    pub fn new(x: i32, y: i32, w: i32, h: i32) -> Self {
        Self { x, y, w, h }
    }
    pub fn intersection(self, other: Self) -> i64 {
        i64::from(
            (self.x + self.w)
                .min(other.x + other.w)
                .saturating_sub(self.x.max(other.x))
                .max(0),
        ) * i64::from(
            (self.y + self.h)
                .min(other.y + other.h)
                .saturating_sub(self.y.max(other.y))
                .max(0),
        )
    }
    pub fn centered(self, area: Self, title: i32) -> Self {
        Self {
            x: (area.x + (area.w - self.w) / 2).max(area.x),
            y: (area.y + (area.h - self.h - title) / 2).max(area.y) + title,
            ..self
        }
    }
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Layout {
    Tile,
    Float,
}
impl Layout {
    pub fn symbol(self) -> &'static str {
        match self {
            Self::Tile => "[]=",
            Self::Float => "><>",
        }
    }
}
#[derive(Clone, Debug)]
pub struct Tag {
    pub layout: Layout,
    pub right: bool,
    pub mfact: f32,
    pub nmaster: usize,
}
#[derive(Clone, Debug)]
pub struct Monitor {
    pub id: MonitorId,
    pub rect: Rect,
    pub work: Rect,
    pub views: [u32; 2],
    pub selected_view: usize,
    pub tags: Vec<Tag>,
    pub active: Tag,
    pub gap: i32,
    pub clients: Vec<ClientId>,
    pub stack: Vec<ClientId>,
    pub selected: Option<ClientId>,
}
impl Monitor {
    pub fn new(id: usize, rect: Rect, cfg: &Config) -> Self {
        let active = Tag {
            layout: Layout::Tile,
            right: false,
            mfact: cfg.mfact,
            nmaster: cfg.nmaster,
        };
        Self {
            id: MonitorId(id),
            rect,
            work: rect,
            views: [1, 1],
            selected_view: 0,
            tags: vec![active.clone(); 9],
            active,
            gap: cfg.gap,
            clients: Vec::new(),
            stack: Vec::new(),
            selected: None,
        }
    }
    pub fn mask(&self) -> u32 {
        self.views[self.selected_view]
    }
    pub fn apply_tag(&mut self) {
        self.active = self.tags[desktop(self.mask()) as usize].clone();
    }
    pub fn save_tag(&mut self) {
        let index = desktop(self.mask()) as usize;
        self.tags[index] = self.active.clone();
    }
}
#[derive(Clone, Debug, Default)]
pub struct SizeHints {
    pub positioned: bool,
    pub fixed: bool,
    pub min: (i32, i32),
    pub max: (i32, i32),
    pub base: (i32, i32),
    pub inc: (i32, i32),
    pub aspect: (f32, f32),
    pub gravity: u32,
}
impl SizeHints {
    pub fn apply(&self, mut r: Rect) -> Rect {
        let base_min = self.base == self.min;
        if !base_min {
            r.w -= self.base.0;
            r.h -= self.base.1;
        }
        if self.aspect.0 > 0. && self.aspect.1 > 0. && r.w > 0 && r.h > 0 {
            if self.aspect.1 < (r.w as f32) / (r.h as f32) {
                r.w = ((r.h as f32) * self.aspect.1 + 0.5) as i32;
            } else if self.aspect.0 < (r.h as f32) / (r.w as f32) {
                r.h = ((r.w as f32) * self.aspect.0 + 0.5) as i32;
            }
        }
        if base_min {
            r.w -= self.base.0;
            r.h -= self.base.1;
        }
        if self.inc.0 > 0 {
            r.w -= r.w % self.inc.0;
        }
        if self.inc.1 > 0 {
            r.h -= r.h % self.inc.1;
        }
        r.w = (r.w + self.base.0).max(self.min.0);
        r.h = (r.h + self.base.1).max(self.min.1);
        if self.max.0 > 0 {
            r.w = r.w.min(self.max.0);
        }
        if self.max.1 > 0 {
            r.h = r.h.min(self.max.1);
        }
        r.w = r.w.clamp(1, 65535);
        r.h = r.h.clamp(1, 65535);
        r
    }
}
#[derive(Clone, Debug, Default)]
pub struct Flags {
    pub floating: bool,
    pub fullscreen: bool,
    pub minimized: bool,
    pub max_h: bool,
    pub max_v: bool,
    pub above: bool,
    pub below: bool,
    pub sticky: bool,
    pub shaded: bool,
    pub modal: bool,
    pub urgent: bool,
    pub attention: bool,
    pub skip_taskbar: bool,
    pub skip_pager: bool,
    pub dock: bool,
    pub desktop: bool,
    pub type_no_focus: bool,
    pub input_no_focus: bool,
    pub take_focus: bool,
}
#[derive(Clone, Debug)]
pub struct Client {
    pub id: ClientId,
    pub monitor: MonitorId,
    pub geom: Rect,
    pub old: Rect,
    pub normal: Option<(Rect, bool)>,
    pub fullscreen_restore: Option<(Rect, bool, i32)>,
    pub title: String,
    pub class: String,
    pub instance: String,
    pub tags: u32,
    pub flags: Flags,
    pub hints: SizeHints,
    pub border: i32,
    pub original_border: u16,
    pub frame: u32,
    pub titlebar: u32,
    pub border_window: u32,
    pub hover: u8,
    pub shape_geometry: Option<(i32, i32, bool)>,
    pub ignore_unmap: u32,
    pub mapped: bool,
    pub transient: u32,
    pub group: u32,
    pub window_type: u32,
    pub protocols: Vec<u32>,
    pub colormaps: Vec<u32>,
    pub user_time: Option<u32>,
    pub user_time_window: u32,
    pub strut: Vec<u32>,
    pub fullscreen_monitors: Option<[u32; 4]>,
    pub ping: Option<(u32, Instant)>,
    pub unresponsive: bool,
    pub sync_counter: u32,
    pub sync_value: u64,
    pub sync_wait: Option<Instant>,
    pub sync_pending: Option<Rect>,
    pub published: Option<Vec<u32>>,
}
impl Client {
    pub fn new(win: u32, mon: MonitorId, geom: Rect, tags: u32) -> Self {
        Self {
            id: ClientId(win),
            monitor: mon,
            geom,
            old: geom,
            normal: None,
            fullscreen_restore: None,
            title: String::new(),
            class: String::new(),
            instance: String::new(),
            tags,
            flags: Flags::default(),
            hints: SizeHints::default(),
            border: 0,
            original_border: 0,
            frame: 0,
            titlebar: 0,
            border_window: 0,
            hover: 0,
            shape_geometry: None,
            ignore_unmap: 0,
            mapped: false,
            transient: 0,
            group: 0,
            window_type: 0,
            protocols: Vec::new(),
            colormaps: Vec::new(),
            user_time: None,
            user_time_window: 0,
            strut: Vec::new(),
            fullscreen_monitors: None,
            ping: None,
            unresponsive: false,
            sync_counter: 0,
            sync_value: 0,
            sync_wait: None,
            sync_pending: None,
            published: None,
        }
    }
    pub fn visible(&self, mask: u32, showing: bool) -> bool {
        !self.flags.minimized
            && (self.flags.dock
                || self.flags.desktop
                || (!showing && (self.flags.sticky || self.tags & mask != 0)))
    }
    pub fn focusable(&self) -> bool {
        !self.flags.type_no_focus && (!self.flags.input_no_focus || self.flags.take_focus)
    }
    pub fn stack_window(&self) -> u32 {
        if self.frame != 0 {
            self.frame
        } else {
            self.id.0
        }
    }
    pub fn maximized(&self) -> bool {
        self.flags.max_h && self.flags.max_v
    }
    pub fn remember_normal(&mut self) {
        if self.normal.is_none() {
            self.normal = Some((self.geom, self.flags.floating));
        }
    }
}
/// Reserve only the portions of edge struts that intersect this physical monitor.
pub fn workarea(
    rect: Rect,
    root: Rect,
    top_offset: i32,
    bottom_offset: i32,
    struts: &[Vec<u32>],
) -> Rect {
    let (mut left, mut right, mut top, mut bottom) = (0, 0, top_offset, bottom_offset);
    for s in struts.iter().filter(|s| s.len() >= 4) {
        let spans = |i: usize, start: i32, end: i32| {
            s.len() < 12
                || i64::from(start) <= i64::from(s[i + 1]) && i64::from(end) >= i64::from(s[i])
        };
        let edge = |i: usize, max: i32| s[i].min(max.max(0) as u32) as i32;
        if spans(4, rect.y, rect.y + rect.h - 1) {
            left = left.max((edge(0, root.w) - rect.x).clamp(0, rect.w));
        }
        if spans(6, rect.y, rect.y + rect.h - 1) {
            right = right.max((rect.x + rect.w - (root.w - edge(1, root.w))).clamp(0, rect.w));
        }
        if spans(8, rect.x, rect.x + rect.w - 1) {
            top = top.max((edge(2, root.h) - rect.y).clamp(0, rect.h));
        }
        if spans(10, rect.x, rect.x + rect.w - 1) {
            bottom = bottom.max((rect.y + rect.h - (root.h - edge(3, root.h))).clamp(0, rect.h));
        }
    }
    Rect::new(
        rect.x + left,
        rect.y + top,
        (rect.w - left - right).max(1),
        (rect.h - top - bottom).max(1),
    )
}
// Keep this bit operation compatible with toolchains predating isolate_lowest_one.
#[allow(clippy::manual_isolate_lowest_one)]
pub fn focus_tag_mask(tags: u32, visible: u32) -> u32 {
    if tags & visible != 0 {
        0
    } else {
        tags & tags.wrapping_neg()
    }
}
pub fn desktop(mask: u32) -> u32 {
    if mask == 0 {
        0
    } else {
        31 - mask.leading_zeros()
    }
}
pub fn client_desktop(mask: u32) -> u32 {
    if mask & TAG_MASK == TAG_MASK {
        u32::MAX
    } else {
        desktop(mask & TAG_MASK)
    }
}
pub fn timestamp_current(value: u32, reference: u32) -> bool {
    value.wrapping_sub(reference) as i32 >= 0
}
pub fn tile(m: &Monitor, clients: &[(ClientId, i32)]) -> Vec<(ClientId, Rect)> {
    let n = clients.len();
    let mut result = Vec::new();
    if n == 0 {
        return result;
    }
    let mw = if n > m.active.nmaster {
        if m.active.nmaster > 0 {
            (m.work.w as f32 * m.active.mfact) as i32
        } else {
            0
        }
    } else {
        m.work.w - m.gap
    };
    let (mx, tx) = if m.active.right {
        (m.work.x + m.work.w - mw, m.work.x + m.gap)
    } else {
        (m.work.x + m.gap, m.work.x + mw + m.gap)
    };
    let (mut my, mut ty) = (m.gap, m.gap);
    for (i, (id, border)) in clients.iter().enumerate() {
        let r = if i < m.active.nmaster {
            let h = (m.work.h - my) / (n.min(m.active.nmaster) - i) as i32 - m.gap;
            let r = Rect::new(mx, m.work.y + my, mw - 2 * border - m.gap, h - 2 * border);
            my += h + m.gap;
            r
        } else {
            let h = (m.work.h - ty) / (n - i) as i32 - m.gap;
            let r = Rect::new(
                tx,
                m.work.y + ty,
                m.work.w - mw - 2 * border - 2 * m.gap,
                h - 2 * border,
            );
            ty += h + m.gap;
            r
        };
        result.push((
            *id,
            Rect {
                w: r.w.max(3),
                h: r.h.max(3),
                ..r
            },
        ));
    }
    result
}
pub fn resize_edge(mut r: Rect, dx: i32, dy: i32, d: u32) -> Rect {
    if matches!(d, 0 | 6 | 7) {
        r.x += dx;
        r.w -= dx;
    }
    if matches!(d, 2 | 3 | 4 | 9) {
        r.w += dx;
    }
    if matches!(d, 0..=2) {
        r.y += dy;
        r.h -= dy;
    }
    if matches!(d, 4 | 5 | 6 | 9) {
        r.h += dy;
    }
    if matches!(d, 8 | 10) {
        r.x += dx;
        r.y += dy;
    }
    r.w = r.w.max(1);
    r.h = r.h.max(1);
    r
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn placement_clamps_oversized_frames() {
        assert_eq!(
            Rect::new(0, 0, 200, 100).centered(Rect::new(100, 50, 800, 600), 28),
            Rect::new(400, 314, 200, 100)
        );
        assert_eq!(
            Rect::new(0, 0, 500, 300).centered(Rect::new(50, 40, 300, 200), 28),
            Rect::new(50, 68, 500, 300)
        );
    }
    #[test]
    fn independent_restore_slots_survive_other_resizes() {
        let mut c = Client::new(1, MonitorId(0), Rect::new(10, 20, 640, 480), 1);
        c.remember_normal();
        c.geom = Rect::new(0, 40, 1920, 1000);
        c.fullscreen_restore = Some((c.geom, true, 0));
        c.old = Rect::new(0, 0, 3840, 1080);
        c.remember_normal();
        assert_eq!(c.normal.unwrap().0, Rect::new(10, 20, 640, 480));
        assert_eq!(
            c.fullscreen_restore.unwrap().0,
            Rect::new(0, 40, 1920, 1000)
        );
    }
    #[test]
    fn focus_tag_selects_lowest_hidden_tag() {
        for (tags, current, want) in [(5, 4, 0), (6, 1, 2), (0, 1, 0)] {
            assert_eq!(focus_tag_mask(tags, current), want);
        }
    }
    #[test]
    fn struts_physical_monitors_and_idempotent_offsets() {
        let root = Rect::new(0, 0, 1920, 1080);
        let left = Rect::new(0, 0, 960, 1080);
        let right = Rect::new(960, 0, 960, 1080);
        let mut strut = vec![0; 12];
        strut[2] = 60;
        strut[9] = 959;
        assert_eq!(
            workarea(left, root, 40, 0, &[strut.clone()]),
            Rect::new(0, 60, 960, 1020)
        );
        assert_eq!(
            workarea(right, root, 40, 0, &[strut]),
            Rect::new(960, 40, 960, 1040)
        );
        assert_eq!(left.intersection(Rect::new(0, 0, 10, 10)), 100);
        let malformed = workarea(left, root, 40, 0, &[vec![u32::MAX; 12]]);
        assert!(malformed.w >= 1 && malformed.h >= 1 && malformed.x >= 0);
        for _ in 0..2 {
            assert_eq!(
                workarea(left, root, 10, 20, &[]),
                Rect::new(0, 10, 960, 1050)
            );
        }
    }
    #[test]
    fn showing_desktop_does_not_hide_docks_and_flags_are_independent() {
        let mut c = Client::new(1, MonitorId(0), Rect::default(), 1);
        assert!(!c.visible(1, true));
        c.flags.dock = true;
        assert!(c.visible(1, true));
        c.flags.dock = false;
        c.flags.sticky = true;
        assert!(c.visible(2, false));
        c.flags.fullscreen = true;
        c.flags.above = true;
        c.flags.fullscreen = false;
        assert!(c.flags.above);
        c.flags.minimized = true;
        assert!(!c.visible(1, false));
    }
    #[test]
    fn all_interactive_resize_directions() {
        let expected = [
            (110, 220, 290, 180),
            (100, 220, 300, 180),
            (100, 220, 310, 180),
            (100, 200, 310, 200),
            (100, 200, 310, 220),
            (100, 200, 300, 220),
            (110, 200, 290, 220),
            (110, 200, 290, 200),
            (110, 220, 300, 200),
        ];
        for (d, (x, y, w, h)) in expected.into_iter().enumerate() {
            assert_eq!(
                resize_edge(Rect::new(100, 200, 300, 200), 10, 20, d as u32),
                Rect::new(x, y, w, h)
            );
        }
    }
    #[test]
    fn size_hints_base_increments_and_fixed_limits() {
        let hints = SizeHints {
            base: (10, 10),
            inc: (8, 16),
            min: (20, 20),
            max: (500, 500),
            ..SizeHints::default()
        };
        assert_eq!(
            hints.apply(Rect::new(7, 9, 105, 105)),
            Rect::new(7, 9, 98, 90)
        );
        assert_eq!(hints.apply(Rect::new(7, 9, 900, 900)).w, 500);
    }
    #[test]
    fn tiled_geometry_and_reverse() {
        let mut m = Monitor::new(0, Rect::new(0, 0, 1280, 800), &Config::default());
        m.work = Rect::new(0, 40, 1280, 760);
        let rows = [(ClientId(1), 2), (ClientId(2), 2)];
        let a = tile(&m, &rows);
        assert_eq!(a[0].1, Rect::new(10, 50, 626, 736));
        assert_eq!(a[1].1.x, 650);
        m.active.right = true;
        assert_eq!(tile(&m, &rows)[0].1.x, 640);
    }
    #[test]
    fn tags_and_timestamp_wrap() {
        assert_eq!(client_desktop(5), 2);
        assert_eq!(client_desktop(511), u32::MAX);
        assert!(timestamp_current(10, u32::MAX - 5));
        assert!(!timestamp_current(5, 100));
    }
    #[test]
    fn resize_edges() {
        let r = Rect::new(100, 100, 200, 100);
        assert_eq!(resize_edge(r, 20, 10, 0), Rect::new(120, 110, 180, 90));
        assert_eq!(resize_edge(r, 20, 10, 4), Rect::new(100, 100, 220, 110));
    }
}
