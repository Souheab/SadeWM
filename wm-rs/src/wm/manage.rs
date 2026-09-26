use super::*;
use crate::render;
impl Wm {
    pub(super) fn manage(&mut self, win: u32) -> Result<()> {
        let id = ClientId(win);
        if self.clients.contains_key(&id) {
            return Ok(());
        }
        let attr = self.conn.get_window_attributes(win)?.reply()?;
        if attr.override_redirect {
            return self.update_dock(win);
        }
        let geom = self.conn.get_geometry(win)?.reply()?;
        let rect = Rect::new(
            i32::from(geom.x),
            i32::from(geom.y),
            i32::from(geom.width),
            i32::from(geom.height),
        );
        let mut c = Client::new(
            win,
            self.selected,
            rect,
            self.monitors[self.selected.0].mask(),
        );
        c.original_border = geom.border_width;
        c.border = self.config.border;
        c.mapped = attr.map_state != MapState::UNMAPPED;
        self.clients.insert(id, c);
        self.refresh_properties(id)?;
        let c = &self.clients[&id];
        let initial_states = self.get32(win, "_NET_WM_STATE");
        let wm_hints = self.prop32(win, AtomEnum::WM_HINTS.into(), AtomEnum::WM_HINTS.into());
        let iconic = self.get32(win, "WM_STATE").first() == Some(&3)
            || (wm_hints.len() >= 3 && wm_hints[0] & 2 != 0 && wm_hints[2] == 3);
        let parent = self
            .clients
            .get(&ClientId(c.transient))
            .map(|p| (p.monitor, p.tags));
        let mut c = self.clients.remove(&id).unwrap();
        if let Some((mon, tags)) = parent {
            c.monitor = mon;
            c.tags = tags;
            c.flags.floating = true;
        } else {
            let mut mask = 0;
            for rule in &self.config.rules {
                if (rule.class.is_empty() || c.class.contains(&rule.class))
                    && (rule.instance.is_empty() || c.instance.contains(&rule.instance))
                    && (rule.title.is_empty() || c.title.contains(&rule.title))
                {
                    c.flags.floating = rule.isfloating;
                    mask |= rule.tags_mask;
                    if rule.monitor >= 0 && (rule.monitor as usize) < self.monitors.len() {
                        c.monitor = MonitorId(rule.monitor as usize);
                    }
                }
            }
            c.tags = if mask & config::TAG_MASK != 0 {
                mask & config::TAG_MASK
            } else {
                self.monitors[c.monitor.0].mask()
            };
        }
        let types = self.get32(win, "_NET_WM_WINDOW_TYPE");
        self.set_type_flags(&mut c, &types);
        if c.hints.fixed || c.transient != 0 {
            c.flags.floating = true;
        }
        let area = self.monitors[c.monitor.0].work;
        c.geom.x = (c.geom.x.min(area.x + area.w - c.geom.w)).max(area.x);
        c.geom.y = (c.geom.y.min(area.y + area.h - c.geom.h)).max(area.y);
        if self.config.center_floating
            && c.flags.floating
            && !c.flags.dock
            && !c.flags.desktop
            && !c.hints.positioned
        {
            c.geom = c.geom.centered(area, TITLE_HEIGHT);
        }
        if let Some(desktop) = self.get32(win, "_NET_WM_DESKTOP").first() {
            if *desktop == u32::MAX {
                c.tags = config::TAG_MASK;
            } else if *desktop < 9 {
                c.tags = 1 << desktop;
            }
        }
        if c.flags.dock || c.flags.desktop {
            c.tags = config::TAG_MASK;
            c.border = 0;
        }
        let mon = c.monitor;
        let no_focus = c.user_time == Some(0);
        c.flags.minimized = iconic;
        self.clients.insert(id, c);
        self.order.push(id);
        self.monitors[mon.0].clients.push(id);
        self.monitors[mon.0].stack.insert(0, id);
        if no_focus && let Some(f) = self.focused {
            self.monitors[mon.0].stack.retain(|i| *i != f);
            self.monitors[mon.0].stack.insert(0, f);
        }
        self.conn.change_save_set(SetMode::INSERT, win)?;
        self.conn
            .configure_window(win, &ConfigureWindowAux::new().border_width(0))?;
        self.conn.change_window_attributes(
            win,
            &ChangeWindowAttributesAux::new().event_mask(
                EventMask::ENTER_WINDOW
                    | EventMask::FOCUS_CHANGE
                    | EventMask::PROPERTY_CHANGE
                    | EventMask::STRUCTURE_NOTIFY,
            ),
        )?;
        self.put32(win, "_NET_FRAME_EXTENTS", AtomEnum::CARDINAL, &[0, 0, 0, 0])?;
        self.grab_buttons(id)?;
        self.publish_membership()?;
        self.publish_desktop(id)?;
        for atom in initial_states {
            self.state_atom(id, atom, 1)?;
        }
        self.put32(
            win,
            "WM_STATE",
            self.a("WM_STATE"),
            &[if iconic { 3 } else { 1 }, 0],
        )?;
        self.publish_actions(id)?;
        self.recompute_work()?;
        if iconic {
            self.minimized.push(id);
            if self.clients[&id].mapped {
                self.clients.get_mut(&id).unwrap().ignore_unmap += 2;
                self.conn.unmap_window(win)?;
            }
        }
        self.suppress_crossings(true)?;
        self.arrange()?;
        if !iconic {
            self.conn.map_window(win)?;
            self.clients.get_mut(&id).unwrap().mapped = true;
            self.arrange()?;
        }
        if no_focus {
            self.focus_with_fallback(self.focused, false)?;
        } else if !iconic && self.clients[&id].focusable() {
            self.focus(Some(id))?;
        } else {
            self.focus(None)?;
        }
        self.suppress_crossings(false)?;
        self.publish_state(id)?;
        self.restack()?;
        Ok(())
    }
    pub(super) fn suppress_crossings(&self, grab: bool) -> Result<()> {
        if self.drag.is_none() {
            if grab {
                let _ = self
                    .conn
                    .grab_pointer(
                        false,
                        self.root,
                        EventMask::NO_EVENT,
                        GrabMode::ASYNC,
                        GrabMode::ASYNC,
                        x11rb::NONE,
                        x11rb::NONE,
                        x11rb::CURRENT_TIME,
                    )?
                    .reply();
            } else {
                self.conn.ungrab_pointer(x11rb::CURRENT_TIME)?;
            }
        }
        Ok(())
    }
    pub(super) fn refresh_properties(&mut self, id: ClientId) -> Result<()> {
        let win = id.0;
        let mut title = self.prop_text(win, self.a("_NET_WM_NAME"));
        if title.is_empty() {
            title = self.prop_text(win, AtomEnum::WM_NAME.into());
        }
        if title.is_empty() {
            title = "broken".into();
        }
        let class = self.prop_text(win, AtomEnum::WM_CLASS.into());
        let mut class = class.split('\0');
        let instance = class.next().unwrap_or_default().to_owned();
        let class = class.next().unwrap_or_default().to_owned();
        let hints = self.prop32(
            win,
            AtomEnum::WM_NORMAL_HINTS.into(),
            AtomEnum::WM_SIZE_HINTS.into(),
        );
        let wh = self.prop32(win, AtomEnum::WM_HINTS.into(), AtomEnum::WM_HINTS.into());
        let protocols = self.get32(win, "WM_PROTOCOLS");
        let transient = self
            .prop32(
                win,
                AtomEnum::WM_TRANSIENT_FOR.into(),
                AtomEnum::WINDOW.into(),
            )
            .first()
            .copied()
            .unwrap_or(0);
        let types = self.get32(win, "_NET_WM_WINDOW_TYPE");
        let mut strut = self.get32(win, "_NET_WM_STRUT_PARTIAL");
        if strut.len() < 12 {
            strut = self.get32(win, "_NET_WM_STRUT");
        }
        let user_window = self
            .get32(win, "_NET_WM_USER_TIME_WINDOW")
            .first()
            .copied()
            .unwrap_or(0);
        let user_time = self
            .get32(
                if user_window != 0 { user_window } else { win },
                "_NET_WM_USER_TIME",
            )
            .first()
            .copied();
        let fullscreen = self.get32(win, "_NET_WM_FULLSCREEN_MONITORS");
        let mut counter = self
            .get32(win, "_NET_WM_SYNC_REQUEST_COUNTER")
            .first()
            .copied()
            .unwrap_or(0);
        if !self.sync || !protocols.contains(&self.a("_NET_WM_SYNC_REQUEST")) {
            counter = 0;
        }
        let colormaps = self.get32(win, "WM_COLORMAP_WINDOWS");
        let take_focus = protocols.contains(&self.a("WM_TAKE_FOCUS"));
        let mut c = self.clients.remove(&id).unwrap();
        c.title = title;
        c.class = class;
        c.instance = instance;
        c.transient = transient;
        if transient != 0 {
            c.flags.floating = true;
        }
        c.protocols = protocols;
        c.flags.take_focus = take_focus;
        c.user_time = user_time;
        c.user_time_window = user_window;
        c.strut = strut;
        c.colormaps = colormaps;
        if fullscreen.len() >= 4 {
            let list = [fullscreen[0], fullscreen[1], fullscreen[2], fullscreen[3]];
            if list.iter().all(|v| (*v as usize) < self.monitors.len()) {
                c.fullscreen_monitors = Some(list);
            }
        }
        if c.sync_counter != counter {
            c.sync_counter = counter;
            c.sync_wait = None;
            c.sync_pending = None;
            if self.sync
                && counter != 0
                && let Ok(reply) = sync::query_counter(&self.conn, counter)?.reply()
            {
                c.sync_value =
                    ((reply.counter_value.hi as u64) << 32) | u64::from(reply.counter_value.lo);
            }
        }
        c.flags.input_no_focus = false;
        c.flags.urgent = false;
        c.group = 0;
        if !wh.is_empty() {
            c.flags.input_no_focus = wh[0] & 1 != 0 && wh.get(1) == Some(&0);
            c.flags.urgent = wh[0] & (1 << 8) != 0;
            c.group = if wh[0] & (1 << 6) != 0 {
                wh.get(8).copied().unwrap_or(0)
            } else {
                0
            };
        }
        let mut size = SizeHints::default();
        if hints.len() >= 15 {
            let flags = hints[0];
            size.positioned = flags & (1 | 4) != 0;
            let at = |i| hints.get(i).copied().unwrap_or(0) as i32;
            if flags & (1 << 4) != 0 {
                size.min = (at(5), at(6));
            }
            if flags & (1 << 5) != 0 {
                size.max = (at(7), at(8));
            }
            if flags & (1 << 6) != 0 {
                size.inc = (at(9), at(10));
            }
            if flags & (1 << 7) != 0 && at(11) > 0 && at(14) > 0 {
                size.aspect = (at(12) as f32 / at(11) as f32, at(13) as f32 / at(14) as f32);
            }
            size.base = if flags & (1 << 8) != 0 {
                (at(15), at(16))
            } else {
                size.min
            };
            if size.min == (0, 0) {
                size.min = size.base;
            }
            if flags & (1 << 9) != 0 {
                size.gravity = at(17) as u32;
            }
            size.fixed = size.min.0 > 0 && size.min.1 > 0 && size.min == size.max;
        }
        c.hints = size;
        self.set_type_flags(&mut c, &types);
        self.clients.insert(id, c);
        if user_window != 0 && user_window != win {
            let _ = self.conn.change_window_attributes(
                user_window,
                &ChangeWindowAttributesAux::new()
                    .event_mask(EventMask::PROPERTY_CHANGE | EventMask::STRUCTURE_NOTIFY),
            );
        }
        for w in &self.clients[&id].colormaps {
            let _ = self.conn.change_window_attributes(
                *w,
                &ChangeWindowAttributesAux::new().event_mask(EventMask::COLOR_MAP_CHANGE),
            );
        }
        Ok(())
    }
    fn set_type_flags(&self, c: &mut Client, types: &[u32]) {
        c.window_type = types
            .iter()
            .find(|a| {
                self.atoms
                    .iter()
                    .any(|(k, v)| k.starts_with("_NET_WM_WINDOW_TYPE_") && v == *a)
            })
            .copied()
            .unwrap_or(self.a("_NET_WM_WINDOW_TYPE_NORMAL"));
        c.flags.dock = c.window_type == self.a("_NET_WM_WINDOW_TYPE_DOCK");
        c.flags.desktop = c.window_type == self.a("_NET_WM_WINDOW_TYPE_DESKTOP");
        if types.iter().any(|a| {
            *a != self.a("_NET_WM_WINDOW_TYPE_NORMAL")
                && self
                    .atoms
                    .iter()
                    .any(|(k, v)| k.starts_with("_NET_WM_WINDOW_TYPE_") && v == a)
        }) {
            c.flags.floating = true;
        }
        c.flags.type_no_focus = [
            "DESKTOP",
            "DOCK",
            "SPLASH",
            "MENU",
            "TOOLTIP",
            "NOTIFICATION",
            "DND",
            "COMBO",
            "DROPDOWN_MENU",
            "POPUP_MENU",
        ]
        .iter()
        .any(|suffix| c.window_type == self.a(&format!("_NET_WM_WINDOW_TYPE_{suffix}")));
        if c.flags.type_no_focus {
            c.flags.skip_pager = true;
            c.flags.skip_taskbar = true;
        }
        if c.flags.dock || c.flags.desktop {
            c.tags = config::TAG_MASK;
            c.border = 0;
        }
    }
    pub(super) fn unmanage(&mut self, id: ClientId, destroyed: bool, shutdown: bool) -> Result<()> {
        let Some(mut c) = self.clients.remove(&id) else {
            return Ok(());
        };
        if self.drag.as_ref().is_some_and(|d| d.id == id) {
            self.drag = None;
            self.conn.ungrab_pointer(x11rb::CURRENT_TIME)?;
            self.conn.ungrab_keyboard(x11rb::CURRENT_TIME)?;
        }
        if c.frame != 0 {
            self.frames.remove(&c.frame);
            self.titles.remove(&c.titlebar);
            if !destroyed {
                self.conn
                    .reparent_window(id.0, self.root, c.geom.x as i16, c.geom.y as i16)?;
            }
            self.conn.destroy_window(c.frame)?;
            c.frame = 0;
        }
        if c.border_window != 0 {
            self.conn.destroy_window(c.border_window)?;
        }
        if !destroyed {
            self.conn
                .ungrab_button(ButtonIndex::ANY, id.0, ModMask::ANY)?;
            self.conn.change_save_set(SetMode::DELETE, id.0)?;
            self.conn.configure_window(
                id.0,
                &ConfigureWindowAux::new()
                    .x(c.geom.x)
                    .y(c.geom.y)
                    .border_width(u32::from(c.original_border)),
            )?;
            if shutdown {
                if !c.flags.minimized {
                    self.conn.map_window(id.0)?;
                }
            } else {
                for name in [
                    "_NET_WM_STATE",
                    "_NET_WM_DESKTOP",
                    "_NET_WM_ALLOWED_ACTIONS",
                    "_NET_FRAME_EXTENTS",
                ] {
                    self.conn.delete_property(id.0, self.a(name))?;
                }
                self.put32(id.0, "WM_STATE", self.a("WM_STATE"), &[0, 0])?;
            }
        }
        self.order.retain(|i| *i != id);
        self.minimized.retain(|i| *i != id);
        for m in &mut self.monitors {
            m.clients.retain(|i| *i != id);
            m.stack.retain(|i| *i != id);
            if m.selected == Some(id) {
                m.selected = None;
            }
        }
        if self.focused == Some(id) {
            self.focused = None;
        }
        self.stack_dirty = true;
        if !shutdown {
            self.publish_membership()?;
            self.recompute_work()?;
            self.focus(None)?;
            self.arrange()?;
        }
        Ok(())
    }
    pub(super) fn frame(&mut self, id: ClientId, wanted: bool) -> Result<()> {
        let c = self.clients[&id].clone();
        if wanted && c.frame == 0 {
            if c.border_window != 0 {
                self.conn.destroy_window(c.border_window)?;
                self.clients.get_mut(&id).unwrap().border_window = 0;
            }
            let frame = self.conn.generate_id()?;
            let title = self.conn.generate_id()?;
            let color = self.native_pixel(&self.config.title.bg);
            self.conn.create_window(
                self.screen.root_depth,
                frame,
                self.root,
                c.geom.x as i16,
                (c.geom.y - TITLE_HEIGHT) as i16,
                c.geom.w.max(1) as u16,
                (c.geom.h + TITLE_HEIGHT).clamp(1, 65535) as u16,
                0,
                WindowClass::INPUT_OUTPUT,
                self.screen.root_visual,
                &CreateWindowAux::new()
                    .background_pixel(color)
                    .override_redirect(1)
                    .event_mask(EventMask::SUBSTRUCTURE_REDIRECT | EventMask::SUBSTRUCTURE_NOTIFY),
            )?;
            self.conn.create_window(
                self.screen.root_depth,
                title,
                frame,
                0,
                0,
                c.geom.w.max(1) as u16,
                TITLE_HEIGHT as u16,
                0,
                WindowClass::INPUT_OUTPUT,
                self.screen.root_visual,
                &CreateWindowAux::new()
                    .background_pixel(color)
                    .override_redirect(1)
                    .event_mask(
                        EventMask::EXPOSURE
                            | EventMask::BUTTON_PRESS
                            | EventMask::BUTTON_RELEASE
                            | EventMask::POINTER_MOTION
                            | EventMask::LEAVE_WINDOW
                            | EventMask::ENTER_WINDOW,
                    ),
            )?;
            self.expect_reparent(id)?;
            self.conn
                .configure_window(id.0, &ConfigureWindowAux::new().border_width(0))?;
            self.conn
                .reparent_window(id.0, frame, 0, TITLE_HEIGHT as i16)?;
            let c = self.clients.get_mut(&id).unwrap();
            c.frame = frame;
            c.titlebar = title;
            c.shape_geometry = None;
            c.border = 0;
            self.frames.insert(frame, id);
            self.titles.insert(title, id);
            self.stack_dirty = true;
            self.put32(
                id.0,
                "_NET_FRAME_EXTENTS",
                AtomEnum::CARDINAL,
                &[0, 0, TITLE_HEIGHT as u32, 0],
            )?;
            self.conn.map_window(title)?;
            if !self.clients[&id].flags.minimized {
                self.conn.map_window(frame)?;
            }
            self.forward_opacity(id)?;
            self.draw_title(id)?;
        } else if !wanted && c.frame != 0 {
            self.expect_reparent(id)?;
            self.conn
                .reparent_window(id.0, self.root, c.geom.x as i16, c.geom.y as i16)?;
            self.conn.destroy_window(c.frame)?;
            self.frames.remove(&c.frame);
            self.titles.remove(&c.titlebar);
            let c = self.clients.get_mut(&id).unwrap();
            c.frame = 0;
            c.titlebar = 0;
            self.stack_dirty = true;
            self.put32(
                id.0,
                "_NET_FRAME_EXTENTS",
                AtomEnum::CARDINAL,
                &[0, 0, 0, 0],
            )?;
        }
        Ok(())
    }
    fn expect_reparent(&mut self, id: ClientId) -> Result<()> {
        if self.conn.get_window_attributes(id.0)?.reply()?.map_state != MapState::UNMAPPED {
            self.clients.get_mut(&id).unwrap().ignore_unmap += 2;
        }
        Ok(())
    }
    pub(super) fn draw_title(&mut self, id: ClientId) -> Result<()> {
        let c = &self.clients[&id];
        if c.titlebar == 0 {
            return Ok(());
        }
        let (title, frame, w, h, shaded) =
            (c.titlebar, c.frame, c.geom.w, c.geom.h, c.flags.shaded);
        let image = self.renderer.titlebar(
            w.max(1) as u32,
            &c.title,
            self.focused == Some(id),
            c.flags.above,
            c.hover,
            &self.config.title,
        )?;
        self.upload(title, w, 28, image.data())?;
        if self.shape && self.clients[&id].shape_geometry != Some((w, h, shaded)) {
            self.clients.get_mut(&id).unwrap().shape_geometry = Some((w, h, shaded));
            let w = w.clamp(1, 65535);
            let mut rects = Vec::new();
            for y in 0..6 {
                let dy = 5.5 - y as f32;
                let inset = (6. - (36. - dy * dy).sqrt()).ceil() as i32;
                rects.push(Rectangle {
                    x: inset as i16,
                    y: y as i16,
                    width: (w - 2 * inset).max(1) as u16,
                    height: 1,
                });
            }
            rects.push(Rectangle {
                x: 0,
                y: 6,
                width: w as u16,
                height: 22,
            });
            shape::rectangles(
                &self.conn,
                shape::SO::SET,
                shape::SK::BOUNDING,
                ClipOrdering::UNSORTED,
                title,
                0,
                0,
                &rects,
            )?;
            if !shaded {
                rects.push(Rectangle {
                    x: 0,
                    y: 28,
                    width: w as u16,
                    height: h.clamp(1, 65507) as u16,
                });
            }
            shape::rectangles(
                &self.conn,
                shape::SO::SET,
                shape::SK::BOUNDING,
                ClipOrdering::UNSORTED,
                frame,
                0,
                0,
                &rects,
            )?;
        }
        Ok(())
    }
    pub(super) fn upload(&self, drawable: u32, w: i32, h: i32, rgba: &[u8]) -> Result<()> {
        let visual = self
            .screen
            .allowed_depths
            .iter()
            .flat_map(|d| &d.visuals)
            .find(|v| v.visual_id == self.screen.root_visual)
            .context("root visual missing")?;
        let format = self
            .conn
            .setup()
            .pixmap_formats
            .iter()
            .find(|f| f.depth == self.screen.root_depth)
            .context("root pixel format missing")?;
        let (data, stride) = render::encode_pixels(
            rgba,
            w as usize,
            h as usize,
            format.bits_per_pixel,
            format.scanline_pad,
            self.conn.setup().image_byte_order == ImageOrder::LSB_FIRST,
            [visual.red_mask, visual.green_mask, visual.blue_mask],
        )?;
        let gc = self.conn.generate_id()?;
        self.conn.create_gc(gc, drawable, &CreateGCAux::new())?;
        let result = (|| -> Result<()> {
            let max = self.conn.maximum_request_bytes().saturating_sub(32);
            anyhow::ensure!(stride <= max, "image row exceeds X request limit");
            let rows = (max / stride).max(1);
            for start in (0..h as usize).step_by(rows) {
                let count = rows.min(h as usize - start);
                self.conn.put_image(
                    ImageFormat::Z_PIXMAP,
                    drawable,
                    gc,
                    w as u16,
                    count as u16,
                    0,
                    start as i16,
                    0,
                    self.screen.root_depth,
                    &data[start * stride..(start + count) * stride],
                )?;
            }
            Ok(())
        })();
        let _ = self.conn.free_gc(gc);
        result
    }
    pub(super) fn border(&mut self, id: ClientId, wanted: bool) -> Result<()> {
        let c = self.clients[&id].clone();
        if !wanted || self.config.border == 0 {
            if c.border_window != 0 {
                self.conn.destroy_window(c.border_window)?;
                self.clients.get_mut(&id).unwrap().border_window = 0;
            }
            return Ok(());
        }
        let bw = self.config.border;
        let r = c.geom;
        let color = self.native_pixel(if self.focused == Some(id) {
            &self.config.selected_border
        } else {
            &self.config.normal_border
        });
        let win = if c.border_window != 0 {
            c.border_window
        } else {
            let win = self.conn.generate_id()?;
            self.conn.create_window(
                self.screen.root_depth,
                win,
                self.root,
                0,
                0,
                1,
                1,
                0,
                WindowClass::INPUT_OUTPUT,
                self.screen.root_visual,
                &CreateWindowAux::new()
                    .override_redirect(1)
                    .background_pixel(color),
            )?;
            self.clients.get_mut(&id).unwrap().border_window = win;
            win
        };
        let w = (r.w + 2 * bw).clamp(1, 65535);
        let h = (r.h + 2 * bw).clamp(1, 65535);
        self.conn.configure_window(
            win,
            &ConfigureWindowAux::new()
                .x(r.x - bw)
                .y(r.y - bw)
                .width(w as u32)
                .height(h as u32)
                .sibling(id.0)
                .stack_mode(StackMode::BELOW),
        )?;
        if self.shape {
            let b = bw as u16;
            let rects = [
                Rectangle {
                    x: 0,
                    y: 0,
                    width: w as u16,
                    height: b,
                },
                Rectangle {
                    x: 0,
                    y: (h - bw) as i16,
                    width: w as u16,
                    height: b,
                },
                Rectangle {
                    x: 0,
                    y: bw as i16,
                    width: b,
                    height: r.h.max(1) as u16,
                },
                Rectangle {
                    x: (w - bw) as i16,
                    y: bw as i16,
                    width: b,
                    height: r.h.max(1) as u16,
                },
            ];
            shape::rectangles(
                &self.conn,
                shape::SO::SET,
                shape::SK::BOUNDING,
                ClipOrdering::UNSORTED,
                win,
                0,
                0,
                &rects,
            )?;
        }
        self.conn.change_window_attributes(
            win,
            &ChangeWindowAttributesAux::new().background_pixel(color),
        )?;
        self.conn.clear_area(false, win, 0, 0, 0, 0)?;
        if self.visible(id) && c.mapped {
            self.conn.map_window(win)?;
        } else {
            self.conn.unmap_window(win)?;
        }
        Ok(())
    }
    pub(super) fn set_wallpaper(&mut self) -> Result<()> {
        let Some(home) = std::env::var_os("HOME") else {
            return Ok(());
        };
        let path = PathBuf::from(home).join(".config/sade/wp.jpg");
        if !path.exists() {
            return Ok(());
        }
        let img = match image::open(&path) {
            Ok(i) => i,
            Err(e) => {
                self.logger.debug(&format!("wallpaper: {e}"));
                return Ok(());
            }
        };
        let (w, h) = (
            u32::from(self.screen.width_in_pixels),
            u32::from(self.screen.height_in_pixels),
        );
        let image = render::cover_image(&img.to_rgba8(), w, h);
        let pixmap = self.conn.generate_id()?;
        self.conn.create_pixmap(
            self.screen.root_depth,
            pixmap,
            self.root,
            w as u16,
            h as u16,
        )?;
        if let Err(e) = self.upload(pixmap, w as i32, h as i32, image.as_raw()) {
            let _ = self.conn.free_pixmap(pixmap);
            return Err(e);
        }
        self.conn.change_window_attributes(
            self.root,
            &ChangeWindowAttributesAux::new().background_pixmap(pixmap),
        )?;
        for name in ["_XROOTPMAP_ID", "ESETROOT_PMAP_ID"] {
            self.put32(self.root, name, AtomEnum::PIXMAP, &[pixmap])?;
        }
        self.conn.clear_area(false, self.root, 0, 0, 0, 0)?;
        if self.wallpaper != 0 {
            self.conn.free_pixmap(self.wallpaper)?;
        }
        self.wallpaper = pixmap;
        Ok(())
    }
}
