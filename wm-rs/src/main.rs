use sadewm_rs::{config::Cli, wm::Wm};

fn main() {
    if let Err(error) = run() {
        eprintln!("sadewm-rs: {error:#}");
        std::process::exit(1);
    }
}

fn run() -> anyhow::Result<()> {
    let cli = Cli::parse(std::env::args().skip(1))?;
    if cli.version {
        println!(
            "sadewm (Rust) {} ({})",
            env!("CARGO_PKG_VERSION"),
            env!("SADEWM_REVISION")
        );
        return Ok(());
    }
    if cli.help {
        println!(
            "sadewm-rs [-v] [-d] [-t pixels] [-c wm.toml] [-custom-config directory] [-no-config]\n\nRust SADE window manager; configuration and IPC are compatible with sadewm."
        );
        return Ok(());
    }
    Wm::connect(cli)?.run()
}
