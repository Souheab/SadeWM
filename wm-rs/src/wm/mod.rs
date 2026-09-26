#[path = "../atoms.rs"]
mod atoms;
mod input;
mod layout;
mod manage;
mod protocol;
use crate::{
    config::{self, Binding, Cli, Config, Paths, Settings},
    ipc::{Request, Server},
    model::*,
    render::{Renderer, TITLE_HEIGHT},
    session::{Job, Logger, Workers},
};
use anyhow::{Context, Result};
use serde_json::{Value, json};
use std::{
    cell::Cell,
    collections::{BTreeMap, HashMap, VecDeque},
    io::Read,
    os::unix::net::UnixStream,
    path::PathBuf,
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    time::{Duration, Instant},
};
use x11rb::{
    connection::{Connection, RequestConnection},
    protocol::{Event, dpms, randr, screensaver, shape, sync, xinerama, xproto::*},
    rust_connection::RustConnection,
    wrapper::ConnectionExt as _,
};

pub struct Wm {
    conn: RustConnection,
    root: u32,
    screen: Screen,
    check: u32,
    cursors: [u32; 3],
    signal_reader: UnixStream,
    selection: u32,
    atoms: HashMap<String, u32>,
    config: Config,
    paths: Paths,
    cli: Cli,
    settings: Settings,
    clients: BTreeMap<ClientId, Client>,
    order: Vec<ClientId>,
    monitors: Vec<Monitor>,
    selected: MonitorId,
    focused: Option<ClientId>,
    minimized: Vec<ClientId>,
    frames: HashMap<u32, ClientId>,
    titles: HashMap<u32, ClientId>,
    docks: HashMap<u32, Vec<u32>>,
    shape: bool,
    xinerama: bool,
    sync: bool,
    dpms: bool,
    screensaver: bool,
    showing: bool,
    running: bool,
    desktop_names: Vec<String>,
    last_user_time: u32,
    event_time: u32,
    stack_dirty: bool,
    last_stack: Vec<u32>,
    last_desktop: Cell<Option<u32>>,
    pending_events: VecDeque<Event>,
    server: Option<Server>,
    renderer: Renderer,
    logger: Logger,
    workers: Workers,
    wallpaper: u32,
    keys: Vec<(u8, u16, Binding)>,
    numlock: u16,
    drag: Option<input::Drag>,
    last_tags: Value,
    power_tick: Instant,
    protocol_tick: Instant,
    sleep_triggered: bool,
    shutdown: Arc<AtomicBool>,
    dump: Arc<AtomicBool>,
    signal_ids: Vec<signal_hook::SigId>,
}
impl Wm {
    pub fn connect(cli: Cli) -> Result<Self> {
        let (conn, index) = x11rb::connect(None).context("cannot open display")?;
        let screen = conn.setup().roots[index].clone();
        let root = screen.root;
        conn.change_window_attributes(
            root,
            &ChangeWindowAttributesAux::new().event_mask(EventMask::SUBSTRUCTURE_REDIRECT),
        )?
        .check()
        .context("another window manager is already running")?;
        let mut atoms = HashMap::new();
        for name in atoms::ATOM_NAMES.iter().copied().chain([
            "_XROOTPMAP_ID",
            "ESETROOT_PMAP_ID",
            "WM_CLIENT_LEADER",
        ]) {
            atoms.insert(
                name.to_owned(),
                conn.intern_atom(false, name.as_bytes())?.reply()?.atom,
            );
        }
        let check = conn.generate_id()?;
        conn.create_window(
            screen.root_depth,
            check,
            root,
            0,
            0,
            1,
            1,
            0,
            WindowClass::INPUT_OUTPUT,
            screen.root_visual,
            &CreateWindowAux::new().event_mask(EventMask::PROPERTY_CHANGE),
        )?
        .check()?;
        conn.change_property32(
            PropMode::APPEND,
            check,
            atoms["MANAGER"],
            AtomEnum::CARDINAL,
            &[0],
        )?;
        conn.flush()?;
        let selection_time = loop {
            if let Event::PropertyNotify(e) = conn.wait_for_event()?
                && e.window == check
            {
                break e.time;
            }
        };
        conn.delete_property(check, atoms["MANAGER"])?;
        let selection = conn
            .intern_atom(false, format!("WM_S{index}").as_bytes())?
            .reply()?
            .atom;
        anyhow::ensure!(
            conn.get_selection_owner(selection)?.reply()?.owner == x11rb::NONE,
            "another window manager already owns WM_S{index}"
        );
        conn.set_selection_owner(check, selection, selection_time)?
            .check()?;
        anyhow::ensure!(
            conn.get_selection_owner(selection)?.reply()?.owner == check,
            "cannot own WM selection"
        );
        conn.send_event(
            false,
            root,
            EventMask::STRUCTURE_NOTIFY,
            ClientMessageEvent::new(
                32,
                root,
                atoms["MANAGER"],
                [selection_time, selection, check, 0, 0],
            ),
        )?;
        conn.change_window_attributes(
            root,
            &ChangeWindowAttributesAux::new().event_mask(
                EventMask::SUBSTRUCTURE_REDIRECT
                    | EventMask::SUBSTRUCTURE_NOTIFY
                    | EventMask::PROPERTY_CHANGE
                    | EventMask::STRUCTURE_NOTIFY
                    | EventMask::BUTTON_PRESS
                    | EventMask::POINTER_MOTION
                    | EventMask::ENTER_WINDOW
                    | EventMask::LEAVE_WINDOW,
            ),
        )?;
        let shape = shape::query_version(&conn)
            .ok()
            .and_then(|c| c.reply().ok())
            .is_some();
        let sync = sync::initialize(&conn, 3, 1)
            .ok()
            .and_then(|c| c.reply().ok())
            .is_some();
        let randr = randr::query_version(&conn, 1, 6)
            .ok()
            .and_then(|c| c.reply().ok())
            .is_some();
        if randr {
            let _ = randr::select_input(
                &conn,
                root,
                randr::NotifyMask::SCREEN_CHANGE
                    | randr::NotifyMask::CRTC_CHANGE
                    | randr::NotifyMask::OUTPUT_CHANGE
                    | randr::NotifyMask::OUTPUT_PROPERTY
                    | randr::NotifyMask::PROVIDER_CHANGE
                    | randr::NotifyMask::RESOURCE_CHANGE,
            );
        }
        let dpms = dpms::get_version(&conn, 1, 2)
            .ok()
            .and_then(|c| c.reply().ok())
            .is_some();
        let screensaver = screensaver::query_version(&conn, 1, 1)
            .ok()
            .and_then(|c| c.reply().ok())
            .is_some();
        let font = conn.generate_id()?;
        conn.open_font(font, b"cursor")?.check()?;
        let mut cursors = [0; 3];
        for (i, glyph) in [68u16, 52, 120].into_iter().enumerate() {
            cursors[i] = conn.generate_id()?;
            conn.create_glyph_cursor(
                cursors[i],
                font,
                font,
                glyph,
                glyph + 1,
                0,
                0,
                0,
                65535,
                65535,
                65535,
            )?
            .check()?;
        }
        conn.close_font(font)?;
        conn.change_window_attributes(root, &ChangeWindowAttributesAux::new().cursor(cursors[0]))?;
        let (signal_reader, signal_writer) = UnixStream::pair()?;
        signal_reader.set_nonblocking(true)?;
        let paths = cli.paths(std::env::var_os("HOME").map(PathBuf::from));
        let mut config = Config::default();
        if let Err(e) = config.load(paths.wm.as_ref()) {
            eprintln!("sadewm-rs: config: {e}");
        }
        if let Some(top) = cli.top.filter(|n| *n > 0) {
            config.top = top.min(65535) as i32;
        }
        let settings = Settings::load(paths.settings.as_ref());
        let shutdown = Arc::new(AtomicBool::new(false));
        let dump = Arc::new(AtomicBool::new(false));
        let mut signal_ids = Vec::new();
        for sig in [
            signal_hook::consts::SIGINT,
            signal_hook::consts::SIGTERM,
            signal_hook::consts::SIGHUP,
        ] {
            signal_ids.push(signal_hook::flag::register(sig, Arc::clone(&shutdown))?);
            signal_ids.push(signal_hook::low_level::pipe::register(
                sig,
                signal_writer.try_clone()?,
            )?);
        }
        signal_ids.push(signal_hook::flag::register(
            signal_hook::consts::SIGUSR1,
            Arc::clone(&dump),
        )?);
        signal_ids.push(signal_hook::low_level::pipe::register(
            signal_hook::consts::SIGUSR1,
            signal_writer,
        )?);
        let logger = Logger::new(cli.debug);
        let mut wm = Self {
            conn,
            root,
            screen,
            check,
            cursors,
            signal_reader,
            selection,
            atoms,
            config,
            paths,
            cli,
            settings,
            clients: BTreeMap::new(),
            order: Vec::new(),
            monitors: Vec::new(),
            selected: MonitorId(0),
            focused: None,
            minimized: Vec::new(),
            frames: HashMap::new(),
            titles: HashMap::new(),
            docks: HashMap::new(),
            shape,
            xinerama: false,
            sync,
            dpms,
            screensaver,
            showing: false,
            running: true,
            desktop_names: (1..=9).map(|n| n.to_string()).collect(),
            last_user_time: 0,
            event_time: 0,
            stack_dirty: true,
            last_stack: Vec::new(),
            last_desktop: Cell::new(None),
            pending_events: VecDeque::new(),
            server: None,
            renderer: Renderer::new(),
            logger,
            workers: Workers::new(),
            wallpaper: 0,
            keys: Vec::new(),
            numlock: 0,
            drag: None,
            last_tags: Value::Null,
            power_tick: Instant::now(),
            protocol_tick: Instant::now(),
            sleep_triggered: false,
            shutdown,
            dump,
            signal_ids,
        };
        wm.refresh_monitors()?;
        wm.publish_supported()?;
        wm.put32(root, "_NET_SUPPORTING_WM_CHECK", AtomEnum::WINDOW, &[check])?;
        wm.put32(
            check,
            "_NET_SUPPORTING_WM_CHECK",
            AtomEnum::WINDOW,
            &[check],
        )?;
        wm.put_text(check, "_NET_WM_NAME", "sadewm")?;
        wm.publish_membership()?;
        wm.publish_desktops()?;
        wm.grab_keys()?;
        wm.focus(None)?;
        wm.server = match Server::bind() {
            Ok(s) => Some(s),
            Err(e) => {
                wm.logger.info(&format!("IPC unavailable: {e}"));
                None
            }
        };
        wm.apply_power();
        if !wm.cli.no_config {
            wm.workers
                .send(Job::Display(usize::MAX, wm.settings.display.clone()));
        }
        let tree = wm.conn.query_tree(root)?.reply()?;
        // Parents before their transient dialogs during takeover.
        for transient in [false, true] {
            for win in &tree.children {
                let attr = wm.conn.get_window_attributes(*win)?.reply();
                if let Ok(attr) = attr {
                    if attr.override_redirect {
                        wm.update_dock(*win)?;
                        continue;
                    }
                    let is_transient = wm
                        .prop32(
                            *win,
                            u32::from(AtomEnum::WM_TRANSIENT_FOR),
                            u32::from(AtomEnum::WINDOW),
                        )
                        .first()
                        .copied()
                        .unwrap_or(0)
                        != 0;
                    let iconic = wm.get32(*win, "WM_STATE").first() == Some(&3);
                    if is_transient == transient
                        && (attr.map_state == MapState::VIEWABLE || iconic)
                        && let Err(e) = wm.manage(*win)
                    {
                        wm.logger.debug(&format!("scan: {e}"));
                    }
                }
            }
        }
        wm.set_wallpaper()?;
        if let Some(path) = &wm.paths.startup
            && path.is_file()
        {
            wm.workers.send(Job::Spawn(vec![
                "sh".into(),
                path.to_string_lossy().into_owned(),
            ]));
        }
        wm.conn.flush()?;
        Ok(wm)
    }
    pub fn run(mut self) -> Result<()> {
        self.logger.info("sadewm-rs ready");
        let result = self.event_loop();
        let cleanup = self.cleanup();
        result.and(cleanup)
    }
    fn event_loop(&mut self) -> Result<()> {
        while self.running && !self.shutdown.load(Ordering::Relaxed) {
            let mut signals = [0u8; 64];
            while matches!(self.signal_reader.read(&mut signals), Ok(n) if n > 0) {}
            for _ in 0..64 {
                let Some(event) = self.next_event()? else {
                    break;
                };
                self.event_time = 0;
                if let Err(e) = self.event(event) {
                    self.logger.debug(&format!("event: {e:#}"));
                }
            }
            self.event_time = 0;
            let requests = self.server.as_mut().map(Server::tick).unwrap_or_default();
            for (id, request) in requests {
                let subscribe = request.cmd == "subscribe_tags";
                let deferred = request.cmd == "reload" && !self.cli.no_config;
                let response = self.request(&request);
                match response {
                    Ok(value) => {
                        if !deferred {
                            if let Some(s) = self.server.as_mut() {
                                if subscribe {
                                    s.subscribe(id, value);
                                } else {
                                    s.respond(id, value);
                                }
                            }
                        } else if !self
                            .workers
                            .send(Job::Display(id, self.settings.display.clone()))
                            && let Some(s) = self.server.as_mut()
                        {
                            s.respond(id, json!({"ok":false,"error":"window manager busy"}));
                        }
                    }
                    Err(e) => {
                        if let Some(s) = self.server.as_mut() {
                            s.respond(id, json!({"ok":false,"error":e.to_string()}));
                        }
                    }
                }
            }
            while let Ok((id, result)) = self.workers.results.try_recv() {
                if let Err(e) = &result {
                    self.logger.info(&format!("display settings: {e}"));
                }
                if id != usize::MAX
                    && let Some(s) = self.server.as_mut()
                {
                    s.respond(
                        id,
                        match result {
                            Ok(()) => json!({"ok":true}),
                            Err(e) => json!({"ok":false,"error":e.to_string()}),
                        },
                    );
                }
            }
            if self.power_tick.elapsed() >= Duration::from_secs(5) {
                self.check_power();
                self.power_tick = Instant::now();
            }
            if self.protocol_tick.elapsed() >= Duration::from_millis(100) {
                self.protocol_timeouts()?;
                self.protocol_tick = Instant::now();
            }
            if self.dump.swap(false, Ordering::Relaxed) {
                self.logger.info(&format!("Rust WM state: clients={} monitors={} selected={:?} focused={:?} drag={:?}\n{}",self.clients.len(),self.monitors.len(),self.selected,self.focused,self.drag,self.state()));
            }
            self.flush_stacking()?;
            let tags = self.tags_event();
            if tags != self.last_tags {
                if let Some(s) = self.server.as_mut() {
                    s.broadcast(&tags);
                }
                self.last_tags = tags;
            }
            if let Some(s) = self.server.as_mut() {
                s.flush();
            }
            self.conn.flush()?;
            if !self.running {
                break;
            }
            // Requests/replies can buffer events inside x11rb even when the socket is no longer readable.
            if let Some(event) = self.next_event()? {
                self.event_time = 0;
                if let Err(e) = self.event(event) {
                    self.logger.debug(&format!("event: {e}"));
                }
                continue;
            }
            let mut fds = vec![rustix::event::PollFd::new(
                self.conn.stream(),
                rustix::event::PollFlags::IN,
            )];
            fds.push(rustix::event::PollFd::new(
                &self.signal_reader,
                rustix::event::PollFlags::IN,
            ));
            if let Some(s) = &self.server {
                fds.extend(s.poll_fds());
            }
            let timeout = rustix::event::Timespec {
                tv_sec: 0,
                tv_nsec: 100_000_000,
            };
            match rustix::event::poll(&mut fds, Some(&timeout)) {
                Ok(_) => {}
                Err(rustix::io::Errno::INTR) => {}
                Err(e) => return Err(e.into()),
            }
        }
        Ok(())
    }
    fn native_pixel(&self, color: &str) -> u32 {
        let rgb = crate::render::rgb(color);
        self.screen
            .allowed_depths
            .iter()
            .flat_map(|d| &d.visuals)
            .find(|v| v.visual_id == self.screen.root_visual)
            .map(|v| {
                [v.red_mask, v.green_mask, v.blue_mask]
                    .into_iter()
                    .zip(rgb)
                    .fold(0, |pixel, (mask, c)| {
                        if mask == 0 {
                            pixel
                        } else {
                            pixel
                                | ((u32::from(c) * (mask >> mask.trailing_zeros()) + 127) / 255)
                                    << mask.trailing_zeros()
                        }
                    })
            })
            .unwrap_or(0)
    }
    fn a(&self, name: &str) -> u32 {
        self.atoms[name]
    }
    fn prop32(&self, win: u32, atom: u32, kind: u32) -> Vec<u32> {
        self.conn
            .get_property(false, win, atom, kind, 0, 4096)
            .ok()
            .and_then(|c| c.reply().ok())
            .and_then(|r| r.value32().map(|v| v.collect()))
            .unwrap_or_default()
    }
    fn get32(&self, win: u32, name: &str) -> Vec<u32> {
        let (kind, min, max) = match name {
            "_NET_WM_STATE" | "_NET_WM_WINDOW_TYPE" | "WM_PROTOCOLS" | "_NET_SUPPORTED" => {
                (u32::from(AtomEnum::ATOM), 0, 4096)
            }
            "WM_COLORMAP_WINDOWS" => (u32::from(AtomEnum::WINDOW), 0, 4096),
            "_NET_WM_USER_TIME_WINDOW" | "WM_CLIENT_LEADER" => (u32::from(AtomEnum::WINDOW), 1, 1),
            "WM_STATE" => (self.a("WM_STATE"), 2, 2),
            "_XROOTPMAP_ID" | "ESETROOT_PMAP_ID" => (u32::from(AtomEnum::PIXMAP), 1, 1),
            "_NET_WM_STRUT_PARTIAL" => (u32::from(AtomEnum::CARDINAL), 12, 12),
            "_NET_WM_STRUT" | "_NET_WM_FULLSCREEN_MONITORS" => {
                (u32::from(AtomEnum::CARDINAL), 4, 4)
            }
            _ => (u32::from(AtomEnum::CARDINAL), 1, 1),
        };
        self.conn
            .get_property(false, win, self.a(name), kind, 0, max as u32)
            .ok()
            .and_then(|r| r.reply().ok())
            .and_then(|r| crate::x11::property32(&r, kind, min, max))
            .unwrap_or_default()
    }
    fn prop_text(&self, win: u32, atom: u32) -> String {
        self.conn
            .get_property(false, win, atom, AtomEnum::ANY, 0, 16384)
            .ok()
            .and_then(|c| c.reply().ok())
            .map(|r| {
                String::from_utf8_lossy(&r.value)
                    .trim_end_matches('\0')
                    .into()
            })
            .unwrap_or_default()
    }
    fn put32(&self, win: u32, name: &str, kind: impl Into<u32>, data: &[u32]) -> Result<()> {
        self.conn
            .change_property32(PropMode::REPLACE, win, self.a(name), kind, data)?;
        Ok(())
    }
    fn put_text(&self, win: u32, name: &str, text: &str) -> Result<()> {
        self.conn.change_property8(
            PropMode::REPLACE,
            win,
            self.a(name),
            self.a("UTF8_STRING"),
            text.as_bytes(),
        )?;
        Ok(())
    }
    fn client_id(&self, win: u32) -> Option<ClientId> {
        let id = ClientId(win);
        if self.clients.contains_key(&id) {
            Some(id)
        } else {
            self.frames
                .get(&win)
                .or_else(|| self.titles.get(&win))
                .copied()
        }
    }
    fn visible(&self, id: ClientId) -> bool {
        self.clients
            .get(&id)
            .is_some_and(|c| c.visible(self.monitors[c.monitor.0].mask(), self.showing))
    }
    fn selected_client(&self) -> Option<ClientId> {
        self.monitors[self.selected.0].selected
    }
    fn current_time(&self) -> u32 {
        self.event_time
    }
    fn next_event(&mut self) -> Result<Option<Event>> {
        if let Some(event) = self.pending_events.pop_front() {
            return Ok(Some(event));
        }
        Ok(self.conn.poll_for_event()?)
    }
    fn record_time(&mut self, t: u32) {
        if t != 0 && (self.last_user_time == 0 || timestamp_current(t, self.last_user_time)) {
            self.last_user_time = t;
        }
        self.event_time = t;
    }
    fn rect_monitor(&self, rect: Rect) -> MonitorId {
        let mut best = self.selected;
        let mut area = 0;
        for m in &self.monitors {
            let overlap = rect.intersection(m.rect);
            if overlap > area {
                area = overlap;
                best = m.id;
            }
        }
        best
    }
    fn tags_event(&self) -> Value {
        let m = &self.monitors[self.selected.0];
        let (mut occupied, mut urgent) = (0, 0);
        for id in &m.clients {
            let c = &self.clients[id];
            if c.tags & config::TAG_MASK != config::TAG_MASK {
                occupied |= c.tags;
                if c.flags.urgent {
                    urgent |= c.tags;
                }
            }
        }
        let states: Vec<_> = (0..9)
            .map(|i| {
                let b = 1 << i;
                if urgent & b != 0 {
                    "U"
                } else if m.mask() & b != 0 {
                    "A"
                } else if occupied & b != 0 {
                    "O"
                } else {
                    "I"
                }
            })
            .collect();
        json!({"event":"tags_state","tag_mask":m.mask(),"tags_state":states})
    }
    fn client_json(&self, c: &Client) -> Value {
        json!({"name":c.title,"win_id":c.id.0,"class":c.class,"tags":c.tags,"width":c.geom.w,"height":c.geom.h,"floating":c.flags.floating,"maximized":c.maximized(),"focused":self.monitors[c.monitor.0].selected==Some(c.id),"minimized":c.flags.minimized})
    }
    fn state(&self) -> Value {
        let m = &self.monitors[self.selected.0];
        let mut v = json!({"ok":true,"tag_mask":m.mask(),"layout":m.active.layout.symbol(),"mfact":m.active.mfact as f64});
        if m.active.nmaster > 0 {
            v["nmaster"] = json!(m.active.nmaster);
        }
        if m.gap != 0 {
            v["gaps"] = json!(m.gap);
        }
        if m.active.right {
            v["isrighttiled"] = json!(true);
        }
        if !m.clients.is_empty() {
            v["clients"] = json!(
                m.clients
                    .iter()
                    .map(|id| self.client_json(&self.clients[id]))
                    .collect::<Vec<_>>()
            );
        }
        v
    }
    fn request(&mut self, r: &Request) -> Result<Value> {
        match r.cmd.as_str() {
            "get_state" => return Ok(self.state()),
            "tags_state" => {
                let mut v = self.tags_event();
                v.as_object_mut().unwrap().remove("event");
                v.as_object_mut().unwrap().remove("tag_mask");
                v["ok"] = json!(true);
                return Ok(v);
            }
            "subscribe_tags" => return Ok(self.tags_event()),
            "get_clients" => {
                let clients: Vec<_> = self
                    .monitors
                    .iter()
                    .flat_map(|m| m.clients.iter())
                    .filter_map(|id| self.clients.get(id))
                    .filter(|c| !c.flags.dock)
                    .map(|c| self.client_json(c))
                    .collect();
                return Ok(if clients.is_empty() {
                    json!({"ok":true})
                } else {
                    json!({"ok":true,"clients":clients})
                });
            }
            "keybinds" => return Ok(self.keybinds()),
            "view" => self.view(r.mask, false)?,
            "toggleview" => self.view(r.mask, true)?,
            "tag" => self.tag(r.mask, false)?,
            "toggletag" => self.tag(r.mask, true)?,
            "reload" => self.reload()?,
            "quit" => self.running = false,
            "focus_window" => {
                anyhow::ensure!(r.win_id != 0, "invalid win_id");
                let id = self
                    .frames
                    .get(&r.win_id)
                    .copied()
                    .or_else(|| {
                        self.clients
                            .contains_key(&ClientId(r.win_id))
                            .then_some(ClientId(r.win_id))
                    })
                    .context("window not found")?;
                let c = &self.clients[&id];
                self.selected = c.monitor;
                let mask = focus_tag_mask(c.tags, self.monitors[self.selected.0].mask());
                if mask != 0 {
                    self.view(mask, false)?;
                }
                self.restore_client(id)?;
                self.focus(Some(id))?;
                self.restack()?;
            }
            "open-window-picker" | "open-minimized-picker" => {
                self.workers.send(Job::Shell(r.cmd.clone()));
            }
            "open-launcher" | "open-keybinds" | "open-emoji-picker" => {
                self.workers
                    .send(Job::Spawn(vec!["sadeshell".into(), format!("--{}", r.cmd)]));
            }
            _ => return Ok(json!({"ok":false,"error":"unknown command"})),
        }
        self.flush_stacking()?;
        Ok(json!({"ok":true}))
    }
    fn cleanup(&mut self) -> Result<()> {
        if self.drag.take().is_some() {
            let _ = self.conn.ungrab_pointer(x11rb::CURRENT_TIME);
            let _ = self.conn.ungrab_keyboard(x11rb::CURRENT_TIME);
        }
        let ids = self.order.clone();
        for id in ids {
            if let Err(e) = self.unmanage(id, false, true) {
                self.logger.debug(&format!("cleanup: {e}"));
            }
        }
        for name in [
            "_NET_SUPPORTED",
            "_NET_SUPPORTING_WM_CHECK",
            "_NET_CLIENT_LIST",
            "_NET_CLIENT_LIST_STACKING",
            "_NET_NUMBER_OF_DESKTOPS",
            "_NET_DESKTOP_NAMES",
            "_NET_DESKTOP_GEOMETRY",
            "_NET_DESKTOP_VIEWPORT",
            "_NET_CURRENT_DESKTOP",
            "_NET_WORKAREA",
            "_NET_ACTIVE_WINDOW",
            "_NET_SHOWING_DESKTOP",
        ] {
            let _ = self.conn.delete_property(self.root, self.a(name));
        }
        if self.wallpaper != 0 {
            let mut owns_background = false;
            for name in ["_XROOTPMAP_ID", "ESETROOT_PMAP_ID"] {
                if self.get32(self.root, name).first() == Some(&self.wallpaper) {
                    owns_background = true;
                    let _ = self.conn.delete_property(self.root, self.a(name));
                }
            }
            if owns_background {
                // The root's background attribute retains a server reference
                // even after FreePixmap; release it before freeing our pixmap.
                let _ = self.conn.change_window_attributes(
                    self.root,
                    &ChangeWindowAttributesAux::new().background_pixmap(x11rb::NONE),
                );
            }
            let _ = self.conn.free_pixmap(self.wallpaper);
            self.wallpaper = 0;
        }
        let _ = self.conn.ungrab_key(0, self.root, ModMask::ANY);
        let _ = self
            .conn
            .set_input_focus(InputFocus::POINTER_ROOT, self.root, x11rb::CURRENT_TIME);
        if self
            .conn
            .get_selection_owner(self.selection)?
            .reply()?
            .owner
            == self.check
        {
            let _ = self
                .conn
                .set_selection_owner(x11rb::NONE, self.selection, x11rb::CURRENT_TIME);
        }
        let _ = self.conn.change_window_attributes(
            self.root,
            &ChangeWindowAttributesAux::new().cursor(x11rb::NONE),
        );
        for cursor in self.cursors {
            let _ = self.conn.free_cursor(cursor);
        }
        let _ = self.conn.destroy_window(self.check);
        if let Some(s) = self.server.as_mut() {
            s.flush();
        }
        self.server.take();
        self.conn.flush()?;
        self.logger.info("sadewm-rs stopped");
        Ok(())
    }
}
impl Drop for Wm {
    fn drop(&mut self) {
        for id in self.signal_ids.drain(..) {
            signal_hook::low_level::unregister(id);
        }
    }
}
