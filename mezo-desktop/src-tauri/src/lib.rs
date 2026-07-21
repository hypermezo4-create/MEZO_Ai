use tauri::{tray::TrayIconBuilder, menu::{Menu, MenuItem}};
use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            let quit_i = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&quit_i])?;

            let tray = TrayIconBuilder::new()
                .menu(&menu)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "quit" => {
                        app.exit(0);
                    }
                    _ => {}
                })
                .build(app)?;

            // Read-only status: set tooltip
            tray.set_tooltip(Some("MEZO AI - Kill Switch ARMED"))?;
            
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("failed to run the MEZO AI desktop application");
}
