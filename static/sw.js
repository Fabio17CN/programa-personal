// Service worker do Painel NM — cache local para o aluno conseguir ver a
// ficha de treino do dia mesmo sem conexão com a internet.
//
// Estratégia: "network first, cache como reserva". Toda vez que uma tela
// (página HTML) ou arquivo estático é aberto com internet, guarda uma
// cópia atualizada no cache. Se depois o aluno abrir a mesma tela sem
// internet, o service worker devolve a última cópia salva em vez de dar
// erro de conexão — funciona automaticamente para "Meus Treinos" e para a
// ficha de cada treino, desde que o aluno já tenha aberto essa tela pelo
// menos uma vez com internet antes.
const CACHE_NOME = 'painelnm-cache-v1';

// Só entra em cache o que é seguro reutilizar offline: páginas de treino do
// aluno e os arquivos estáticos (CSS/JS/ícones). Nunca mensagens, envio de
// formulários (POST) nem áreas do personal — pra não mostrar dado antigo
// escondendo uma ação que precisa de internet de verdade.
function podeGuardarNoCache(url) {
  if (url.pathname.startsWith('/static/')) return true;
  if (url.pathname === '/aluno/meus-treinos') return true;
  if (/^\/aluno\/treino\/\d+$/.test(url.pathname)) return true;
  if (/^\/aluno\/meus-treinos\/\d+$/.test(url.pathname)) return true;
  return false;
}

self.addEventListener('install', function (ev) {
  self.skipWaiting();
});

self.addEventListener('activate', function (ev) {
  ev.waitUntil(
    caches.keys().then(function (nomes) {
      return Promise.all(
        nomes.filter(function (n) { return n !== CACHE_NOME; }).map(function (n) { return caches.delete(n); })
      );
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener('fetch', function (ev) {
  var req = ev.request;
  if (req.method !== 'GET') return; // nunca intercepta envios (POST) de formulário/chat/etc.
  var url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (!podeGuardarNoCache(url)) return;

  ev.respondWith(
    fetch(req).then(function (resposta) {
      if (resposta && resposta.ok) {
        var copia = resposta.clone();
        caches.open(CACHE_NOME).then(function (cache) { cache.put(req, copia); });
      }
      return resposta;
    }).catch(function () {
      return caches.match(req).then(function (cacheado) {
        if (cacheado) return cacheado;
        throw new Error('offline-sem-cache');
      });
    })
  );
});
