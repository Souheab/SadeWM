fn main() {
    println!("cargo:rerun-if-env-changed=SADEWM_REVISION");
    println!("cargo:rerun-if-changed=../.git/HEAD");
    let revision = std::env::var("SADEWM_REVISION")
        .ok()
        .or_else(|| {
            // Commits update the branch ref without changing HEAD's symbolic
            // contents. Track both loose and packed refs, including worktrees.
            let mut refs = vec!["HEAD".to_owned(), "packed-refs".to_owned()];
            if let Some(branch) = git_output(&["symbolic-ref", "--quiet", "HEAD"]) {
                refs.push(branch);
            }
            for reference in refs {
                if let Some(path) = git_output(&["rev-parse", "--git-path", &reference]) {
                    println!("cargo:rerun-if-changed={path}");
                }
            }
            git_output(&["rev-parse", "HEAD"])
        })
        .unwrap_or_else(|| "unknown".into());
    println!("cargo:rustc-env=SADEWM_REVISION={revision}");
}

fn git_output(args: &[&str]) -> Option<String> {
    std::process::Command::new("git")
        .args(args)
        .output()
        .ok()
        .filter(|out| out.status.success())
        .map(|out| String::from_utf8_lossy(&out.stdout).trim().to_owned())
}
