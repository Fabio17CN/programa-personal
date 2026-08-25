// Chat real (estilo WhatsApp) entre personal e aluno — texto, áudio,
// vídeo, foto e o cartão automático de relatório de avaliação física.
// Este mesmo arquivo é usado nas duas telas (mensagens_conversa.html, do
// personal, e aluno_minhas_mensagens_conversa.html, do aluno) — cada
// template define antes de carregar este script: URL_ENVIAR,
// URL_ENVIAR_MIDIA, URL_NOVAS_BASE e MINHA_CHAVE ('personal' ou 'aluno').
(function () {
  var lista = document.getElementById('chatMessages');
  if (!lista) return;
 
  var ultimoId = parseInt(lista.dataset.ultimoId || '0', 10) || 0;
  var ultimoDia = lista.dataset.ultimoDia || '';
  var enviando = false;
  var intervaloBusca = null;
 
  // Ícones usados na hora de montar bolha via JS (mesmo traçado do
  // templates/_icons.html) — usados como HTML puro porque aqui não temos
  // como chamar a macro do Jinja.
  var ICONE_PLAY = '<svg class="icone-svg" viewBox="0 0 24 24" fill="currentColor" stroke="none"><path d="M8 5.3v13.4a1 1 0 0 0 1.53.85l10.7-6.7a1 1 0 0 0 0-1.7l-10.7-6.7A1 1 0 0 0 8 5.3z"/></svg>';
  var ICONE_PAUSE = '<svg class="icone-svg" viewBox="0 0 24 24" fill="currentColor" stroke="none"><rect x="6.5" y="5" width="4" height="14" rx="1"/><rect x="13.5" y="5" width="4" height="14" rx="1"/></svg>';
  var ICONE_CHECK_DUPLO = '<svg class="icone-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12.5l5 5L16 7"/><path d="M8.5 12.5l5 5L23.5 7"/></svg>';
  var ICONE_GRAFICO = '<svg class="icone-svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3.5a8.5 8.5 0 1 0 8.5 8.5H12V3.5z"/><path d="M15.5 3.9A8.5 8.5 0 0 1 20.1 8.5H12l3.5-4.6z"/></svg>';
 
  function escapeHtml(s) {
    return (s || '').replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
 
  function formatarTempo(seg) {
    seg = Math.max(0, Math.round(seg || 0));
    var m = Math.floor(seg / 60), s = seg % 60;
    return m + ':' + (s < 10 ? '0' : '') + s;
  }
 
  function rolarParaFinal() {
    lista.scrollTop = lista.scrollHeight;
  }
 
  function pertoDoFinal() {
    return (lista.scrollTop + lista.clientHeight) >= (lista.scrollHeight - 60);
  }
 
  function rotuloData(diaIso) {
    var hoje = new Date();
    var d = new Date(diaIso + 'T00:00:00');
    var diffDias = Math.round((new Date(hoje.getFullYear(), hoje.getMonth(), hoje.getDate()) - d) / 86400000);
    if (diffDias === 0) return 'Hoje';
    if (diffDias === 1) return 'Ontem';
    var partes = diaIso.split('-');
    return partes[2] + '/' + partes[1] + '/' + partes[0];
  }
 
  // ---------- Montagem das bolhas (espelha templates/_chat_bolha.html) ----------
 
  function montarGaugeMiniSvg(gauge) {
    var r = 26, circ = 2 * Math.PI * r;
    var cor = (gauge && gauge.cor) || '#D4AF37';
    var pct = (gauge && gauge.pct) || 0;
    var offset = circ * (1 - pct / 100);
    return '<svg viewBox="0 0 64 64">' +
      '<circle cx="32" cy="32" r="' + r + '" fill="none" stroke="#17130D" stroke-width="7"/>' +
      '<circle cx="32" cy="32" r="' + r + '" fill="none" stroke="' + cor + '" stroke-width="7" stroke-linecap="round" ' +
      'transform="rotate(-90 32 32)" stroke-dasharray="' + circ + '" stroke-dashoffset="' + offset + '"/></svg>';
  }
 
  function montarConteudoBolha(msg) {
    var tipo = msg.tipo || 'texto';
    if (tipo === 'audio') {
      return '' +
        '<div class="chat-audio-player" data-src="' + (msg.midia_url || '') + '" data-duracao="' + (msg.midia_duracao || 0) + '">' +
          '<button type="button" class="chat-audio-btn" onclick="window.alternarAudio(this)">' + ICONE_PLAY + '</button>' +
          '<div class="chat-audio-meio">' +
            '<input type="range" class="chat-audio-progress" min="0" max="100" value="0" oninput="window.buscarAudio(this)">' +
            '<span class="chat-audio-tempo">' + formatarTempo(msg.midia_duracao) + '</span>' +
          '</div>' +
          '<button type="button" class="chat-audio-velocidade" onclick="window.alternarVelocidade(this)">1x</button>' +
        '</div>';
    }
    if (tipo === 'video') {
      return '' +
        '<div class="chat-midia-thumb chat-midia-video" onclick="window.abrirVisualizador(\'video\', \'' + (msg.midia_url || '') + '\')">' +
          '<video src="' + (msg.midia_url || '') + '" preload="metadata" muted playsinline></video>' +
          '<span class="chat-midia-play-overlay">' + ICONE_PLAY + '</span>' +
        '</div>';
    }
    if (tipo === 'imagem') {
      return '' +
        '<div class="chat-midia-thumb" onclick="window.abrirVisualizador(\'imagem\', \'' + (msg.midia_url || '') + '\')">' +
          '<img src="' + (msg.midia_url || '') + '" alt="Foto enviada" loading="lazy">' +
        '</div>';
    }
    if (tipo === 'relatorio_avaliacao' && msg.resumo_avaliacao) {
      var r = msg.resumo_avaliacao;
      var chips = '';
      if (r.peso) chips += '<span class="chat-relatorio-chip">Peso: ' + r.peso + 'kg</span>';
      if (r.massa_magra) chips += '<span class="chat-relatorio-chip">Massa magra: ' + r.massa_magra + 'kg</span>';
      if (r.massa_gorda) chips += '<span class="chat-relatorio-chip">Massa gorda: ' + r.massa_gorda + 'kg</span>';
      return '' +
        '<div class="chat-relatorio-card">' +
          '<div class="chat-relatorio-titulo">' + ICONE_GRAFICO + ' Relatório de avaliação física</div>' +
          '<div class="chat-relatorio-gauges">' +
            '<div class="chat-gauge-mini">' + montarGaugeMiniSvg(r.gauge_imc) +
              '<div class="chat-gauge-mini-num">' + (r.imc != null ? r.imc : '-') + '</div>' +
              '<div class="chat-gauge-mini-rot">IMC</div></div>' +
            '<div class="chat-gauge-mini">' + montarGaugeMiniSvg(r.gauge_bf) +
              '<div class="chat-gauge-mini-num">' + (r.bf != null ? r.bf : '-') + '%</div>' +
              '<div class="chat-gauge-mini-rot">Gordura</div></div>' +
          '</div>' +
          '<div class="chat-relatorio-stats">' + chips + '</div>' +
          '<a href="' + (msg.url_relatorio || '#') + '" class="chat-relatorio-btn">Ver relatório completo</a>' +
        '</div>';
    }
    return '<div class="chat-bolha-texto">' + escapeHtml(msg.texto) + '</div>';
  }
 
  function adicionarMensagem(msg) {
    // Proteção contra duplicidade: a checagem de novas mensagens roda
    // sozinha a cada poucos segundos (setInterval) E também é chamada na
    // hora em que a própria pessoa termina de enviar uma mensagem — se as
    // duas rodarem quase juntas, a mesma mensagem pode voltar em duas
    // respostas antes do "ultimoId" ser atualizado, e apareceria em
    // dobro na tela (como se o botão de enviar tivesse sido apertado duas
    // vezes). Por isso, se a bolha com esse id já existe, não duplica.
    if (msg.id != null && lista.querySelector('.chat-bolha[data-id="' + msg.id + '"]')) {
      if (msg.id > ultimoId) ultimoId = msg.id;
      return;
    }
    // Mensagem apagada: não deixa nenhum rastro visível na conversa (nem
    // bolha, nem "🚫 Mensagem apagada") — a tela fica totalmente limpa,
    // como se ela nunca tivesse existido ali.
    if (msg.apagada) {
      if (msg.id > ultimoId) ultimoId = msg.id;
      return;
    }
    var dia = (msg.enviado_em || '').slice(0, 10);
    if (dia && dia !== ultimoDia) {
      var sep = document.createElement('div');
      sep.className = 'chat-date-sep';
      var span = document.createElement('span');
      span.textContent = rotuloData(dia);
      sep.appendChild(span);
      lista.appendChild(sep);
      ultimoDia = dia;
    }
    var vazio = lista.querySelector('.chat-empty');
    if (vazio) vazio.remove();
 
    var minha = msg.remetente === MINHA_CHAVE;
    var bolha = document.createElement('div');
    bolha.className = 'chat-bolha tipo-' + (msg.tipo || 'texto') + ' ' + (minha ? 'minha' : 'dele') + (msg.apagada ? ' apagada' : '');
    bolha.dataset.id = msg.id;
    bolha.dataset.lida = msg.lida ? '1' : '0';
    bolha.dataset.apagada = msg.apagada ? '1' : '0';
 
    var rodapeChecks = minha
      ? '<span class="chat-checks ' + (msg.lida ? 'lida' : 'entregue') + '">' + ICONE_CHECK_DUPLO + '</span>'
      : '';
 
    bolha.innerHTML = montarConteudoBolha(msg) +
      '<div class="chat-bolha-rodape">' +
        '<span class="chat-bolha-hora">' + (msg.enviado_em || '').slice(11, 16) + '</span>' +
        rodapeChecks +
      '</div>';
 
    lista.appendChild(bolha);
    if (msg.id > ultimoId) ultimoId = msg.id;
  }
 
  function aplicarLidas(ids) {
    if (!ids || !ids.length) return;
    ids.forEach(function (id) {
      var checks = lista.querySelector('.chat-bolha[data-id="' + id + '"] .chat-checks');
      if (checks && !checks.classList.contains('lida')) {
        checks.classList.remove('entregue');
        checks.classList.add('lida');
      }
    });
  }
 
  // Remove a bolha da conversa por completo (sem deixar nenhum aviso tipo
  // "🚫 Mensagem apagada") — usada tanto na hora em que a própria pessoa
  // apaga quanto quando o polling descobre que o outro lado apagou uma
  // mensagem, inclusive dias depois. A tela fica totalmente limpa, sem
  // rastro nenhum daquela mensagem.
  function marcarBolhaApagada(id) {
    var bolha = lista.querySelector('.chat-bolha[data-id="' + id + '"]');
    if (!bolha) return;
    var sepAnterior = bolha.previousElementSibling;
    var sepProximo = bolha.nextElementSibling;
    bolha.remove();
    // Se a bolha apagada era a única mensagem daquele dia, o separador de
    // data ("Hoje", "Ontem", "12/08"...) também fica sem sentido sozinho —
    // remove ele também pra não sobrar um separador "no vazio".
    if (sepAnterior && sepAnterior.classList && sepAnterior.classList.contains('chat-date-sep')) {
      var proximoEhOutroSeparadorOuFim = !sepProximo || (sepProximo.classList && sepProximo.classList.contains('chat-date-sep'));
      if (proximoEhOutroSeparadorOuFim) sepAnterior.remove();
    }
  }
 
  function aplicarApagadas(ids) {
    if (!ids || !ids.length) return;
    ids.forEach(marcarBolhaApagada);
  }
 
  var buscandoNovas = false;
  function buscarNovas() {
    // Evita duas checagens de mensagens novas rodando ao mesmo tempo (ex:
    // o intervalo automático e a checagem manual logo após enviar uma
    // mensagem) — é essa sobreposição que fazia uma mensagem aparecer
    // duas vezes na tela.
    if (buscandoNovas) return;
    buscandoNovas = true;
    fetch(URL_NOVAS_BASE + '?depois_de=' + ultimoId)
      .then(function (r) { return r.json(); })
      .then(function (r) {
        buscandoNovas = false;
        if (!r || !r.ok) return;
        var seguirColado = pertoDoFinal();
        if (r.mensagens && r.mensagens.length) {
          r.mensagens.forEach(adicionarMensagem);
        }
        aplicarLidas(r.lidas);
        aplicarApagadas(r.apagadas);
        if (seguirColado && r.mensagens && r.mensagens.length) rolarParaFinal();
      })
      .catch(function () {
        buscandoNovas = false;
        /* falha de rede silenciosa: tenta de novo no próximo ciclo */
      });
  }
 
  // ---------- Envio de texto ----------
 
  window.enviarChat = function (ev) {
    if (ev) ev.preventDefault();
    var campo = document.getElementById('chatTexto');
    var texto = campo.value.trim();
    if (!texto || enviando) return false;
    enviando = true;
 
    var fd = new FormData();
    fd.append('csrf_token', document.getElementById('csrfToken').value);
    fd.append('texto', texto);
 
    fetch(URL_ENVIAR, { method: 'POST', body: fd })
      .then(function (r) { return r.json(); })
      .then(function (r) {
        enviando = false;
        if (r && r.ok) {
          campo.value = '';
          autoAltura(campo);
          window.alternarBotoesEnvio();
          buscarNovas();
          if (navigator.vibrate) navigator.vibrate(20);
        } else if (window.mostrarToast) {
          mostrarToast((r && r.erro) || 'Não foi possível enviar.', 'error');
        }
      })
      .catch(function () {
        enviando = false;
        if (window.mostrarToast) mostrarToast('Falha de conexão. Tente novamente.', 'error');
      });
    return false;
  };
 
  window.teclaChat = function (ev) {
    if (ev.key === 'Enter' && !ev.shiftKey) {
      ev.preventDefault();
      window.enviarChat(ev);
    }
  };
 
  window.autoAltura = function (campo) {
    campo.style.height = 'auto';
    campo.style.height = Math.min(campo.scrollHeight, 120) + 'px';
  };
 
  // Troca entre "microfone + vídeo" e "botão de enviar" conforme o campo
  // de texto tem ou não conteúdo — igual ao comportamento do WhatsApp.
  window.alternarBotoesEnvio = function () {
    var campo = document.getElementById('chatTexto');
    var temTexto = campo && campo.value.trim().length > 0;
    var btnAudio = document.getElementById('btnGravarAudio');
    var btnVideo = document.getElementById('btnGravarVideo');
    var btnEnviar = document.getElementById('btnEnviarTexto');
    if (!btnEnviar) return;
    btnEnviar.style.display = temTexto ? '' : 'none';
    if (btnAudio) btnAudio.style.display = temTexto ? 'none' : '';
    if (btnVideo) btnVideo.style.display = temTexto ? 'none' : '';
  };
 
  // ---------- Envio de foto ----------
 
  function enviarMidia(tipo, blobOuArquivo, nomeArquivo, duracao) {
    var fd = new FormData();
    fd.append('csrf_token', document.getElementById('csrfToken').value);
    fd.append('tipo', tipo);
    fd.append('arquivo', blobOuArquivo, nomeArquivo);
    if (duracao) fd.append('duracao', duracao);
    return fetch(URL_ENVIAR_MIDIA, { method: 'POST', body: fd })
      .then(function (r) { return r.json(); })
      .then(function (r) {
        if (r && r.ok) {
          buscarNovas();
        } else if (window.mostrarToast) {
          mostrarToast((r && r.erro) || 'Não foi possível enviar.', 'error');
        }
        return r;
      })
      .catch(function () {
        if (window.mostrarToast) mostrarToast('Falha de conexão. Tente novamente.', 'error');
      });
  }
 
  window.enviarFotoSelecionada = function (ev) {
    var input = ev.target;
    var arquivo = input.files && input.files[0];
    if (!arquivo) return;
    if (arquivo.size > 25 * 1024 * 1024) {
      if (window.mostrarToast) mostrarToast('Foto muito grande (máx. 25MB).', 'error');
      input.value = '';
      return;
    }
    enviarMidia('imagem', arquivo, arquivo.name || 'foto.jpg').then(function (r) {
      input.value = '';
      if (r && r.ok && navigator.vibrate) navigator.vibrate(20);
    });
  };
 
  // ---------- Gravação de áudio / vídeo instantâneo (tela cheia) ----------
 
  var gravador = null;
  var streamAtual = null;
  var chunksGravados = [];
  var tipoGravando = null;
  var timerGravacao = null;
  var inicioGravacao = 0;
  var gravacaoCancelada = false;
  var facingModeAtual = 'user';
  var LIMITE_SEGUNDOS = { audio: 180, video: 60 };
 
  // Onda de nível de áudio (Web Audio API): mede o volume do microfone em
  // tempo real e anima as 8 barrinhas — dá um retorno visual claro de que
  // o áudio está sendo captado, mesmo sem vídeo na tela.
  var audioCtxGravacao = null;
  var analyserGravacao = null;
  var dadosAnalyser = null;
  var animacaoOndaId = null;
 
  function iniciarOndaAudio(stream) {
    try {
      audioCtxGravacao = new (window.AudioContext || window.webkitAudioContext)();
      var origem = audioCtxGravacao.createMediaStreamSource(stream);
      analyserGravacao = audioCtxGravacao.createAnalyser();
      analyserGravacao.fftSize = 64;
      dadosAnalyser = new Uint8Array(analyserGravacao.frequencyBinCount);
      origem.connect(analyserGravacao);
      var barras = document.querySelectorAll('#recAudioOnda span');
      (function animar() {
        animacaoOndaId = requestAnimationFrame(animar);
        analyserGravacao.getByteFrequencyData(dadosAnalyser);
        for (var i = 0; i < barras.length; i++) {
          var v = dadosAnalyser[i * 2] || 0;
          var altura = Math.max(6, Math.round((v / 255) * 80));
          barras[i].style.height = altura + 'px';
        }
      })();
    } catch (e) { /* sem suporte a Web Audio — segue só com o timer visual */ }
  }
 
  function pararOndaAudio() {
    if (animacaoOndaId) cancelAnimationFrame(animacaoOndaId);
    animacaoOndaId = null;
    if (audioCtxGravacao) { try { audioCtxGravacao.close(); } catch (e) {} }
    audioCtxGravacao = null;
    analyserGravacao = null;
  }
 
  function pararTrilhas() {
    if (streamAtual) {
      streamAtual.getTracks().forEach(function (t) { t.stop(); });
      streamAtual = null;
    }
  }
 
  function atualizarTimer() {
    var passados = (Date.now() - inicioGravacao) / 1000;
    var el = document.getElementById('recTimer');
    if (el) el.textContent = formatarTempo(passados);
    if (passados >= LIMITE_SEGUNDOS[tipoGravando]) {
      window.confirmarGravacao();
    }
  }
 
  function anexarEventosStream(stream) {
    stream.getTracks().forEach(function (track) {
      track.onended = function () {
        if (gravador && gravador.state !== 'inactive') {
          if (window.mostrarToast) mostrarToast('Gravação interrompida (sinal perdido). Tente novamente.', 'error');
          window.cancelarGravacao();
        }
      };
    });
  }
 
  function criarGravadorNoStream(stream, tipoAlvo) {
    // Escolhe explicitamente um formato suportado pelo navegador, em vez
    // de deixar no automático — em vários navegadores (principalmente
    // Safari/iOS) o MediaRecorder sem um mimeType explícito ou falha ao
    // iniciar, ou grava num formato que depois não bate com o que a gente
    // assume no envio, gerando um arquivo de áudio corrompido/mudo que
    // nunca chega a tocar do outro lado (a causa do "erro que impede o
    // envio de áudio" relatado). Tenta cada candidato, na ordem, e usa o
    // primeiro que o navegador realmente suporta.
    var candidatos = tipoAlvo === 'video'
      // vp8 primeiro: é o codec com o suporte de hardware mais confiável
      // em aparelhos Android médios/entrada de linha — vp9 é suportado
      // "no papel" em mais navegadores, mas falha silenciosamente na
      // gravação em bastante celular real, o que gerava vídeos vazios
      // que nunca chegavam a ser enviados.
      ? ['video/mp4', 'video/webm;codecs=vp8,opus', 'video/webm;codecs=vp9,opus', 'video/webm']
      : ['audio/mp4', 'audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus'];
    var opcoes = {};
    if (window.MediaRecorder && MediaRecorder.isTypeSupported) {
      for (var i = 0; i < candidatos.length; i++) {
        if (MediaRecorder.isTypeSupported(candidatos[i])) { opcoes.mimeType = candidatos[i]; break; }
      }
    }
    var g;
    try {
      g = opcoes.mimeType ? new MediaRecorder(stream, opcoes) : new MediaRecorder(stream);
    } catch (e) {
      // Se o formato escolhido falhar por algum motivo, tenta de novo sem
      // forçar nenhum mimeType (deixa o navegador escolher sozinho) antes
      // de desistir de vez.
      try {
        g = new MediaRecorder(stream);
      } catch (e2) {
        if (window.mostrarToast) mostrarToast('Não foi possível iniciar a gravação.', 'error');
        pararTrilhas();
        return null;
      }
    }
    g.ondataavailable = function (ev) {
      if (ev.data && ev.data.size > 0) chunksGravados.push(ev.data);
    };
    g.onerror = function () {
      // Falha do próprio gravador no meio da captura (ex: dispositivo de
      // áudio/câmera foi desconectado ou teve algum problema do SO) —
      // avisa o usuário e cancela com segurança, sem tentar enviar um
      // arquivo corrompido/incompleto.
      if (window.mostrarToast) mostrarToast('A gravação foi interrompida. Tente novamente.', 'error');
      window.cancelarGravacao();
    };
    return g;
  }
 
  window.iniciarGravacao = function (tipo) {
    if (gravador) return;
    if (!navigator.mediaDevices || !window.MediaRecorder) {
      if (window.mostrarToast) mostrarToast('Seu navegador não suporta gravação.', 'error');
      return;
    }
    facingModeAtual = 'user';
    var restricoes = tipo === 'video'
      ? { audio: true, video: { facingMode: facingModeAtual, width: { ideal: 640 } } }
      : { audio: true };
 
    navigator.mediaDevices.getUserMedia(restricoes).then(function (stream) {
      streamAtual = stream;
      tipoGravando = tipo;
      chunksGravados = [];
      gravacaoCancelada = false;
 
      gravador = criarGravadorNoStream(stream, tipo);
      if (!gravador) return;
      anexarEventosStream(stream);
      gravador.onstop = function () {
        var mimeReal = gravador && gravador.mimeType;
        var el = document.getElementById('recVideoEl');
        if (el) el.srcObject = null;
        pararOndaAudio();
        pararTrilhas();
        if (gravacaoCancelada) {
          gravador = null;
          tipoGravando = null;
          return;
        }
        // Se a pessoa tocar em "enviar" rápido demais (menos de meio
        // segundo), o gravador às vezes ainda não produziu nenhum dado —
        // antes disso ficava tudo em silêncio (a câmera fechava e nada
        // acontecia); agora avisa e deixa gravar de novo.
        var tamanhoTotal = chunksGravados.reduce(function (soma, c) { return soma + (c.size || 0); }, 0);
        if (!chunksGravados.length || tamanhoTotal < 500) {
          if (window.mostrarToast) mostrarToast('Grave por mais um instante antes de enviar.', 'warning');
          gravador = null;
          tipoGravando = null;
          return;
        }
        abrirPreviewGravacao((Date.now() - inicioGravacao) / 1000, mimeReal);
        gravador = null;
      };
 
      document.getElementById('formChat').style.display = 'none';
      var tela = document.getElementById('chatGravando');
      tela.style.display = 'flex';
      document.getElementById('recLabel').textContent = tipo === 'video' ? 'Gravando vídeo…' : 'Gravando áudio…';
      var videoEl = document.getElementById('recVideoEl');
      var ondaEl = document.getElementById('recAudioOnda');
      var btnTrocar = document.getElementById('btnTrocarCamera');
      if (tipo === 'video') {
        videoEl.style.display = '';
        videoEl.style.transform = facingModeAtual === 'user' ? 'scaleX(-1)' : 'none';
        videoEl.srcObject = stream;
        ondaEl.style.display = 'none';
        if (btnTrocar) btnTrocar.style.display = '';
      } else {
        videoEl.style.display = 'none';
        ondaEl.style.display = 'flex';
        if (btnTrocar) btnTrocar.style.display = 'none';
        iniciarOndaAudio(stream);
      }
 
      // Vibração curta ao começar a gravar — mesmo retorno tátil de apps
      // de mensagem conhecidos, avisa que a gravação começou de verdade.
      if (navigator.vibrate) navigator.vibrate(30);
 
      inicioGravacao = Date.now();
      document.getElementById('recTimer').textContent = '0:00';
      timerGravacao = setInterval(atualizarTimer, 500);
      gravador.start();
    }).catch(function () {
      if (window.mostrarToast) mostrarToast('Permissão de câmera/microfone negada.', 'error');
    });
  };
 
  // Troca entre câmera frontal e traseira SEM perder o que já foi gravado:
  // fecha o pedaço atual do gravador, troca de câmera e continua gravando
  // num novo pedaço que é somado ao mesmo arquivo final (o cronômetro
  // segue contando normalmente, sem resetar).
  window.trocarCamera = function () {
    if (!gravador || tipoGravando !== 'video') return;
    facingModeAtual = facingModeAtual === 'user' ? 'environment' : 'user';
    var gravadorAntigo = gravador;
    gravador = null; // evita cancelarGravacao/onstop tratarem isso como fim da gravação
    gravadorAntigo.onstop = function () {
      pararTrilhas();
      navigator.mediaDevices.getUserMedia({ audio: true, video: { facingMode: facingModeAtual, width: { ideal: 640 } } })
        .then(function (novoStream) {
          streamAtual = novoStream;
          anexarEventosStream(novoStream);
          var videoEl = document.getElementById('recVideoEl');
          videoEl.srcObject = novoStream;
          videoEl.style.transform = facingModeAtual === 'user' ? 'scaleX(-1)' : 'none';
          gravador = criarGravadorNoStream(novoStream, 'video');
          if (!gravador) return;
          gravador.onstop = gravadorAntigo.onstop; // reaplica o mesmo fluxo se trocar de novo ou parar
          gravador.start();
        })
        .catch(function () {
          if (window.mostrarToast) mostrarToast('Não foi possível trocar de câmera.', 'error');
        });
    };
    gravadorAntigo.stop();
  };
 
  function finalizarUiGravacao() {
    clearInterval(timerGravacao);
    timerGravacao = null;
    pararOndaAudio();
    document.getElementById('chatGravando').style.display = 'none';
    document.getElementById('formChat').style.display = '';
  }
 
  window.cancelarGravacao = function () {
    gravacaoCancelada = true;
    if (gravador && gravador.state !== 'inactive') gravador.stop();
    else pararTrilhas();
    finalizarUiGravacao();
  };
 
  window.confirmarGravacao = function () {
    // Garante meio segundo de gravação real antes de parar — tocar em
    // "enviar" muito rápido (comum quando a pessoa já tinha decidido não
    // gravar mais nada e quer só confirmar) podia pegar o gravador ainda
    // sem nenhum dado, fechando a câmera sem enviar nada e sem avisar.
    var decorrido = Date.now() - inicioGravacao;
    if (decorrido < 600) {
      setTimeout(window.confirmarGravacao, 600 - decorrido);
      return;
    }
    if (gravador && gravador.state !== 'inactive') gravador.stop();
    finalizarUiGravacao();
  };
 
  // ---------- Pré-visualização antes de enviar ----------
 
  var blobPreviewAtual = null;
  var urlPreviewAtual = null;
  var tipoPreviewAtual = null;
  var duracaoPreviewAtual = 0;
 
  function abrirPreviewGravacao(duracao, mimeReal) {
    // Usa o mimeType REAL negociado pelo MediaRecorder (mais confiável) e
    // só cai para o tipo de um chunk individual, ou pro palpite antigo, se
    // por algum motivo o navegador não informar — evita criar um Blob com
    // um "rótulo" de formato que não bate com o conteúdo gravado de
    // verdade, que é o que gerava áudios que não iam/tocavam do outro lado.
    var mime = mimeReal || (chunksGravados[0] && chunksGravados[0].type) || (tipoGravando === 'video' ? 'video/webm' : 'audio/webm');
    blobPreviewAtual = new Blob(chunksGravados, { type: mime });
    tipoPreviewAtual = tipoGravando;
    duracaoPreviewAtual = duracao;
    urlPreviewAtual = URL.createObjectURL(blobPreviewAtual);
 
    var caixaVideo = document.getElementById('previewVideoEl');
    var caixaAudio = document.getElementById('previewAudioEl');
    if (tipoPreviewAtual === 'video') {
      caixaVideo.src = urlPreviewAtual;
      caixaVideo.style.display = '';
      caixaAudio.style.display = 'none';
      caixaAudio.removeAttribute('src');
    } else {
      caixaAudio.src = urlPreviewAtual;
      caixaAudio.style.display = '';
      caixaVideo.style.display = 'none';
      caixaVideo.removeAttribute('src');
    }
    document.getElementById('chatPreviewMidia').style.display = 'flex';
    tipoGravando = null;
  }
 
  function fecharPreviewGravacao() {
    document.getElementById('chatPreviewMidia').style.display = 'none';
    if (urlPreviewAtual) URL.revokeObjectURL(urlPreviewAtual);
    urlPreviewAtual = null;
    blobPreviewAtual = null;
    tipoPreviewAtual = null;
  }
 
  window.descartarPreviewMidia = function () {
    fecharPreviewGravacao();
  };
 
  window.enviarPreviewMidia = function () {
    if (!blobPreviewAtual) return;
    var mime = blobPreviewAtual.type || '';
    var ext = '.webm';
    if (mime.indexOf('mp4') !== -1) ext = (tipoPreviewAtual === 'audio') ? '.m4a' : '.mp4';
    else if (mime.indexOf('ogg') !== -1) ext = '.ogg';
    else if (mime.indexOf('wav') !== -1) ext = '.wav';
    else if (mime.indexOf('webm') !== -1) ext = '.webm';
    enviarMidia(tipoPreviewAtual, blobPreviewAtual, 'gravacao' + ext, duracaoPreviewAtual).then(function (r) {
      if (r && r.ok && navigator.vibrate) navigator.vibrate(25);
    });
    fecharPreviewGravacao();
  };
 
  // ---------- Player de áudio (play/pause, progresso, velocidade) ----------
 
  var audioAtivo = null; // só um áudio toca por vez, igual WhatsApp
 
  function obterAudio(container) {
    if (container._audioObj) return container._audioObj;
    var audio = new Audio(container.dataset.src);
    var progresso = container.querySelector('.chat-audio-progress');
    var tempo = container.querySelector('.chat-audio-tempo');
    var btn = container.querySelector('.chat-audio-btn');
    audio.addEventListener('timeupdate', function () {
      if (audio.duration) progresso.value = (audio.currentTime / audio.duration) * 100;
      tempo.textContent = formatarTempo(audio.currentTime || container.dataset.duracao);
    });
    audio.addEventListener('loadedmetadata', function () {
      if (isFinite(audio.duration)) container.dataset.duracao = audio.duration;
    });
    audio.addEventListener('ended', function () {
      btn.innerHTML = ICONE_PLAY;
      progresso.value = 0;
      tempo.textContent = formatarTempo(container.dataset.duracao);
      if (audioAtivo === audio) audioAtivo = null;
    });
    container._audioObj = audio;
    return audio;
  }
 
  window.alternarAudio = function (btn) {
    var container = btn.closest('.chat-audio-player');
    var audio = obterAudio(container);
    if (audioAtivo && audioAtivo !== audio) {
      audioAtivo.pause();
      var outroBtn = audioAtivo._container && audioAtivo._container.querySelector('.chat-audio-btn');
      if (outroBtn) outroBtn.innerHTML = ICONE_PLAY;
    }
    audio._container = container;
    if (audio.paused) {
      var velBtn = container.querySelector('.chat-audio-velocidade');
      audio.playbackRate = parseFloat((velBtn.textContent || '1x').replace('x', '')) || 1;
      audio.play();
      btn.innerHTML = ICONE_PAUSE;
      audioAtivo = audio;
    } else {
      audio.pause();
      btn.innerHTML = ICONE_PLAY;
      audioAtivo = null;
    }
  };
 
  window.buscarAudio = function (input) {
    var container = input.closest('.chat-audio-player');
    var audio = obterAudio(container);
    if (audio.duration) audio.currentTime = (input.value / 100) * audio.duration;
  };
 
  window.alternarVelocidade = function (btn) {
    var ordem = [1, 1.5, 2];
    var atual = parseFloat((btn.textContent || '1x').replace('x', '')) || 1;
    var idx = ordem.indexOf(atual);
    var proxima = ordem[(idx + 1) % ordem.length];
    btn.textContent = proxima + 'x';
    var container = btn.closest('.chat-audio-player');
    if (container._audioObj) container._audioObj.playbackRate = proxima;
  };
 
  // ---------- Visualizador em tela cheia (fotos e vídeos) ----------
 
  window.abrirVisualizador = function (tipo, url) {
    var overlay = document.getElementById('midiaViewer');
    var conteudo = document.getElementById('midiaViewerConteudo');
    if (!overlay || !conteudo) return;
    conteudo.innerHTML = tipo === 'video'
      ? '<video src="' + url + '" controls autoplay playsinline></video>'
      : '<img src="' + url + '" alt="Mídia enviada">';
    overlay.classList.add('aberto');
  };
 
  window.fecharVisualizador = function () {
    var overlay = document.getElementById('midiaViewer');
    var conteudo = document.getElementById('midiaViewerConteudo');
    if (!overlay) return;
    overlay.classList.remove('aberto');
    if (conteudo) conteudo.innerHTML = '';
  };
 
  // ---------- Apagar mensagem "para todos" (apertar e segurar, estilo WhatsApp) ----------
 
  var mensagemSelecionadaId = null;
  var pressTimer = null;
  var pressIniciouEm = null;
  var PRESS_MS = 450;
  var TOLERANCIA_MOVIMENTO = 10;
 
  function podeApagarBolha(bolha) {
    return !!bolha && bolha.classList.contains('minha') && bolha.dataset.apagada !== '1';
  }
 
  function pontoDoEvento(ev) {
    if (ev.touches && ev.touches.length) return ev.touches[0];
    if (ev.changedTouches && ev.changedTouches.length) return ev.changedTouches[0];
    return ev;
  }
 
  function iniciarPress(ev) {
    var bolha = ev.target.closest && ev.target.closest('.chat-bolha');
    if (!podeApagarBolha(bolha)) return;
    var p = pontoDoEvento(ev);
    pressIniciouEm = { x: p.clientX, y: p.clientY, bolha: bolha };
    clearTimeout(pressTimer);
    pressTimer = setTimeout(function () {
      if (pressIniciouEm) window.abrirMenuMensagem(pressIniciouEm.bolha);
      pressTimer = null;
    }, PRESS_MS);
  }
 
  function moverPress(ev) {
    if (!pressTimer || !pressIniciouEm) return;
    var p = pontoDoEvento(ev);
    if (Math.abs(p.clientX - pressIniciouEm.x) > TOLERANCIA_MOVIMENTO ||
        Math.abs(p.clientY - pressIniciouEm.y) > TOLERANCIA_MOVIMENTO) {
      clearTimeout(pressTimer);
      pressTimer = null;
      pressIniciouEm = null;
    }
  }
 
  function cancelarPress() {
    clearTimeout(pressTimer);
    pressTimer = null;
    pressIniciouEm = null;
  }
 
  lista.addEventListener('mousedown', iniciarPress);
  lista.addEventListener('touchstart', iniciarPress, { passive: true });
  lista.addEventListener('mousemove', moverPress);
  lista.addEventListener('touchmove', moverPress, { passive: true });
  lista.addEventListener('mouseup', cancelarPress);
  lista.addEventListener('mouseleave', cancelarPress);
  lista.addEventListener('touchend', cancelarPress);
  lista.addEventListener('touchcancel', cancelarPress);
 
  // Clique direito (desktop) também abre o menu direto, sem precisar segurar.
  lista.addEventListener('contextmenu', function (ev) {
    var bolha = ev.target.closest && ev.target.closest('.chat-bolha');
    if (podeApagarBolha(bolha)) {
      ev.preventDefault();
      window.abrirMenuMensagem(bolha);
    }
  });
 
  window.abrirMenuMensagem = function (bolha) {
    if (!bolha) return;
    mensagemSelecionadaId = bolha.dataset.id;
    var overlay = document.getElementById('menuMensagemOverlay');
    if (overlay) overlay.classList.add('aberto');
    if (navigator.vibrate) navigator.vibrate(12);
  };
 
  window.fecharMenuMensagem = function () {
    mensagemSelecionadaId = null;
    var overlay = document.getElementById('menuMensagemOverlay');
    if (overlay) overlay.classList.remove('aberto');
  };
 
  window.apagarMensagemSelecionada = function () {
    var id = mensagemSelecionadaId;
    window.fecharMenuMensagem();
    if (!id) return;
    var fd = new FormData();
    fd.append('csrf_token', document.getElementById('csrfToken').value);
    fd.append('mensagem_id', id);
    fetch(URL_APAGAR, { method: 'POST', body: fd })
      .then(function (r) { return r.json(); })
      .then(function (r) {
        if (r && r.ok) {
          marcarBolhaApagada(id);
        } else if (window.mostrarToast) {
          mostrarToast((r && r.erro) || 'Não foi possível apagar.', 'error');
        }
      })
      .catch(function () {
        if (window.mostrarToast) mostrarToast('Falha de conexão. Tente novamente.', 'error');
      });
  };
 
  // ---------- Inicialização ----------
 
  rolarParaFinal();
  window.alternarBotoesEnvio();
  var campoInicial = document.getElementById('chatTexto');
  if (campoInicial) campoInicial.focus();
 
  intervaloBusca = setInterval(buscarNovas, 3500);
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) buscarNovas();
  });
  window.addEventListener('beforeunload', function () {
    if (intervaloBusca) clearInterval(intervaloBusca);
    if (gravador && gravador.state !== 'inactive') {
      gravacaoCancelada = true;
      gravador.stop();
    }
  });
})();