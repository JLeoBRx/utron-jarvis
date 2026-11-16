//! SAFRA — prova de conceito da casca do desktop em Tauri.
//!
//! Avalia, para a decisão AD-07: janela com a interface web local, ícone na bandeja com menu, fechar a janela
//! recolhendo para a bandeja, notificação nativa, instância única, e um processo do Assistant iniciado,
//! supervisionado e encerrado pela casca. O áudio fica no processo do Assistant (Python), não na casca.
//!
//! `--self-test`: grava em SAFRA_POC_REPORT (ou na saída padrão) os tempos medidos e o resultado de cada item,
//! para o instrumento `desktop/measure_shell.py`.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{Read, Write};
use std::net::TcpStream;
use std::process::{Child, Command};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde_json::{json, Value};
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, RunEvent, State, WindowEvent};
use tauri_plugin_notification::NotificationExt;

struct Shell {
    started: Instant,
    self_test: bool,
    backend: Mutex<Option<Child>>,
    backend_port: u16,
    tray_ok: Mutex<Option<String>>,
}

/// GET /api/v1/health no Assistant local, sem dependência extra (o Assistant só escuta em 127.0.0.1).
fn backend_health(port: u16) -> Result<(u128, Value), String> {
    let started = Instant::now();
    let address = format!("127.0.0.1:{port}");
    let mut stream = TcpStream::connect_timeout(&address.parse().map_err(|e| format!("{e}"))?, Duration::from_secs(2))
        .map_err(|e| format!("sem conexão com o Assistant: {e}"))?;
    stream.set_read_timeout(Some(Duration::from_secs(3))).map_err(|e| e.to_string())?;
    let request = format!("GET /api/v1/health HTTP/1.1\r\nHost: {address}\r\nConnection: close\r\n\r\n");
    stream.write_all(request.as_bytes()).map_err(|e| e.to_string())?;
    let mut response = String::new();
    stream.read_to_string(&mut response).map_err(|e| e.to_string())?;
    let elapsed = started.elapsed().as_millis();
    if !response.starts_with("HTTP/1.1 200") {
        return Err(response.lines().next().unwrap_or("resposta vazia").to_string());
    }
    let body = response.split("\r\n\r\n").nth(1).unwrap_or("{}");
    let value: Value = serde_json::from_str(body).map_err(|e| format!("resposta inválida: {e}"))?;
    Ok((elapsed, value))
}

fn start_backend() -> Result<Option<Child>, String> {
    let Ok(program) = std::env::var("SAFRA_POC_BACKEND") else { return Ok(None) };
    let args: Vec<String> = std::env::var("SAFRA_POC_BACKEND_ARGS").unwrap_or_default()
        .split_whitespace().map(str::to_string).collect();
    Command::new(program).args(args).spawn().map(Some).map_err(|e| format!("não foi possível iniciar o Assistant: {e}"))
}

fn stop_backend(shell: &Shell) {
    if let Some(mut child) = shell.backend.lock().map(|mut g| g.take()).unwrap_or(None) {
        let _ = child.kill();
        let _ = child.wait();
    }
}

fn show_main(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

fn notify(app: &AppHandle, body: &str) -> Result<(), String> {
    app.notification().builder().title("SAFRA").body(body).show().map_err(|e| e.to_string())
}

#[tauri::command]
fn backend_status(shell: State<'_, Shell>) -> Value {
    match backend_health(shell.backend_port) {
        Ok((ms, value)) => json!({ "ok": true, "latency_ms": ms, "health": value }),
        Err(error) => json!({ "ok": false, "error": error }),
    }
}

#[tauri::command]
fn send_notification(app: AppHandle) -> Value {
    match notify(&app, "Notificação de teste da prova de conceito.") {
        Ok(()) => json!({ "ok": true }),
        Err(error) => json!({ "ok": false, "error": error }),
    }
}

/// Chamado pela página quando termina de carregar: mede o tempo até a interface utilizável.
#[tauri::command]
fn ui_ready(app: AppHandle, shell: State<'_, Shell>) -> Value {
    let ready_ms = shell.started.elapsed().as_millis();
    if !shell.self_test {
        return json!({ "ready_ms": ready_ms });
    }
    // espera curta pelo Assistant, se ele foi iniciado pela casca
    let mut health = backend_health(shell.backend_port);
    let deadline = Instant::now() + Duration::from_secs(20);
    while health.is_err() && shell.backend.lock().map(|g| g.is_some()).unwrap_or(false) && Instant::now() < deadline {
        std::thread::sleep(Duration::from_millis(250));
        health = backend_health(shell.backend_port);
    }
    let report = json!({
        "shell": "tauri",
        "ready_ms": ready_ms,
        "tray": shell.tray_ok.lock().map(|g| g.clone()).unwrap_or(None),
        "notification": match notify(&app, "Autoteste da casca") { Ok(()) => "ok".to_string(), Err(e) => e },
        "backend": match health { Ok((ms, value)) => json!({ "ok": true, "latency_ms": ms, "health": value }),
                                  Err(e) => json!({ "ok": false, "error": e }) },
        "platform": std::env::consts::OS,
    });
    let line = format!("SELFTEST_READY {report}");
    match std::env::var("SAFRA_POC_REPORT") {
        Ok(path) => { let _ = std::fs::write(path, &line); }
        Err(_) => println!("{line}"),
    }
    report
}

fn main() {
    let self_test = std::env::args().any(|a| a == "--self-test");
    let port: u16 = std::env::var("SAFRA_POC_BACKEND_PORT").ok().and_then(|p| p.parse().ok()).unwrap_or(47800);
    let shell = Shell { started: Instant::now(), self_test, backend: Mutex::new(None), backend_port: port, tray_ok: Mutex::new(None) };

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| show_main(app)))
        .plugin(tauri_plugin_notification::init())
        .manage(shell)
        .setup(|app| {
            let state = app.state::<Shell>();
            match start_backend() {
                Ok(child) => *state.backend.lock().expect("trava do processo") = child,
                Err(error) => eprintln!("{error}"),
            }
            let show = MenuItem::with_id(app, "mostrar", "Mostrar o SAFRA", true, None::<&str>)?;
            let test = MenuItem::with_id(app, "notificar", "Enviar notificação de teste", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "sair", "Sair", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&show, &test, &quit])?;
            let tray = TrayIconBuilder::with_id("principal")
                .tooltip("SAFRA (prova de conceito)")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id().as_ref() {
                    "mostrar" => show_main(app),
                    "notificar" => { let _ = notify(app, "Notificação de teste da prova de conceito."); }
                    "sair" => app.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = event {
                        show_main(tray.app_handle());
                    }
                });
            let tray = match app.default_window_icon() { Some(icon) => tray.icon(icon.clone()), None => tray };
            let outcome = tray.build(app).map(|_| "ok".to_string()).unwrap_or_else(|e| e.to_string());
            *state.tray_ok.lock().expect("trava da bandeja") = Some(outcome);
            Ok(())
        })
        .on_window_event(|window, event| {
            // Fechar a janela recolhe para a bandeja; "Sair" no menu encerra a casca e o Assistant.
            if let WindowEvent::CloseRequested { api, .. } = event {
                if !window.state::<Shell>().self_test {
                    let _ = window.hide();
                    api.prevent_close();
                }
            }
        })
        .invoke_handler(tauri::generate_handler![backend_status, send_notification, ui_ready])
        .build(tauri::generate_context!())
        .expect("a casca não pôde ser montada");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            stop_backend(&handle.state::<Shell>());
        }
    });
}
