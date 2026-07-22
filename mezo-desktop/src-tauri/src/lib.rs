use std::{process::{Command, Stdio}, sync::{Arc, atomic::{AtomicBool, Ordering}}, thread, time::Duration};
use tauri::{menu::{Menu, MenuItem}, tray::TrayIconBuilder};

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

fn tunnel(stop: Arc<AtomicBool>) {
    thread::spawn(move || {
        while !stop.load(Ordering::Relaxed) {
            let mut command = Command::new("fly");
            command.args(["proxy", "8787:8080", "--app", "mezo-web", "--bind-addr", "127.0.0.1"])
                .stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::null());
            #[cfg(target_os = "windows")]
            command.creation_flags(0x08000000);
            match command.spawn() {
                Ok(mut child) => {
                    while !stop.load(Ordering::Relaxed) {
                        if child.try_wait().ok().flatten().is_some() { break; }
                        thread::sleep(Duration::from_millis(500));
                    }
                    let _ = child.kill();
                }
                Err(_) => thread::sleep(Duration::from_secs(2)),
            }
            if !stop.load(Ordering::Relaxed) { thread::sleep(Duration::from_secs(1)); }
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
            TrayIconBuilder::new().menu(&menu).on_menu_event(|app, event| {
                if event.id.as_ref() == "quit" { app.exit(0); }
            }).tooltip("MEZO AI private Fly cluster").build(app)?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build MEZO AI")
        .run(move |_handle, event| {
            if matches!(event, tauri::RunEvent::Exit | tauri::RunEvent::ExitRequested { .. }) {
                stop.store(true, Ordering::Relaxed);
            }
        });
}
