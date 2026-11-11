// Ponte com o SAFRA (Python) pelo QWebChannel do Qt.
//
// Python → página: JARVIS.receive(mensagem) (estado resolvido, legenda, sala da TARDIS, vista, perfil).
// Página → Python: ready, report, select, request — o objeto "jarvis" registrado no canal. A página não
// executa nada no computador: só PEDE (abrir a TARDIS, alternar o microfone, escolher um painel) e o lado
// Python decide pelo mesmo caminho dos botões da interface.

/** Conecta ao canal; fora do SAFRA (navegador comum) devolve null. */
export function connectBridge(timeoutMs = 4000) {
  return new Promise((resolve) => {
    const qt = window.qt;
    if (!qt || !qt.webChannelTransport || typeof window.QWebChannel !== 'function') { resolve(null); return; }
    const timer = setTimeout(() => resolve(null), timeoutMs);
    new window.QWebChannel(qt.webChannelTransport, (channel) => {
      clearTimeout(timer);
      resolve(channel.objects.jarvis || null);
    });
  });
}

/** Envia ao Python sem nunca derrubar a página (o canal pode ter fechado no encerramento). */
export function makeSender(bridge) {
  const call = (name, ...args) => {
    try { if (bridge && typeof bridge[name] === 'function') bridge[name](...args); } catch (e) { /* canal fechado */ }
  };
  return {
    connected: !!bridge,
    ready: (info) => call('ready', JSON.stringify(info)),
    report: (data) => call('report', JSON.stringify(data)),
    select: (key) => call('select', String(key)),
    request: (action) => call('request', String(action)),
  };
}
