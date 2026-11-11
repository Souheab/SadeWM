use super::*;
use crate::{actions::Action, render};
#[derive(Clone, Debug)]
pub(super) struct Drag {
    pub id: ClientId,
    start: (i32, i32),
    original: Rect,
    before: Client,
    layouts: Vec<(MonitorId, Vec<ClientId>, Tag)>,
    direction: u32,
    pub(super) button: u8,
    external: bool,
    last_swap: Option<ClientId>,
    last: (i32, i32),
}
#[derive(Clone, Debug)]
pub(super) struct TitlePress {
    pub id: ClientId,
    pub time: u32,
    pub pos: (i32, i32),
}
impl Wm {
    pub(super) fn grab_keys(&mut self) -> Result<()> {
        let setup = self.conn.setup();
        let min = setup.min_keycode;
        let max = setup.max_keycode;
        let mapping = self
            .conn
            .get_keyboard_mapping(min, max - min + 1)?
            .reply()?;
        let per = usize::from(mapping.keysyms_per_keycode);
        let names = config::keysyms();
        self.numlock = 0;
        let mods = self.conn.get_modifier_mapping()?.reply()?;
        let mod_per = mods.keycodes.len() / 8;
        if per > 0 && mod_per > 0 {
            for (i, code) in mods.keycodes.iter().enumerate() {
                if *code >= min && *code <= max {
                    let start = usize::from(*code - min) * per;
                    if mapping.keysyms[start..start + per].contains(&0xff7f) {
                        self.numlock |= 1 << (i / mod_per);
                    }
                }
            }
        }
        self.keys.clear();
        if per == 0 {
            return Ok(());
        }
        // Resolve mappings before removing grabs. Round trips in the ungrabbed
        // interval can lose the first shortcut after XTest/XKB changes devices.
        self.conn.grab_server()?;
        self.conn.ungrab_key(0, self.root, ModMask::ANY)?;
        for b in &self.config.keys {
            let symbol = names.get(b.key.as_str()).copied().or_else(|| {
                if b.key.chars().count() == 1 {
                    b.key.chars().next().map(|c| c as u32)
                } else {
                    None
                }
            });
            let Some(symbol) = symbol else {
                continue;
            };
            for (index, row) in mapping.keysyms.chunks(per).enumerate() {
                if row.contains(&symbol) {
                    let key = min + index as u8;
                    for extra in [0, 2, self.numlock, 2 | self.numlock] {
                        self.conn.grab_key(
                            false,
                            self.root,
                            ModMask::from(b.mask() | extra),
                            key,
                            GrabMode::ASYNC,
                            GrabMode::ASYNC,
                        )?;
                    }
                    self.keys.push((key, b.mask(), b.clone()));
                }
            }
        }
        self.conn.ungrab_server()?;
        for id in self.order.clone() {
            self.grab_buttons(id)?;
        }
        Ok(())
    }
    pub(super) fn grab_buttons(&self, id: ClientId) -> Result<()> {
        self.conn
            .ungrab_button(ButtonIndex::ANY, id.0, ModMask::ANY)?;
        if self.focused != Some(id)
            || self.clients[&id].flags.floating
            || self.monitors[self.clients[&id].monitor.0].active.layout == Layout::Float
        {
            self.conn.grab_button(
                false,
                id.0,
                EventMask::BUTTON_PRESS,
                GrabMode::SYNC,
                GrabMode::ASYNC,
                x11rb::NONE,
                x11rb::NONE,
                ButtonIndex::ANY,
                ModMask::ANY,
            )?;
        }
        for extra in [0, 2, self.numlock, 2 | self.numlock] {
            for button in [ButtonIndex::M1, ButtonIndex::M2, ButtonIndex::M3] {
                self.conn.grab_button(
                    false,
                    id.0,
                    EventMask::BUTTON_PRESS | EventMask::BUTTON_RELEASE,
                    GrabMode::ASYNC,
                    GrabMode::ASYNC,
                    x11rb::NONE,
                    x11rb::NONE,
                    button,
                    ModMask::from(config::SUPER | extra),
                )?;
            }
        }
        Ok(())
    }
    fn clean_mask(&self, state: u16) -> u16 {
        state & 255 & !(2 | self.numlock)
    }
    pub(super) fn key_press(&mut self, e: KeyPressEvent) -> Result<()> {
        if self.drag.is_some() || self.title_press.is_some() {
            let mapping = self.conn.get_keyboard_mapping(e.detail, 1)?.reply()?;
            let sym = mapping.keysyms.first().copied().unwrap_or(0);
            match sym {
                0xff1b => {
                    self.title_press = None;
                    self.last_title_click = None;
                    return self.end_drag(0, true);
                }
                0xff0d if self.drag.as_ref().is_some_and(|d| d.external) => {
                    return self.end_drag(0, false);
                }
                0xff51..=0xff54 if self.drag.as_ref().is_some_and(|d| d.external) => {
                    let d = self.drag.clone().unwrap();
                    let step = if u16::from(e.state) & config::CTRL != 0 {
                        1
                    } else {
                        10
                    };
                    let (dx, dy) = match sym {
                        0xff51 => (-step, 0),
                        0xff52 => (0, -step),
                        0xff53 => (step, 0),
                        _ => (0, step),
                    };
                    return self.drag_motion(d.last.0 + dx, d.last.1 + dy);
                }
                _ => return Ok(()),
            }
        }
        let mask = self.clean_mask(e.state.into());
        self.logger.debug(&format!(
            "key event: code={} mask={} numlock={}",
            e.detail, mask, self.numlock
        ));
        let bindings: Vec<_> = self
            .keys
            .iter()
            .filter(|(k, m, _)| *k == e.detail && *m == mask)
            .map(|(_, _, b)| b.clone())
            .collect();
        for b in bindings {
            self.logger.debug(&format!(
                "key: {} selected={:?}",
                b.action,
                self.selected_client()
            ));
            self.action(&b)?;
        }
        Ok(())
    }
    pub(super) fn button_press(&mut self, e: ButtonPressEvent) -> Result<()> {
        let Some(id) = self.client_id(e.event) else {
            return Ok(());
        };
        // X11 wheel directions are buttons 4–7. Floating clients (including
        // fullscreen ones) grab every button, but scrolling must not trigger
        // click-to-raise: restacking briefly exposes overlapping windows.
        if (4..=7).contains(&e.detail) {
            self.conn.allow_events(Allow::REPLAY_POINTER, e.time)?;
            self.conn.allow_events(Allow::ASYNC_KEYBOARD, e.time)?;
            return Ok(());
        }
        self.focus(Some(id))?;
        self.restack()?;
        if self.frames.contains_key(&e.event) && self.clean_mask(e.state.into()) != config::SUPER {
            let c = &self.clients[&id];
            if e.detail == 1
                && let Some(direction) = c.extents.resize_direction(
                    c.geom,
                    c.flags.shaded,
                    e.event_x.into(),
                    e.event_y.into(),
                )
            {
                self.begin_drag(id, e.root_x.into(), e.root_y.into(), direction, 1, false)?;
            }
            return Ok(());
        }
        if self.titles.contains_key(&e.event) && self.clean_mask(e.state.into()) != config::SUPER {
            if e.detail == 1 {
                let hit = render::hit_button(e.event_x.into(), e.event_y.into());
                if hit != 4 {
                    self.last_title_click = None;
                }
                match hit {
                    1 => self.close_client(id, e.time)?,
                    2 => {
                        let atom = self.a("_NET_WM_STATE_ABOVE");
                        self.state_atom(id, atom, 2)?;
                        self.publish_state(id)?;
                        self.draw_title(id)?;
                        self.restack()?;
                    }
                    3 => self.minimize_client(id)?,
                    4 => {
                        let pos = (i32::from(e.root_x), i32::from(e.root_y));
                        let double =
                            self.last_title_click
                                .take()
                                .is_some_and(|(last_id, time, last)| {
                                    last_id == id
                                        && e.time.wrapping_sub(time) <= 400
                                        && (pos.0 - last.0).abs() <= 5
                                        && (pos.1 - last.1).abs() <= 5
                                });
                        if double && !self.clients[&id].hints.fixed {
                            let on = !self.clients[&id].maximized();
                            self.maximize(id, on, on)?;
                            self.arrange()?;
                        } else {
                            self.title_press = Some(TitlePress {
                                id,
                                time: e.time,
                                pos,
                            });
                        }
                    }
                    _ => {}
                }
            }
            return Ok(());
        }
        self.last_title_click = None;
        if self.clean_mask(e.state.into()) == config::SUPER {
            self.conn.ungrab_pointer(x11rb::CURRENT_TIME)?;
            self.conn
                .allow_events(Allow::ASYNC_KEYBOARD, x11rb::CURRENT_TIME)?;
            match e.detail {
                1 => self.begin_drag(id, e.root_x.into(), e.root_y.into(), 8, 1, false)?,
                2 => self.toggle_floating(id)?,
                3 => self.begin_drag(id, e.root_x.into(), e.root_y.into(), 4, 3, false)?,
                _ => {}
            }
        } else {
            self.conn.allow_events(Allow::REPLAY_POINTER, e.time)?;
            self.conn.allow_events(Allow::ASYNC_KEYBOARD, e.time)?;
        }
        Ok(())
    }
    pub(super) fn motion(&mut self, e: MotionNotifyEvent) -> Result<()> {
        self.start_title_drag(e.root_x.into(), e.root_y.into())?;
        if self.drag.is_some() {
            return self.drag_motion(e.root_x.into(), e.root_y.into());
        }
        if let Some(id) = self.titles.get(&e.event).copied() {
            let hover = render::hit_button(e.event_x.into(), e.event_y.into());
            if self.clients[&id].hover != hover {
                self.clients.get_mut(&id).unwrap().hover = hover;
                self.draw_title(id)?;
            }
        }
        if let Some(id) = self.frames.get(&e.event).copied() {
            self.frame_cursor(id, e.event_x.into(), e.event_y.into())?;
        }
        Ok(())
    }
    pub(super) fn frame_cursor(&self, id: ClientId, x: i32, y: i32) -> Result<()> {
        let c = &self.clients[&id];
        let cursor = c
            .extents
            .resize_direction(c.geom, c.flags.shaded, x, y)
            .map(|d| self.cursors[3 + d as usize])
            .unwrap_or(self.cursors[0]);
        self.conn
            .change_window_attributes(c.frame, &ChangeWindowAttributesAux::new().cursor(cursor))?;
        Ok(())
    }
    pub(super) fn start_title_drag(&mut self, x: i32, y: i32) -> Result<()> {
        if let Some(press) = self.title_press.clone()
            && ((x - press.pos.0).abs() > 5 || (y - press.pos.1).abs() > 5)
        {
            self.title_press = None;
            self.last_title_click = None;
            if self.clients.contains_key(&press.id) {
                self.begin_drag(press.id, press.pos.0, press.pos.1, 8, 1, false)?;
            }
        }
        Ok(())
    }
    pub(super) fn begin_drag(
        &mut self,
        id: ClientId,
        x: i32,
        y: i32,
        direction: u32,
        button: u8,
        external: bool,
    ) -> Result<()> {
        let (x, y) = if external && x == 0 && y == 0 {
            let pointer = self.conn.query_pointer(self.root)?.reply()?;
            (i32::from(pointer.root_x), i32::from(pointer.root_y))
        } else {
            (x, y)
        };
        let c = &self.clients[&id];
        if self.drag.is_some()
            || c.flags.dock
            || c.flags.desktop
            || (!external && c.flags.fullscreen)
            || (c.hints.fixed && !matches!(direction, 8 | 10))
        {
            return Ok(());
        }
        let before = c.clone();
        let layouts = self
            .monitors
            .iter()
            .map(|m| (m.id, m.clients.clone(), m.active.clone()))
            .collect();
        self.conn.ungrab_pointer(x11rb::CURRENT_TIME)?;
        let cursor = if matches!(direction, 8 | 10) {
            1
        } else if direction <= 7 {
            3 + direction as usize
        } else {
            2
        };
        let reply = self
            .conn
            .grab_pointer(
                false,
                self.root,
                EventMask::BUTTON_PRESS | EventMask::BUTTON_RELEASE | EventMask::POINTER_MOTION,
                GrabMode::ASYNC,
                GrabMode::ASYNC,
                x11rb::NONE,
                self.cursors[cursor],
                x11rb::CURRENT_TIME,
            )?
            .reply()?;
        if reply.status != GrabStatus::SUCCESS {
            return Ok(());
        }
        {
            let reply = self
                .conn
                .grab_keyboard(
                    false,
                    self.root,
                    x11rb::CURRENT_TIME,
                    GrabMode::ASYNC,
                    GrabMode::ASYNC,
                )?
                .reply()?;
            if reply.status != GrabStatus::SUCCESS {
                self.conn.ungrab_pointer(x11rb::CURRENT_TIME)?;
                return Ok(());
            }
        }
        self.drag = Some(Drag {
            id,
            start: (x, y),
            original: before.geom,
            before: before.clone(),
            layouts,
            direction,
            button,
            external,
            last_swap: None,
            last: (x, y),
        });
        if external && before.flags.fullscreen {
            self.fullscreen(id, false)?;
        }
        if external && before.flags.shaded {
            self.shade(id, false)?;
        }
        let free =
            before.flags.floating || self.monitors[before.monitor.0].active.layout == Layout::Float;
        if (external || free) && (before.flags.max_h || before.flags.max_v) {
            self.maximize(id, false, false)?;
            if self.clients[&id].flags.shaded
                && let Some((r, _)) = self.clients[&id].normal
            {
                self.resize_now(id, r)?;
            }
            if matches!(direction, 8 | 10) {
                let c = &self.clients[&id];
                let fraction =
                    (x - before.geom.x).clamp(0, before.geom.w) as f32 / before.geom.w as f32;
                let r = Rect::new(
                    x - (fraction * c.geom.w as f32) as i32,
                    y - (y - before.geom.y).clamp(-c.extents.top, c.geom.h),
                    c.geom.w,
                    c.geom.h,
                );
                self.resize_now(id, r)?;
            }
        }
        if external {
            let c = self.clients.get_mut(&id).unwrap();
            c.flags.floating = true;
            c.was_free = true;
        }
        self.arrange_windows()?;
        self.focus(Some(id))?;
        self.restack()?;
        self.drag.as_mut().unwrap().original = self.clients[&id].geom;
        if !external && direction == 4 && button == 3 {
            let c = &self.clients[&id];
            self.conn.warp_pointer(
                x11rb::NONE,
                id.0,
                0,
                0,
                0,
                0,
                (c.geom.w + c.border - 1) as i16,
                (c.geom.h + c.border - 1) as i16,
            )?;
        }
        Ok(())
    }
    pub(super) fn drag_motion(&mut self, x: i32, y: i32) -> Result<()> {
        let Some(d) = self.drag.clone() else {
            return Ok(());
        };
        if !self.clients.contains_key(&d.id) {
            return Ok(());
        }
        self.drag.as_mut().unwrap().last = (x, y);
        let c = &self.clients[&d.id];
        let m = &self.monitors[c.monitor.0];
        if !d.external
            && d.direction == 4
            && d.button == 3
            && !c.flags.floating
            && m.active.layout == Layout::Tile
        {
            let mut fraction = (x - m.work.x) as f32 / m.work.w as f32;
            if m.active.right {
                fraction = 1. - fraction;
            }
            if (0.05..=0.95).contains(&fraction) {
                let m = &mut self.monitors[c.monitor.0];
                m.active.mfact = fraction;
                m.save_tag();
                self.arrange()?;
            }
            return Ok(());
        }
        if !d.external && d.direction == 8 && !c.flags.floating && m.active.layout == Layout::Tile {
            let target = m.clients.iter().copied().find(|id| {
                *id != d.id
                    && !self.clients[id].flags.floating
                    && self.visible(*id)
                    && Rect::new(x, y, 1, 1).intersection(self.clients[id].geom) > 0
            });
            if target != d.last_swap {
                if let Some(target) = target {
                    self.swap_clients(d.id, target)?;
                }
                if let Some(d) = &mut self.drag {
                    d.last_swap = target;
                }
            }
            return Ok(());
        }
        let mut r = if !d.external && d.direction == 4 && d.button == 3 {
            Rect::new(
                c.geom.x,
                c.geom.y,
                (x - d.original.x - 2 * c.border + 1).max(1),
                (y - d.original.y - 2 * c.border + 1).max(1),
            )
        } else {
            resize_edge(d.original, x - d.start.0, y - d.start.1, d.direction)
        };
        if !d.external && d.direction == 8 {
            let area = m.work;
            let extents = c.extents;
            let top = extents.top;
            let minx = area.x + extents.left;
            let maxx = (area.x + area.w - r.w - extents.right).max(minx);
            let maxy = (area.y + area.h - r.h - extents.bottom).max(area.y + top);
            r.x = r.x.clamp(minx, maxx);
            r.y = r.y.clamp(area.y + top, maxy);
            let snap = self.config.snap;
            if (r.x - minx).abs() < snap && r.x < d.original.x {
                r.x = minx;
            }
            if (r.x - maxx).abs() < snap && r.x > d.original.x {
                r.x = maxx;
            }
            if (r.y - area.y - top).abs() < snap && r.y < d.original.y {
                r.y = area.y + top;
            }
            if (r.y - maxy).abs() < snap && r.y > d.original.y {
                r.y = maxy;
            }
        }
        self.resize(d.id, r, true)
    }
    pub(super) fn end_drag(&mut self, button: u8, cancel: bool) -> Result<()> {
        let Some(d) = self.drag.clone() else {
            return Ok(());
        };
        if !cancel && button != 0 && d.button != 0 && button != d.button {
            return Ok(());
        }
        self.drag = None;
        self.conn.ungrab_pointer(x11rb::CURRENT_TIME)?;
        self.conn.ungrab_keyboard(x11rb::CURRENT_TIME)?;
        if !self.clients.contains_key(&d.id) {
            return Ok(());
        }
        let c = self.clients.get_mut(&d.id).unwrap();
        c.sync_wait = None;
        if cancel {
            c.sync_pending = None;
            c.flags.floating = d.before.flags.floating;
            c.flags.fullscreen = d.before.flags.fullscreen;
            c.flags.shaded = d.before.flags.shaded;
            c.flags.max_h = d.before.flags.max_h;
            c.flags.max_v = d.before.flags.max_v;
            c.normal = d.before.normal;
            c.fullscreen_restore = d.before.fullscreen_restore;
            c.floating_geom = d.before.floating_geom;
            c.was_free = d.before.was_free;
            c.border = d.before.border;
            c.tags = d.before.tags;
            if !d.external {
                for (id, order, active) in d.layouts {
                    if let Some(m) = self.monitors.get_mut(id.0) {
                        m.clients.sort_by_key(|id| {
                            order.iter().position(|i| i == id).unwrap_or(usize::MAX)
                        });
                        if !d.before.flags.floating && active.layout == Layout::Tile {
                            m.active = active;
                            m.save_tag();
                        }
                    }
                }
            }
            self.resize_now(d.id, d.before.geom)?;
            self.publish_desktop(d.id)?;
        } else if let Some(r) = c.sync_pending.take() {
            self.resize_now(d.id, r)?;
        }
        if !cancel {
            let mon = self.rect_monitor(self.clients[&d.id].geom);
            self.move_monitor(d.id, mon, true)?;
            self.selected = mon;
        }
        self.arrange_windows()?;
        self.focus(Some(d.id))?;
        self.restack()?;
        self.draw_title(d.id)
    }
    fn toggle_floating(&mut self, id: ClientId) -> Result<()> {
        let c = self.clients.get_mut(&id).unwrap();
        if c.flags.fullscreen {
            return Ok(());
        }
        c.flags.floating = !c.flags.floating || c.hints.fixed;
        self.suppress_crossings(true)?;
        self.arrange()?;
        self.suppress_crossings(false)
    }
    fn swap_clients(&mut self, a: ClientId, b: ClientId) -> Result<()> {
        let ma = self.clients[&a].monitor;
        let mb = self.clients[&b].monitor;
        if ma != mb {
            return Ok(());
        }
        let clients = &mut self.monitors[ma.0].clients;
        if let (Some(a), Some(b)) = (
            clients.iter().position(|i| *i == a),
            clients.iter().position(|i| *i == b),
        ) {
            clients.swap(a, b);
        }
        // The windows trade places under a stationary pointer; without this,
        // focus-follows-mouse would hand focus to whichever lands beneath it.
        self.suppress_crossings(true)?;
        self.arrange()?;
        self.suppress_crossings(false)
    }
    /// Whether `id` occupies a tile slot (as opposed to floating freely).
    fn tiled(&self, id: ClientId) -> bool {
        let c = &self.clients[&id];
        !c.flags.floating
            && !c.flags.fullscreen
            && self.monitors[c.monitor.0].active.layout == Layout::Tile
    }
    /// The on-screen footprint used for directional navigation: frame plus border.
    fn nav_rect(&self, id: ClientId) -> Rect {
        let c = &self.clients[&id];
        let r = c.extents.outer(c.geom, c.flags.shaded && !c.flags.fullscreen);
        Rect::new(r.x, r.y, r.w + 2 * c.border, r.h + 2 * c.border)
    }
    /// The window to focus or swap with when moving from `id` in `dir`.
    ///
    /// Tiled windows navigate among tiled windows first and only fall back to
    /// floating ones when nothing tiled lies in that direction; floating
    /// windows consider everything. Swaps (`tiled_only`) never involve
    /// floating windows.
    fn directional(&self, id: ClientId, dir: Direction, tiled_only: bool) -> Option<ClientId> {
        let m = &self.monitors[self.clients[&id].monitor.0];
        // Most-recently-focused first, so ties return to where you came from.
        let ordered = m
            .stack
            .iter()
            .chain(m.clients.iter().filter(|i| !m.stack.contains(i)))
            .copied()
            .filter(|i| {
                let c = &self.clients[i];
                *i != id
                    && self.visible(*i)
                    && c.focusable()
                    && !c.flags.dock
                    && !c.flags.desktop
            });
        let from = self.nav_rect(id);
        let pick = |tiled: Option<bool>| {
            let candidates: Vec<_> = ordered
                .clone()
                .filter(|i| tiled.is_none_or(|t| self.tiled(*i) == t))
                .map(|i| (i, self.nav_rect(i)))
                .collect();
            neighbor(from, dir, &candidates)
        };
        if tiled_only {
            return if self.tiled(id) { pick(Some(true)) } else { None };
        }
        if self.tiled(id) {
            pick(Some(true)).or_else(|| pick(Some(false)))
        } else {
            pick(None)
        }
    }
    fn action(&mut self, b: &Binding) -> Result<()> {
        let selected = self.selected_client();
        let action = Action::from(b.action.as_str());
        match action {
            Action::Spawn => {
                let argv = if b.command_is_shell {
                    vec!["sh".into(), "-c".into(), b.cmd.clone()]
                } else {
                    b.cmd.split_whitespace().map(str::to_owned).collect()
                };
                self.workers.send(Job::Spawn(argv));
            }
            Action::Shellcmd => {
                if !b.command_is_shell {
                    self.workers.send(Job::Shell(b.cmd.clone()));
                }
            }
            Action::Quit => self.running = false,
            Action::Reloadconfig => {
                self.reload()?;
                self.workers
                    .send(Job::Display(usize::MAX, self.settings.display.clone()));
            }
            Action::View => self.view(b.uint(), false)?,
            Action::Toggleview => self.view(b.uint(), true)?,
            Action::Tag => self.tag(b.uint(), false)?,
            Action::Toggletag => self.tag(b.uint(), true)?,
            Action::Swapview => {
                let m = &self.monitors[self.selected.0];
                self.view(m.views[m.selected_view ^ 1], false)?;
            }
            Action::Viewnext | Action::Viewprev => {
                let index = desktop(self.monitors[self.selected.0].mask()) as i32;
                let index = (index + if action == Action::Viewnext { 1 } else { 8 }) % 9;
                self.view(1 << index, false)?;
            }
            Action::Focusmon | Action::Tagmon => {
                let mon = MonitorId(
                    (self.selected.0 as i32 + b.int().signum())
                        .rem_euclid(self.monitors.len() as i32) as usize,
                );
                if action == Action::Tagmon {
                    if let Some(id) = selected {
                        self.move_monitor(id, mon, true)?;
                    }
                } else {
                    self.selected = mon;
                }
                self.focus(None)?;
            }
            Action::Setgaps => {
                let m = &mut self.monitors[self.selected.0];
                m.gap = if b.int() == 0 {
                    0
                } else {
                    (m.gap + b.int()).max(0)
                };
                self.arrange()?;
            }
            Action::Setmfact
            | Action::Incnmaster
            | Action::Setlayout
            | Action::Layoutnext
            | Action::Layoutprev
            | Action::Toggletiledir => {
                let m = &mut self.monitors[self.selected.0];
                match action {
                    Action::Setmfact => {
                        let value = if b.float() < 1. {
                            m.active.mfact + b.float()
                        } else {
                            b.float() - 1.
                        };
                        if (0.05..=0.95).contains(&value) {
                            m.active.mfact = value;
                        }
                    }
                    Action::Incnmaster => {
                        m.active.nmaster = (m.active.nmaster as i32 + b.int()).max(0) as usize
                    }
                    Action::Setlayout => {
                        m.active.layout = if b.layout == "float" || b.int() == 1 {
                            Layout::Float
                        } else {
                            Layout::Tile
                        }
                    }
                    Action::Toggletiledir => m.active.right = !m.active.right,
                    _ => {
                        let current = if m.active.layout == Layout::Float {
                            2
                        } else if m.active.right {
                            1
                        } else {
                            0
                        };
                        let next = (current + if action == Action::Layoutprev { 2 } else { 1 }) % 3;
                        m.active.layout = if next == 2 {
                            Layout::Float
                        } else {
                            Layout::Tile
                        };
                        m.active.right = next != 0;
                    }
                }
                m.save_tag();
                self.suppress_crossings(true)?;
                self.arrange()?;
                self.suppress_crossings(false)?;
            }
            Action::Restore => {
                if let Some(id) = self.minimized.last().copied() {
                    self.restore_client(id)?;
                }
            }
            _ => {
                if let Some(id) = selected {
                    match action {
                        Action::Killclient => self.close_client(id, self.last_user_time)?,
                        Action::Minimize => self.minimize_client(id)?,
                        Action::Togglefloating => self.toggle_floating(id)?,
                        Action::Togglefullscr => {
                            self.fullscreen(id, !self.clients[&id].flags.fullscreen)?
                        }
                        Action::Togglemaximize => {
                            if self.clients[&id].flags.fullscreen {
                                self.fullscreen(id, false)?;
                            }
                            let on = !self.clients[&id].maximized();
                            self.maximize(id, on, on)?;
                            self.suppress_crossings(true)?;
                            self.arrange()?;
                            self.suppress_crossings(false)?;
                        }
                        Action::Zoom => {
                            if !self.clients[&id].flags.floating
                                && self.monitors[self.selected.0].active.layout == Layout::Tile
                            {
                                let tiled: Vec<_> = self.monitors[self.selected.0]
                                    .clients
                                    .iter()
                                    .copied()
                                    .filter(|i| !self.clients[i].flags.floating && self.visible(*i))
                                    .collect();
                                let target = if tiled.first() == Some(&id) {
                                    tiled.get(1).copied()
                                } else {
                                    Some(id)
                                };
                                if let Some(target) = target {
                                    let list = &mut self.monitors[self.selected.0].clients;
                                    list.retain(|i| *i != target);
                                    list.insert(0, target);
                                    self.focus(Some(target))?;
                                    self.arrange()?;
                                }
                            }
                        }
                        Action::Focusstack => {
                            if !(self.config.lock_fullscreen && self.clients[&id].flags.fullscreen)
                            {
                                let ids: Vec<_> = self.monitors[self.selected.0]
                                    .clients
                                    .iter()
                                    .copied()
                                    .filter(|i| {
                                        self.visible(*i)
                                            && self.clients[i].focusable()
                                            && !self.clients[i].flags.dock
                                    })
                                    .collect();
                                if let Some(index) = ids.iter().position(|i| *i == id) {
                                    let next = (index as i32 + if b.int() < 0 { -1 } else { 1 })
                                        .rem_euclid(ids.len() as i32)
                                        as usize;
                                    self.focus(Some(ids[next]))?;
                                    self.restack()?;
                                }
                            }
                        }
                        Action::Focusup
                        | Action::Focusdown
                        | Action::Focusleft
                        | Action::Focusright => {
                            let dir = Direction::parse(&b.action[5..]);
                            if let Some(next) = dir.and_then(|d| self.directional(id, d, false)) {
                                self.focus(Some(next))?;
                                // Raise a floating target without letting the
                                // pointer's window reclaim focus.
                                self.suppress_crossings(true)?;
                                self.restack()?;
                                self.suppress_crossings(false)?;
                            }
                        }
                        Action::Swapup
                        | Action::Swapdown
                        | Action::Swapleft
                        | Action::Swapright => {
                            let dir = Direction::parse(&b.action[4..]);
                            if let Some(next) = dir.and_then(|d| self.directional(id, d, true)) {
                                self.swap_clients(id, next)?;
                            }
                        }
                        _ => {}
                    }
                }
            }
        }
        Ok(())
    }
    pub(super) fn keybinds(&self) -> Value {
        json!({"ok":true,"keybinds":self.config.keys.iter().map(|b|json!({"mod":config::modifier_names(b.mask()),"key":format_key(&b.key),"action":b.action,"description":describe_binding(b)})).collect::<Vec<_>>()})
    }
}
fn format_key(key: &str) -> String {
    match key {
        "Return" => "Enter".into(),
        "Escape" => "Esc".into(),
        "space" => "Space".into(),
        "period" => ".".into(),
        "comma" => ",".into(),
        "minus" => "-".into(),
        "equal" => "=".into(),
        _ if key.len() == 1 => key.to_uppercase(),
        _ => key.into(),
    }
}
fn describe_binding(b: &Binding) -> String {
    let a = b.action.as_str();
    let text = match a {
        "spawn" if b.command_is_shell => return format!("Run /bin/sh -c {}", b.cmd),
        "spawn" => match b.cmd.as_str() {
            "sadeshell --open-launcher" => "Open application launcher",
            "sadeshell --open-keybinds" => "Show keybinds",
            "sadeshell --open-emoji-picker" => "Open emoji picker",
            "sadeshell --open-window-picker" => "Search windows",
            "sadeshell --open-minimized-picker" => "Restore minimized window",
            "sadeshell --confirm-exit" => "Open exit menu",
            "wezterm" => "Open terminal",
            _ => return format!("Run {}", b.cmd),
        },
        "shellcmd" => match b.cmd.as_str() {
            "open-window-picker" => "Search windows",
            "open-minimized-picker" => "Restore minimized window",
            _ => "Open shell control",
        },
        "focusstack" => {
            if b.int() < 0 {
                "Focus previous window"
            } else {
                "Focus next window"
            }
        }
        "focusup" => "Focus window above",
        "focusdown" => "Focus window below",
        "focusleft" => "Focus window left",
        "focusright" => "Focus window right",
        "swapup" => "Swap window up",
        "swapdown" => "Swap window down",
        "swapleft" => "Swap window left",
        "swapright" => "Swap window right",
        "incnmaster" => {
            if b.int() > 0 {
                "Increase master count"
            } else {
                "Decrease master count"
            }
        }
        "setmfact" => {
            if b.float() > 0. {
                "Increase master area"
            } else {
                "Decrease master area"
            }
        }
        "zoom" => "Zoom focused window",
        "killclient" => "Close focused window",
        "minimize" => "Minimize focused window",
        "restore" => "Restore minimized window",
        "setlayout" => {
            if b.int() == 1 || b.layout == "float" {
                "Use floating layout"
            } else {
                "Use tile layout"
            }
        }
        "togglefullscr" => "Toggle fullscreen",
        "togglemaximize" => "Toggle maximize",
        "layoutnext" => "Next layout",
        "layoutprev" => "Previous layout",
        "togglefloating" => "Toggle floating",
        "view" | "toggleview" | "tag" | "toggletag" => {
            let prefix = match a {
                "view" => "View",
                "toggleview" => "Toggle view",
                "tag" => "Move window to",
                _ => "Toggle window on",
            };
            return if b.uint() == u32::MAX {
                format!("{prefix} all tags")
            } else if b.uint().is_power_of_two() && b.uint() < 512 {
                format!("{prefix} tag {}", b.uint().trailing_zeros() + 1)
            } else {
                format!("{prefix} tags")
            };
        }
        "swapview" => "Return to previous tag",
        "viewprev" => "View previous tag",
        "viewnext" => "View next tag",
        "focusmon" => {
            if b.int() < 0 {
                "Focus previous monitor"
            } else {
                "Focus next monitor"
            }
        }
        "tagmon" => {
            if b.int() < 0 {
                "Move window to previous monitor"
            } else {
                "Move window to next monitor"
            }
        }
        "setgaps" => {
            if b.int() > 0 {
                "Increase gaps"
            } else if b.int() < 0 {
                "Decrease gaps"
            } else {
                "Reset gaps"
            }
        }
        "reloadconfig" => "Reload config",
        "quit" => "Quit sadewm",
        _ => {
            if a.is_empty() {
                return "Run action".into();
            }
            let label = a.replace(['_', '-'], " ");
            let mut chars = label.chars();
            return chars.next().unwrap().to_uppercase().collect::<String>() + chars.as_str();
        }
    };
    text.into()
}
