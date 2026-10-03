use anyhow::{Result, bail};
use serde::Deserialize;
use std::{collections::BTreeMap, path::PathBuf};

pub const TAG_MASK: u32 = 0x1ff;
pub const SUPER: u16 = 64;
pub const ALT: u16 = 8;
pub const SHIFT: u16 = 1;
pub const CTRL: u16 = 4;

#[derive(Clone, Debug, Default)]
pub struct Cli {
    pub version: bool,
    pub help: bool,
    pub debug: bool,
    pub no_config: bool,
    pub top: Option<u32>,
    pub config: Option<PathBuf>,
    pub custom: Option<PathBuf>,
}
impl Cli {
    pub fn parse(args: impl IntoIterator<Item = String>) -> Result<Self> {
        let mut cli = Self::default();
        let mut args = args.into_iter();
        while let Some(raw) = args.next() {
            if !raw.starts_with('-') {
                break;
            }
            let raw = raw.trim_start_matches('-');
            let (key, inline) = raw
                .split_once('=')
                .map_or((raw, None), |(k, v)| (k, Some(v)));
            let mut value = || {
                inline
                    .map(str::to_owned)
                    .or_else(|| args.next())
                    .ok_or_else(|| anyhow::anyhow!("missing value for -{key}"))
            };
            let boolean = || -> Result<bool> {
                Ok(match inline {
                    None | Some("true" | "1" | "t" | "TRUE" | "True" | "T") => true,
                    Some("false" | "0" | "f" | "FALSE" | "False" | "F") => false,
                    _ => bail!("invalid boolean for -{key}"),
                })
            };
            match key {
                "v" => cli.version = boolean()?,
                "h" | "help" => cli.help = true,
                "d" => cli.debug = boolean()?,
                "no-config" => cli.no_config = boolean()?,
                "t" => cli.top = Some(value()?.parse()?),
                "c" => cli.config = Some(value()?.into()),
                "custom-config" => cli.custom = Some(value()?.into()),
                "" => break,
                _ => bail!("unknown flag -{key}"),
            }
        }
        Ok(cli)
    }
    pub fn paths(&self, home: Option<PathBuf>) -> Paths {
        if self.no_config {
            return Paths::default();
        }
        let dir = self
            .custom
            .clone()
            .filter(|p| !p.as_os_str().is_empty())
            .or_else(|| {
                home.filter(|p| !p.as_os_str().is_empty())
                    .map(|p| p.join(".config/sade"))
            });
        Paths {
            wm: self
                .config
                .clone()
                .filter(|p| !p.as_os_str().is_empty())
                .or_else(|| dir.as_ref().map(|p| p.join("wm.toml"))),
            settings: dir.as_ref().map(|p| p.join("settings.toml")),
            startup: dir.map(|p| p.join("startup.sh")),
        }
    }
}
#[derive(Clone, Debug, Default)]
pub struct Paths {
    pub wm: Option<PathBuf>,
    pub settings: Option<PathBuf>,
    pub startup: Option<PathBuf>,
}

