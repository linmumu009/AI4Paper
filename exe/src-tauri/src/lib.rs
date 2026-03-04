use base64::{engine::general_purpose::STANDARD as B64, Engine as _};
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager, WindowEvent,
};

/// 绕过系统代理，直连目标 URL 并返回响应体文本。
/// 仅用于关键只读接口的兜底（如 /api/dates、/api/digest/{date}）。
/// 不携带 Cookie，不用于需要认证的接口。
#[tauri::command]
async fn direct_get(url: String) -> Result<String, String> {
    let client = reqwest::Client::builder()
        .no_proxy()
        .timeout(std::time::Duration::from_secs(20))
        .build()
        .map_err(|e| format!("CLIENT_BUILD:{}", e))?;

    let resp = client
        .get(&url)
        .header("Accept", "application/json")
        .header("User-Agent", "AI4Papers-Desktop/1.0")
        .send()
        .await
        .map_err(|e| format!("NETWORK:{}", e))?;

    let status = resp.status().as_u16();
    let body = resp.text().await.map_err(|e| format!("READ_BODY:{}", e))?;

    if status >= 400 {
        return Err(format!("HTTP_ERROR:{}:{}", status, body));
    }
    Ok(body)
}

// ---------------------------------------------------------------------------
// 通用 HTTP 请求命令 —— 前端所有 axios / fetch 调用均通过此命令发出，
// 完全绕过 WebView2 的网络栈，解决桌面端无法直接 fetch 外部域名的问题。
// ---------------------------------------------------------------------------

#[derive(serde::Serialize)]
struct DirectResponse {
    status: u16,
    headers: std::collections::HashMap<String, String>,
    body: String,
}

#[tauri::command]
async fn direct_request(
    method: String,
    url: String,
    headers: std::collections::HashMap<String, String>,
    body: Option<String>,
) -> Result<DirectResponse, String> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(60))
        .build()
        .map_err(|e| format!("CLIENT_BUILD:{}", e))?;

    let req_method = match method.to_uppercase().as_str() {
        "GET" => reqwest::Method::GET,
        "POST" => reqwest::Method::POST,
        "PUT" => reqwest::Method::PUT,
        "PATCH" => reqwest::Method::PATCH,
        "DELETE" => reqwest::Method::DELETE,
        "HEAD" => reqwest::Method::HEAD,
        "OPTIONS" => reqwest::Method::OPTIONS,
        other => return Err(format!("UNSUPPORTED_METHOD:{}", other)),
    };

    let mut builder = client.request(req_method, &url);
    builder = builder.header("User-Agent", "AI4Papers-Desktop/1.0");

    for (k, v) in &headers {
        builder = builder.header(k.as_str(), v.as_str());
    }

    if let Some(ref b) = body {
        builder = builder.body(b.clone());
    }

    let resp = builder
        .send()
        .await
        .map_err(|e| format!("NETWORK:{}", e))?;

    let status = resp.status().as_u16();
    let mut resp_headers = std::collections::HashMap::new();
    for (k, v) in resp.headers().iter() {
        if let Ok(val) = v.to_str() {
            resp_headers.insert(k.to_string(), val.to_string());
        }
    }
    let resp_body = resp.text().await.map_err(|e| format!("READ_BODY:{}", e))?;

    Ok(DirectResponse {
        status,
        headers: resp_headers,
        body: resp_body,
    })
}

// ---------------------------------------------------------------------------
// 文件上传命令 —— 处理 multipart/form-data 请求（如知识库附件上传）。
// 前端将文件内容以 base64 编码传入，Rust 重建 multipart 表单后发送。
// ---------------------------------------------------------------------------

#[tauri::command]
async fn direct_upload(
    url: String,
    headers: std::collections::HashMap<String, String>,
    file_name: String,
    file_base64: String,
    mime_type: String,
    form_fields: std::collections::HashMap<String, String>,
) -> Result<DirectResponse, String> {
    // Decode base64 → raw bytes
    let bytes = B64.decode(&file_base64).map_err(|e| format!("BASE64_DECODE:{}", e))?;

    // Build multipart form
    let file_part = reqwest::multipart::Part::bytes(bytes)
        .file_name(file_name.clone())
        .mime_str(&mime_type)
        .map_err(|e| format!("MIME_STR:{}", e))?;

    let mut form = reqwest::multipart::Form::new().part("file", file_part);
    for (k, v) in &form_fields {
        form = form.text(k.clone(), v.clone());
    }

    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(120))
        .build()
        .map_err(|e| format!("CLIENT_BUILD:{}", e))?;

    let mut builder = client.post(&url).multipart(form);
    builder = builder.header("User-Agent", "AI4Papers-Desktop/1.0");

    // Apply extra headers (skip Content-Type — reqwest sets it with the boundary)
    for (k, v) in &headers {
        let kl = k.to_lowercase();
        if kl != "content-type" && kl != "user-agent" {
            builder = builder.header(k.as_str(), v.as_str());
        }
    }

    let resp = builder
        .send()
        .await
        .map_err(|e| format!("NETWORK:{}", e))?;

    let status = resp.status().as_u16();
    let mut resp_headers = std::collections::HashMap::new();
    for (k, v) in resp.headers().iter() {
        if let Ok(val) = v.to_str() {
            resp_headers.insert(k.to_string(), val.to_string());
        }
    }
    let resp_body = resp.text().await.map_err(|e| format!("READ_BODY:{}", e))?;

    Ok(DirectResponse {
        status,
        headers: resp_headers,
        body: resp_body,
    })
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![direct_get, direct_request, direct_upload])
        .plugin(tauri_plugin_global_shortcut::Builder::new().build())
        .setup(|app| {
            // ── Debug logging in dev builds ──────────────────────────────────
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            // ── System tray ──────────────────────────────────────────────────
            let show_i = MenuItem::with_id(app, "show", "显示窗口", true, None::<&str>)?;
            let hide_i = MenuItem::with_id(app, "hide", "隐藏窗口", true, None::<&str>)?;
            let sep = tauri::menu::PredefinedMenuItem::separator(app)?;
            let quit_i = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;

            let menu = Menu::with_items(app, &[&show_i, &hide_i, &sep, &quit_i])?;

            TrayIconBuilder::with_id("main")
                .tooltip("AI4Papers")
                .icon(app.default_window_icon().unwrap().clone())
                .menu(&menu)
                .show_menu_on_left_click(false)
                // Double-click / left-click on tray icon → toggle window
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        toggle_main_window(app);
                    }
                })
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "show" => {
                        show_main_window(app);
                    }
                    "hide" => {
                        if let Some(win) = app.get_webview_window("main") {
                            let _ = win.hide();
                        }
                    }
                    "quit" => {
                        app.exit(0);
                    }
                    _ => {}
                })
                .build(app)?;

            Ok(())
        })
        // ── Window close → hide to tray instead of quitting ─────────────────
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                // Prevent the window from actually closing
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

fn show_main_window(app: &tauri::AppHandle) {
    if let Some(win) = app.get_webview_window("main") {
        let _ = win.show();
        let _ = win.set_focus();
    }
}

fn toggle_main_window(app: &tauri::AppHandle) {
    if let Some(win) = app.get_webview_window("main") {
        if win.is_visible().unwrap_or(false) {
            let _ = win.hide();
        } else {
            let _ = win.show();
            let _ = win.set_focus();
        }
    }
}
