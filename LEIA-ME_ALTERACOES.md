# O que mudou

Arquivos alterados (copie substituindo os originais na mesma pasta do seu projeto):

- webapp_v8/templates/dashboard.html
- webapp_v8/templates/base.html
- webapp_v8/templates/_icons.html
- webapp_v8/static/css/style.css
- webapp_v8/static/img/quote-atleta.jpg   (nova imagem, usada no rodapé "Disciplina hoje, resultado sempre.")

## Resumo das correções (Painel NM x imagem de referência)

1. Título "PAINEL" branco + "NM" dourado (estava invertido).
2. Ícone de hambúrguer e sino sem caixa de fundo (só o traço), como na imagem.
3. Nome do personal + "Online" ao lado da foto no topo (antes só aparecia embaixo da foto, sem nome).
4. "Online": só o pontinho fica verde, o texto fica branco (antes os dois ficavam verdes).
5. Card "alunos cadastrados": trocou de lugar com a saudação (agora saudação à esquerda, card à direita, do jeito que está na imagem), ganhou o ícone sem caixa de fundo, o "+X% este mês" (usa o cálculo que já existia em `estatisticas_cadastro_mes`, só não estava sendo mostrado) e a seta ">".
6. Badges (sino e contador dos blocos) trocaram de vermelho para dourado.
7. Os 16 blocos do painel agora usam os ícones SVG dourados que já existiam prontos em `_icons.html` (mas não eram usados) em vez de emojis, com o conteúdo centralizado e sem caixa atrás do ícone.
8. "Check-ins hoje" corrigido para "Treinos Concluídos" no resumo do dia.
9. Botão "+" central: virou um círculo escuro com anel dourado (estava preenchido de dourado, invertido).
10. Ícones da barra inferior (Painel/Alunos/Agenda/Mais) trocados de emoji para os SVGs dourados; "Alunos" agora é um ícone de pessoa avulsa e "Mais" uma grade 2x2, iguais aos da imagem.
11. Rodapé "Disciplina hoje, resultado sempre.": aspas maiores, "sempre" em destaque dourado, assinatura em fonte cursiva ao lado do texto, e a foto do atleta (que você enviou) encaixada com um degradê na borda direita do cartão.

## O que eu NÃO inventei (de propósito)

- O número "3" no sino e o "5" em Mensagens na imagem enviada são só valores de exemplo do print. O sino já está ligado a um dado real (atendimentos de hoje). Já "Mensagens" não tem, hoje, um conceito de "não lidas" no banco — não coloquei um número fixo ali pra não mostrar uma contagem falsa. Se quiser esse contador, dá pra criar uma coluna/tabela pra isso.
- Testei tudo com dados fictícios numa cópia do banco (nunca toquei no seu `instance/app.db` de verdade).

---

# Atualização — Chat (caixa de texto, apagar mensagem, janelão e barra de menu)

Arquivos alterados nesta rodada:

- webapp_v8/templates/base.html
- webapp_v8/templates/_chat_bolha.html
- webapp_v8/templates/mensagens_conversa.html
- webapp_v8/templates/aluno_minhas_mensagens_conversa.html
- webapp_v8/templates/mensagens.html
- webapp_v8/templates/aluno_minhas_mensagens.html
- webapp_v8/static/css/style.css
- webapp_v8/static/js/chat.js
- webapp_v8/database.py
- webapp_v8/app.py

## 1. Caixa de digitar mensagem menor
A caixa de texto do chat estava com altura máxima de 110px e mínima de 40px, ocupando bastante espaço da tela quando a pessoa digitava várias linhas. Reduzi para mínimo de 36px e máximo de 68px (tanto no CSS quanto no limite usado pelo JavaScript que ajusta a altura automaticamente).

## 2. Apagar mensagem "para todos" (igual WhatsApp)
- Aperte e segure (ou clique com o botão direito, no computador) em cima de uma mensagem **que você mesmo enviou** para abrir um menu com a opção "Apagar para todos".
- Só quem enviou a mensagem pode apagá-la — isso é validado no servidor, não só na tela.
- Ao apagar, o texto/mídia é realmente removido do banco de dados; a bolha vira "🚫 Mensagem apagada" nos dois lados da conversa (o outro lado atualiza sozinho, sem precisar recarregar a página, no próximo ciclo de verificação de mensagens novas — a cada poucos segundos).
- A pré-visualização da conversa nas telas de lista ("Mensagens") também mostra "🚫 Mensagem apagada" quando a última mensagem foi apagada.
- Foi criada uma nova coluna `apagada` na tabela `mensagens_chat` (migração automática, não precisa fazer nada manual — roda sozinha na primeira vez que o app subir com esse código novo).

