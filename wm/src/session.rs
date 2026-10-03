use crate::config::Display;
use anyhow::{Result, anyhow};
use std::{
    fs::{File, OpenOptions},
    io::{Read, Write},
    os::unix::{fs::OpenOptionsExt, net::UnixStream, process::CommandExt},
    path::PathBuf,
    process::{Command, Stdio},
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
        mpsc::{self, Receiver, SyncSender},
    },
    time::{Duration, Instant},
};

pub struct Logger {
    file: Option<File>,
    fifo: Option<File>,
    path: Option<PathBuf>,
    debug: bool,
}
impl Logger {
    pub fn new(debug: bool) -> Self {
        let data = std::env::var_os("XDG_DATA_HOME")
            .map(PathBuf::from)
            .or_else(|| std::env::var_os("HOME").map(|p| PathBuf::from(p).join(".local/share")));
        let mut logger = Self {
            file: None,
            fifo: None,
            path: None,
            debug,
        };
        if let Some(dir) = data.map(|p| p.join("sadewm")) {
            let _ = std::fs::create_dir_all(&dir);
            logger.file = OpenOptions::new()
                .append(true)
                .create(true)
                .open(dir.join("sadewm.log"))
                .ok();
            let path = dir.join("sadewm.fifo");
            let mut owns_fifo = false;
            if !path.exists() {
                owns_fifo = rustix::fs::mknodat(
                    rustix::fs::CWD,
                    &path,
                    rustix::fs::FileType::Fifo,
                    rustix::fs::Mode::from_raw_mode(0o644),
                    0,
                )
                .is_ok();
            }
            logger.fifo = OpenOptions::new()
                .read(true)
                .write(true)
                .custom_flags(rustix::fs::OFlags::NONBLOCK.bits() as i32)
                .open(&path)
                .ok();
            logger.path = owns_fifo.then_some(path);
        }
        logger
    }
    pub fn info(&mut self, text: &str) {
        let line = format!("INFO: {text}\n");
        if let Some(f) = &mut self.file {
            let _ = f.write_all(line.as_bytes());
        }
        if let Some(f) = &mut self.fifo {
            let _ = f.write(line.as_bytes());
        }
        if self.debug {
            eprint!("{line}");
        }
    }
    pub fn debug(&mut self, text: &str) {
        if self.debug {
            self.info(text);
        }
    }
}
impl Drop for Logger {
    fn drop(&mut self) {
        if let Some(p) = &self.path {
            let _ = std::fs::remove_file(p);
        }
    }
}
pub enum Job {
    Spawn(Vec<String>),
    Shell(String),
    Display(usize, Option<Display>),
    Suspend,
}
pub struct Workers {
    tx: Option<SyncSender<Job>>,
    pub results: Receiver<(usize, Result<()>)>,
    cancelled: Arc<AtomicBool>,
    threads: Vec<std::thread::JoinHandle<()>>,
}
impl Default for Workers {
    fn default() -> Self {
        Self::new()
    }
}
impl Workers {
    pub fn new() -> Self {
        let (tx, rx) = mpsc::sync_channel(32);
        let (result_tx, results) = mpsc::sync_channel(64);
        let rx = Arc::new(Mutex::new(rx));
        let cancelled = Arc::new(AtomicBool::new(false));
        let mut threads = Vec::new();
        for _ in 0..2 {
            let rx = Arc::clone(&rx);
            let results = result_tx.clone();
            let cancelled = Arc::clone(&cancelled);
            threads.push(std::thread::spawn(move || {
                // A fixed number of reapers owns all launched children. Never create a
                // thread per application or wait for its lifetime on the WM thread.
                let mut children: Vec<std::process::Child> = Vec::new();
                while !cancelled.load(Ordering::Acquire) {
                    children.retain_mut(|child| matches!(child.try_wait(), Ok(None)));
                    let job = { rx.lock().unwrap().recv_timeout(Duration::from_millis(100)) };
                    let job = match job {
                        Ok(job) => job,
                        Err(mpsc::RecvTimeoutError::Timeout) => continue,
                        Err(mpsc::RecvTimeoutError::Disconnected) => break,
                    };
                    if cancelled.load(Ordering::Acquire) {
                        break;
                    }
                    match job {
                        Job::Spawn(args) => {
                            if let Some((program, args)) = args.split_first() {
                                if children.len() >= 256 {
                                    continue;
                                }
                                if let Ok(child) = Command::new(program)
                                    .args(args)
                                    .stdin(Stdio::null())
                                    .stdout(Stdio::null())
                                    .stderr(Stdio::null())
                                    .process_group(0)
                                    .spawn()
                                {
                                    children.push(child);
                                }
                            }
                        }
                        Job::Shell(command) => {
                            if matches!(
                                command.as_str(),
                                "open-window-picker" | "open-minimized-picker"
                            ) && shell_command(&command).is_err()
                                && !cancelled.load(Ordering::Acquire)
                                && children.len() < 256
                                && let Ok(child) = Command::new("sadeshell")
                                    .arg(format!("--{command}"))
                                    .stdin(Stdio::null())
                                    .stdout(Stdio::null())
                                    .stderr(Stdio::null())
                                    .process_group(0)
                                    .spawn()
                            {
                                children.push(child);
                            }
                        }
                        Job::Display(id, display) => {
                            let _ = results.try_send((id, apply_display(&display, &cancelled)));
                        }
                        Job::Suspend => {
                            let _ = run_bounded_cancel(
                                "systemctl",
                                &["suspend"],
                                Duration::from_secs(10),
                                Some(&cancelled),
                            );
                        }
                    }
                }
            }));
        }
        Self {
            tx: Some(tx),
            results,
            cancelled,
            threads,
        }
    }
    pub fn send(&self, job: Job) -> bool {
        self.tx.as_ref().is_some_and(|tx| tx.try_send(job).is_ok())
    }
}
impl Drop for Workers {
    fn drop(&mut self) {
        self.cancelled.store(true, Ordering::Release);
        self.tx.take();
        for worker in self.threads.drain(..) {
            let _ = worker.join();
        }
    }
}
pub fn run_bounded(program: &str, args: &[&str], timeout: Duration) -> Result<String> {
    run_bounded_cancel(program, args, timeout, None)
}
fn run_bounded_cancel(
    program: &str,
    args: &[&str],
    timeout: Duration,
    cancelled: Option<&AtomicBool>,
) -> Result<String> {
    let mut child = Command::new(program)
        .args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .process_group(0)
        .spawn()?;
    let mut stdout = child
        .stdout
        .take()
        .ok_or_else(|| anyhow!("missing stdout"))?;
    rustix::fs::fcntl_setfl(&stdout, rustix::fs::OFlags::NONBLOCK)?;
    let until = Instant::now() + timeout;
    let mut data = Vec::new();
    let mut buffer = [0u8; 4096];
    let mut status = None;
    let mut eof = false;
    loop {
        // Bound each read batch so continuous output cannot starve the deadline.
        for _ in 0..64 {
            match stdout.read(&mut buffer) {
                Ok(0) => {
                    eof = true;
                    break;
                }
                Ok(n) => {
                    if data.len() + n <= 1024 * 1024 {
                        data.extend_from_slice(&buffer[..n]);
                    }
                }
                Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => break,
                Err(e) => {
                    let _ = child.kill();
                    let _ = child.wait();
                    return Err(e.into());
                }
            }
        }
        if status.is_none() {
            status = child.try_wait()?;
        }
        if eof && status.is_some() {
            break;
        }
        if Instant::now() >= until || cancelled.is_some_and(|flag| flag.load(Ordering::Acquire)) {
            if let Some(pid) = rustix::process::Pid::from_raw(child.id() as i32) {
                let _ = rustix::process::kill_process_group(pid, rustix::process::Signal::KILL);
            }
            let _ = child.kill();
            let _ = child.wait();
            return Err(anyhow!("signal: killed"));
        }
        std::thread::sleep(Duration::from_millis(10));
    }
    let status = status.ok_or_else(|| anyhow!("missing process status"))?;
    anyhow::ensure!(
        status.success(),
        "exit status {}",
        status.code().unwrap_or(-1)
    );
    Ok(String::from_utf8_lossy(&data).into_owned())
}
pub fn display_args(d: &Display, query: &str) -> Option<Vec<String>> {
    if !d.enabled || d.resolution.is_empty() || d.refresh_rate <= 0. {
        return None;
    }
    let mut output = d.output.trim().to_owned();
    if output.is_empty() || output == "default" {
        output = query
            .lines()
            .find_map(|l| {
                let mut f = l.split_whitespace();
                let name = f.next()?;
                (f.next() == Some("connected")).then(|| name.to_owned())
            })
            .unwrap_or_default();
    }
    if output.is_empty() {
        return None;
    }
    let rate = format!("{:.2}", d.refresh_rate);
    Some(vec![
        "--output".into(),
        output,
        "--mode".into(),
        d.resolution.clone(),
        "--rate".into(),
        rate.trim_end_matches('0').trim_end_matches('.').into(),
    ])
}
fn apply_display(d: &Option<Display>, cancelled: &AtomicBool) -> Result<()> {
    let Some(d) = d else {
        return Ok(());
    };
    let start = Instant::now();
    let query = run_bounded_cancel(
        "xrandr",
        &["--query"],
        Duration::from_secs(10),
        Some(cancelled),
    )
    .map_err(|e| anyhow!("xrandr query failed: {e}"))?;
    let Some(args) = display_args(d, &query) else {
        return Ok(());
    };
    let remaining = Duration::from_secs(10).saturating_sub(start.elapsed());
    run_bounded_cancel(
        "xrandr",
        &args.iter().map(String::as_str).collect::<Vec<_>>(),
        remaining,
        Some(cancelled),
    )
    .map_err(|e| anyhow!("xrandr apply failed: {e}"))
    .map(|_| ())
}
pub fn shell_socket_candidates(display: &str, runtime: Option<&str>) -> Vec<PathBuf> {
    let display = if display.is_empty() { ":0" } else { display };
    let display = match display.rsplit_once('.') {
        Some((base, suffix))
            if !suffix.is_empty() && suffix.chars().all(|c| c.is_ascii_digit()) =>
        {
            base
        }
        _ => display,
    };
    let display = display.trim_start_matches(':').replace('/', "_");
    let name = format!(
        "sadeshell-{}.sock",
        if display.is_empty() { "0" } else { &display }
    );
    let mut dirs = Vec::new();
    if let Some(r) = runtime.filter(|r| !r.is_empty()) {
        dirs.push(PathBuf::from(r).join(&name));
    }
    let tmp = PathBuf::from("/tmp").join(name);
    if !dirs.contains(&tmp) {
        dirs.push(tmp);
    }
    dirs
}
fn connect_shell(path: &std::path::Path) -> Result<UnixStream> {
    use rustix::{
        event::{PollFd, PollFlags, Timespec, poll},
        net::{self, AddressFamily, SocketAddrUnix, SocketFlags, SocketType},
    };
    let fd = net::socket_with(
        AddressFamily::UNIX,
        SocketType::STREAM,
        SocketFlags::CLOEXEC | SocketFlags::NONBLOCK,
        None,
    )?;
    if let Err(error) = net::connect(&fd, &SocketAddrUnix::new(path)?) {
        if error != rustix::io::Errno::INPROGRESS {
            return Err(error.into());
        }
        let mut fds = [PollFd::new(&fd, PollFlags::OUT)];
        anyhow::ensure!(
            poll(
                &mut fds,
                Some(&Timespec {
                    tv_sec: 0,
                    tv_nsec: 250_000_000
                })
            )? > 0,
            "shell connect timed out"
        );
        net::sockopt::socket_error(&fd)??;
    }
    let stream = UnixStream::from(fd);
    stream.set_nonblocking(false)?;
    Ok(stream)
}
pub fn shell_command(command: &str) -> Result<()> {
    for path in shell_socket_candidates(
        &std::env::var("DISPLAY").unwrap_or_default(),
        std::env::var("XDG_RUNTIME_DIR").ok().as_deref(),
    ) {
        if let Ok(mut s) = connect_shell(&path) {
            s.set_read_timeout(Some(Duration::from_millis(250)))?;
            s.set_write_timeout(Some(Duration::from_millis(250)))?;
            s.write_all(format!("{command}\n").as_bytes())?;
            let mut buf = [0; 256];
            let n = s.read(&mut buf)?;
            if String::from_utf8_lossy(&buf[..n]).trim() == "ok" {
                return Ok(());
            }
        }
    }
    Err(anyhow!("shell IPC unavailable"))
}
pub fn monitor_timeout(minutes: i64) -> u16 {
    if minutes <= 0 {
        0
    } else {
        minutes.saturating_mul(60).min(65535) as u16
    }
}
pub fn idle_sleep(idle: u64, minutes: i64, triggered: bool) -> (bool, bool) {
    if minutes <= 0 {
        return (false, false);
    }
    let Some(timeout) = (minutes as u64).checked_mul(60_000) else {
        return (false, false);
    };
    if idle < timeout {
        (false, false)
    } else {
        (!triggered, true)
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn display_selection_and_rate_format() {
        let mut d = Display {
            enabled: true,
            output: "default".into(),
            resolution: "1920x1080".into(),
            refresh_rate: 60.,
        };
        let query = "DP-1 disconnected\nHDMI-1 connected primary 1920x1080+0+0";
        assert_eq!(
            display_args(&d, query).unwrap(),
            ["--output", "HDMI-1", "--mode", "1920x1080", "--rate", "60"]
        );
        d.refresh_rate = 59.94;
        assert_eq!(display_args(&d, query).unwrap()[5], "59.94");
        d.enabled = false;
        assert!(display_args(&d, query).is_none());
    }
    #[test]
    fn power_limits() {
        assert_eq!(monitor_timeout(1440), 65535);
        assert_eq!(idle_sleep(120_000, 2, false), (true, true));
        assert_eq!(idle_sleep(120_000, 2, true), (false, true));
        assert_eq!(idle_sleep(100, 2, true), (false, false));
    }
    #[test]
    fn display_normalization() {
        assert_eq!(
            shell_socket_candidates(":1.0", Some("/tmp")),
            vec![PathBuf::from("/tmp/sadeshell-1.sock")]
        );
    }
    #[test]
    fn subprocess_descendant_pipe_deadline() {
        let start = Instant::now();
        assert!(
            run_bounded(
                "sh",
                &["-c", "sleep 10 & exit 0"],
                Duration::from_millis(100)
            )
            .is_err()
        );
        assert!(start.elapsed() < Duration::from_secs(2));
    }
}
