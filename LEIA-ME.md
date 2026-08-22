# Personal Trainer — v4 (Painel NM: novo visual + módulos novos)

## Atualização mais recente — visual "Painel NM" (preto/dourado) + 9 módulos novos
1. **Novo visual em todo o sistema**: tema trocado de azul/escuro para preto e
   dourado, no estilo do painel de referência (login em vidro fosco com selo
   de segurança, barra inferior Painel/Alunos/➕/Agenda/Mais, cards e botões
   com gradiente dourado). O botão "Sair" mudou de lugar: agora fica dentro
   de Configurações (aba "Mais").
2. **Painel reorganizado** com os 16 atalhos do mockup: além dos que já
   existiam (Cadastrar Aluno, Gerenciar Alunos, Montar Treino, Agenda), agora
   tem também Treinos Registrados e Avaliações Físicas (listas com todos os
   alunos juntos) e mais 9 módulos novos, todos funcionais de verdade:
   - **Financeiro**: lança receitas/despesas, mostra resumo do mês.
   - **Controle de Pagamentos**: cobranças por aluno com vencimento; marcar
     como pago já lança a receita correspondente no Financeiro sozinho.
   - **Planos Personalizados**: cadastra planos (nome, valor, duração) e
     vincula a um aluno.
   - **Metas dos Alunos**: meta com valor inicial/atual/alvo (ex: %BF de 22
     pra 16), barra de progresso, marcar concluída/cancelada.
   - **Anotações**: registro rápido, geral ou de um aluno específico, com
     opção de fixar no topo.
   - **Check-in de Alunos**: marca presença do dia; feito por aluno, uma vez
     por dia.
   - **Mensagens**: modelos de mensagem reutilizáveis + envio que abre no seu
     próprio WhatsApp já com o texto preenchido (o sistema não manda
     mensagem sozinho, só prepara e guarda o histórico).
   - **Biblioteca de Exercícios**: navegação com busca e filtro por grupo
     muscular sobre a mesma base de 1.112 exercícios (com GIF) que já era
     usada na hora de montar treino.
   - **Relatórios Avançados**: gráficos dos últimos 30 dias (receita x
     despesa, novos alunos, check-ins) em SVG puro, sem depender de internet.
   - O "Resumo do dia" do painel (atendimentos, check-ins, novos alunos,
     faturamento) agora usa dados reais desses módulos novos.
3. **Banco de dados**: tabelas novas criadas automaticamente na primeira vez
   que o sistema roda (`financeiro`, `planos`, `aluno_planos`, `pagamentos`,
   `metas`, `anotacoes`, `checkins`, `mensagens_modelo`, `mensagens_enviadas`).
   Excluir um aluno agora também apaga os registros dele nessas tabelas novas.

## Atualização anterior (correção de bug + parecer combinado)
1. **Corrigido bug grave nas fotos LATERAIS**: em foto de perfil, ombro
   esquerdo e direito ficam quase colados no eixo X (é a mesma pessoa vista
   de lado) — isso fazia a "largura do ombro" (usada como referência de
   cálculo) virar quase zero e os números explodiam (ex.: 194% de desvio de
   tronco, 44° de ombro, tudo sem sentido). Agora a vista lateral usa a
   altura do tronco como referência, e as métricas que só fazem sentido em
   frontal/costas (nível do ombro, do quadril, desvio do tronco) não são mais
   calculadas em foto lateral — só as métricas próprias dela (cabeça e braço
   projetados à frente).
2. **Painel duplicado removido**: RCQ/RCEst/Conicidade/TMB apareciam duas
   vezes na tela de resultado — ficou só uma vez.
3. **Indicadores agora aparecem no PDF**: RCEst, Índice de Conicidade, TMB e
   Peso de Referência entraram numa segunda linha da tabela de indicadores.
4. **Parecer geral combinando as 4 vistas**: em vez de julgar cada foto
   isolada, o sistema agora cruza frontal + costas + laterais — um sinal (ex.
   ombro desnivelado) que aparece em MAIS DE UMA foto ao mesmo tempo conta
   mais forte do que um sinal isolado numa foto só. Esse parecer final
   aparece na tela de avaliação postural (depois de pelo menos 2 fotos
   analisadas) e no PDF. Importante: continua sendo um apoio visual, não um
   diagnóstico — escoliose só se confirma com exame físico (teste de Adams)
   e, se necessário, radiografia com um profissional de saúde.

