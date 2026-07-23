use std::{
    process::{Command, Stdio},
    sync::{
        Arc,
        atomic::{AtomicBool, Ordering},
    },
    thread,
    time::Duration,
};
use tauri::{
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
};

const FLY_APP: &str = "mezo-ai";

fn control_machine_hostname() -> Result<String, String> {
    let output = Command::new("fly")
        .args(["machines", "list", "--app", FLY_APP, "--json"])
        .output()
        .map_err(|error| format!("cannot run flyctl: {error}"))?;
    if !output.status.success() {
        return Err("cannot inventory mezo-ai Machines; check flyctl authentication".into());
    }
    let machines: serde_json::Value = serde_json::from_slice(&output.stdout)
        .map_err(|_| "flyctl returned invalid Machine inventory".to_string())?;
    for machine in machines.as_array().into_iter().flatten() {
        let role = machine
            .pointer("/config/metadata/role")
            .and_then(|v| v.as_str())
            .or_else(|| {
                machine
                    .pointer("/config/metadata/fly_process_group")
                    .and_then(|v| v.as_str())
            });
        let state = machine.get("state").and_then(|v| v.as_str());
        if role != Some("control") || state != Some("started") {
            continue;
        }
        let Some(id) = machine.get("id").and_then(|v| v.as_str()) else {
            continue;
        };
        let status = Command::new("fly")
            .args(["machine", "status", id, "--app", FLY_APP, "--json"])
            .output();
        if let Ok(status) = status {
            let body = String::from_utf8_lossy(&status.stdout).to_ascii_lowercase();
            if status.status.success() && !body.contains("\"critical\"") {
                return Ok(format!("{id}.vm.{FLY_APP}.internal"));
            }
        }
    }
    Err("no healthy control Machine exists; run `fly machines list --app mezo-ai`".into())
}

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

fn tunnel(stop: Arc<AtomicBool>) {
    thread::spawn(move || {
        while !stop.load(Ordering::Relaxed) {
            let remote_host = match control_machine_hostname() {
                Ok(host) => host,
                Err(error) => {
                    eprintln!("MEZO tunnel: {error}");
                    thread::sleep(Duration::from_secs(2));
                    continue;
                }
            };
            let mut command = Command::new("fly");
            command
                .args([
                    "proxy",
                    "8787:8080",
                    &remote_host,
                    "--app",
                    FLY_APP,
                    "--bind-addr",
                    "127.0.0.1",
                ])
                .stdin(Stdio::null())
                .stdout(Stdio::null())
                .stderr(Stdio::null());
            #[cfg(target_os = "windows")]
            command.creation_flags(0x08000000);
            match command.spawn() {
                Ok(mut child) => {
                    while !stop.load(Ordering::Relaxed) {
                        if child.try_wait().ok().flatten().is_some() {
                            break;
                        }
                        thread::sleep(Duration::from_millis(500));
                    }
                    let _ = child.kill();
                }
                Err(_) => thread::sleep(Duration::from_secs(2)),
            }
            if !stop.load(Ordering::Relaxed) {
                thread::sleep(Duration::from_secs(1));
            }
        }
    });
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let stop = Arc::new(AtomicBool::new(false));
    tunnel(stop.clone());
    tauri::Builder::default()
        .setup(|app| {
            let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&quit])?;
            TrayIconBuilder::new()
                .menu(&menu)
                .on_menu_event(|app, event| {
                    if event.id.as_ref() == "quit" {
                        app.exit(0);
                    }
                })
                .tooltip("MEZO AI private Fly cluster")
                .build(app)?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build MEZO AI")
        .run(move |_handle, event| {
            if matches!(
                event,
                tauri::RunEvent::Exit | tauri::RunEvent::ExitRequested { .. }
            ) {
                stop.store(true, Ordering::Relaxed);
            }
        });
}
