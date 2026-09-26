use super::*;
impl Wm {
    pub(super) fn event(&mut self, event: Event) -> Result<()> {
        match event {
            Event::MapRequest(e) => {
                if self.clients.contains_key(&ClientId(e.window)) {
                    self.restore_client(ClientId(e.window))?;
                } else {
                    self.manage(e.window)?;
                }
            }
            Event::MapNotify(e) => {
                if let Some(c) = self.clients.get_mut(&ClientId(e.window)) {
                    c.mapped = true;
                } else {
                    self.update_dock(e.window)?;
                }
            }
            Event::DestroyNotify(e) => {
                if self.clients.contains_key(&ClientId(e.window)) {
                    self.unmanage(ClientId(e.window), true, false)?;
                }
                if self.docks.remove(&e.window).is_some() {
                    self.recompute_work()?;
                    self.arrange()?;
                }
                for c in self.clients.values_mut() {
                    if c.user_time_window == e.window {
                        c.user_time_window = 0;
                        c.user_time = None;
                    }
                }
            }
            Event::UnmapNotify(e) => {
                let id = ClientId(e.window);
                if let Some(c) = self.clients.get_mut(&id) {
                    if c.ignore_unmap > 0 {
                        c.ignore_unmap -= 1;
                    } else {
                        self.unmanage(id, false, false)?;
                    }
                } else if self.docks.remove(&e.window).is_some() {
                    self.recompute_work()?;
                    self.arrange()?;
                }
            }
            Event::ConfigureRequest(e) => self.configure_request(e)?,
            Event::ConfigureNotify(e) if e.window == self.root => {
                self.refresh_monitors()?;
            }
            Event::ConfigureNotify(_) => {
                self.stack_dirty = true;
            }
            Event::RandrNotify(_) | Event::RandrScreenChangeNotify(_) => self.refresh_monitors()?,
            Event::PropertyNotify(e) => self.property(e)?,
            Event::ClientMessage(e) => self.client_message(e)?,
            Event::SelectionClear(e) if e.selection == self.selection => self.running = false,
            Event::KeyPress(e) => {
                self.record_time(e.time);
                self.key_press(e)?;
            }
            Event::MappingNotify(e) if e.request != Mapping::POINTER => {
                self.logger
                    .debug(&format!("keyboard mapping changed: {:?}", e.request));
                self.grab_keys()?;
            }
            Event::ButtonPress(e) => {
                self.record_time(e.time);
                self.button_press(e)?;
            }
            Event::ButtonRelease(e) => {
                self.record_time(e.time);
                if self
                    .drag
                    .as_ref()
                    .is_some_and(|d| d.button == 0 || d.button == e.detail)
                {
                    self.drag_motion(e.root_x.into(), e.root_y.into())?;
                }
                self.end_drag(e.detail, false)?;
            }
            Event::MotionNotify(e) => {
                self.event_time = e.time;
                self.motion(e)?;
            }
            Event::EnterNotify(e) => {
                if let Some(id) = self.titles.get(&e.event).copied() {
                    self.clients.get_mut(&id).unwrap().hover =
                        crate::render::hit_button(e.event_x.into(), e.event_y.into());
                    self.draw_title(id)?;
                }
                if self.drag.is_none()
                    && e.mode == NotifyMode::NORMAL
                    && e.detail != NotifyDetail::INFERIOR
                    && !self.titles.contains_key(&e.event)
                {
                    self.record_time(e.time);
                    if let Some(id) = self.client_id(e.event) {
                        if self.focused != Some(id) {
                            self.focus(Some(id))?;
                        }
                    } else if e.event == self.root {
                        let mon =
                            self.rect_monitor(Rect::new(e.root_x.into(), e.root_y.into(), 1, 1));
                        if mon != self.selected {
                            self.selected = mon;
                            self.focus(None)?;
                        }
                    }
                }
            }
            Event::LeaveNotify(e) => {
                if let Some(id) = self.titles.get(&e.event).copied() {
                    self.clients.get_mut(&id).unwrap().hover = 0;
                    self.draw_title(id)?;
                }
            }
            Event::Expose(e) => {
                if let Some(id) = self.titles.get(&e.window).copied()
                    && e.count == 0
                {
                    self.draw_title(id)?;
                }
            }
            Event::FocusIn(e) => {
                if let Some(id) = self.focused
                    && e.event != id.0
                    && e.mode == NotifyMode::NORMAL
                    && e.detail != NotifyDetail::INFERIOR
                {
                    // A queued event may describe an obsolete transition, and
                    // toolkits can legitimately focus a descendant widget.
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
                    if window != id.0 {
                        let timestamp = self.server_time()?;
                        let client = &self.clients[&id];
                        if !client.flags.input_no_focus && !client.flags.type_no_focus {
                            self.conn
                                .set_input_focus(InputFocus::POINTER_ROOT, id.0, timestamp)?;
                        }
                        if client.flags.take_focus {
                            self.send_protocol(id, "WM_TAKE_FOCUS", timestamp, 0, 0)?;
                        }
                        self.put32(self.root, "_NET_ACTIVE_WINDOW", AtomEnum::WINDOW, &[id.0])?;
                    }
                }
            }
            Event::ColormapNotify(e) => {
                if e.new
                    && let Some(id) = self.focused
                    && (id.0 == e.window || self.clients[&id].colormaps.contains(&e.window))
                {
                    self.focus(Some(id))?;
                }
            }
            Event::Error(e) => self.logger.debug(&format!("X11: {e:?}")),
            _ => {}
        }
        Ok(())
    }
    fn configure_request(&mut self, e: ConfigureRequestEvent) -> Result<()> {
        let id = ClientId(e.window);
        if let Some(c) = self.clients.get(&id) {
            if (c.flags.floating || self.monitors[c.monitor.0].active.layout == Layout::Float)
                && !c.flags.fullscreen
            {
                let mut r = c.geom;
                let m = e.value_mask;
                if m.contains(ConfigWindow::X) {
                    r.x = e.x.into();
                }
                if m.contains(ConfigWindow::Y) {
                    r.y = e.y.into();
                }
                if m.contains(ConfigWindow::WIDTH) {
                    r.w = e.width.into();
                }
                if m.contains(ConfigWindow::HEIGHT) {
                    r.h = e.height.into();
                }
                if self.visible(id) {
                    self.resize(id, r, false)?;
                } else {
                    let c = self.clients.get_mut(&id).unwrap();
                    c.old = c.geom;
                    c.geom = r;
                    self.configure_notify(id)?;
                }
            } else {
                self.configure_notify(id)?;
            }
        } else {
            self.conn
                .configure_window(e.window, &ConfigureWindowAux::from_configure_request(&e))?;
            self.stack_dirty = true;
        }
        Ok(())
    }
    fn property(&mut self, e: PropertyNotifyEvent) -> Result<()> {
        if e.window == self.root {
            if e.atom == self.a("_NET_DESKTOP_NAMES") && e.state == Property::NEW_VALUE {
                let names = self.prop_text(self.root, e.atom);
                let names: Vec<_> = names
                    .trim_end_matches('\0')
                    .split('\0')
                    .map(str::to_owned)
                    .collect();
                if names.len() == 9 {
                    self.desktop_names = names;
                }
            }
            if e.state == Property::DELETE {
                if e.atom == self.a("_NET_CURRENT_DESKTOP") {
                    self.last_desktop.set(None);
                }
                if e.atom == self.a("_NET_CLIENT_LIST") {
                    self.publish_membership()?;
                } else if e.atom == self.a("_NET_CLIENT_LIST_STACKING") {
                    self.last_stack.clear();
                    self.stack_dirty = true;
                } else if e.atom == self.a("_NET_SUPPORTED") {
                    self.publish_supported()?;
                } else if [
                    "_NET_NUMBER_OF_DESKTOPS",
                    "_NET_DESKTOP_NAMES",
                    "_NET_DESKTOP_GEOMETRY",
                    "_NET_DESKTOP_VIEWPORT",
                    "_NET_CURRENT_DESKTOP",
                    "_NET_WORKAREA",
                ]
                .iter()
                .any(|n| e.atom == self.a(n))
                {
                    self.publish_desktops()?;
                }
            }
            return Ok(());
        }
        if e.atom == self.a("_NET_WM_USER_TIME") {
            let ids: Vec<_> = self
                .clients
                .values()
                .filter(|c| c.user_time_window == e.window)
                .map(|c| c.id)
                .collect();
            for id in ids {
                let value = self.get32(e.window, "_NET_WM_USER_TIME").first().copied();
                self.clients.get_mut(&id).unwrap().user_time = value;
            }
        }
        let id = ClientId(e.window);
        if !self.clients.contains_key(&id) {
            if [
                "_NET_WM_STRUT",
                "_NET_WM_STRUT_PARTIAL",
                "_NET_WM_WINDOW_TYPE",
            ]
            .iter()
            .any(|n| e.atom == self.a(n))
            {
                self.update_dock(e.window)?;
            }
            return Ok(());
        }
        if e.atom == self.a("_NET_WM_STATE") {
            if e.state == Property::DELETE {
                self.clients.get_mut(&id).unwrap().published = None;
                self.publish_state(id)?;
            }
            return Ok(());
        }
        if e.state == Property::DELETE {
            if e.atom == self.a("_NET_WM_DESKTOP") {
                self.publish_desktop(id)?;
            } else if e.atom == self.a("_NET_WM_ALLOWED_ACTIONS") {
                self.publish_actions(id)?;
            } else if e.atom == self.a("_NET_FRAME_EXTENTS") {
                let top = if self.clients[&id].frame != 0 { 28 } else { 0 };
                self.put32(
                    id.0,
                    "_NET_FRAME_EXTENTS",
                    AtomEnum::CARDINAL,
                    &[0, 0, top, 0],
                )?;
            }
        }
        if e.atom == self.a("_NET_WM_WINDOW_OPACITY") {
            return self.forward_opacity(id);
        }
        let core = [
            AtomEnum::WM_NAME.into(),
            AtomEnum::WM_CLASS.into(),
            AtomEnum::WM_NORMAL_HINTS.into(),
            AtomEnum::WM_HINTS.into(),
            AtomEnum::WM_TRANSIENT_FOR.into(),
        ];
        let extra = [
            "_NET_WM_NAME",
            "_NET_WM_WINDOW_TYPE",
            "WM_PROTOCOLS",
            "WM_COLORMAP_WINDOWS",
            "_NET_WM_USER_TIME",
            "_NET_WM_USER_TIME_WINDOW",
            "_NET_WM_FULLSCREEN_MONITORS",
            "_NET_WM_SYNC_REQUEST_COUNTER",
            "_NET_WM_STRUT",
            "_NET_WM_STRUT_PARTIAL",
        ];
        if core.contains(&e.atom) || extra.iter().any(|n| self.a(n) == e.atom) {
            self.refresh_properties(id)?;
            self.publish_actions(id)?;
            if self.focused == Some(id) && !self.clients[&id].focusable() {
                self.focus(None)?;
            }
            if e.atom == u32::from(AtomEnum::WM_NAME) || e.atom == self.a("_NET_WM_NAME") {
                self.draw_title(id)?;
            }
            if e.atom == self.a("_NET_WM_WINDOW_TYPE")
                || e.atom == u32::from(AtomEnum::WM_TRANSIENT_FOR)
            {
                self.publish_desktop(id)?;
                self.arrange()?;
            }
            if e.atom == self.a("_NET_WM_STRUT") || e.atom == self.a("_NET_WM_STRUT_PARTIAL") {
                self.recompute_work()?;
                self.arrange()?;
            }
            if e.atom == self.a("_NET_WM_FULLSCREEN_MONITORS") && self.clients[&id].flags.fullscreen
            {
                self.resize_now(id, self.fullscreen_rect(id))?;
            }
            self.publish_state(id)?;
        }
        Ok(())
    }
    pub(super) fn update_dock(&mut self, win: u32) -> Result<()> {
        let types = self.get32(win, "_NET_WM_WINDOW_TYPE");
        if !types.contains(&self.a("_NET_WM_WINDOW_TYPE_DOCK")) {
            if self.docks.remove(&win).is_some() {
                self.recompute_work()?;
                self.arrange()?;
            }
            return Ok(());
        }
        let attrs = self.conn.get_window_attributes(win)?.reply()?;
        if !attrs.override_redirect || attrs.map_state == MapState::UNMAPPED {
            return Ok(());
        }
        let mut strut = self.get32(win, "_NET_WM_STRUT_PARTIAL");
        if strut.len() < 12 {
            strut = self.get32(win, "_NET_WM_STRUT");
        }
        self.docks.insert(win, strut);
        self.conn.change_window_attributes(
            win,
            &ChangeWindowAttributesAux::new()
                .event_mask(EventMask::PROPERTY_CHANGE | EventMask::STRUCTURE_NOTIFY),
        )?;
        self.recompute_work()?;
        self.arrange()
    }
    fn client_message(&mut self, e: ClientMessageEvent) -> Result<()> {
        if e.format != 32 {
            return Ok(());
        }
        let d = e.data.as_data32();
        let ty = e.type_;
        if ty == self.a("_NET_CURRENT_DESKTOP") {
            if d[0] < 9 {
                self.view(1 << d[0], false)?;
            }
            return Ok(());
        }
        if ty == self.a("_NET_SHOWING_DESKTOP") {
            if d[0] <= 1 {
                self.showing = d[0] == 1;
                self.put32(
                    self.root,
                    "_NET_SHOWING_DESKTOP",
                    AtomEnum::CARDINAL,
                    &[d[0]],
                )?;
                self.focus(None)?;
                self.arrange()?;
            }
            return Ok(());
        }
        if ty == self.a("_NET_REQUEST_FRAME_EXTENTS") {
            let top = if let Some(c) = self.clients.get(&ClientId(e.window)) {
                if c.frame != 0 { 28 } else { 0 }
            } else {
                let types = self.get32(e.window, "_NET_WM_WINDOW_TYPE");
                if types.iter().any(|a| {
                    *a == self.a("_NET_WM_WINDOW_TYPE_DIALOG")
                        || *a == self.a("_NET_WM_WINDOW_TYPE_UTILITY")
                }) {
                    28
                } else {
                    0
                }
            };
            self.put32(
                e.window,
                "_NET_FRAME_EXTENTS",
                AtomEnum::CARDINAL,
                &[0, 0, top, 0],
            )?;
            return Ok(());
        }
        if ty == self.a("WM_PROTOCOLS") && d[0] == self.a("_NET_WM_PING") {
            let id = ClientId(d[2]);
            if let Some(c) = self.clients.get_mut(&id)
                && c.ping.is_some_and(|(t, _)| t == d[1])
            {
                c.ping = None;
                c.unresponsive = false;
                c.flags.attention = false;
                self.publish_state(id)?;
            }
            return Ok(());
        }
        let id = ClientId(e.window);
        if !self.clients.contains_key(&id) {
            return Ok(());
        }
        if ty == self.a("_NET_WM_STATE") {
            if d[0] <= 2 {
                for atom in [d[1], d[2]] {
                    if atom != 0 {
                        self.state_atom(id, atom, d[0])?;
                    }
                }
                self.publish_state(id)?;
                self.arrange()?;
            }
        } else if ty == self.a("WM_CHANGE_STATE") && d[0] == 3 {
            self.minimize_client(id)?;
        } else if ty == self.a("_NET_ACTIVE_WINDOW") {
            let c = &self.clients[&id];
            let stamp = if d[1] != 0 {
                d[1]
            } else {
                c.user_time.unwrap_or(0)
            };
            if d[0] == 2
                || self.selected_client() == Some(id)
                || (stamp != 0 && timestamp_current(stamp, self.last_user_time))
            {
                self.selected = c.monitor;
                let tags = c.tags;
                if self.showing {
                    self.showing = false;
                    self.put32(self.root, "_NET_SHOWING_DESKTOP", AtomEnum::CARDINAL, &[0])?;
                    self.arrange()?;
                }
                if tags & self.monitors[self.selected.0].mask() == 0 {
                    self.view(1 << desktop(tags & config::TAG_MASK), false)?;
                }
                self.restore_client(id)?;
                self.event_time = stamp;
                self.focus(Some(id))?;
                self.restack()?;
            } else {
                self.clients.get_mut(&id).unwrap().flags.attention = true;
                self.set_urgent(id, true)?;
                self.publish_state(id)?;
            }
        } else if ty == self.a("_NET_WM_DESKTOP") {
            if d[0] < 9 || d[0] == u32::MAX {
                self.clients.get_mut(&id).unwrap().tags = if d[0] == u32::MAX {
                    config::TAG_MASK
                } else {
                    1 << d[0]
                };
                self.publish_desktop(id)?;
                self.focus(None)?;
                self.arrange()?;
            }
        } else if ty == self.a("_NET_CLOSE_WINDOW") {
            self.close_client(id, d[0])?;
        } else if ty == self.a("_NET_WM_FULLSCREEN_MONITORS") {
            if self.xinerama && d[..4].iter().all(|i| (*i as usize) < self.monitors.len()) {
                self.clients.get_mut(&id).unwrap().fullscreen_monitors =
                    Some([d[0], d[1], d[2], d[3]]);
                self.put32(
                    id.0,
                    "_NET_WM_FULLSCREEN_MONITORS",
                    AtomEnum::CARDINAL,
                    &d[..4],
                )?;
                if self.clients[&id].flags.fullscreen {
                    self.resize_now(id, self.fullscreen_rect(id))?;
                }
            }
        } else if ty == self.a("_NET_MOVERESIZE_WINDOW") {
            self.net_move_resize(id, d)?;
        } else if ty == self.a("_NET_WM_MOVERESIZE") {
            if d[2] == 11 {
                self.end_drag(0, true)?;
            } else if d[2] <= 10 {
                self.begin_drag(id, d[0] as i32, d[1] as i32, d[2], d[3] as u8, true)?;
            }
        } else if ty == self.a("_NET_RESTACK_WINDOW") && d[2] <= 4 {
            let win = self.clients[&id].stack_window();
            let mut aux = ConfigureWindowAux::new().stack_mode(StackMode::from(d[2] as u8));
            if let Some(sibling) = self.clients.get(&ClientId(d[1])) {
                aux = aux.sibling(sibling.stack_window());
            }
            self.conn.configure_window(win, &aux)?;
            self.stack_dirty = true;
        }
        Ok(())
    }
    fn net_move_resize(&mut self, id: ClientId, d: [u32; 5]) -> Result<()> {
        if self.clients[&id].flags.fullscreen {
            self.fullscreen(id, false)?;
        }
        if self.clients[&id].flags.max_h || self.clients[&id].flags.max_v {
            self.maximize(id, false, false)?;
        }
        if self.clients[&id].flags.shaded {
            self.shade(id, false)?;
        }
        self.clients.get_mut(&id).unwrap().flags.floating = true;
        self.frame(id, true)?;
        let mut r = self.clients[&id].geom;
        let gravity = if d[0] & 255 == 0 {
            self.clients[&id].hints.gravity
        } else {
            d[0] & 255
        };
        let top = if self.clients[&id].frame != 0 { 28 } else { 0 };
        if d[0] & (1 << 8) != 0 {
            r.x = d[1] as i32;
        }
        if d[0] & (1 << 9) != 0 {
            r.y = d[2] as i32
                + match gravity {
                    1..=3 => top,
                    4..=6 => top / 2,
                    7..=10 => 0,
                    _ => top,
                };
        }
        if d[0] & (1 << 10) != 0 {
            r.w = d[3] as i32;
        }
        if d[0] & (1 << 11) != 0 {
            r.h = d[4] as i32;
        }
        self.clients.get_mut(&id).unwrap().flags.floating = true;
        self.resize(id, r, false)?;
        self.arrange()
    }
    pub(super) fn state_atom(&mut self, id: ClientId, atom: u32, action: u32) -> Result<()> {
        if action > 2 {
            return Ok(());
        }
        let name = self
            .atoms
            .iter()
            .find(|(_, a)| **a == atom)
            .map(|(s, _)| s.clone())
            .unwrap_or_default();
        let set = |v: bool| match action {
            0 => false,
            1 => true,
            _ => !v,
        };
        let c = self.clients.get_mut(&id).unwrap();
        match name.as_str() {
            "_NET_WM_STATE_FULLSCREEN" => {
                let on = set(c.flags.fullscreen);
                self.fullscreen(id, on)?;
            }
            "_NET_WM_STATE_MAXIMIZED_HORZ" => {
                let (h, v) = (set(c.flags.max_h), c.flags.max_v);
                self.maximize(id, h, v)?;
            }
            "_NET_WM_STATE_MAXIMIZED_VERT" => {
                let (h, v) = (c.flags.max_h, set(c.flags.max_v));
                self.maximize(id, h, v)?;
            }
            "_NET_WM_STATE_MODAL" => {
                c.flags.modal = set(c.flags.modal);
                if c.flags.modal {
                    c.flags.floating = true;
                }
            }
            "_NET_WM_STATE_STICKY" => c.flags.sticky = set(c.flags.sticky),
            "_NET_WM_STATE_SHADED" => {
                let on = set(c.flags.shaded);
                self.shade(id, on)?;
            }
            "_NET_WM_STATE_ABOVE" | "_NET_WM_STATE_STAYS_ON_TOP" => {
                c.flags.above = set(c.flags.above);
                if c.flags.above {
                    c.flags.below = false;
                }
            }
            "_NET_WM_STATE_BELOW" => {
                c.flags.below = set(c.flags.below);
                if c.flags.below {
                    c.flags.above = false;
                }
            }
            "_NET_WM_STATE_SKIP_TASKBAR" => c.flags.skip_taskbar = set(c.flags.skip_taskbar),
            "_NET_WM_STATE_SKIP_PAGER" => c.flags.skip_pager = set(c.flags.skip_pager),
            "_NET_WM_STATE_DEMANDS_ATTENTION" => {
                let on = set(c.flags.attention);
                c.flags.attention = on;
                self.set_urgent(id, on)?;
            }
            _ => {}
        }
        Ok(())
    }
    pub(super) fn publish_state(&mut self, id: ClientId) -> Result<()> {
        let c = &self.clients[&id];
        let f = &c.flags;
        let pairs = [
            ("MODAL", f.modal),
            ("STICKY", f.sticky),
            ("MAXIMIZED_VERT", f.max_v),
            ("MAXIMIZED_HORZ", f.max_h),
            ("SHADED", f.shaded),
            (
                "HIDDEN",
                f.minimized || (self.showing && !f.dock && !f.desktop),
            ),
            ("SKIP_TASKBAR", f.skip_taskbar),
            ("SKIP_PAGER", f.skip_pager),
            ("FULLSCREEN", f.fullscreen),
            ("ABOVE", f.above),
            ("BELOW", f.below),
            ("DEMANDS_ATTENTION", f.attention),
            ("FOCUSED", self.focused == Some(id)),
        ];
        let mut state: Vec<_> = pairs
            .into_iter()
            .filter(|&(_name, on)| on)
            .map(|(name, _on)| self.a(&format!("_NET_WM_STATE_{name}")))
            .collect();
        state.sort_unstable();
        state.dedup();
        if c.published.as_ref() != Some(&state) {
            self.put32(id.0, "_NET_WM_STATE", AtomEnum::ATOM, &state)?;
            self.clients.get_mut(&id).unwrap().published = Some(state);
        }
        Ok(())
    }
    pub(super) fn publish_actions(&self, id: ClientId) -> Result<()> {
        let c = &self.clients[&id];
        let mut names = Vec::new();
        if !c.flags.dock && !c.flags.desktop {
            names.extend([
                "CLOSE",
                "MOVE",
                "MINIMIZE",
                "SHADE",
                "STICK",
                "FULLSCREEN",
                "CHANGE_DESKTOP",
                "ABOVE",
                "BELOW",
            ]);
            if !c.hints.fixed {
                names.extend(["RESIZE", "MAXIMIZE_HORZ", "MAXIMIZE_VERT"]);
            }
        }
        let atoms: Vec<_> = names
            .into_iter()
            .map(|n| self.a(&format!("_NET_WM_ACTION_{n}")))
            .collect();
        self.put32(id.0, "_NET_WM_ALLOWED_ACTIONS", AtomEnum::ATOM, &atoms)
    }
    pub(super) fn publish_desktop(&self, id: ClientId) -> Result<()> {
        self.put32(
            id.0,
            "_NET_WM_DESKTOP",
            AtomEnum::CARDINAL,
            &[client_desktop(self.clients[&id].tags)],
        )
    }
    pub(super) fn publish_membership(&mut self) -> Result<()> {
        self.put32(
            self.root,
            "_NET_CLIENT_LIST",
            AtomEnum::WINDOW,
            &self.order.iter().map(|i| i.0).collect::<Vec<_>>(),
        )?;
        self.stack_dirty = true;
        Ok(())
    }
    pub(super) fn flush_stacking(&mut self) -> Result<()> {
        if !self.stack_dirty {
            return Ok(());
        }
        let tree = self.conn.query_tree(self.root)?.reply()?;
        let mut stack = Vec::new();
        for win in tree.children {
            if let Some(id) = self.client_id(win)
                && !stack.contains(&id.0)
            {
                stack.push(id.0);
            }
        }
        if stack != self.last_stack || self.last_stack.is_empty() {
            self.put32(
                self.root,
                "_NET_CLIENT_LIST_STACKING",
                AtomEnum::WINDOW,
                &stack,
            )?;
            self.last_stack = stack;
        }
        self.stack_dirty = false;
        Ok(())
    }
    pub(super) fn publish_supported(&self) -> Result<()> {
        let mut supported: Vec<_> = atoms::SUPPORTED.iter().map(|n| self.a(n)).collect();
        if self.sync {
            supported.extend([
                self.a("_NET_WM_SYNC_REQUEST"),
                self.a("_NET_WM_SYNC_REQUEST_COUNTER"),
            ]);
        }
        if self.xinerama {
            supported.push(self.a("_NET_WM_FULLSCREEN_MONITORS"));
        }
        self.put32(self.root, "_NET_SUPPORTED", AtomEnum::ATOM, &supported)
    }
    pub(super) fn publish_desktops(&self) -> Result<()> {
        self.put32(
            self.root,
            "_NET_NUMBER_OF_DESKTOPS",
            AtomEnum::CARDINAL,
            &[9],
        )?;
        self.put_text(
            self.root,
            "_NET_DESKTOP_NAMES",
            &(self.desktop_names.join("\0") + "\0"),
        )?;
        self.put32(
            self.root,
            "_NET_DESKTOP_GEOMETRY",
            AtomEnum::CARDINAL,
            &[
                self.screen.width_in_pixels.into(),
                self.screen.height_in_pixels.into(),
            ],
        )?;
        self.put32(
            self.root,
            "_NET_DESKTOP_VIEWPORT",
            AtomEnum::CARDINAL,
            &[0; 18],
        )?;
        self.publish_current_desktop()?;
        self.put32(
            self.root,
            "_NET_SHOWING_DESKTOP",
            AtomEnum::CARDINAL,
            &[u32::from(self.showing)],
        )?;
        self.publish_workarea()
    }
    pub(super) fn publish_current_desktop(&self) -> Result<()> {
        let current = desktop(self.monitors[self.selected.0].mask());
        if self.last_desktop.get() == Some(current) {
            return Ok(());
        }
        self.put32(
            self.root,
            "_NET_CURRENT_DESKTOP",
            AtomEnum::CARDINAL,
            &[current],
        )?;
        self.last_desktop.set(Some(current));
        Ok(())
    }
    pub(super) fn publish_workarea(&self) -> Result<()> {
        if self.monitors.is_empty() {
            return Ok(());
        }
        let left = self.monitors.iter().map(|m| m.work.x).min().unwrap();
        let top = self.monitors.iter().map(|m| m.work.y).min().unwrap();
        let right = self
            .monitors
            .iter()
            .map(|m| m.work.x + m.work.w)
            .max()
            .unwrap();
        let bottom = self
            .monitors
            .iter()
            .map(|m| m.work.y + m.work.h)
            .max()
            .unwrap();
        let row = [
            left as u32,
            top as u32,
            (right - left) as u32,
            (bottom - top) as u32,
        ];
        self.put32(
            self.root,
            "_NET_WORKAREA",
            AtomEnum::CARDINAL,
            &row.repeat(9),
        )
    }
    pub(super) fn forward_opacity(&self, id: ClientId) -> Result<()> {
        let c = &self.clients[&id];
        if c.frame != 0 {
            let value = self.get32(id.0, "_NET_WM_WINDOW_OPACITY");
            if value.is_empty() {
                self.conn
                    .delete_property(c.frame, self.a("_NET_WM_WINDOW_OPACITY"))?;
            } else {
                self.put32(
                    c.frame,
                    "_NET_WM_WINDOW_OPACITY",
                    AtomEnum::CARDINAL,
                    &value[..1],
                )?;
            }
        }
        Ok(())
    }
    pub(super) fn set_urgent(&mut self, id: ClientId, on: bool) -> Result<()> {
        self.clients.get_mut(&id).unwrap().flags.urgent = on;
        let mut hints = self.prop32(id.0, AtomEnum::WM_HINTS.into(), AtomEnum::WM_HINTS.into());
        if hints.len() < 9 {
            hints.resize(9, 0);
        }
        let old = hints[0];
        if on {
            hints[0] |= 1 << 8;
        } else {
            hints[0] &= !(1 << 8);
        }
        if old != hints[0] {
            self.conn.change_property32(
                PropMode::REPLACE,
                id.0,
                AtomEnum::WM_HINTS,
                AtomEnum::WM_HINTS,
                &hints,
            )?;
        }
        Ok(())
    }
    pub(super) fn send_protocol(
        &self,
        id: ClientId,
        name: &str,
        time: u32,
        data2: u32,
        data3: u32,
    ) -> Result<()> {
        self.conn.send_event(
            false,
            id.0,
            EventMask::NO_EVENT,
            ClientMessageEvent::new(
                32,
                id.0,
                self.a("WM_PROTOCOLS"),
                [self.a(name), time, data2, data3, 0],
            ),
        )?;
        Ok(())
    }
    pub(super) fn close_client(&mut self, id: ClientId, time: u32) -> Result<()> {
        let c = &self.clients[&id];
        if c.unresponsive || !c.protocols.contains(&self.a("WM_DELETE_WINDOW")) {
            self.conn.kill_client(id.0)?;
            return Ok(());
        }
        self.send_protocol(id, "WM_DELETE_WINDOW", time, 0, 0)?;
        if c.protocols.contains(&self.a("_NET_WM_PING")) {
            let time = if time == 0 { self.server_time()? } else { time };
            self.send_protocol(id, "_NET_WM_PING", time, id.0, 0)?;
            self.clients.get_mut(&id).unwrap().ping = Some((time, Instant::now()));
        }
        Ok(())
    }
    pub(super) fn server_time(&mut self) -> Result<u32> {
        // Preserve events encountered while obtaining a fresh server timestamp.
        self.conn.change_property32(
            PropMode::REPLACE,
            self.check,
            self.a("MANAGER"),
            AtomEnum::CARDINAL,
            &[0],
        )?;
        self.conn.flush()?;
        let deadline = Instant::now() + Duration::from_secs(1);
        while Instant::now() < deadline {
            while let Some(event) = self.conn.poll_for_event()? {
                if let Event::PropertyNotify(e) = &event
                    && e.window == self.check
                    && e.atom == self.a("MANAGER")
                {
                    return Ok(e.time);
                }
                self.pending_events.push_back(event);
            }
            let mut fds = [rustix::event::PollFd::new(
                self.conn.stream(),
                rustix::event::PollFlags::IN,
            )];
            let timeout = rustix::event::Timespec {
                tv_sec: 0,
                tv_nsec: 10_000_000,
            };
            let _ = rustix::event::poll(&mut fds, Some(&timeout));
        }
        Ok(0)
    }
    pub(super) fn protocol_timeouts(&mut self) -> Result<()> {
        for id in self.order.clone() {
            let c = &self.clients[&id];
            if c.ping
                .is_some_and(|(_, t)| t.elapsed() >= Duration::from_secs(5))
            {
                let c = self.clients.get_mut(&id).unwrap();
                c.ping = None;
                c.unresponsive = true;
                c.flags.attention = true;
                self.set_urgent(id, true)?;
                self.publish_state(id)?;
            }
            let c = &self.clients[&id];
            if let Some(start) = c.sync_wait {
                let ack = sync::query_counter(&self.conn, c.sync_counter)
                    .ok()
                    .and_then(|r| r.reply().ok())
                    .is_some_and(|r| {
                        ((r.counter_value.hi as u64) << 32 | u64::from(r.counter_value.lo))
                            >= c.sync_value
                    });
                if ack || start.elapsed() >= Duration::from_secs(1) {
                    let c = self.clients.get_mut(&id).unwrap();
                    c.sync_wait = None;
                    if let Some(r) = c.sync_pending.take() {
                        self.resize(id, r, true)?;
                    }
                }
            }
        }
        Ok(())
    }
    pub(super) fn apply_power(&mut self) {
        self.sleep_triggered = false;
        if self.cli.no_config {
            return;
        }
        let Some(power) = &self.settings.power else {
            return;
        };
        let seconds = crate::session::monitor_timeout(power.monitor_timeout_minutes);
        let _ = self
            .conn
            .set_screen_saver(0, 0, Blanking::NOT_PREFERRED, Exposures::DEFAULT);
        if self.dpms {
            if seconds == 0 {
                let _ = dpms::disable(&self.conn);
            } else {
                let _ = dpms::set_timeouts(&self.conn, 0, 0, seconds);
                let _ = dpms::enable(&self.conn);
            }
        }
    }
    pub(super) fn check_power(&mut self) {
        if self.cli.no_config || !self.screensaver {
            return;
        }
        if let Ok(cookie) = screensaver::query_info(&self.conn, self.root)
            && let Ok(info) = cookie.reply()
        {
            let (suspend, triggered) = crate::session::idle_sleep(
                info.ms_since_user_input.into(),
                self.settings
                    .power
                    .as_ref()
                    .map_or(0, |p| p.sleep_timeout_minutes),
                self.sleep_triggered,
            );
            self.sleep_triggered = triggered;
            if suspend {
                self.workers.send(Job::Suspend);
            }
        }
    }
}
