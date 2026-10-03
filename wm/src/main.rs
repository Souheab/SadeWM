use sadewm::{config::Cli, wm::Wm};

fn main() {
    if let Err(error) = run() {
        eprintln!("sadewm: {error:#}");
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
            "sadewm [-v] [-d] [-t pixels] [-c wm.toml] [-custom-config directory] [-no-config]\n\nSADE X11 window manager (Rust)."
        );
        return Ok(());
    }
    Wm::connect(cli)?.run()
}