## 3. Janelão de fundo sumindo e barra de menu quadrada em telas do aluno
Encontrei a causa: no `base.html`, a tela só ganha o visual de "vidro" (janelão) e a barra inferior arredondada quando o `<body>` recebe uma classe específica (`pagina-interna`, `pagina-aluno-fixa`, etc.). Isso já estava correto para o personal, mas faltava para várias telas do **aluno**: Mensagens (lista), Notificações, Meus Treinos, Detalhe do treino, Minhas Avaliações, Detalhe da avaliação, Minha Anamnese, Minha Agenda e Meu Perfil — nenhuma delas caía em nenhum `elif` do `base.html`, então ficavam sem classe nenhuma e usavam o visual padrão (sem vidro, com a barra de baixo quadrada e colada na borda da tela).

Corrigi adicionando a mesma classe `pagina-interna` (a mesma que o personal já usa) pra qualquer tela do aluno que não seja uma das telas "fixas" especiais (Início do aluno, Chat, Anamnese). Testei e confirmei que agora todas essas telas do aluno abrem com o janelão de vidro por trás e a barra de menu com cantos arredondados, iguais ao restante do sistema.


---

# Atualização — Login, ativação de conta e senhas

Arquivos alterados nesta rodada:

- webapp_v8/templates/base.html
- webapp_v8/templates/aluno_criar_conta.html
- webapp_v8/templates/aluno_perfil.html
- webapp_v8/templates/configuracoes.html
- webapp_v8/static/css/style.css
- webapp_v8/database.py
- webapp_v8/app.py

## 1. Olho mágico (mostrar/ocultar senha) em TODO o sistema
Em vez de mexer tela por tela, coloquei um script único no `base.html` que encontra sozinho qualquer campo de senha da página (login, cadastro do personal, ativação de conta do aluno, "esqueci minha senha" e a nova troca de senha nas configurações) e adiciona o ícone de olho automaticamente. Ou seja: já cobre o login e o cadastro do personal, como você pediu, e de brinde cobre as outras telas com senha também — sem precisar repetir o código em cada uma.

## 2. Senha incorreta no login mais visível
Quando a senha está errada, além do aviso no topo da tela ("Usuário ou senha inválidos"), o campo de senha agora:
- fica com a borda vermelha e balança (efeito de "shake") pra chamar atenção na hora;
- já limpa o campo e coloca o foco nele, pronto pra tentar de novo.

## 3. Reenviar código de verificação por e-mail (aluno)
Encontrei um bug de verdade aqui: ao cadastrar a ficha de um aluno com e-mail, o sistema mostra a mensagem *"você pode reenviar depois pelo perfil do aluno"* — só que esse botão nunca existiu. Corrigi de duas formas:

- **No perfil do aluno (lado do personal):** apareceu um botão "📧 Reenviar código de acesso" — só é mostrado enquanto o aluno ainda não ativou a própria conta.
- **Na tela "Ativar meu acesso" (lado do aluno):** agora tem a opção "Reenviar código", onde o próprio aluno digita o e-mail que o personal cadastrou na ficha dele e recebe um novo código na hora — sem precisar esperar o personal, que é exatamente o problema que você descreveu (personal demora pra liberar/enviar).
  - Se o e-mail não bate com nenhuma ficha cadastrada, mostra uma mensagem clara pedindo para confirmar com o personal.
  - Se a conta já foi ativada, avisa que não precisa reenviar e já pode fazer login.

## 4. Nova seção "Segurança" em Configurações
Outro gap que encontrei: o personal não tinha, dentro do sistema, nenhuma forma de trocar a própria senha — só existia o fluxo de "esqueci minha senha" (que exige sair e usar código por e-mail). Agora, em Configurações, tem um formulário de "Alterar senha" (senha atual + nova senha + confirmação), com a mesma regra de força de senha do cadastro (mínimo 8 caracteres, maiúscula, minúscula e número). Também mostra o e-mail e o ID de acesso (ex: PT0007) da conta, pra facilitar caso precise informar ao suporte ou lembrar do ID de login.

Trocar a senha continua desconectando qualquer OUTRO aparelho logado com a mesma conta (como já acontecia no "esqueci minha senha"), mas a sessão atual (de quem está trocando) continua ativa — não desloga quem acabou de trocar a própria senha.

## O que testei (com dados fictícios, sem tocar no seu banco real)
- Login com senha errada → aviso aparece, campo destaca.
- Login certo, troca de senha certa/errada, sessão continua válida após trocar, outro navegador logado é desconectado, login com a senha antiga passa a falhar e com a nova funciona.
- Reenvio de código (self-service do aluno): e-mail não encontrado, conta já ativa, e envio com sucesso (testado com e sem SMTP configurado).
- Botão "Reenviar código de acesso" no perfil do aluno aparece só enquanto a conta está pendente e some depois de ativada.

