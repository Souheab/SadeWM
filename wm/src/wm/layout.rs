use super::*;
impl Wm {
    pub(super) fn refresh_monitors(&mut self) -> Result<()> {
        if let Ok(g) = self.conn.get_geometry(self.root)?.reply() {
            self.screen.width_in_pixels = g.width;
            self.screen.height_in_pixels = g.height;
        }
        self.xinerama = xinerama::is_active(&self.conn)
            .ok()
            .and_then(|c| c.reply().ok())
            .is_some_and(|r| r.state != 0);
        let mut rects = if self.xinerama {
            xinerama::query_screens(&self.conn)
                .ok()
                .and_then(|c| c.reply().ok())
                .map(|r| {
                    r.screen_info
                        .into_iter()
                        .map(|s| {
                            Rect::new(
                                i32::from(s.x_org),
                                i32::from(s.y_org),
                                i32::from(s.width),
                                i32::from(s.height),
                            )
                        })
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default()
        } else {
            Vec::new()
        };
        rects.retain(|r| r.w > 0 && r.h > 0);
        rects.sort_by_key(|r| (r.y, r.x));
        rects.dedup();
        if rects.is_empty() {
            rects.push(Rect::new(
                0,
                0,
                self.screen.width_in_pixels.into(),
                self.screen.height_in_pixels.into(),
            ));
        }
        let changed = self.monitors.len() != rects.len()
            || self.monitors.iter().zip(&rects).any(|(m, r)| m.rect != *r);
        let old = self.monitors.clone();
        self.monitors = rects
            .into_iter()
            .enumerate()
            .map(|(i, r)| {
                let mut m = old
                    .get(i)
                    .cloned()
                    .unwrap_or_else(|| Monitor::new(i, r, &self.config));
                m.rect = r;
                m.work = r;
                m.clients.clear();
                m.stack.clear();
                m
            })
            .collect();
        if self.selected.0 >= self.monitors.len() {
            self.selected = MonitorId(0);
        }
        for id in old.iter().flat_map(|m| m.clients.iter()).copied() {
            let c = &self.clients[&id];
            let mon = if changed {
                self.rect_monitor(c.geom)
            } else {
                c.monitor
            };
            self.clients.get_mut(&id).unwrap().monitor = mon;
            self.monitors[mon.0].clients.push(id);
        }
        for id in old.iter().flat_map(|m| m.stack.iter()).copied() {
            let mon = self.clients[&id].monitor;
            self.monitors[mon.0].stack.push(id);
        }
        for m in &mut self.monitors {
            if !m.selected.is_some_and(|id| m.clients.contains(&id)) {
                m.selected = None;
            }
        }
        self.recompute_work()?;
        self.publish_supported()?;
        self.publish_desktops()?;
        if !self.clients.is_empty() {
            self.arrange()?;
            self.focus(None)?;
        }
        Ok(())
    }
    pub(super) fn recompute_work(&mut self) -> Result<()> {
        let struts: Vec<_> = self
            .docks
            .values()
            .chain(
                self.clients
                    .values()
                    .filter(|c| !c.strut.is_empty())
                    .map(|c| &c.strut),
            )
            .cloned()
            .collect();
        let root = Rect::new(
            0,
            0,
            self.screen.width_in_pixels.into(),
            self.screen.height_in_pixels.into(),
        );
        for m in &mut self.monitors {
            m.work = workarea(m.rect, root, self.config.top, self.config.bottom, &struts);
        }
        self.publish_workarea()
    }
    pub(super) fn arrange(&mut self) -> Result<()> {
        self.arrange_windows()?;
        self.restack()
    }
    pub(super) fn arrange_windows(&mut self) -> Result<()> {
        let ids = self.order.clone();
        for id in &ids {
            let c = &self.clients[id];
            let free =
                c.flags.floating || self.monitors[c.monitor.0].active.layout == Layout::Float;
            let ordinary =
                !c.flags.fullscreen && !c.flags.shaded && !c.flags.max_h && !c.flags.max_v;
            if ordinary && free != c.was_free {
                if free {
                    self.resize_now(*id, c.floating_geom)?;
                } else {
                    let c = self.clients.get_mut(id).unwrap();
                    c.floating_geom = c.geom;
                }
            }
            if !self.clients[id].flags.fullscreen {
                self.clients.get_mut(id).unwrap().was_free = free;
            }
            let title = self.decoration_extents(&self.clients[id]).top != 0;
            self.frame(*id, title)?;
            let c = self.clients.get_mut(id).unwrap();
            c.border = if !free && !c.flags.fullscreen && !c.flags.dock && !c.flags.desktop {
                self.config.border
            } else {
                0
            };
            self.grab_buttons(*id)?;
        }
        let mut positions = Vec::new();
        for m in &self.monitors {
            if m.active.layout == Layout::Tile {
                let rows: Vec<_> = m
                    .clients
                    .iter()
                    .filter_map(|id| {
                        let c = &self.clients[id];
                        (!c.flags.floating && self.visible(*id)).then_some((*id, c.border))
                    })
                    .collect();
                positions.extend(tile(m, &rows));
            }
        }
        for (id, r) in positions {
            let c = self.clients.get_mut(&id).unwrap();
            if c.flags.max_h || c.flags.max_v {
                // Reserve the tile slot and track its current geometry without
                // briefly resizing the maximized window back into that slot.
                c.normal = Some((r, false));
            } else {
                self.resize(id, r, false)?;
            }
        }
        for id in ids {
            self.reconcile_mapping(id)?;
            let c = self.clients[&id].clone();
            let visible = self.visible(id);
            if visible {
                if c.flags.fullscreen {
                    let r = self.fullscreen_rect(id);
                    self.resize(id, r, false)?;
                } else if c.flags.max_h || c.flags.max_v {
                    self.apply_maximized(id)?;
                } else {
                    self.resize(id, c.geom, false)?;
                }
                let c = &self.clients[&id];
                if c.frame != 0 {
                    self.conn.map_window(c.frame)?;
                    self.conn.map_window(c.titlebar)?;
                }
            } else {
                let c = &self.clients[&id];
                if c.frame != 0 {
                    self.conn.configure_window(
                        c.frame,
                        &ConfigureWindowAux::new().x(-2 * (c.geom.w + 2 * c.border)),
                    )?;
                } else if !c.flags.minimized {
                    self.conn.configure_window(
                        id.0,
                        &ConfigureWindowAux::new().x(-2 * (c.geom.w + 2 * c.border)),
                    )?;
                }
            }
            self.border(id, c.border > 0)?;
            self.publish_state(id)?;
            self.publish_actions(id)?;
        }
        Ok(())
    }
    pub(super) fn resize(&mut self, id: ClientId, mut rect: Rect, interactive: bool) -> Result<()> {
        let c = &self.clients[&id];
        rect.w = rect.w.clamp(3, 65535 - c.extents.left - c.extents.right);
        rect.h = rect.h.clamp(3, 65535 - c.extents.top - c.extents.bottom);
        // Fullscreen fills the monitor; mpv handles letterboxing inside it.
        if !c.flags.fullscreen
            && (c.class == "mpv" || c.instance == "mpv")
            && (self.config.resize_hints
                || c.flags.floating
                || self.monitors[c.monitor.0].active.layout == Layout::Float)
        {
            rect = c.hints.apply(rect);
        }
        let c = self.clients.get_mut(&id).unwrap();
        if interactive
            && self.sync
            && c.sync_counter != 0
            && (rect.w != c.geom.w || rect.h != c.geom.h)
        {
            if c.sync_wait.is_some() {
                c.sync_pending = Some(rect);
                return Ok(());
            }
            c.sync_value = c.sync_value.wrapping_add(1);
            c.sync_wait = Some(Instant::now());
            let value = c.sync_value;
            self.send_protocol(
                id,
                "_NET_WM_SYNC_REQUEST",
                self.current_time(),
                value as u32,
                (value >> 32) as u32,
            )?;
        }
        self.resize_now(id, rect)
    }
    pub(super) fn resize_now(&mut self, id: ClientId, rect: Rect) -> Result<()> {
        let free = self.clients[&id].flags.floating
            || self.monitors[self.clients[&id].monitor.0].active.layout == Layout::Float;
        let c = self.clients.get_mut(&id).unwrap();
        let changed = c.geom != rect;
        if changed {
            c.old = c.geom;
            c.geom = rect;
        }
        if free && !c.flags.fullscreen && !c.flags.shaded && !c.flags.max_h && !c.flags.max_v {
            c.floating_geom = rect;
        }
        let c = c.clone();
        let r = rect;
        if c.frame != 0 {
            let outer = c.extents.outer(r, c.flags.shaded && !c.flags.fullscreen);
            self.conn.configure_window(
                id.0,
                &ConfigureWindowAux::new()
                    .x(c.extents.left)
                    .y(c.extents.top)
                    .width(r.w as u32)
                    .height(r.h as u32)
                    .border_width(0),
            )?;
            self.conn.configure_window(
                c.frame,
                &ConfigureWindowAux::new()
                    .x(outer.x)
                    .y(outer.y)
                    .width(outer.w.clamp(1, 65535) as u32)
                    .height(outer.h.clamp(1, 65535) as u32),
            )?;
            self.conn.configure_window(
                c.titlebar,
                &ConfigureWindowAux::new()
                    .x(c.extents.left)
                    .y(c.extents.top - TITLE_HEIGHT)
                    .width(r.w as u32)
                    .height(TITLE_HEIGHT as u32),
            )?;
            if changed || c.shape_geometry != Some((r.w, r.h, c.flags.shaded, c.extents)) {
                self.draw_title(id)?;
            }
        } else {
            self.conn.configure_window(
                id.0,
                &ConfigureWindowAux::new()
                    .x(r.x)
                    .y(r.y)
                    .width(r.w as u32)
                    .height(r.h as u32)
                    .border_width(0),
            )?;
        }
        if changed {
            self.configure_notify(id)?;
        }
        self.border(id, c.border > 0)?;
        Ok(())
    }
    pub(super) fn configure_notify(&self, id: ClientId) -> Result<()> {
        let c = &self.clients[&id];
        self.conn.send_event(
            false,
            id.0,
            EventMask::STRUCTURE_NOTIFY,
            ConfigureNotifyEvent {
                response_type: CONFIGURE_NOTIFY_EVENT,
                sequence: 0,
                event: id.0,
                window: id.0,
                above_sibling: 0,
                x: c.geom.x as i16,
                y: c.geom.y as i16,
                width: c.geom.w as u16,
                height: c.geom.h as u16,
                border_width: c.border as u16,
                override_redirect: false,
            },
        )?;
        Ok(())
    }
    pub(super) fn focus(&mut self, want: Option<ClientId>) -> Result<()> {
        self.focus_with_fallback(want, true)
    }
    pub(super) fn focus_with_fallback(
        &mut self,
        want: Option<ClientId>,
        fallback: bool,
    ) -> Result<()> {
        let timestamp = if self.event_time != 0 {
            self.event_time
        } else {
            self.server_time()?
        };
        let mut target = want.filter(|id| self.visible(*id) && self.clients[id].focusable());
        if let Some(id) = target {
            let c = &self.clients[&id];
            if let Some(modal) = self.monitors[c.monitor.0].stack.iter().copied().find(|i| {
                *i != id
                    && self.visible(*i)
                    && self.clients[i].flags.modal
                    && (self.clients[i].transient == id.0
                        || (c.group != 0 && self.clients[i].group == c.group))
            }) {
                target = Some(modal);
            }
        }
        if target.is_none() && fallback {
            target = self.monitors[self.selected.0]
                .stack
                .iter()
                .copied()
                .find(|id| self.visible(*id) && self.clients[id].focusable());
        }
        let previous = self.focused;
        self.focused = target;
        if let Some(id) = target {
            let c = self.clients.get_mut(&id).unwrap();
            self.selected = c.monitor;
            c.flags.urgent = false;
            c.flags.attention = false;
            let m = &mut self.monitors[self.selected.0];
            m.selected = Some(id);
            m.stack.retain(|i| *i != id);
            m.stack.insert(0, id);
            let c = &self.clients[&id];
            let set_focus = previous != target || !self.input_focus_within(id)?;
            if set_focus && c.mapped && !c.flags.input_no_focus && !c.flags.type_no_focus {
                self.conn
                    .set_input_focus(InputFocus::POINTER_ROOT, id.0, timestamp)?;
            }
            if set_focus && c.mapped && c.flags.take_focus {
                self.send_protocol(id, "WM_TAKE_FOCUS", timestamp, 0, 0)?;
            }
            for w in c
                .colormaps
                .iter()
                .rev()
                .copied()
                .chain(std::iter::once(id.0))
            {
                if let Ok(attr) = self.conn.get_window_attributes(w)?.reply()
                    && attr.colormap != 0
                {
                    self.conn.install_colormap(attr.colormap)?;
                }
            }
            self.put32(self.root, "_NET_ACTIVE_WINDOW", AtomEnum::WINDOW, &[id.0])?;
            self.set_urgent(id, false)?;
            self.grab_buttons(id)?;
            self.publish_state(id)?;
            self.draw_title(id)?;
            self.border(id, self.clients[&id].border > 0)?;
        } else {
            self.monitors[self.selected.0].selected = None;
            self.conn
                .set_input_focus(InputFocus::POINTER_ROOT, self.root, timestamp)?;
            self.put32(self.root, "_NET_ACTIVE_WINDOW", AtomEnum::WINDOW, &[0])?;
        }
        if let Some(id) = previous.filter(|i| Some(*i) != target && self.clients.contains_key(i)) {
            self.grab_buttons(id)?;
            self.publish_state(id)?;
            self.draw_title(id)?;
            self.border(id, self.clients[&id].border > 0)?;
        }
        self.stack_dirty = true;
        self.publish_current_desktop()?;
        Ok(())
    }
    pub(super) fn restack(&mut self) -> Result<()> {
        let mut ids: Vec<_> = self
            .monitors
            .iter()
            .flat_map(|m| m.stack.iter().rev().copied())
            .filter(|id| self.visible(*id))
            .collect();
        let layer = |c: &Client| {
            if c.flags.desktop {
                0
            } else if c.flags.fullscreen && self.focused == Some(c.id) {
                4
            } else if c.flags.above || c.flags.dock {
                3
            } else if c.flags.below {
                1
            } else {
                2
            }
        };
        ids.sort_by_key(|id| {
            let c = &self.clients[id];
            let own = layer(c);
            let parent = self
                .clients
                .get(&ClientId(c.transient))
                .map(&layer)
                .unwrap_or(own);
            (
                own.max(parent),
                if c.flags.modal {
                    2
                } else if c.transient != 0 {
                    1
                } else {
                    0
                },
            )
        });
        let ceiling = self.docks.keys().min().copied();
        let mut actual = self.conn.query_tree(self.root)?.reply()?.children;
        let mut anchor = ceiling;
        // Establish the top first, then tuck each lower window underneath it.
        // An already correct stack generates no X Configure requests.
        for id in ids.into_iter().rev() {
            let c = &self.clients[&id];
            let win = c.stack_window();
            let pos = actual.iter().position(|w| *w == win);
            let below_anchor = anchor.and_then(|a| actual.iter().position(|w| *w == a));
            let correct = match (pos, below_anchor) {
                (Some(p), Some(a)) => p + 1 == a,
                (Some(p), None) => p + 1 == actual.len(),
                _ => false,
            };
            if !correct {
                let aux = if let Some(a) = anchor {
                    ConfigureWindowAux::new()
                        .sibling(a)
                        .stack_mode(StackMode::BELOW)
                } else {
                    ConfigureWindowAux::new().stack_mode(StackMode::ABOVE)
                };
                self.conn.configure_window(win, &aux)?;
                actual.retain(|w| *w != win);
                let index = anchor
                    .and_then(|a| actual.iter().position(|w| *w == a))
                    .unwrap_or(actual.len());
                actual.insert(index, win);
                self.stack_dirty = true;
            }
            anchor = Some(win);
            if c.border_window != 0 {
                let border = c.border_window;
                let p = actual.iter().position(|w| *w == border);
                let a = actual.iter().position(|w| *w == win).unwrap();
                if !p.is_some_and(|p| p + 1 == a) {
                    self.conn.configure_window(
                        border,
                        &ConfigureWindowAux::new()
                            .sibling(win)
                            .stack_mode(StackMode::BELOW),
                    )?;
                    actual.retain(|w| *w != border);
                    let index = actual.iter().position(|w| *w == win).unwrap();
                    actual.insert(index, border);
                    self.stack_dirty = true;
                }
                anchor = Some(border);
            }
        }
        Ok(())
    }
    pub(super) fn input_focus_within(&self, id: ClientId) -> Result<bool> {
        let mut window = self.conn.get_input_focus()?.reply()?.focus;
        while window != 0 && window != 1 && window != self.root && window != id.0 {
            let Ok(tree) = self.conn.query_tree(window)?.reply() else {
                break;
            };
            if tree.parent == window {
                break;
            }
            window = tree.parent;
        }
        Ok(window == id.0)
    }
    pub(super) fn view(&mut self, mask: u32, toggle: bool) -> Result<()> {
        let m = &mut self.monitors[self.selected.0];
        let mask = mask & config::TAG_MASK;
        if toggle {
            let next = m.mask() ^ mask;
            if next == 0 {
                return Ok(());
            }
            m.views[m.selected_view] = next;
            m.apply_tag();
        } else {
            if mask == m.mask() {
                return Ok(());
            }
            m.selected_view ^= 1;
            if mask != 0 {
                m.views[m.selected_view] = mask;
                m.apply_tag();
            }
        }
        self.suppress_crossings(true)?;
        self.focus(None)?;
        self.arrange()?;
        self.publish_current_desktop()?;
        self.publish_workarea()?;
        self.suppress_crossings(false)
    }
    pub(super) fn tag(&mut self, mask: u32, toggle: bool) -> Result<()> {
        if let Some(id) = self.selected_client() {
            let mask = mask & config::TAG_MASK;
            let c = self.clients.get_mut(&id).unwrap();
            let next = if toggle { c.tags ^ mask } else { mask };
            if next != 0 {
                c.tags = next;
                self.publish_desktop(id)?;
                self.focus(None)?;
                self.arrange()?;
            }
        }
        Ok(())
    }
    pub(super) fn minimize_client(&mut self, id: ClientId) -> Result<()> {
        let c = self.clients.get_mut(&id).unwrap();
        if c.flags.minimized || c.flags.dock || c.flags.desktop {
            return Ok(());
        }
        c.flags.minimized = true;
        self.minimized.push(id);
        c.ignore_unmap += 2;
        c.mapped = false;
        self.conn.unmap_window(id.0)?;
        if c.frame != 0 {
            self.conn.unmap_window(c.frame)?;
        }
        self.put32(id.0, "WM_STATE", self.a("WM_STATE"), &[3, 0])?;
        self.publish_state(id)?;
        self.focus(None)?;
        self.arrange()
    }
    pub(super) fn restore_client(&mut self, id: ClientId) -> Result<()> {
        let c = self.clients.get_mut(&id).unwrap();
        if !c.flags.minimized {
            return Ok(());
        }
        c.flags.minimized = false;
        self.minimized.retain(|i| *i != id);
        self.put32(id.0, "WM_STATE", self.a("WM_STATE"), &[1, 0])?;
        self.suppress_crossings(true)?;
        self.arrange_windows()?;
        self.focus(Some(id))?;
        self.restack()?;
        self.suppress_crossings(false)
    }
    pub(super) fn fullscreen_rect(&self, id: ClientId) -> Rect {
        let c = &self.clients[&id];
        if let Some([t, b, l, r]) = c.fullscreen_monitors
            && [t, b, l, r]
                .iter()
                .all(|i| (*i as usize) < self.monitors.len())
        {
            let left = self.monitors[l as usize].rect;
            let right = self.monitors[r as usize].rect;
            let top = self.monitors[t as usize].rect;
            let bottom = self.monitors[b as usize].rect;
            let rect = Rect::new(
                left.x,
                top.y,
                right.x + right.w - left.x,
                bottom.y + bottom.h - top.y,
            );
            if rect.w > 0 && rect.h > 0 {
                return rect;
            }
        }
        self.monitors[c.monitor.0].rect
    }
    pub(super) fn fullscreen(&mut self, id: ClientId, on: bool) -> Result<()> {
        if self.clients[&id].flags.fullscreen == on {
            return Ok(());
        }
        self.suppress_crossings(true)?;
        let c = self.clients.get_mut(&id).unwrap();
        if on {
            c.fullscreen_restore = Some((c.geom, c.flags.floating, c.border));
            c.flags.fullscreen = true;
            c.flags.floating = true;
            c.border = 0;
            self.frame(id, false)?;
            self.reconcile_mapping(id)?;
            self.resize_now(id, self.fullscreen_rect(id))?;
        } else {
            c.flags.fullscreen = false;
            if let Some((r, f, b)) = c.fullscreen_restore.take() {
                c.geom = r;
                c.flags.floating = f;
                c.border = b;
            }
            if c.flags.shaded {
                c.flags.floating = true;
            }
            if !c.flags.shaded
                && !c.flags.max_h
                && !c.flags.max_v
                && let Some((r, f)) = c.normal.take()
            {
                c.geom = r;
                c.flags.floating = f;
            }
        }
        self.publish_state(id)?;
        self.arrange_windows()?;
        if self.focused == Some(id) && self.visible(id) && self.clients[&id].mapped {
            self.focus(Some(id))?;
        }
        self.restack()?;
        self.suppress_crossings(false)
    }
    pub(super) fn shade(&mut self, id: ClientId, on: bool) -> Result<()> {
        let c = self.clients.get_mut(&id).unwrap();
        if c.flags.shaded == on {
            return Ok(());
        }
        if on {
            c.remember_normal();
        }
        c.flags.shaded = on;
        if !c.flags.fullscreen {
            if on {
                c.flags.floating = true;
            } else if let Some((r, f)) = c.normal {
                c.flags.floating = f;
                if !c.flags.max_h && !c.flags.max_v {
                    c.normal = None;
                    self.resize_now(id, r)?;
                }
            }
        }
        self.arrange_windows()?;
        if self.focused == Some(id) && self.visible(id) && self.clients[&id].mapped {
            self.focus(Some(id))?;
        }
        self.restack()
    }
    pub(super) fn maximize(&mut self, id: ClientId, h: bool, v: bool) -> Result<()> {
        let c = self.clients.get_mut(&id).unwrap();
        if h || v {
            c.remember_normal();
        }
        c.flags.max_h = h;
        c.flags.max_v = v;
        if c.flags.fullscreen || c.flags.shaded {
            return Ok(());
        }
        if h || v {
            let decorated =
                c.flags.floating || self.monitors[c.monitor.0].active.layout == Layout::Float;
            self.frame(id, decorated)?;
            self.apply_maximized(id)?;
        } else if let Some((r, f)) = c.normal.take() {
            c.flags.floating = f;
            self.resize_now(id, r)?;
        }
        self.publish_state(id)?;
        Ok(())
    }
    fn apply_maximized(&mut self, id: ClientId) -> Result<()> {
        let c = &self.clients[&id];
        if c.flags.fullscreen {
            return Ok(());
        }
        let normal = c.normal.map(|(r, _)| r).unwrap_or(c.geom);
        let work = self.monitors[c.monitor.0].work;
        let extents = c.extents;
        let r = Rect::new(
            if c.flags.max_h {
                work.x + extents.left
            } else {
                normal.x
            },
            if c.flags.max_v {
                work.y + extents.top
            } else {
                normal.y
            },
            if c.flags.max_h {
                work.w - extents.left - extents.right - 2 * c.border
            } else {
                normal.w
            },
            if c.flags.max_v {
                work.h - extents.top - extents.bottom - 2 * c.border
            } else {
                normal.h
            },
        );
        self.resize_now(id, r)
    }
    pub(super) fn move_monitor(&mut self, id: ClientId, mon: MonitorId, retag: bool) -> Result<()> {
        let old = self.clients[&id].monitor;
        if old == mon {
            return Ok(());
        }
        self.monitors[old.0].clients.retain(|i| *i != id);
        self.monitors[old.0].stack.retain(|i| *i != id);
        if self.monitors[old.0].selected == Some(id) {
            self.monitors[old.0].selected = None;
        }
        self.monitors[mon.0].clients.push(id);
        self.monitors[mon.0].stack.insert(0, id);
        let c = self.clients.get_mut(&id).unwrap();
        c.monitor = mon;
        if retag {
            c.tags = self.monitors[mon.0].mask();
        }
        self.publish_desktop(id)?;
        self.arrange()
    }
    pub(super) fn reload(&mut self) -> Result<()> {
        if self.cli.no_config {
            return Ok(());
        }
        if let Err(e) = self.config.load(self.paths.wm.as_ref()) {
            self.logger.info(&format!("config: {e}"));
        }
        self.settings = Settings::load(self.paths.settings.as_ref());
        self.desktop_names = (1..=9).map(|n| n.to_string()).collect();
        for m in &mut self.monitors {
            m.gap = self.config.gap;
            for t in &mut m.tags {
                t.mfact = self.config.mfact;
                t.nmaster = self.config.nmaster;
            }
            m.apply_tag();
        }
        self.apply_power();
        self.grab_keys()?;
        self.recompute_work()?;
        self.publish_desktops()?;
        self.arrange()?;
        for id in self.order.clone() {
            self.draw_title(id)?;
        }
        self.focus(None)
    }
}
