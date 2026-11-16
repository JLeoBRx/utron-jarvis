// Mesma página para as duas cascas. Na Tauri, fala pelo canal de comandos; na Qt, pelo QWebChannel não é preciso:
// a casca Qt mede por fora e só lê o título do documento.
(function () {
  var tauri = window.__TAURI__ && window.__TAURI__.core;
  var casca = document.getElementById("casca");
  var assistant = document.getElementById("assistant");
  if (!tauri) {
    casca.textContent = "Casca: QtWebEngine";
    assistant.textContent = "Assistant: consultado pela casca Qt";
    document.getElementById("notificar").disabled = true;
    document.title = "PRONTO";
    return;
  }
  casca.textContent = "Casca: Tauri";
  tauri.invoke("ui_ready").then(function (report) {
    var backend = report.backend || null;
    if (backend) assistant.textContent = backend.ok ? "Assistant: no ar (" + backend.latency_ms + " ms)" : "Assistant: " + backend.error;
  });
  tauri.invoke("backend_status").then(function (status) {
    assistant.textContent = status.ok ? "Assistant: no ar (" + status.latency_ms + " ms)" : "Assistant: " + status.error;
  });
  document.getElementById("notificar").addEventListener("click", function () {
    tauri.invoke("send_notification");
  });
})();
