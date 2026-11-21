"""Translations: Portuguese, English, Spanish, Chinese, Japanese and Russian.

Code calls _("source text", name=value). The source text is the original
Portuguese string (kept without accents, as it always was in the code); the
catalog maps it to each language. A string missing from the catalog is shown
as written, so nothing ever breaks - it just stays in Portuguese.

The language comes from config.json ("language": "auto" | "pt" | "en" | "es" | "zh" | "ja" | "ru");
"auto" follows the system's language and falls back to English.

Portuguese, English and Spanish live in CATALOG below; Chinese, Japanese and
Russian in i18n_extra.py (one dict per language, same keys). To add a
language: add its code to LANGUAGES and a dict to i18n_extra.EXTRA; missing
strings fall back to English.
"""

from __future__ import annotations

import locale
import os
import sys

LANGUAGES = {"pt": "Português", "en": "English", "es": "Español",
             "zh": "中文 (简体)", "ja": "日本語", "ru": "Русский"}
_ORDER = list(LANGUAGES)            # position of each language in the tuples
_lang = "pt"


def system_language() -> str:
    code = ""
    if sys.platform == "win32":
        try:
            import ctypes
            lcid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            code = {0x16: "pt", 0x0A: "es", 0x09: "en", 0x04: "zh", 0x11: "ja",
                    0x19: "ru"}.get(lcid & 0x3FF, "")
        except Exception:
            code = ""
    if not code:
        for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
            if os.environ.get(var):
                code = os.environ[var][:2].lower()
                break
        else:
            try:
                code = (locale.getlocale()[0] or "")[:2].lower()
            except Exception:
                code = ""
    return code if code in LANGUAGES else "en"


def set_language(code: str | None) -> str:
    global _lang
    _lang = code if code in LANGUAGES else system_language()
    return _lang


def current() -> str:
    return _lang


def _(text: str, **kw) -> str:
    entry = CATALOG.get(text)
    extra = _EXTRA.get(_lang)
    if extra is not None:
        out = extra.get(text) or (entry[1] if entry else text)
    elif entry:
        i = _ORDER.index(_lang)
        out = entry[i] if i < len(entry) and entry[i] else entry[1]
    else:
        out = text
    return out.format(**kw) if kw else out


try:
    from i18n_extra import EXTRA as _EXTRA      # zh, ja, ru
except ImportError:
    _EXTRA = {}