#[derive(Clone, Debug, Deserialize, Default)]
#[serde(default)]
pub struct Rule {
    pub class: String,
    pub instance: String,
    pub title: String,
    #[serde(deserialize_with = "go_u32")]
    pub tags_mask: u32,
    pub isfloating: bool,
    pub monitor: i32,
}
#[derive(Clone, Debug, Deserialize, Default)]
#[serde(default)]
pub struct Binding {
    #[serde(rename = "mod")]
    pub modifiers: Vec<String>,
    pub key: String,
    pub action: String,
    pub cmd: String,
    #[serde(skip)]
    pub command_is_shell: bool,
    pub layout: String,
    pub arg_int: Option<i32>,
    #[serde(deserialize_with = "go_optional_u32")]
    pub arg_uint: Option<u32>,
    pub arg_float: Option<f32>,
}
// Go's TOML schema accepts signed integers, then casts tag masks/arguments.
fn go_u32<'de, D: serde::Deserializer<'de>>(d: D) -> Result<u32, D::Error> {
    Ok(i64::deserialize(d)? as u32)
}
fn go_optional_u32<'de, D: serde::Deserializer<'de>>(d: D) -> Result<Option<u32>, D::Error> {
    Ok(Option::<i64>::deserialize(d)?.map(|n| n as u32))
}
impl Binding {
    pub fn mask(&self) -> u16 {
        self.modifiers.iter().fold(0, |v, m| {
            v | match m.to_ascii_lowercase().as_str() {
                "super" => SUPER,
                "alt" => ALT,
                "shift" => SHIFT,
                "control" | "ctrl" => CTRL,
                _ => 0,
            }
        })
    }
    pub fn int(&self) -> i32 {
        self.arg_int.unwrap_or(0)
    }
    pub fn uint(&self) -> u32 {
        self.arg_uint.unwrap_or(0)
    }
    pub fn float(&self) -> f32 {
        self.arg_float.unwrap_or(0.)
    }
}
#[derive(Clone, Debug)]
pub struct Config {
    pub border: i32,
    pub gap: i32,
    pub snap: i32,
    pub top: i32,
    pub bottom: i32,
    pub mfact: f32,
    pub nmaster: usize,
    pub resize_hints: bool,
    pub lock_fullscreen: bool,
    pub center_floating: bool,
    pub bar_on_top: bool,
    pub normal_border: String,
    pub selected_border: String,
    pub title: TitleColors,
    pub rules: Vec<Rule>,
    pub keys: Vec<Binding>,
}
#[derive(Clone, Debug, Deserialize)]
#[serde(default)]
pub struct TitleColors {
    pub bg: String,
    pub bg_focused: String,
    pub sep: String,
    pub text: String,
    pub close: String,
    pub above: String,
    pub minimize: String,
}
impl Default for TitleColors {
    fn default() -> Self {
        Self {
            bg: "#24283b".into(),
            bg_focused: "#2a2e45".into(),
            sep: "#414868".into(),
            text: "#c0caf5".into(),
            close: "#f7768e".into(),
            above: "#7aa2f7".into(),
            minimize: "#9ece6a".into(),
        }
    }
}
impl Default for Config {
    fn default() -> Self {
        Self {
            border: 2,
            gap: 10,
            snap: 32,
            top: 40,
            bottom: 0,
            mfact: 0.5,
            nmaster: 1,
            resize_hints: true,
            lock_fullscreen: true,
            center_floating: true,
            bar_on_top: false,
            normal_border: "#444444".into(),
            selected_border: "#0099ff".into(),
            title: TitleColors::default(),
            rules: vec![Rule {
                class: "Gimp".into(),
                isfloating: true,
                monitor: -1,
                ..Rule::default()
            }],
            keys: default_keys(),
        }
    }
}
impl Config {
    /// Reload scalar overrides over the active configuration, as the Go WM does.
    /// Rules/key bindings are rebuilt from defaults on every reload.
    pub fn load(&mut self, path: Option<&PathBuf>) -> Result<()> {
        self.keys = default_keys();
        self.rules = Self::default().rules;
        let Some(path) = path else {
            return Ok(());
        };
        let text = match std::fs::read_to_string(path) {
            Ok(s) => s,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(()),
            Err(e) => return Err(e.into()),
        };
        self.apply(&text)
    }
    pub fn apply(&mut self, text: &str) -> Result<()> {
        let mut next = self.clone();
        next.apply_inner(text)?;
        *self = next;
        Ok(())
    }
    fn apply_inner(&mut self, text: &str) -> Result<()> {
        let doc: toml::Value = toml::from_str(text)?;
        let get = |path: &str| path.split('.').try_fold(&doc, |v, k| v.get(k));
        for section in ["appearance", "bar", "colors", "titlebar", "layout"] {
            if let Some(value) = get(section) {
                anyhow::ensure!(value.is_table(), "{section} must be a table");
            }
        }
        for (paths, kind) in [
            (
                "appearance.borderpx appearance.gappx appearance.snap layout.topoffset layout.bottomoffset layout.nmaster",
                "integer",
            ),
            (
                "layout.resizehints layout.lockfullscreen layout.center_floating bar.always_on_top",
                "boolean",
            ),
            (
                "colors.norm.border colors.sel.border titlebar.bg titlebar.bg_focused titlebar.sep titlebar.text titlebar.close titlebar.above titlebar.minimize",
                "string",
            ),
            ("layout.mfact", "number"),
        ] {
            for path in paths.split_whitespace() {
                if let Some(v) = get(path) {
                    let valid = match kind {
                        "integer" => v.is_integer(),
                        "boolean" => v.is_bool(),
                        "string" => v.is_str(),
                        _ => v.is_float() || v.is_integer(),
                    };
                    anyhow::ensure!(valid, "invalid {kind} at {path}");
                }
            }
        }
        for (path, target) in [
            ("appearance.borderpx", &mut self.border),
            ("appearance.gappx", &mut self.gap),
            ("appearance.snap", &mut self.snap),
            ("layout.topoffset", &mut self.top),
            ("layout.bottomoffset", &mut self.bottom),
        ] {
            if let Some(n) = get(path).and_then(toml::Value::as_integer) {
                *target = n.clamp(0, 65535) as i32;
            }
        }
        if let Some(n) = get("layout.mfact")
            .and_then(|v| v.as_float().or_else(|| v.as_integer().map(|i| i as f64)))
        {
            self.mfact = (n as f32).clamp(0.05, 0.95);
        }
        if let Some(n) = get("layout.nmaster").and_then(toml::Value::as_integer) {
            self.nmaster = n.clamp(0, 65535) as usize;
        }
        for (path, target) in [
            ("layout.resizehints", &mut self.resize_hints),
            ("layout.lockfullscreen", &mut self.lock_fullscreen),
            ("layout.center_floating", &mut self.center_floating),
            ("bar.always_on_top", &mut self.bar_on_top),
        ] {
            if let Some(v) = get(path).and_then(toml::Value::as_bool) {
                *target = v;
            }
        }
        for (path, target) in [
            ("colors.norm.border", &mut self.normal_border),
            ("colors.sel.border", &mut self.selected_border),
            ("titlebar.bg", &mut self.title.bg),
            ("titlebar.bg_focused", &mut self.title.bg_focused),
            ("titlebar.sep", &mut self.title.sep),
            ("titlebar.text", &mut self.title.text),
            ("titlebar.close", &mut self.title.close),
            ("titlebar.above", &mut self.title.above),
            ("titlebar.minimize", &mut self.title.minimize),
        ] {
            if let Some(v) = get(path)
                .and_then(toml::Value::as_str)
                .filter(|s| !s.is_empty())
            {
                *target = v.into();
            }
        }
        if let Some(v) = doc.get("rules") {
            let rules: Vec<Rule> = v.clone().try_into()?;
            if !rules.is_empty() {
                self.rules = rules;
            }
        }
        if let Some(v) = doc.get("keys") {
            let keys: Vec<Binding> = v.clone().try_into()?;
            for mut k in keys {
                if !k.cmd.is_empty() {
                    k.command_is_shell = true;
                    k.layout.clear();
                    k.arg_float = None;
                    k.arg_uint = None;
                    k.arg_int = None;
                } else if !k.layout.is_empty() {
                    k.arg_int = Some(i32::from(k.layout == "float"));
                    k.arg_float = None;
                    k.arg_uint = None;
                } else if k.arg_float.is_some() {
                    k.arg_uint = None;
                    k.arg_int = None;
                } else if k.arg_uint.is_some() {
                    k.arg_int = None;
                }
                if k.action == "none" {
                    self.keys
                        .retain(|b| !(b.mask() == k.mask() && b.key == k.key));
                } else {
                    upsert(&mut self.keys, k);
                }
            }
        }
        if let Some(rows) = doc.get("tagkeys").and_then(toml::Value::as_array) {
            for row in rows {
                if let (Some(key), Some(tag)) = (
                    row.get("key").and_then(toml::Value::as_str),
                    row.get("tag").and_then(toml::Value::as_integer),
                ) {
                    if !(0..=8).contains(&tag) {
                        continue;
                    }
                    for (mods, action) in [
                        ("super", "view"),
                        ("super+ctrl", "toggleview"),
                        ("super+shift", "tag"),
                        ("super+ctrl+shift", "toggletag"),
                    ] {
                        let mut k = binding(mods, key, action);
                        k.arg_uint = Some(1 << tag);
                        upsert(&mut self.keys, k);
                    }
                }
            }
        }
        Ok(())
    }
}
fn upsert(keys: &mut Vec<Binding>, key: Binding) {
    if let Some(old) = keys
        .iter_mut()
        .find(|b| b.mask() == key.mask() && b.key == key.key)
    {
        *old = key;
    } else {
        keys.push(key);
    }
}
pub fn binding(mods: &str, key: &str, action: &str) -> Binding {
    Binding {
        modifiers: mods.split('+').map(str::to_owned).collect(),
        key: key.into(),
        action: action.into(),
        ..Binding::default()
    }
}
pub fn default_keys() -> Vec<Binding> {
    let mut keys = Vec::new();
    for (mods, key, action, arg) in [
        ("super", "p", "spawn", "sadeshell --open-launcher"),
        ("super", "s", "spawn", "sadeshell --open-keybinds"),
        ("super", "period", "spawn", "sadeshell --open-emoji-picker"),
        ("alt", "s", "shellcmd", "open-window-picker"),
        ("super+shift", "Tab", "shellcmd", "open-minimized-picker"),
        ("super", "Return", "spawn", "wezterm"),
        ("super", "Tab", "focusstack", "1"),
        ("super", "j", "focusdown", ""),
        ("super", "k", "focusup", ""),
        ("super", "h", "focusleft", ""),
        ("super", "l", "focusright", ""),
        ("super+shift", "j", "swapdown", ""),
        ("super+shift", "k", "swapup", ""),
        ("super+shift", "h", "swapleft", ""),
        ("super+shift", "l", "swapright", ""),
        ("alt", "k", "incnmaster", "1"),
        ("alt", "j", "incnmaster", "-1"),
        ("super+ctrl", "h", "setmfact", "-0.05"),
        ("super+ctrl", "l", "setmfact", "0.05"),
        ("super+shift", "Return", "zoom", ""),
        ("super", "q", "killclient", ""),
        ("super", "n", "minimize", ""),
        ("super+ctrl", "n", "restore", ""),
        ("super", "t", "setlayout", "0"),
        ("super+shift", "f", "setlayout", "1"),
        ("super", "f", "togglefullscr", ""),
        ("super", "m", "togglemaximize", ""),
        ("super", "space", "layoutnext", ""),
        ("super+shift", "space", "layoutprev", ""),
        ("super+ctrl", "space", "togglefloating", ""),
        ("super", "0", "view", "4294967295"),
        ("super", "Escape", "swapview", ""),
        ("super", "Left", "viewprev", ""),
        ("super", "Right", "viewnext", ""),
        ("super+shift", "0", "tag", "4294967295"),
        ("super", "comma", "focusmon", "-1"),
        ("super+alt", "period", "focusmon", "1"),
        ("super+shift", "comma", "tagmon", "-1"),
        ("super+alt+shift", "period", "tagmon", "1"),
        ("super", "minus", "setgaps", "-1"),
        ("super", "equal", "setgaps", "1"),
        ("super+shift", "equal", "setgaps", "0"),
        ("super+shift", "r", "reloadconfig", ""),
        ("super+shift", "q", "spawn", "sadeshell --confirm-exit"),
        ("super+ctrl+shift", "q", "quit", ""),
    ] {
        let mut b = binding(mods, key, action);
        if matches!(action, "spawn" | "shellcmd") {
            b.cmd = arg.into();
        } else {
            b.arg_int = arg.parse().ok();
            b.arg_uint = arg.parse().ok();
            b.arg_float = arg.parse().ok();
        }
        keys.push(b);
    }
    for tag in 0..9 {
        for (mods, action) in [
            ("super", "view"),
            ("super+ctrl", "toggleview"),
            ("super+shift", "tag"),
            ("super+ctrl+shift", "toggletag"),
        ] {
            let mut b = binding(mods, &(tag + 1).to_string(), action);
            b.arg_uint = Some(1 << tag);
            keys.push(b);
        }
    }
    keys
}
#[derive(Clone, Debug, Default, Deserialize)]
#[serde(default)]
pub struct Settings {
    pub display: Option<Display>,
    pub power: Option<Power>,
}
#[derive(Clone, Debug, Default, Deserialize)]
#[serde(default)]
pub struct Display {
    pub enabled: bool,
    pub output: String,
    pub resolution: String,
    pub refresh_rate: f64,
}
#[derive(Clone, Debug, Default, Deserialize)]
#[serde(default)]
pub struct Power {
    pub monitor_timeout_minutes: i64,
    pub sleep_timeout_minutes: i64,
}
impl Settings {
    pub fn load(path: Option<&PathBuf>) -> Self {
        path.and_then(|p| std::fs::read_to_string(p).ok())
            .and_then(|s| toml::from_str(&s).ok())
            .unwrap_or_default()
    }
}
pub fn modifier_names(mask: u16) -> Vec<&'static str> {
    [
        (SUPER, "Super"),
        (ALT, "Alt"),
        (CTRL, "Ctrl"),
        (SHIFT, "Shift"),
    ]
    .into_iter()
    .filter_map(|(m, s)| (mask & m != 0).then_some(s))
    .collect()
}
pub fn keysyms() -> BTreeMap<&'static str, u32> {
    include!("keysyms.rs")
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn signed_toml_tag_masks_preserve_legacy_casts() {
        let mut config = Config::default();
        config.apply("[[rules]]\nclass='example'\ntags_mask=-1\n[[keys]]\nmod=['Super']\nkey='a'\naction='view'\narg_uint=-1\n").unwrap();
        assert_eq!(config.rules[0].tags_mask, u32::MAX);
        assert_eq!(
            config
                .keys
                .iter()
                .find(|b| b.key == "a" && b.mask() == SUPER)
                .unwrap()
                .uint(),
            u32::MAX
        );
    }
    #[test]
    fn malformed_reload_is_atomic() {
        let mut c = Config::default();
        assert!(
            c.apply("[appearance]\ngappx=19\n[layout]\ncenter_floating='no'")
                .is_err()
        );
        assert_eq!(c.gap, 10);
        assert!(
            c.apply("[appearance]\ngappx=19\n[[rules]]\nmonitor='no'")
                .is_err()
        );
        assert_eq!(c.gap, 10);
    }
    #[test]
    fn binding_overrides_preserve_order_and_argument_precedence() {
        let mut c = Config::default();
        c.apply("[[keys]]\nmod=['super']\nkey='p'\naction='spawn'\ncmd='echo hi'\narg_int=99\n[[tagkeys]]\nkey='1'\ntag=8").unwrap();
        assert_eq!(c.keys[0].key, "p");
        assert_eq!(c.keys[0].cmd, "echo hi");
        assert_eq!(c.keys[0].int(), 0);
        assert!(c.keys[0].command_is_shell);
        assert_eq!(
            c.keys
                .iter()
                .find(|k| k.key == "1" && k.mask() == SUPER)
                .unwrap()
                .uint(),
            256
        );
    }
    #[test]
    fn missing_power_section_leaves_server_settings_alone() {
        let s: Settings = toml::from_str("[display]\nenabled=false").unwrap();
        assert!(s.power.is_none());
        let s: Settings = toml::from_str("[power]\nmonitor_timeout_minutes=0").unwrap();
        assert_eq!(s.power.unwrap().monitor_timeout_minutes, 0);
    }
    #[test]
    fn paths_and_cli() {
        let cli =
            Cli::parse(["--custom-config=/tmp/sade", "-c", "/tmp/custom.toml"].map(str::to_owned))
                .unwrap();
        let p = cli.paths(Some("/home/test".into()));
        assert_eq!(p.wm.unwrap(), PathBuf::from("/tmp/custom.toml"));
        assert_eq!(p.startup.unwrap(), PathBuf::from("/tmp/sade/startup.sh"));
        assert!(
            Cli {
                no_config: true,
                ..cli
            }
            .paths(None)
            .wm
            .is_none()
        );
    }
    #[test]
    fn reload_and_unbind() {
        let mut c = Config::default();
        c.apply("[appearance]\ngappx=17\n[[keys]]\nmod=['super']\nkey='q'\naction='none'")
            .unwrap();
        assert_eq!(c.gap, 17);
        assert!(!c.keys.iter().any(|k| k.key == "q" && k.mask() == SUPER));
        c.apply("[layout]\nmfact=0.65").unwrap();
        assert_eq!(c.gap, 17);
        assert_eq!(c.mfact, 0.65);
    }
    #[test]
    fn invalid_dimensions_are_bounded() {
        let mut c = Config::default();
        c.apply("[appearance]\ngappx=-2\n[layout]\nnmaster=-1")
            .unwrap();
        assert_eq!((c.gap, c.nmaster), (0, 0));
    }
}
