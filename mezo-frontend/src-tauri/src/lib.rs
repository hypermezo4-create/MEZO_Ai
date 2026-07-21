#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .plugin(tauri_plugin_shell::init())
    .setup(|app| {
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }
      
      // Spawn the backend sidecar
      use tauri_plugin_shell::ShellExt;
      use tauri_plugin_shell::process::CommandEvent;
      
      let sidecar_command = app.shell().sidecar("mezo-backend")
        .expect("failed to create `mezo-backend` binary command");
      let (mut rx, _child) = sidecar_command.spawn()
        .expect("Failed to spawn sidecar");

      tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
          if let CommandEvent::Stdout(line) = event {
            println!("Sidecar: {:?}", String::from_utf8_lossy(&line));
          }
        }
      });

      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