# source (pt, as in the code): (pt, en, es)
CATALOG: dict[str, tuple[str, ...]] = {
    # -- common ---------------------------------------------------------------
    "Perfil {n}": ("Perfil {n}", "Profile {n}", "Perfil {n}"),
    "Perfil {n} ({name})": ("Perfil {n} ({name})", "Profile {n} ({name})", "Perfil {n} ({name})"),
    "Desktop": ("Área de trabalho", "Desktop", "Escritorio"),
    "Normal": ("Normal", "Everyday", "Normal"),
    "Jogo": ("Jogo", "Gaming", "Juego"),
    "Novo perfil": ("Novo perfil", "New profile", "Nuevo perfil"),
    "Cancelar": ("Cancelar", "Cancel", "Cancelar"),
    "Remover": ("Remover", "Remove", "Quitar"),

    # -- settings window ------------------------------------------------------
    "Attack Shark - Configuracoes": ("Attack Shark - Configurações", "Attack Shark - Settings",
                                     "Attack Shark - Configuración"),
    "O config.json tem um erro e sera recriado ao salvar:\n{exc}": (
        "O config.json tem um erro e será recriado ao salvar:\n{exc}",
        "config.json has an error and will be recreated when you save:\n{exc}",
        "El config.json tiene un error y se recreará al guardar:\n{exc}"),
    "Perfis do mouse e troca automatica nos jogos": (
        "Perfis do mouse e troca automática nos jogos",
        "Mouse profiles and automatic switching in games",
        "Perfiles del ratón y cambio automático en los juegos"),
    "procurando mouse...": ("procurando mouse...", "looking for the mouse...", "buscando el ratón..."),
    "Perfis": ("Perfis", "Profiles", "Perfiles"),
    "Jogos": ("Jogos", "Games", "Juegos"),
    "Logs": ("Logs", "Logs", "Registros"),
    "Sobre": ("Sobre", "About", "Acerca de"),
    "Fechar": ("Fechar", "Close", "Cerrar"),
    "Salvar": ("Salvar", "Save", "Guardar"),
    "Seus perfis": ("Seus perfis", "Your profiles", "Tus perfiles"),
    "+  Novo": ("+  Novo", "+  New", "+  Nuevo"),
    "Duplicar": ("Duplicar", "Duplicate", "Duplicar"),
    "Testar no mouse": ("Testar no mouse", "Try on the mouse", "Probar en el ratón"),
    "multiplos de 50": ("múltiplos de 50", "multiples of 50", "múltiplos de 50"),
    "Polling rate": ("Polling rate", "Polling rate", "Polling rate"),
    "atualizacoes por segundo": ("atualizações por segundo", "updates per second",
                                 "actualizaciones por segundo"),
    "Resposta do clique": ("Resposta do clique", "Click response", "Respuesta del clic"),
    "menor = mais rapido": ("menor = mais rápido", "lower = faster", "menor = más rápido"),
    "Dormir apos": ("Dormir após", "Sleep after", "Dormir tras"),
    "sem uso, em minutos": ("sem uso, em minutos", "idle, in minutes", "sin uso, en minutos"),
    "Ripple control  —  suaviza tremidas do cursor": (
        "Ripple control  —  suaviza tremidas do cursor",
        "Ripple control  —  smooths cursor jitter",
        "Ripple control  —  suaviza temblores del cursor"),
    "Angle snap  —  endireita movimentos (ruim para mira)": (
        "Angle snap  —  endireita movimentos (ruim para mira)",
        "Angle snap  —  straightens movements (bad for aiming)",
        "Angle snap  —  endereza los movimientos (malo para apuntar)"),
    "Iluminacao": ("Iluminação", "Lighting", "Iluminación"),
    "Efeito": ("Efeito", "Effect", "Efecto"),
    "Escolher cor": ("Escolher cor", "Pick color", "Elegir color"),
    "Brilho": ("Brilho", "Brightness", "Brillo"),
    "Velocidade": ("Velocidade", "Speed", "Velocidad"),
    "Desligado": ("Desligado", "Off", "Apagado"),
    "Estatico": ("Estático", "Static", "Estático"),
    "Breathing": ("Respiração", "Breathing", "Respiración"),
    "Neon": ("Neon", "Neon", "Neón"),
    "Breathing colorido": ("Respiração colorida", "Color breathing", "Respiración de colores"),
    "DPI estatico": ("Cor do DPI, estática", "DPI color, static", "Color del DPI, estático"),
    "DPI breathing": ("Cor do DPI, respirando", "DPI color, breathing", "Color del DPI, respirando"),
    "Macros": ("Macros", "Macros", "Macros"),
    "Botao do mouse": ("Botão do mouse", "Mouse button", "Botón del ratón"),
    "Lateral da frente": ("Lateral da frente", "Front side button", "Lateral delantero"),
    "Lateral de tras": ("Lateral de trás", "Back side button", "Lateral trasero"),
    "Usar macro neste botao": ("Usar macro neste botão", "Use a macro on this button",
                               "Usar macro en este botón"),
    "Repetir": ("Repetir", "Repeat", "Repetir"),
    "vezes a cada clique": ("vezes a cada clique", "times per click", "veces por clic"),
    "Sem macro, o botao faz a funcao normal dele (avancar / voltar no navegador).": (
        "Sem macro, o botão faz a função normal dele (avançar / voltar no navegador).",
        "Without a macro, the button does its normal job (forward / back in the browser).",
        "Sin macro, el botón hace su función normal (adelante / atrás en el navegador)."),
    "Passos da macro": ("Passos da macro", "Macro steps", "Pasos de la macro"),
    "●  Gravar": ("●  Gravar", "●  Record", "●  Grabar"),
    "■  Parar": ("■  Parar", "■  Stop", "■  Detener"),
    "Remover passo": ("Remover passo", "Remove step", "Quitar paso"),
    "Limpar": ("Limpar", "Clear", "Borrar"),
    "Tecla": ("Tecla", "Key", "Tecla"),
    "Acao": ("Ação", "Action", "Acción"),
    "Espera depois (ms)": ("Espera depois (ms)", "Wait after (ms)", "Espera después (ms)"),
    "Espera depois do passo selecionado": ("Espera depois do passo selecionado",
                                           "Wait after the selected step",
                                           "Espera después del paso seleccionado"),
    "Aplicar": ("Aplicar", "Apply", "Aplicar"),
    "Clique em Gravar e aperte as teclas: o programa guarda as teclas e o tempo entre elas.": (
        "Clique em Gravar e aperte as teclas: o programa guarda as teclas e o tempo entre elas.",
        "Click Record and press the keys: the program saves the keys and the time between them.",
        "Haz clic en Grabar y pulsa las teclas: el programa guarda las teclas y el tiempo entre ellas."),
    "As macros ficam gravadas no proprio mouse.": ("As macros ficam gravadas no próprio mouse.",
                                                   "Macros are stored in the mouse itself.",
                                                   "Las macros se guardan en el propio ratón."),
    "Enviar macros para o mouse": ("Enviar macros para o mouse", "Send macros to the mouse",
                                   "Enviar macros al ratón"),
    "Apertar": ("Apertar", "Press", "Pulsar"),
    "Soltar": ("Soltar", "Release", "Soltar"),
    "Gravando... aperte as teclas da macro e depois clique em Parar.": (
        "Gravando... aperte as teclas da macro e depois clique em Parar.",
        "Recording... press the macro's keys, then click Stop.",
        "Grabando... pulsa las teclas de la macro y luego haz clic en Detener."),
    "{count} passo(s) gravado(s).": ("{count} passo(s) gravado(s).", "{count} step(s) recorded.",
                                     "{count} paso(s) grabado(s)."),
    "Limite de {n} passos atingido.": ("Limite de {n} passos atingido.", "Limit of {n} steps reached.",
                                       "Se alcanzó el límite de {n} pasos."),
    "A macro do botao '{button}' nao tem passos.": ("A macro do botão '{button}' não tem passos.",
                                                    "The macro for '{button}' has no steps.",
                                                    "La macro del botón '{button}' no tiene pasos."),
    "✔  Macros enviadas para o mouse.": ("✔  Macros enviadas para o mouse.", "✔  Macros sent to the mouse.",
                                         "✔  Macros enviadas al ratón."),
    "Salvo, mas as macros nao chegaram ao mouse. Use 'Enviar macros para o mouse' com ele conectado.": (
        "Salvo, mas as macros não chegaram ao mouse. Use 'Enviar macros para o mouse' com ele conectado.",
        "Saved, but the macros did not reach the mouse. Use 'Send macros to the mouse' with it connected.",
        "Guardado, pero las macros no llegaron al ratón. Usa 'Enviar macros al ratón' con él conectado."),
    "Bateria {pct}%": ("Bateria {pct}%", "Battery {pct}%", "Batería {pct}%"),
    "Carregando": ("Carregando", "Charging", "Cargando"),
    "Bateria baixa: {pct}%. Hora de carregar o mouse.": (
        "Bateria baixa: {pct}%. Hora de carregar o mouse.",
        "Low battery: {pct}%. Time to charge the mouse.",
        "Batería baja: {pct}%. Es hora de cargar el ratón."),
    "Quando usar": ("Quando usar", "When to use", "Cuándo usar"),
    "Fora de jogos": ("Fora de jogos", "Outside games", "Fuera de juegos"),
    "Em jogos": ("Em jogos", "In games", "En juegos"),
    "Botao de DPI do mouse": ("Botão de DPI do mouse", "Mouse DPI button", "Botón de DPI del ratón"),
    "os 6 estagios que o botao percorre": ("os 6 estágios que o botão percorre",
                                           "the 6 steps the button cycles through",
                                           "las 6 etapas que recorre el botón"),
    "Jogos que ativam o perfil de jogo": ("Jogos que ativam o perfil de jogo",
                                          "Games that turn on the gaming profile",
                                          "Juegos que activan el perfil de juego"),
    "Nome do executavel, sem a pasta. Para descobrir, abra o jogo e veja Gerenciador de Tarefas > Detalhes.": (
        "Nome do executável, sem a pasta. Para descobrir, abra o jogo e veja Gerenciador de Tarefas > Detalhes.",
        "Executable name, without the folder. To find it, open the game and check Task Manager > Details.",
        "Nombre del ejecutable, sin la carpeta. Para saberlo, abre el juego y mira Administrador de tareas > Detalles."),
    "Nome do processo ou do .exe (jogos pelo Proton). Para descobrir, abra o jogo e rode: ps -eo comm,args | grep -i nome": (
        "Nome do processo ou do .exe (jogos pelo Proton). Para descobrir, abra o jogo e rode: ps -eo comm,args | grep -i nome",
        "Process name or .exe name (Proton games). To find it, open the game and run: ps -eo comm,args | grep -i name",
        "Nombre del proceso o del .exe (juegos con Proton). Para saberlo, abre el juego y ejecuta: ps -eo comm,args | grep -i nombre"),
    "Adicionar": ("Adicionar", "Add", "Añadir"),
    "Detectar jogos instalados (Steam e Epic)": ("Detectar jogos instalados (Steam e Epic)",
                                                 "Detect installed games (Steam and Epic)",
                                                 "Detectar juegos instalados (Steam y Epic)"),
    "Atividade do switcher": ("Atividade do programa", "Program activity", "Actividad del programa"),
    "Acompanhar ao vivo": ("Acompanhar ao vivo", "Follow live", "Seguir en vivo"),
    "Copiar": ("Copiar", "Copy", "Copiar"),
    "Abrir pasta": ("Abrir pasta", "Open folder", "Abrir carpeta"),
    "Versao {version}  ·  {system}": ("Versão {version}  ·  {system}", "Version {version}  ·  {system}",
                                      "Versión {version}  ·  {system}"),
    "Troca automatica de perfil para mouses Attack Shark V8 e X6. Codigo aberto, licenca MIT.": (
        "Troca automática de perfil para mouses Attack Shark V8 e X6. Código aberto, licença MIT.",
        "Automatic profile switching for Attack Shark V8 and X6 mice. Open source, MIT license.",
        "Cambio automático de perfil para ratones Attack Shark V8 y X6. Código abierto, licencia MIT."),
    "Idioma": ("Idioma", "Language", "Idioma"),
    "Automatico (idioma do sistema)": ("Automático (idioma do sistema)", "Automatic (system language)",
                                       "Automático (idioma del sistema)"),
    "Atualizacoes": ("Atualizações", "Updates", "Actualizaciones"),
    "Clique em Verificar para procurar uma versao nova.": (
        "Clique em Verificar para procurar uma versão nova.",
        "Click Check to look for a new version.",
        "Haz clic en Comprobar para buscar una versión nueva."),
    "Verificar agora": ("Verificar agora", "Check now", "Comprobar ahora"),
    "Atualizar agora": ("Atualizar agora", "Update now", "Actualizar ahora"),
    "Verificar atualizacoes automaticamente (uma vez por dia)": (
        "Verificar atualizações automaticamente (uma vez por dia)",
        "Check for updates automatically (once a day)",
        "Buscar actualizaciones automáticamente (una vez al día)"),
    "Links": ("Links", "Links", "Enlaces"),
    "Pagina do projeto": ("Página do projeto", "Project page", "Página del proyecto"),
    "Versoes publicadas": ("Versões publicadas", "Releases", "Versiones publicadas"),
    "Relatar um problema": ("Relatar um problema", "Report a problem", "Informar un problema"),
    "Verificando...": ("Verificando...", "Checking...", "Comprobando..."),
    "✔  Voce esta na versao mais recente ({version}).": (
        "✔  Você está na versão mais recente ({version}).",
        "✔  You have the latest version ({version}).",
        "✔  Tienes la versión más reciente ({version})."),
    "⬆  Versao {new} disponivel (voce tem a {version}).": (
        "⬆  Versão {new} disponível (você tem a {version}).",
        "⬆  Version {new} is available (you have {version}).",
        "⬆  Versión {new} disponible (tienes la {version})."),
    "Abrir pagina da versao": ("Abrir página da versão", "Open the release page", "Abrir la página de la versión"),
    "Voce tem alteracoes nao salvas, que serao perdidas. Atualizar mesmo assim?": (
        "Você tem alterações não salvas, que serão perdidas. Atualizar mesmo assim?",
        "You have unsaved changes, which will be lost. Update anyway?",
        "Tienes cambios sin guardar, que se perderán. ¿Actualizar de todos modos?"),
    "Baixando... {pct}%": ("Baixando... {pct}%", "Downloading... {pct}%", "Descargando... {pct}%"),
    "Instalando... o Attack Shark vai fechar e abrir de novo sozinho.": (
        "Instalando... o Attack Shark vai fechar e abrir de novo sozinho.",
        "Installing... Attack Shark will close and reopen by itself.",
        "Instalando... Attack Shark se cerrará y volverá a abrirse solo."),
    "●  Mouse conectado": ("●  Mouse conectado", "●  Mouse connected", "●  Ratón conectado"),
    "●  Mouse nao encontrado": ("●  Mouse não encontrado", "●  Mouse not found", "●  Ratón no encontrado"),
    "(sem nome)": ("(sem nome)", "(no name)", "(sin nombre)"),
    "●  Alteracoes nao salvas   (Ctrl+S para salvar)": (
        "●  Alterações não salvas   (Ctrl+S para salvar)",
        "●  Unsaved changes   (Ctrl+S to save)",
        "●  Cambios sin guardar   (Ctrl+S para guardar)"),
    " (copia)": (" (cópia)", " (copy)", " (copia)"),
    "Perfil": ("Perfil", "Profile", "Perfil"),
    "Precisa ter pelo menos um perfil.": ("Precisa ter pelo menos um perfil.",
                                          "You need at least one profile.",
                                          "Necesitas al menos un perfil."),
    "este perfil": ("este perfil", "this profile", "este perfil"),
    "Remover {name}?": ("Remover {name}?", "Remove {name}?", "¿Quitar {name}?"),
    "Nenhum jogo ainda - adicione abaixo ou use Detectar": (
        "Nenhum jogo ainda - adicione abaixo ou use Detectar",
        "No games yet - add one below or use Detect",
        "Aún no hay juegos - añade uno abajo o usa Detectar"),
    "{name} ja esta na lista": ("{name} já está na lista", "{name} is already on the list",
                                "{name} ya está en la lista"),
    "Procurando...": ("Procurando...", "Searching...", "Buscando..."),
    "Falha ao procurar jogos:\n{error}": ("Falha ao procurar jogos:\n{error}",
                                          "Could not search for games:\n{error}",
                                          "Error al buscar juegos:\n{error}"),
    "{count} jogo(s) adicionado(s):\n\n{list}\n\nConfira a lista: a deteccao pode errar o .exe.": (
        "{count} jogo(s) adicionado(s):\n\n{list}\n\nConfira a lista: a detecção pode errar o .exe.",
        "{count} game(s) added:\n\n{list}\n\nCheck the list: detection can pick the wrong .exe.",
        "{count} juego(s) añadido(s):\n\n{list}\n\nRevisa la lista: la detección puede equivocarse de .exe."),
    "Nenhum jogo novo ({count} encontrado(s)).": ("Nenhum jogo novo ({count} encontrado(s)).",
                                                  "No new games ({count} found).",
                                                  "Ningún juego nuevo ({count} encontrado(s))."),
    "Nenhum log ainda. Ele aparece aqui assim que o switcher estiver rodando (icone na bandeja).": (
        "Nenhum log ainda. Ele aparece aqui assim que o programa estiver rodando (ícone perto do relógio).",
        "No log yet. It shows up here as soon as the program is running (icon next to the clock).",
        "Aún no hay registros. Aparecen aquí cuando el programa esté en marcha (icono junto al reloj)."),
    "Log copiado": ("Log copiado", "Log copied", "Registro copiado"),
    "A pasta de logs ainda nao existe.": ("A pasta de logs ainda não existe.",
                                          "The log folder does not exist yet.",
                                          "La carpeta de registros aún no existe."),
    "Os estagios de DPI precisam ser numeros.": ("Os estágios de DPI precisam ser números.",
                                                 "DPI steps must be numbers.",
                                                 "Las etapas de DPI deben ser números."),
    "Estagio de DPI invalido: {d}\nUse multiplos de 50, de 50 a 12800.": (
        "Estágio de DPI inválido: {d}\nUse múltiplos de 50, de 50 a 12800.",
        "Invalid DPI step: {d}\nUse multiples of 50, from 50 to 12800.",
        "Etapa de DPI no válida: {d}\nUsa múltiplos de 50, de 50 a 12800."),
    "O perfil {n} precisa de um nome.": ("O perfil {n} precisa de um nome.",
                                         "Profile {n} needs a name.",
                                         "El perfil {n} necesita un nombre."),
    "'{name}': o DPI precisa ser um numero.": ("'{name}': o DPI precisa ser um número.",
                                               "'{name}': DPI must be a number.",
                                               "'{name}': el DPI debe ser un número."),
    "'{name}': DPI invalido ({dpi}).\nUse multiplos de 50, de 50 a 12800.": (
        "'{name}': DPI inválido ({dpi}).\nUse múltiplos de 50, de 50 a 12800.",
        "'{name}': invalid DPI ({dpi}).\nUse multiples of 50, from 50 to 12800.",
        "'{name}': DPI no válido ({dpi}).\nUsa múltiplos de 50, de 50 a 12800."),
    "Configuracao invalida: {exc}": ("Configuração inválida: {exc}", "Invalid settings: {exc}",
                                     "Configuración no válida: {exc}"),
    "Nao consegui falar com o mouse:\n{exc}": ("Não consegui falar com o mouse:\n{exc}",
                                               "Could not talk to the mouse:\n{exc}",
                                               "No pude comunicarme con el ratón:\n{exc}"),
    "▶  '{name}' aplicado no mouse (teste, ainda nao salvo)": (
        "▶  '{name}' aplicado no mouse (teste, ainda não salvo)",
        "▶  '{name}' applied to the mouse (test, not saved yet)",
        "▶  '{name}' aplicado al ratón (prueba, aún sin guardar)"),
    "Nao consegui salvar o config.json:\n{exc}": ("Não consegui salvar o config.json:\n{exc}",
                                                  "Could not save config.json:\n{exc}",
                                                  "No pude guardar el config.json:\n{exc}"),
    "✔  Salvo. O switcher aplica em ate 2 segundos.": (
        "✔  Salvo. O programa aplica em até 2 segundos.",
        "✔  Saved. The program applies it within 2 seconds.",
        "✔  Guardado. El programa lo aplica en 2 segundos como máximo."),
    "Salvar as alteracoes antes de fechar?": ("Salvar as alterações antes de fechar?",
                                              "Save your changes before closing?",
                                              "¿Guardar los cambios antes de cerrar?"),
    "O idioma muda quando a janela abrir de novo. Reabrir agora?": (
        "O idioma muda quando a janela abrir de novo. Reabrir agora?",
        "The language changes when the window opens again. Reopen now?",
        "El idioma cambia cuando la ventana se vuelva a abrir. ¿Reabrir ahora?"),

    # -- installer ------------------------------------------------------------
    "Instalar {app}": ("Instalar {app}", "Install {app}", "Instalar {app}"),
    "Bem-vindo": ("Bem-vindo", "Welcome", "Bienvenida"),
    "Opcoes": ("Opções", "Options", "Opciones"),
    "Instalacao": ("Instalação", "Installing", "Instalación"),
    "Pronto": ("Pronto", "Done", "Listo"),
    "Arquivos do programa nao encontrados dentro do instalador.": (
        "Arquivos do programa não encontrados dentro do instalador.",
        "Program files not found inside the installer.",
        "No se encontraron los archivos del programa dentro del instalador."),
    "Fechando o Attack Shark, se estiver aberto...": ("Fechando o Attack Shark, se estiver aberto...",
                                                      "Closing Attack Shark if it is open...",
                                                      "Cerrando Attack Shark si está abierto..."),
    "Preparando a pasta...": ("Preparando a pasta...", "Preparing the folder...", "Preparando la carpeta..."),
    "A pasta escolhida ja tem outros arquivos:\n{target}\n\nEscolha uma pasta vazia.": (
        "A pasta escolhida já tem outros arquivos:\n{target}\n\nEscolha uma pasta vazia.",
        "The chosen folder already has other files:\n{target}\n\nPick an empty folder.",
        "La carpeta elegida ya tiene otros archivos:\n{target}\n\nElige una carpeta vacía."),
    "Nao consegui substituir a versao anterior:\n{exc}": ("Não consegui substituir a versão anterior:\n{exc}",
                                                          "Could not replace the previous version:\n{exc}",
                                                          "No pude reemplazar la versión anterior:\n{exc}"),
    "Copiando arquivos... {n}/{total}": ("Copiando arquivos... {n}/{total}", "Copying files... {n}/{total}",
                                         "Copiando archivos... {n}/{total}"),
    "A copia terminou mas o programa nao apareceu na pasta.": (
        "A cópia terminou, mas o programa não apareceu na pasta.",
        "Copying finished, but the program did not show up in the folder.",
        "La copia terminó, pero el programa no apareció en la carpeta."),
    "Criando atalhos...": ("Criando atalhos...", "Creating shortcuts...", "Creando accesos directos..."),
    "Troca de perfil automatica do mouse Attack Shark": ("Troca de perfil automática do mouse Attack Shark",
                                                         "Automatic profile switching for Attack Shark mice",
                                                         "Cambio automático de perfil del ratón Attack Shark"),
    "Nao consegui criar o atalho:\n{link}\n\n{exc}": ("Não consegui criar o atalho:\n{link}\n\n{exc}",
                                                      "Could not create the shortcut:\n{link}\n\n{exc}",
                                                      "No pude crear el acceso directo:\n{link}\n\n{exc}"),
    "Configurando a inicializacao com o Windows...": ("Configurando a inicialização com o Windows...",
                                                      "Setting up start with Windows...",
                                                      "Configurando el inicio con Windows..."),
    "Registrando em Aplicativos instalados...": ("Registrando em Aplicativos instalados...",
                                                 "Registering under Installed apps...",
                                                 "Registrando en Aplicaciones instaladas..."),
    "Concluido": ("Concluído", "Done", "Completado"),
    "Instalador  ·  versao {version}": ("Instalador  ·  versão {version}", "Installer  ·  version {version}",
                                        "Instalador  ·  versión {version}"),
    "Voltar": ("Voltar", "Back", "Atrás"),
    "Troca de perfil automatica\npara o seu mouse Attack Shark": (
        "Troca de perfil automática\npara o seu mouse Attack Shark",
        "Automatic profile switching\nfor your Attack Shark mouse",
        "Cambio automático de perfil\npara tu ratón Attack Shark"),
    "Em poucos segundos o programa fica pronto e rodando.": (
        "Em poucos segundos o programa fica pronto e rodando.",
        "In a few seconds the program is ready and running.",
        "En pocos segundos el programa estará listo y funcionando."),
    "Muda o perfil sozinho quando voce abre ou fecha um jogo": (
        "Muda o perfil sozinho quando você abre ou fecha um jogo",
        "Switches profile by itself when you open or close a game",
        "Cambia de perfil solo cuando abres o cierras un juego"),
    "Tela para criar perfis de DPI, polling, resposta do clique e mais": (
        "Tela para criar perfis de DPI, polling, resposta do clique e mais",
        "A window to create profiles with DPI, polling, click response and more",
        "Ventana para crear perfiles de DPI, polling, respuesta del clic y más"),
    "Funciona com o V8 e o X6, sem o app oficial aberto": (
        "Funciona com o V8 e o X6, sem o app oficial aberto",
        "Works with the V8 and the X6, without the official app open",
        "Funciona con el V8 y el X6, sin la app oficial abierta"),
    "Nao precisa de Python nem de administrador": ("Não precisa de Python nem de administrador",
                                                   "No Python or administrator rights needed",
                                                   "No necesita Python ni permisos de administrador"),
    "↻  Ja existe uma versao instalada. Ela sera atualizada e seus perfis e jogos serao mantidos.": (
        "↻  Já existe uma versão instalada. Ela será atualizada e seus perfis e jogos serão mantidos.",
        "↻  A version is already installed. It will be updated and your profiles and games kept.",
        "↻  Ya hay una versión instalada. Se actualizará y se conservarán tus perfiles y juegos."),
    "Proximo  →": ("Próximo  →", "Next  →", "Siguiente  →"),
    "Onde instalar": ("Onde instalar", "Where to install", "Dónde instalar"),
    "Alterar...": ("Alterar...", "Change...", "Cambiar..."),
    "Espaco necessario: cerca de {mb} MB  ·  sem administrador": (
        "Espaço necessário: cerca de {mb} MB  ·  sem administrador",
        "Space needed: about {mb} MB  ·  no administrator",
        "Espacio necesario: unos {mb} MB  ·  sin administrador"),
    "Criar atalho na area de trabalho": ("Criar atalho na área de trabalho", "Create a desktop shortcut",
                                         "Crear acceso directo en el escritorio"),
    "Adicionar ao Menu Iniciar": ("Adicionar ao Menu Iniciar", "Add to the Start menu",
                                  "Añadir al menú Inicio"),
    "Iniciar junto com o Windows": ("Iniciar junto com o Windows", "Start with Windows", "Iniciar con Windows"),
    "recomendado: e o que faz a troca automatica funcionar sem voce lembrar de abrir": (
        "recomendado: é o que faz a troca automática funcionar sem você lembrar de abrir",
        "recommended: it keeps automatic switching working without you having to open it",
        "recomendado: así el cambio automático funciona sin que tengas que abrirlo"),
    "Instalar": ("Instalar", "Install", "Instalar"),
    "Escolha onde instalar": ("Escolha onde instalar", "Choose where to install", "Elige dónde instalar"),
    "Instalando...": ("Instalando...", "Installing...", "Instalando..."),
    "Isso leva poucos segundos.": ("Isso leva poucos segundos.", "This takes a few seconds.",
                                   "Esto tarda unos segundos."),
    "Tudo pronto!": ("Tudo pronto!", "All set!", "¡Todo listo!"),
    "O Attack Shark ja esta rodando. Procure o icone dele perto do relogio: clique nele\npara abrir as configuracoes, ou use o atalho \"Attack Shark\" na area de trabalho.": (
        "O Attack Shark já está rodando. Procure o ícone dele perto do relógio: clique nele\npara abrir as configurações, ou use o atalho \"Attack Shark\" na área de trabalho.",
        "Attack Shark is already running. Look for its icon next to the clock: click it\nto open the settings, or use the \"Attack Shark\" shortcut on the desktop.",
        "Attack Shark ya está en marcha. Busca su icono junto al reloj: haz clic en él\npara abrir la configuración, o usa el acceso directo \"Attack Shark\" del escritorio."),
    "Abrir as configuracoes agora para revisar os perfis": (
        "Abrir as configurações agora para revisar os perfis",
        "Open the settings now to review the profiles",
        "Abrir la configuración ahora para revisar los perfiles"),
    "Concluir": ("Concluir", "Finish", "Finalizar"),
    "Nao foi possivel instalar": ("Não foi possível instalar", "Installation failed", "No se pudo instalar"),
    "Tentar de novo": ("Tentar de novo", "Try again", "Intentar de nuevo"),
    "Escolha uma pasta valida.": ("Escolha uma pasta válida.", "Choose a valid folder.",
                                  "Elige una carpeta válida."),
    "Erro inesperado: {exc}": ("Erro inesperado: {exc}", "Unexpected error: {exc}", "Error inesperado: {exc}"),
    "Cancelar a instalacao?": ("Cancelar a instalação?", "Cancel the installation?", "¿Cancelar la instalación?"),

    # -- uninstall --------------------------------------------------------------
    "Desinstalar Attack Shark": ("Desinstalar Attack Shark", "Uninstall Attack Shark", "Desinstalar Attack Shark"),
    "Remover o Attack Shark deste computador?\n\nO mouse fica com a configuracao que estiver ativa agora.": (
        "Remover o Attack Shark deste computador?\n\nO mouse fica com a configuração que estiver ativa agora.",
        "Remove Attack Shark from this computer?\n\nThe mouse keeps whatever settings are active now.",
        "¿Quitar Attack Shark de este equipo?\n\nEl ratón conserva la configuración que tenga activa ahora."),
    "Apagar tambem seus perfis e a lista de jogos?\n\nEscolha Nao para mante-los caso instale de novo.": (
        "Apagar também seus perfis e a lista de jogos?\n\nEscolha Não para mantê-los caso instale de novo.",
        "Also delete your profiles and games list?\n\nChoose No to keep them in case you reinstall.",
        "¿Borrar también tus perfiles y la lista de juegos?\n\nElige No para conservarlos si vuelves a instalar."),
    "Attack Shark foi removido.": ("Attack Shark foi removido.", "Attack Shark was removed.",
                                   "Attack Shark se ha quitado."),

    # -- updater ----------------------------------------------------------------
    "Nao consegui consultar o GitHub: {exc}": ("Não consegui consultar o GitHub: {exc}",
                                               "Could not reach GitHub: {exc}",
                                               "No pude consultar GitHub: {exc}"),
    "Nenhuma versao publicada ainda.": ("Nenhuma versão publicada ainda.", "No release published yet.",
                                        "Aún no hay versiones publicadas."),
    "Esta versao nao tem o instalador anexado.": ("Esta versão não tem o instalador anexado.",
                                                  "This release has no installer attached.",
                                                  "Esta versión no tiene el instalador adjunto."),
    "Endereco de download inesperado: {host}": ("Endereço de download inesperado: {host}",
                                                "Unexpected download address: {host}",
                                                "Dirección de descarga inesperada: {host}"),
    "Download redirecionado para um endereco inesperado: {host}": (
        "Download redirecionado para um endereço inesperado: {host}",
        "Download redirected to an unexpected address: {host}",
        "Descarga redirigida a una dirección inesperada: {host}"),
    "Download maior que o esperado; cancelado.": ("Download maior que o esperado; cancelado.",
                                                  "Download larger than expected; cancelled.",
                                                  "Descarga más grande de lo esperado; cancelada."),
    "Falha ao baixar a atualizacao: {exc}": ("Falha ao baixar a atualização: {exc}",
                                             "Could not download the update: {exc}",
                                             "Error al descargar la actualización: {exc}"),
    "O download veio incompleto. Tente de novo.": ("O download veio incompleto. Tente de novo.",
                                                   "The download is incomplete. Try again.",
                                                   "La descarga quedó incompleta. Inténtalo de nuevo."),

    # -- tray -----------------------------------------------------------------------
    "fixo no Perfil {n}": ("fixo no Perfil {n}", "pinned to Profile {n}", "fijo en el Perfil {n}"),
    "no jogo: {game}": ("no jogo: {game}", "in game: {game}", "en juego: {game}"),
    "area de trabalho": ("área de trabalho", "desktop", "escritorio"),
    "Attack Shark - Perfil {n} ({state})": ("Attack Shark - Perfil {n} ({state})",
                                            "Attack Shark - Profile {n} ({state})",
                                            "Attack Shark - Perfil {n} ({state})"),
    "Iniciar com o sistema  (aplicando...)": ("Iniciar com o sistema  (aplicando...)",
                                              "Start with the system  (applying...)",
                                              "Iniciar con el sistema  (aplicando...)"),
    "Iniciar com o sistema": ("Iniciar com o sistema", "Start with the system", "Iniciar con el sistema"),
    "Nao consegui alterar a inicializacao.": ("Não consegui alterar a inicialização.",
                                              "Could not change start at login.",
                                              "No pude cambiar el inicio automático."),
    "{count} jogo(s) novo(s) adicionado(s).": ("{count} jogo(s) novo(s) adicionado(s).",
                                               "{count} new game(s) added.",
                                               "{count} juego(s) nuevo(s) añadido(s)."),
    "Nenhum jogo novo encontrado.": ("Nenhum jogo novo encontrado.", "No new games found.",
                                     "No se encontraron juegos nuevos."),
    "Versao {version} disponivel. Clique com o botao direito no icone > Atualizar.": (
        "Versão {version} disponível. Clique com o botão direito no ícone > Atualizar.",
        "Version {version} is available. Right-click the icon > Update.",
        "Versión {version} disponible. Clic derecho en el icono > Actualizar."),
    "Baixando a versao {version}...": ("Baixando a versão {version}...", "Downloading version {version}...",
                                       "Descargando la versión {version}..."),
    "A atualizacao falhou: {exc}": ("A atualização falhou: {exc}", "The update failed: {exc}",
                                    "La actualización falló: {exc}"),
    "Atualizando para {version}...": ("Atualizando para {version}...", "Updating to {version}...",
                                      "Actualizando a {version}..."),
    "⬆  Atualizar para {version}": ("⬆  Atualizar para {version}", "⬆  Update to {version}",
                                    "⬆  Actualizar a {version}"),
    "Automatico (conforme o jogo)": ("Automático (conforme o jogo)", "Automatic (game-aware)",
                                     "Automático (según el juego)"),
    "Fixar no {label}": ("Fixar no {label}", "Pin to {label}", "Fijar en {label}"),
    "Mostrar avisos": ("Mostrar avisos", "Show popups", "Mostrar avisos"),
    "Configuracoes (perfis, jogos, logs)": ("Configurações (perfis, jogos, logs)",
                                            "Settings (profiles, games, logs)",
                                            "Configuración (perfiles, juegos, registros)"),
    "Detectar jogos": ("Detectar jogos", "Detect games", "Detectar juegos"),
    "Editar lista de jogos": ("Editar lista de jogos", "Edit games list", "Editar lista de juegos"),
    "Abrir log": ("Abrir log", "Open log", "Abrir registro"),
    "Sair": ("Sair", "Quit", "Salir"),

    # -- device messages --------------------------------------------------------------
    "Attack Shark X6 nao encontrado. O receptor ou o cabo esta conectado?": (
        "Attack Shark X6 não encontrado. O receptor ou o cabo está conectado?",
        "Attack Shark X6 not found. Is the receiver or cable plugged in?",
        "Attack Shark X6 no encontrado. ¿Está conectado el receptor o el cable?"),
    "Sem permissao para abrir {path}. Rode o install.sh (ele instala a regra udev do mouse) e reconecte o receptor.": (
        "Sem permissão para abrir {path}. Rode o install.sh (ele instala a regra udev do mouse) e reconecte o receptor.",
        "No permission to open {path}. Run install.sh (it installs the mouse's udev rule) and replug the receiver.",
        "Sin permiso para abrir {path}. Ejecuta install.sh (instala la regla udev del ratón) y reconecta el receptor."),
}
