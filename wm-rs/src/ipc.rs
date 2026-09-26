//! Nonblocking, bounded Unix socket transport. WM requests are executed by the owner thread.
use anyhow::Result;
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    collections::BTreeMap,
    io::{Read, Write},
    os::unix::net::{UnixListener, UnixStream},
    path::PathBuf,
    time::{Duration, Instant},
};
pub const MAX_REQUEST: usize = 64 * 1024;
const TIMEOUT: Duration = Duration::from_secs(2);
#[derive(Clone, Debug, Default)]
pub struct Request {
    pub cmd: String,
    pub mask: u32,
    pub win_id: u32,
}
impl<'de> Deserialize<'de> for Request {
    fn deserialize<D: serde::Deserializer<'de>>(d: D) -> std::result::Result<Self, D::Error> {
        struct RequestVisitor;
        impl<'de> serde::de::Visitor<'de> for RequestVisitor {
            type Value = Request;
            fn expecting(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
                formatter.write_str("a request object or null")
            }
            fn visit_unit<E: serde::de::Error>(self) -> std::result::Result<Request, E> {
                Ok(Request::default())
            }
            fn visit_map<M: serde::de::MapAccess<'de>>(
                self,
                mut map: M,
            ) -> std::result::Result<Request, M::Error> {
                let mut req = Request::default();
                // Preserve wire order: Go applies repeated/case-insensitive
                // fields in their original order, ignoring null values.
                while let Some(key) = map.next_key::<String>()? {
                    let value = map.next_value::<Value>()?;
                    if value.is_null() {
                        continue;
                    }
                    match key.to_ascii_lowercase().as_str() {
                        "cmd" => {
                            req.cmd = value
                                .as_str()
                                .ok_or_else(|| serde::de::Error::custom("invalid cmd"))?
                                .into()
                        }
                        "mask" | "win_id" => {
                            let n = value
                                .as_u64()
                                .and_then(|n| u32::try_from(n).ok())
                                .ok_or_else(|| {
                                    serde::de::Error::custom("invalid window or tag id")
                                })?;
                            if key.eq_ignore_ascii_case("mask") {
                                req.mask = n;
                            } else {
                                req.win_id = n;
                            }
                        }
                        _ => {}
                    }
                }
                Ok(req)
            }
        }
        d.deserialize_any(RequestVisitor)
    }
}
struct Peer {
    stream: UnixStream,
    input: Vec<u8>,
    output: Vec<u8>,
    written: usize,
    deadline: Instant,
    read: bool,
    subscription: bool,
    pending: Option<Vec<u8>>,
}
pub struct Server {
    listener: UnixListener,
    path: PathBuf,
    peers: BTreeMap<usize, Peer>,
    next: usize,
}
pub fn socket_path(display: Option<&str>, custom: Option<&str>) -> PathBuf {
    if let Some(p) = custom.filter(|p| !p.is_empty()) {
        return p.into();
    }
    match display.filter(|s| !s.is_empty()) {
        None => "/tmp/sadewm.sock".into(),
        Some(d) => format!(
            "/tmp/sadewm-{}.sock",
            d.trim_start_matches(':').replace('.', "-")
        )
        .into(),
    }
}
impl Server {
    pub fn bind() -> Result<Self> {
        Self::at(socket_path(
            std::env::var("DISPLAY").ok().as_deref(),
            std::env::var("SADEWM_SOCKET").ok().as_deref(),
        ))
    }
    pub fn at(path: PathBuf) -> Result<Self> {
        if path.exists() {
            anyhow::ensure!(
                UnixStream::connect(&path).is_err(),
                "IPC socket already in use: {}",
                path.display()
            );
            std::fs::remove_file(&path)?;
        }
        let listener = UnixListener::bind(&path)?;
        listener.set_nonblocking(true)?;
        Ok(Self {
            listener,
            path,
            peers: BTreeMap::new(),
            next: 0,
        })
    }
    pub fn poll_fds(&self) -> Vec<rustix::event::PollFd<'_>> {
        use rustix::event::{PollFd, PollFlags};
        let mut result = vec![PollFd::new(&self.listener, PollFlags::IN)];
        for p in self.peers.values() {
            let flags = if !p.read {
                PollFlags::IN
            } else if p.written < p.output.len() {
                PollFlags::OUT
            } else {
                PollFlags::empty()
            };
            result.push(PollFd::new(&p.stream, flags));
        }
        result
    }
    pub fn tick(&mut self) -> Vec<(usize, Request)> {
        for _ in 0..64 {
            let Ok((stream, _)) = self.listener.accept() else {
                break;
            };
            if self.peers.len() >= 128 {
                continue;
            }
            if stream.set_nonblocking(true).is_err() {
                continue;
            }
            let id = self.next;
            self.next = self.next.wrapping_add(1);
            self.peers.insert(
                id,
                Peer {
                    stream,
                    input: Vec::new(),
                    output: Vec::new(),
                    written: 0,
                    deadline: Instant::now() + TIMEOUT,
                    read: false,
                    subscription: false,
                    pending: None,
                },
            );
        }
        let mut requests = Vec::new();
        let mut dead = Vec::new();
        // Half-closing the request is part of the protocol; POLLHUP means the
        // reader has also gone away. Reap those peers even between tag updates
        // so a closed idle subscription cannot keep poll waking continuously.
        {
            use rustix::event::{PollFd, PollFlags, Timespec, poll};
            let mut fds: Vec<_> = self
                .peers
                .values()
                .map(|p| PollFd::new(&p.stream, PollFlags::empty()))
                .collect();
            if !fds.is_empty()
                && poll(
                    &mut fds,
                    Some(&Timespec {
                        tv_sec: 0,
                        tv_nsec: 0,
                    }),
                )
                .is_ok()
            {
                for (&id, fd) in self.peers.keys().zip(&fds) {
                    if fd
                        .revents()
                        .intersects(PollFlags::HUP | PollFlags::ERR | PollFlags::NVAL)
                    {
                        dead.push(id);
                    }
                }
            }
        }
        for id in dead.drain(..) {
            self.peers.remove(&id);
        }
        for (&id, p) in &mut self.peers {
            if !p.read {
                let mut buf = [0u8; 4096];
                let mut eof = false;
                loop {
                    match p.stream.read(&mut buf) {
                        Ok(0) => {
                            eof = true;
                            break;
                        }
                        Ok(n) => {
                            p.input.extend_from_slice(&buf[..n]);
                            if p.input.len() > MAX_REQUEST {
                                break;
                            }
                        }
                        Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => break,
                        Err(_) => {
                            dead.push(id);
                            break;
                        }
                    }
                }
                if p.input.len() > MAX_REQUEST {
                    queue(p, json!({"ok":false,"error":"request too large"}));
                } else if eof {
                    if p.input.is_empty() {
                        dead.push(id);
                        continue;
                    }
                    match serde_json::from_slice::<Request>(&p.input) {
                        Ok(req) => {
                            p.read = true;
                            p.deadline = Instant::now() + TIMEOUT;
                            requests.push((id, req));
                        }
                        Err(_) => queue(p, json!({"ok":false,"error":"invalid JSON"})),
                    }
                } else if Instant::now() >= p.deadline {
                    dead.push(id);
                }
            }
            if p.read && p.output.is_empty() && !p.subscription && Instant::now() >= p.deadline {
                queue(
                    p,
                    json!({"ok":false,"error":"window manager response timed out"}),
                );
            }
            if p.read && p.written < p.output.len() {
                match p.stream.write(&p.output[p.written..]) {
                    Ok(0) => dead.push(id),
                    Ok(n) => p.written += n,
                    Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {}
                    Err(_) => dead.push(id),
                }
                if Instant::now() >= p.deadline {
                    dead.push(id);
                }
            }
            if p.read && !p.output.is_empty() && p.written == p.output.len() {
                if p.subscription {
                    p.output.clear();
                    p.written = 0;
                    if let Some(next) = p.pending.take() {
                        p.output = next;
                        p.deadline = Instant::now() + TIMEOUT;
                    }
                } else {
                    dead.push(id);
                }
            }
        }
        for id in dead {
            self.peers.remove(&id);
        }
        requests
    }
    pub fn respond(&mut self, id: usize, value: Value) {
        if let Some(p) = self.peers.get_mut(&id) {
            queue(p, value);
        }
    }
    pub fn subscribe(&mut self, id: usize, value: Value) {
        if let Some(p) = self.peers.get_mut(&id) {
            p.subscription = true;
            queue(p, value);
        }
    }
    pub fn broadcast(&mut self, value: &Value) {
        for p in self.peers.values_mut().filter(|p| p.subscription) {
            if p.output.is_empty() {
                queue(p, value.clone());
            } else {
                p.pending = Some(encode(value));
            }
        }
    }
    pub fn flush(&mut self) {
        // Do not read requests here: only tick's caller can dispatch them.
        let mut dead = Vec::new();
        for (&id, p) in &mut self.peers {
            if p.written < p.output.len() {
                match p.stream.write(&p.output[p.written..]) {
                    Ok(0) => dead.push(id),
                    Ok(n) => p.written += n,
                    Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {}
                    Err(_) => dead.push(id),
                }
            }
            if !p.output.is_empty() && p.written == p.output.len() {
                if p.subscription {
                    p.output.clear();
                    p.written = 0;
                    if let Some(next) = p.pending.take() {
                        p.output = next;
                        p.deadline = Instant::now() + TIMEOUT;
                    }
                } else {
                    dead.push(id);
                }
            }
        }
        for id in dead {
            self.peers.remove(&id);
        }
    }
}
fn encode(value: &Value) -> Vec<u8> {
    let mut v = serde_json::to_vec(value).unwrap_or_default();
    v.push(b'\n');
    v
}
fn queue(p: &mut Peer, value: Value) {
    p.output = encode(&value);
    p.written = 0;
    p.read = true;
    p.deadline = Instant::now() + TIMEOUT;
}
impl Drop for Server {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.path);
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    use std::net::Shutdown;
    #[test]
    fn nulls_case_insensitivity_and_invalid_fields_match_go_decoder() {
        let repeated: Request = serde_json::from_str(
            r#"{"cmd":"unknown","CMD":"get_state","mask":2,"MASK":3,"mask":null}"#,
        )
        .unwrap();
        assert_eq!(repeated.cmd, "get_state");
        assert_eq!(repeated.mask, 3);
        assert_eq!(serde_json::from_str::<Request>("null").unwrap().cmd, "");
        assert_eq!(
            serde_json::from_str::<Request>(r#"{"cMd":"view","mask":null}"#)
                .unwrap()
                .cmd,
            "view"
        );
        for invalid in [
            r#"{"mask":-1}"#,
            r#"{"mask":4294967296}"#,
            r#"{"cmd":1}"#,
            r#"[]"#,
        ] {
            assert!(serde_json::from_str::<Request>(invalid).is_err());
        }
    }
    #[test]
    fn slow_subscriber_keeps_only_latest_queued_state_and_socket_is_removed() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("stream.sock");
        let mut server = Server::at(path.clone()).unwrap();
        let mut client = UnixStream::connect(&path).unwrap();
        client.write_all(br#"{"cmd":"subscribe_tags"}"#).unwrap();
        client.shutdown(Shutdown::Write).unwrap();
        let id = server.tick()[0].0;
        server.subscribe(id, json!({"event":"tags_state","tag_mask":1}));
        for mask in 2..10000 {
            server.broadcast(&json!({"event":"tags_state","tag_mask":mask}));
        }
        let peer = &server.peers[&id];
        assert!(peer.output.len() < 100 && peer.pending.as_ref().unwrap().len() < 100);
        assert_eq!(
            serde_json::from_slice::<Value>(peer.pending.as_ref().unwrap()).unwrap()["tag_mask"],
            9999
        );
        drop(server);
        assert!(!path.exists());
    }
    #[test]
    fn idle_subscriber_is_reaped_only_after_its_reader_closes() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("stream.sock");
        let mut server = Server::at(path.clone()).unwrap();
        let mut client = UnixStream::connect(path).unwrap();
        client.write_all(br#"{"cmd":"subscribe_tags"}"#).unwrap();
        client.shutdown(Shutdown::Write).unwrap();
        let id = server.tick()[0].0;
        server.subscribe(id, json!({"event":"tags_state"}));
        server.tick();
        server.tick();
        assert!(server.peers.contains_key(&id));
        drop(client);
        server.tick();
        assert!(server.peers.is_empty());
    }
    #[test]
    fn names() {
        assert_eq!(
            socket_path(Some(":1.2"), None),
            PathBuf::from("/tmp/sadewm-1-2.sock")
        );
        assert_eq!(
            socket_path(None, Some("/tmp/custom")),
            PathBuf::from("/tmp/custom")
        );
    }
    #[test]
    fn request_roundtrip_and_limits() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("wm.sock");
        let mut server = Server::at(path.clone()).unwrap();
        let mut client = UnixStream::connect(&path).unwrap();
        client.write_all(b"{\"cmd\":\"view\",\"mask\":4}").unwrap();
        client.shutdown(Shutdown::Write).unwrap();
        let requests = server.tick();
        assert_eq!(requests[0].1.mask, 4);
        server.respond(requests[0].0, json!({"ok":true}));
        server.tick();
        let mut data = String::new();
        client.read_to_string(&mut data).unwrap();
        assert_eq!(data, "{\"ok\":true}\n");
        let mut client = UnixStream::connect(&path).unwrap();
        client.write_all(&vec![b' '; MAX_REQUEST + 1]).unwrap();
        server.tick();
        let mut data = String::new();
        client.read_to_string(&mut data).unwrap();
        assert!(data.contains("request too large"));
    }
}