## Atualização anterior (a partir do v22)
1. **Indicadores profissionais novos**: TMB (Mifflin-St Jeor), Relação
   Cintura-Estatura (RCEst), Índice de Conicidade e Peso Ideal de referência —
   aparecem automaticamente na tela de medidas e no resultado final, usando
   os campos que já existiam (peso, altura, cintura, quadril, idade, sexo).
2. **Avaliação postural com 4 vistas**: Frontal, Lado Direito, Lado Esquerdo
   e Costas (antes era só "Frontal / Lateral / Costas"). O ponto de
   referência do tronco agora é estimado um pouco ACIMA do quadril (posição
   aproximada da cintura), o que deixa a leitura do desvio do tronco mais
   precisa. O rastreio visual de possível escoliose (que já existia) continua
   ativo, e agora cada foto tem também um campo de **Observação do
   profissional**, pra você escrever à mão o que notou (ex.: "ombro direito
   mais alto", "suspeita de leve escoliose") — isso entra destacado no PDF.
   Segue não sendo um diagnóstico médico: é apoio visual + observação
   profissional, casos relevantes devem ser encaminhados a um especialista.
3. **Anamnese**: campo de observações livres no final do questionário, que
   também vai para o PDF.
4. **Perfil do aluno redesenhado**: gráfico de evolução (peso + BF) maior,
   com curva suave e área preenchida, sem depender de internet/CDN. As
   listas de avaliações e treinos agora têm um ícone de excluir do lado e,
   ao tocar no item, abre uma janela com as opções "Compartilhar no
   WhatsApp" (usa o telefone cadastrado do aluno e anexa o PDF de verdade
   quando o navegador permite) e "Baixar PDF".

## O que mudou nesta versão (pedido do dia)
1. **Tela de login**: marca/slogan maior e centralizada ("PERSONAL TRAINER" com
   tipografia elegante + slogan em destaque), fundo de academia mais vivo
   (saturação/contraste ajustados, sem escurecer demais).
2. **Cadastro do aluno simplificado**: removidos CPF, Rua e Endereço completo.
   Campos agora: Nome, Idade, Cidade, Região, Academia, Objetivo (caixa de
   texto). Telefone continua existindo pois é usado no envio por WhatsApp.
3. **Gestão de alunos**: busca é só por nome; adicionado botão "Excluir aluno"
   no perfil (com confirmação), que apaga aluno + avaliações + fotos + treinos.
