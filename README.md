![Logo](assets/logo.png?raw=true "Attack Shark Profile Switcher")

# Attack Shark Profile Switcher — V8 e X6, Windows e Linux

Troca o perfil do mouse Attack Shark sozinho: quando você abre um jogo, o
mouse vai para o perfil de jogo (ex.: 1000 Hz, DPI de mira); quando fecha,
volta para o perfil do dia a dia (ex.: 500 Hz, para economizar bateria).
Fica um ícone na bandeja do sistema, uma tela de configurações com abas para
perfis, jogos, logs e atualizações, e o programa se atualiza sozinho.

> **English:** automatic, game-aware profile switcher for Attack Shark mice.
> Works with the **V8** (onboard profiles) and the **X6** (profiles stored in
> `config.json` and sent to the mouse on each switch), on **Windows** (one-file
> installer, self-updating) and **Linux** (`install.sh`). Includes a settings
> window to create and edit profiles, manage the games list and watch logs.
> Fork of [alexandrewillame/Attack-Shark-Profile-Switcher](https://github.com/alexandrewillame/Attack-Shark-Profile-Switcher).

O programa fala direto com o mouse pelo receptor USB. O software oficial da
Attack Shark **não precisa ficar aberto**.

## Mouses suportados

| Mouse | Como funcionam os perfis | Conexão |
|---|---|---|
| **Attack Shark V8** | 4 perfis guardados no próprio mouse, configurados no Attack Shark Mouse Hub | receptor 8K |
| **Attack Shark X6** | o X6 guarda só uma configuração, então os perfis ficam no `config.json` e são enviados inteiros a cada troca | receptor 2.4G ou cabo USB |

No X6, cada perfil define: DPI, polling rate, tempo de resposta do clique,
tempo até dormir, ripple control e angle snap. Não é preciso configurar nada
no software oficial.

## Instalação no Windows

1. Baixe o **`Instalar Attack Shark.exe`** na página de
   [Releases](https://github.com/Vitordotpy/Attack-Shark-Profile-Switcher/releases).
2. Dê dois cliques nele e siga as telas: **Próximo**, **Instalar**, **Concluir**.

Não precisa de Python nem de administrador. O instalador coloca o programa em
`%LOCALAPPDATA%\Programs\Attack Shark`, cria o atalho **Attack Shark** na área
de trabalho e no Menu Iniciar, liga a inicialização com o Windows (opcional) e
já deixa o programa rodando. Rodar o instalador de novo atualiza o programa e
mantém seus perfis e jogos, que ficam em `%APPDATA%\Attack Shark`.

> Como o instalador não tem assinatura digital, o Windows pode mostrar
> "O Windows protegeu o computador". Clique em **Mais informações** >
> **Executar assim mesmo**.

**Desinstalar:** Configurações do Windows > Aplicativos > Aplicativos
instalados > **Attack Shark Profile Switcher** > Desinstalar.

### Rodando pelo código (Python)

Para quem prefere não usar o instalador ou quer mexer no código:

- Windows 10 ou 11 e Python **3.9+ 64-bit** com **tkinter** ("tcl/tk and IDLE"
  no instalador do python.org).
- Baixe o projeto (**Code > Download ZIP**), extraia e dê dois cliques em
  **`install.bat`**. Ele instala as dependências (e o Python, pelo winget, se
  faltar), liga a inicialização com o Windows, cria atalhos e abre o programa.

Não use as duas formas ao mesmo tempo. O instalador `.exe` fecha e remove a
versão em Python se encontrar uma.

## Instalação no Linux

> O suporte ao Linux é novo e **ainda não foi testado em um computador Linux
> com o mouse conectado**. Se algo não funcionar, abra uma
> [issue](https://github.com/Vitordotpy/Attack-Shark-Profile-Switcher/issues)
> com o que aparece na aba **Logs**.

1. Baixe o código-fonte da versão mais recente em
   [Releases](https://github.com/Vitordotpy/Attack-Shark-Profile-Switcher/releases)
   (ou `git clone`) e extraia.
2. No terminal, dentro da pasta:

   ```bash
   ./install.sh
   ```

O instalador:

- confere o Python 3.9+, o `venv` e o `tkinter`, e diz o comando da sua
  distro se faltar algo (ex.: `sudo apt install python3-tk`);
- copia o programa para `~/.local/share/attack-shark`, com um ambiente Python
  próprio (não mexe no Python do sistema);
- instala, com `sudo`, **uma regra udev** que deixa o usuário logado falar com
  o mouse sem ser root (`/etc/udev/rules.d/70-attack-shark.rules`);
- cria o atalho no menu de aplicativos, o ícone na área de trabalho e o início
  automático com o sistema (os dois últimos são opcionais);
- abre o programa.

Os perfis e jogos ficam em `~/.config/attack-shark/config.json` e os logs em
`~/.local/state/attack-shark/`. Rodar o `install.sh` de novo atualiza o
programa. Para remover: `~/.local/share/attack-shark/uninstall.sh`.

**Ícone na bandeja:** no GNOME é preciso a extensão *AppIndicator and
KStatusNotifierItem Support*. KDE, Cinnamon, XFCE e outros já mostram. O
`install.sh` avisa se faltar a biblioteca `AppIndicator`.

**Jogos no Linux:** a detecção procura na Steam (nativa e Flatpak) e na Heroic
(jogos da Epic). Jogos pelo Proton/Wine são reconhecidos pelo nome do `.exe`;
jogos nativos, pelo nome do processo.

## Tela de configurações

Clique no ícone da bandeja (ou botão direito > **Settings**). A tela tem quatro
abas:

- **Perfis**: criar, duplicar, reordenar e remover perfis, e editar DPI,
  polling, resposta do clique, tempo até dormir, ripple e angle snap. O botão
  **Testar no mouse** aplica o perfil na hora, antes de salvar. Também é aqui
  que se escolhe qual perfil usar **fora de jogos** e **em jogos**, e os 6
  estágios do botão de DPI.
- **Jogos**: lista de executáveis que ativam o perfil de jogo. Dá para
  adicionar na mão ou usar **Detectar jogos instalados** (Steam e Epic).
- **Logs**: atividade do programa ao vivo, colorida (trocas de perfil, jogos
  detectados, avisos e erros).

- **Sobre**: versão instalada, **Verificar agora** e **Atualizar agora**, a
  opção de verificar atualizações sozinho e links do projeto.

Ao salvar (botão **Salvar** ou `Ctrl+S`), o programa percebe a mudança e
aplica em até 2 segundos, sem reiniciar. No canto superior aparece se o mouse
está conectado.

A tela também abre sem a bandeja:

```bash
python profiles_editor.py
```

## Atualizações

O programa consulta as [Releases](https://github.com/Vitordotpy/Attack-Shark-Profile-Switcher/releases)
do GitHub 20 segundos depois de abrir e depois uma vez por dia. É uma única
consulta à página pública do projeto; nenhum dado seu é enviado.

- **Windows:** quando há versão nova, aparece uma notificação e o item
  **Update to X.Y.Z** no menu do ícone (ou **Atualizar agora** na aba Sobre).
  Um clique baixa o instalador da Release e atualiza sem telas: o programa
  fecha, troca os arquivos e abre de novo, mantendo perfis, jogos, atalhos e a
  inicialização com o Windows.
- **Linux:** o aviso abre a página da versão nova; para atualizar, baixe o
  código e rode o `install.sh` de novo.

Dá para desligar a verificação na aba **Sobre**.

## Menu da bandeja

![Menu da bandeja](assets/screenshot1.png?raw=true "Menu da bandeja")

- **Update to X.Y.Z**: aparece só quando há versão nova.
- **Settings**: abre a tela de configurações.
- **Auto (game-aware)**: modo normal, troca sozinho conforme o jogo.
- **Pin to Profile N**: trava num perfil e pausa a troca automática.
- **Show popups**: liga ou desliga o aviso na tela nesta sessão.
- **Start at boot**: iniciar junto com o Windows.
- **Detect games**: procura jogos instalados e adiciona os novos.
- **Edit games list**: abre o `config.json`.
- **Open log**: abre a pasta do log.
- **Quit**: fecha o programa e volta o mouse para o perfil do dia a dia.

## Aviso na tela

Ao entrar ou sair de um jogo, aparece um cartão no canto inferior direito com
o perfil novo e o nome do jogo (ou "Desktop"):

![Aviso de troca de perfil](assets/screenshot2.png?raw=true "Aviso de troca de perfil")

## config.json

A tela de configurações edita tudo isso. Se preferir editar na mão, salve o
arquivo em UTF-8.

```json
{
  "default_profile": 1,
  "game_profile": 2,
  "poll_seconds": 2,
  "popup_enabled": true,
  "popup_duration_ms": 10000,
  "games": ["cs2.exe"],
  "x6": {
    "dpi_stages": [800, 1200, 1600, 3200, 5600, 400],
    "profiles": [
      { "name": "Normal", "dpi": 800,  "polling": 500,  "key_response_ms": 8,
        "deep_sleep_min": 10, "ripple": true,  "angle_snap": false },
      { "name": "Jogo",   "dpi": 1600, "polling": 1000, "key_response_ms": 4,
        "deep_sleep_min": 15, "ripple": false, "angle_snap": false }
    ]
  }
}
```

| Campo | Significado |
|---|---|
| `default_profile` | perfil usado fora de jogos (1 = primeiro da lista) |
| `game_profile` | perfil usado enquanto um jogo da lista estiver aberto |
| `poll_seconds` | de quantos em quantos segundos procura jogos abertos |
| `games` | nomes dos executáveis, sem pasta, sem diferenciar maiúsculas. Para descobrir, abra o jogo e veja em Gerenciador de Tarefas > Detalhes |
| `x6.dpi_stages` | os 6 estágios do botão de DPI do X6 (múltiplos de 50, de 50 a 12800) |
| `x6.profiles[].dpi` | DPI do perfil. Se não estiver em `dpi_stages`, ocupa o estágio 1 enquanto o perfil estiver ativo |
| `x6.profiles[].polling` | 125, 250, 500 ou 1000 Hz |
| `x6.profiles[].key_response_ms` | tempo de resposta do clique: número par de 2 a 20 |
| `x6.profiles[].deep_sleep_min` | minutos sem uso até o mouse dormir: 1 a 15 |
| `x6.profiles[].ripple` / `angle_snap` | `true` ou `false` |

No V8, o conteúdo de cada perfil continua sendo configurado no Attack Shark
Mouse Hub; a seção `x6` é ignorada.

## Linha de comando

```bash
python sharkctl.py 2          # vai para o perfil 2
python sharkctl.py get        # lê o perfil ativo (só no V8; o X6 não informa)
python sharkctl.py list       # mostra as interfaces HID encontradas
python switcher.py --dry-run  # registra as decisões sem mexer no mouse
python switcher.py --no-tray  # roda sem ícone na bandeja (avisos continuam)
python profiles_editor.py     # abre a tela de configurações
```

## Gerando os executáveis (Windows)

```bash
python build.py
```

Cria um ambiente virtual próprio (`.venv-build`), instala as dependências e o
PyInstaller e gera `dist\Instalar Attack Shark.exe`. O programa em si
(`Attack Shark.exe`) é gerado como pasta e vai compactado dentro do
instalador. O `Attack Shark.exe` também aceita:

```bash
"Attack Shark.exe" --settings          # abre a tela de configurações
"Attack Shark.exe" --uninstall         # desinstala (o que o Windows chama)
"Instalar Attack Shark.exe" --silent   # instala sem telas (--no-desktop,
                                       # --no-start-menu, --no-startup, --dir)
```

## Publicando uma versão nova

1. Aumente `APP_VERSION` em `app_paths.py` (ex.: `2.1.0` → `2.2.0`).
2. Rode `python build.py` no Windows.
3. No GitHub, crie uma Release com a tag `v2.2.0` e anexe o
   `dist\Instalar Attack Shark.exe`. O GitHub troca os espaços do nome por
   pontos, e o atualizador aceita assim mesmo.

Quem tem a versão anterior recebe o aviso em até um dia, ou na hora pelo
**Verificar agora**.

## Notas técnicas

- **V8:** testado pelo autor original com firmware do mouse V3.03, firmware do
  receptor v3.00 e Attack Shark Mouse Hub V1.0.2.0.
- **Linux:** o acesso ao mouse é pelo `/dev/hidraw*`. Como o Linux tem um nó
  por interface USB (e não um por coleção HID, como o Windows), o programa lê
  o descritor HID em `/sys/class/hidraw/*/device/report_descriptor` para achar
  o canal de configuração (`linhid.py`).
- **X6:** testado com o receptor 2.4G (VID `1D57`, PID `FA60`); o cabo usa o
  PID `FA61`. O protocolo foi capturado do software oficial (`X6.exe`):
  feature reports `0x04` (DPI, ripple, angle snap), `0x06` (polling) e `0x05`
  (resposta do clique, deep sleep e efeito de luz), cada um terminando com uma
  soma de 16 bits. Detalhes em `sharkctl.py`.
- **X6, valores não capturados:** 250 Hz e resposta de 2 a 4 ms seguem a mesma
  regra dos valores capturados, mas não foram vistos sendo enviados pelo app
  oficial. Se notar comportamento estranho, use 500/1000 Hz e 6/8 ms.
- **X6:** enviar resposta do clique ou deep sleep coloca a luz no efeito
  "breathing", porque os três vão no mesmo comando. O motion sync não é
  alterado.

## Créditos

Baseado no [Attack Shark Profile Switcher](https://github.com/alexandrewillame/Attack-Shark-Profile-Switcher)
de **alexandrewillame** (suporte ao V8, detecção de jogos, bandeja e avisos).
Suporte ao X6 e tela de configurações por **Vitordotpy**.

## Licença

[MIT](LICENSE).
