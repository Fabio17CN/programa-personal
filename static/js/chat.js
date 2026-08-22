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
    if (msg.apagada) {
      return '<div class="chat-bolha-texto chat-apagada-texto">🚫 Mensagem apagada</div>';
    }
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

  // Transforma a bolha numa mensagem "apagada" (estilo WhatsApp) sem
  // recarregar a tela — usada tanto na hora em que a própria pessoa apaga
  // quanto quando o polling descobre que o outro lado apagou uma mensagem.
  function marcarBolhaApagada(id) {
    var bolha = lista.querySelector('.chat-bolha[data-id="' + id + '"]');
    if (!bolha || bolha.dataset.apagada === '1') return;
    bolha.dataset.apagada = '1';
    bolha.classList.add('apagada');
    bolha.className = bolha.className.replace(/tipo-\S+/, 'tipo-texto');
    var conteudoAntigo = bolha.querySelector(
      '.chat-audio-player, .chat-midia-thumb, .chat-relatorio-card, .chat-bolha-texto'
    );
    if (conteudoAntigo) conteudoAntigo.remove();
    var placeholder = document.createElement('div');
    placeholder.className = 'chat-bolha-texto chat-apagada-texto';
    placeholder.textContent = '🚫 Mensagem apagada';
    var rodape = bolha.querySelector('.chat-bolha-rodape');
    if (rodape) bolha.insertBefore(placeholder, rodape);
    else bolha.appendChild(placeholder);
  }

  function aplicarApagadas(ids) {
    if (!ids || !ids.length) return;
    ids.forEach(marcarBolhaApagada);
  }

  function buscarNovas() {
    fetch(URL_NOVAS_BASE + '?depois_de=' + ultimoId)
      .then(function (r) { return r.json(); })
      .then(function (r) {
        if (!r || !r.ok) return;
        var seguirColado = pertoDoFinal();
        if (r.mensagens && r.mensagens.length) {
          r.mensagens.forEach(adicionarMensagem);
        }
        aplicarLidas(r.lidas);
        aplicarApagadas(r.apagadas);
        if (seguirColado && r.mensagens && r.mensagens.length) rolarParaFinal();
      })
      .catch(function () { /* falha de rede silenciosa: tenta de novo no próximo ciclo */ });
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
    enviarMidia('imagem', arquivo, arquivo.name || 'foto.jpg').then(function () {
      input.value = '';
    });
  };

  // ---------- Gravação de áudio / vídeo instantâneo ----------

  var gravador = null;
  var streamAtual = null;
  var chunksGravados = [];
  var tipoGravando = null;
  var timerGravacao = null;
  var inicioGravacao = 0;
  var gravacaoCancelada = false;
  var LIMITE_SEGUNDOS = { audio: 180, video: 60 };

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

  window.iniciarGravacao = function (tipo) {
    if (gravador) return;
    if (!navigator.mediaDevices || !window.MediaRecorder) {
      if (window.mostrarToast) mostrarToast('Seu navegador não suporta gravação.', 'error');
      return;
    }
    var restricoes = tipo === 'video'
      ? { audio: true, video: { facingMode: 'user', width: { ideal: 640 } } }
      : { audio: true };

    navigator.mediaDevices.getUserMedia(restricoes).then(function (stream) {
      streamAtual = stream;
      tipoGravando = tipo;
      chunksGravados = [];
      gravacaoCancelada = false;

      try {
        gravador = new MediaRecorder(stream);
      } catch (e) {
        if (window.mostrarToast) mostrarToast('Não foi possível iniciar a gravação.', 'error');
        pararTrilhas();
        return;
      }
      gravador.ondataavailable = function (ev) {
        if (ev.data && ev.data.size > 0) chunksGravados.push(ev.data);
      };
      gravador.onerror = function () {
        // Falha do próprio gravador no meio da captura (ex: dispositivo de
        // áudio/câmera foi desconectado ou teve algum problema do SO) —
        // avisa o usuário e cancela com segurança, sem tentar enviar um
        // arquivo corrompido/incompleto.
        if (window.mostrarToast) mostrarToast('A gravação foi interrompida. Tente novamente.', 'error');
        window.cancelarGravacao();
      };
      // Se a trilha de mídia terminar sozinha no meio da gravação (ex:
      // permissão revogada, câmera/microfone perdida, ou o app foi pra
      // segundo plano e o navegador cortou o acesso), trata como uma
      // interrupção de conexão com o hardware: cancela e avisa — evita
      // enviar um áudio/vídeo pela metade sem o usuário perceber.
      stream.getTracks().forEach(function (track) {
        track.onended = function () {
          if (gravador && gravador.state !== 'inactive') {
            if (window.mostrarToast) mostrarToast('Gravação interrompida (sinal perdido). Tente novamente.', 'error');
            window.cancelarGravacao();
          }
        };
      });
      gravador.onstop = function () {
        pararTrilhas();
        var el = document.getElementById('recVideoEl');
        if (el) el.srcObject = null;
        if (!gravacaoCancelada && chunksGravados.length) {
          var duracao = (Date.now() - inicioGravacao) / 1000;
          var mime = gravador.mimeType || (tipoGravando === 'video' ? 'video/webm' : 'audio/webm');
          var blob = new Blob(chunksGravados, { type: mime });
          var ext = mime.indexOf('mp4') !== -1 ? '.mp4' : '.webm';
          enviarMidia(tipoGravando, blob, 'gravacao' + ext, duracao);
        }
        gravador = null;
        tipoGravando = null;
      };

      document.getElementById('formChat').style.display = 'none';
      var barra = document.getElementById('chatGravando');
      barra.style.display = 'flex';
      document.getElementById('recLabel').textContent = tipo === 'video' ? 'Gravando vídeo…' : 'Gravando áudio…';
      var previewVideo = document.getElementById('recPreviewVideo');
      if (tipo === 'video') {
        previewVideo.style.display = '';
        document.getElementById('recVideoEl').srcObject = stream;
      } else {
        previewVideo.style.display = 'none';
      }

      inicioGravacao = Date.now();
      document.getElementById('recTimer').textContent = '0:00';
      timerGravacao = setInterval(atualizarTimer, 500);
      gravador.start();
    }).catch(function () {
      if (window.mostrarToast) mostrarToast('Permissão de câmera/microfone negada.', 'error');
    });
  };

  function finalizarUiGravacao() {
    clearInterval(timerGravacao);
    timerGravacao = null;
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
    if (gravador && gravador.state !== 'inactive') gravador.stop();
    finalizarUiGravacao();
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