4. **Perfil do aluno**: upload de foto de perfil (toque em "Adicionar foto de
   perfil"), e um card de "Comparativo de evolução" que compara automaticamente
   a última avaliação com a anterior, mostrando ganhos (▲ verde) e perdas
   (▼ vermelho) em peso, BF%, massa magra/gorda e medidas.
5. **Envio pelo WhatsApp com checkboxes**: na tela de compartilhar, marque
   "Avaliação Física" e/ou "Ficha de Treino" e um botão só baixa os PDFs
   marcados e já abre a conversa do WhatsApp do aluno.
6. **Avaliação postural com IA**: além da linha e do ângulo, a detecção
   automática agora gera pontos de atenção em texto (ex: qual ombro está mais
   alto, sugestão de observar tensão/mobilidade) — tudo isso já sai anexado
   no PDF final, junto com as fotos posturais.

---

# NM Personal Trainer — v2 (refeito do zero)

App web mobile-first que reproduz o fluxo do seu programa desktop original
(login → cadastro do aluno → anamnese pergunta-a-pergunta → medidas →
resultado final → avaliação postural opcional → PDF), acessível de qualquer
wifi por estar na nuvem, com login mais seguro.

## O que mudou em relação à v1 que te mandei antes
- **Fluxo igual ao desktop**: cadastro do aluno → anamnese (as mesmas 17
  perguntas Sim/Não, uma de cada vez) → tela de medidas (agora com dobras
  cutâneas também, não só perímetros) → tela de **resultado final** com IMC
  e % de gordura já classificados.
- **Avaliação postural agora é uma etapa opcional** depois do resultado:
  tem o botão "Sim, fazer avaliação postural" e o botão "Pular e ver
  resultado final (PDF)".
- **Segurança**: senha agora é armazenada com hash (nunca em texto puro),
  login bloqueia por 10 minutos após 5 tentativas erradas, proteção contra
  CSRF em todos os formulários, cookies de sessão seguros.

## Avaliação postural: as duas formas
1. **Linha manual**: depois de tirar a foto, toque em "Desenhar linha" e
   arraste o dedo/mouse sobre a foto pra marcar a linha que quiser (ombro,
   quadril, referência vertical, etc.).
2. **Detecção automática por IA**: o servidor tenta identificar ombros e
   quadril na foto sozinho, desenha as linhas e calcula o ângulo de
   inclinação de cada uma. Se a assimetria for maior que o esperado, mostra
   um aviso — **isso é só um apoio visual, não é diagnóstico médico**; casos
   de dúvida devem ir para um profissional de saúde.

### Ativar a detecção automática (1 vez só, e é OBRIGATÓRIO pra IA funcionar)
Sem esse passo, o botão "Detectar automaticamente" nunca vai analisar a foto —
ele só mostra o aviso de que a IA não está instalada. Isso NÃO é um bug do
sistema, é só um arquivo que falta instalar (proposital, pra não deixar o
zip gigante).

**Windows / Mac / Linux — jeito mais fácil:** dentro da pasta `webapp_v2`,
com o mesmo Python que você usa pra rodar o site, rode:

```bash
python baixar_modelo_ia.py
```

Isso baixa o arquivo automaticamente e te avisa quando terminar. Depois é só
reiniciar o site (fechar com Ctrl+C e rodar `python app.py` de novo).

Se por algum motivo o script não conseguir (rede bloqueada, firewall etc.),
baixe manualmente esse arquivo:
`https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task`
e salve como `instance/models/pose_landmarker.task`. Se esse link específico
mudar no futuro, procure por "mediapipe pose landmarker task file download".

## Rodar local (teste)
```bash
pip install -r requirements.txt
python app.py
```
Acesse `http://localhost:5000`.

## Rodar com Docker (alternativa mais "profissional")
Se você já tem o Docker Desktop instalado no seu PC, isso substitui o passo
acima — não precisa instalar Python nem as bibliotecas na mão, o Docker
cuida de tudo isolado num container.

```bash
docker compose up --build
```

Isso vai:
- Instalar tudo que o sistema precisa dentro do container (não mexe no seu PC)
- Tentar baixar o modelo de IA automaticamente na primeira vez
- Deixar o site em `http://localhost:5000`
- Guardar o banco de dados e as fotos na pasta do projeto mesmo (pastas
  `instance/` e `uploads/`), então nada se perde se você reiniciar o container

Para parar: `Ctrl+C` ou `docker compose down`. Para rodar em segundo plano:
`docker compose up -d --build`.

**Importante:** eu escrevi e revisei o `Dockerfile`/`docker-compose.yml` com
cuidado, mas não tenho como testar a construção da imagem de verdade aqui
no meu ambiente (não tenho Docker nem internet para baixar as camadas
base). Teste no seu PC — se der algum erro na hora do `docker compose up`,
me manda a mensagem que eu ajusto.

Esse mesmo `Dockerfile` também é o que você usaria pra rodar isso num
servidor na nuvem que aceite containers (Render, Railway, Fly.io, um VPS
qualquer) em vez do passo a passo manual abaixo.

## Colocar na nuvem (acesso de qualquer lugar)
Mesmo passo a passo do Render.com que te passei antes:
1. Suba esses arquivos num repositório GitHub.
2. Render → New → Web Service → conecte o repositório.
3. Build: `pip install -r requirements.txt`
4. Start: `gunicorn app:app`
5. Adicione **Persistent Disk** para as pastas `instance/` e `uploads/`
   (senão o banco e as fotos somem a cada novo deploy).
6. Defina a variável de ambiente `SECRET_KEY` com um valor aleatório seu.
7. (Opcional) Rode o comando de download do modelo de IA no shell do
   Render depois do deploy, se quiser a detecção automática ativa.

Alternativa: no Render também dá pra escolher "Docker" como ambiente do
Web Service em vez do build manual — aí ele usa o `Dockerfile` direto.

## Enviar PDF pro aluno
Segue a mesma lógica de antes: baixa o PDF e usa o botão que abre a
conversa do WhatsApp do aluno já pronta pra anexar.