## O que eu NÃO mudei (fora do escopo do que foi pedido)
Dei uma passada geral procurando bugs simples e corrigi os dois que encontrei relacionados a login/senha (itens 3 e 4 acima). Não fiz uma auditoria de segurança completa nem mexi em outras áreas do sistema (treinos, avaliações, agenda) nesta rodada — se quiser, posso focar nelas depois.

---

# Atualização — Configuração do aluno, anamnese e bugs nos menus do aluno

Arquivos alterados nesta rodada:

- webapp_v8/app.py
- webapp_v8/templates/base.html
- webapp_v8/templates/aluno_meu_perfil.html
- webapp_v8/templates/aluno_perfil.html
- webapp_v8/templates/aluno_notificacoes.html
- webapp_v8/templates/aluno_treino_detalhe.html
- webapp_v8/static/css/style.css

## 1. "Meu Perfil" do aluno — Segurança (faltava trocar a própria senha)
O personal já tinha, em Configurações, como trocar a própria senha de dentro do app. O aluno não tinha nada parecido — só dava pra ver os próprios dados. Adicionei a mesma seção "Segurança" no Meu Perfil do aluno: senha atual + nova senha + confirmação, mesma regra de força (mínimo 8 caracteres, maiúscula, minúscula e número), e mostra o e-mail/ID de acesso da conta (ex: AL0007). Ao trocar, a sessão atual continua ativa, mas qualquer outro aparelho logado cai.

## 2. Anamnese enviada pro aluno: agora fica marcado em algum lugar
Fui atrás do "não fica selecionando" que você descreveu e não achei nenhum indicador, em lugar nenhum da tela do personal, mostrando se uma anamnese foi enviada, está pendente ou já foi respondida — o personal enviava e não tinha como conferir depois que aquilo realmente "ficou marcado". Adicionei um aviso no perfil do aluno (visão do personal), logo abaixo dos botões "Nova Avaliação"/"Novo Treino":
- 🕓 "Anamnese enviada — aguardando o aluno responder"
- 🕓 "Anamnese em andamento — o aluno já começou a responder"
- ✅ "Anamnese respondida em [data]"

## 3. Caixinha de resposta da anamnese (lado do aluno)
O modal que abre quando o aluno toca em "Você tem uma anamnese pendente" já existia e já funcionava — pergunta por pergunta, Sim/Não, e salva automático sem precisar apertar nada. O que ajustei foi o campo de observação: antes era um campo de texto sempre visível do lado de cada pergunta; agora é um botão "📝 Tem alguma coisa pra falar sobre isso?" que, ao tocar, abre uma caixinha embaixo pra escrever — igual ao que você pediu, e igual ao padrão que já existe do lado do personal. Continua salvando sozinho enquanto o aluno digita.

## 4. Bugs encontrados e corrigidos nos menus do aluno
Dei uma passada por todas as telas do aluno (Meus Treinos, Minhas Avaliações, Minha Agenda, Notificações, Mensagens, Meu Perfil) procurando bugs. Achei dois de verdade:

- **Meus Treinos — o principal.** A ficha de treino é salva como uma lista de "dias" (A, B, C...), cada um com seus próprios exercícios dentro. A tela de detalhe do treino do aluno não sabia disso: lia cada "dia" como se fosse um único exercício, então em vez de mostrar os exercícios de verdade (nome, séries, repetições), aparecia um card genérico escrito só "Exercício", sem séries, sem reps, sem nada — pra TODO treino que tivesse mais de um dia cadastrado. Corrigi reaproveitando a mesma lógica que já existia (e já funcionava certinho) na geração do PDF do treino. Agora a tela mostra cada dia com seu nome (ex.: "Treino A — Segunda · Peito/Tríceps") e, dentro dele, os exercícios de verdade com séries, repetições, observação e link pro vídeo quando o personal cadastrou um.
- **Notificações.** Tocar numa notificação que não era de anamnese (por exemplo, aviso de nova avaliação) não levava a lugar nenhum — só voltava pra própria tela de Notificações. Agora notificação de avaliação leva pra "Minhas Avaliações".

## O que testei
- Troca de senha do aluno: senha atual errada, nova senha fraca, confirmação não bate, e troca certa (sessão atual continua, outro aparelho é desconectado).
- Chip de status da anamnese: enviada, em andamento e respondida — nas três situações, com dados fictícios.
- Caixinha de observação no modal: abre, salva automático, e continua aberta mesmo depois de responder outra pergunta do questionário (não fecha sozinha).
- Detalhe do treino do aluno: testei com uma ficha de 1 dia e outra com 3 dias (letras A/B/C), cada uma com exercícios reais — todos aparecem certos agora, com séries e reps.

## O que eu NÃO mudei (fora do escopo do que foi pedido)
Não mexi nas fichas do personal (treino_form.html, avaliação) nem no restante do sistema fora das telas do aluno — o pedido desta rodada foi especificamente sobre a configuração e os menus do aluno.
