import time
import requests
import logging
import socket
import json
import pyaudio
import psutil
import subprocess
import os
import shutil # Needed for shutil.which
from pathlib import Path
from datetime import datetime
import sys # Needed for exiting on critical errors

# --- Configuration Loading ---
CONFIG_FILE = 'config.json'

def load_config():
    """Loads configuration from JSON file."""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
        # Basic validation (add more as needed)
        if not all(k in config for k in ['headsets', 'log_directory', 'restart_app_path', 'settings_ini_path', 'target_app_process_name', 'restart_app_process_name', 'powershell_device_pattern']):
             raise ValueError("Arquivo de configuração incompleto. Verifique config.example.json.")
        return config
    except FileNotFoundError:
        logging.critical(f"Erro Crítico: Arquivo de configuração '{CONFIG_FILE}' não encontrado.")
        sys.exit(1) # Exit if config is missing
    except json.JSONDecodeError as e:
        logging.critical(f"Erro Crítico: Erro ao decodificar JSON do arquivo de configuração '{CONFIG_FILE}': {e}")
        sys.exit(1)
    except ValueError as e:
         logging.critical(f"Erro Crítico: {e}")
         sys.exit(1)
    except Exception as e:
        logging.critical(f"Erro Crítico inesperado ao carregar configuração: {e}")
        sys.exit(1)

config = load_config()

# --- Environment Variable Loading (Secrets) ---
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

if not BOT_TOKEN:
    logging.critical("Erro Crítico: Variável de ambiente 'TELEGRAM_BOT_TOKEN' não definida.")
    sys.exit(1)
if not CHAT_ID:
    logging.critical("Erro Crítico: Variável de ambiente 'TELEGRAM_CHAT_ID' não definida.")
    sys.exit(1)

# --- Basic Configuration from Loaded Config ---
NOME_DA_MAQUINA = socket.gethostname()
BASE_LOG_DIR = config.get('log_directory', r".\logs") # Default to relative 'logs' dir if not set
os.makedirs(BASE_LOG_DIR, exist_ok=True)

# --- Log File Paths ---
MAIN_LOG_FILE = os.path.join(BASE_LOG_DIR, f"monitoramento_conexao_{NOME_DA_MAQUINA}.txt")
ERROR_LOG_FILE = os.path.join(BASE_LOG_DIR, f"erros_monitoramento_{NOME_DA_MAQUINA}.txt")

# --- Logging Setup ---
# (Setup remains the same, just uses the variables defined above)
# Get the root logger
logger = logging.getLogger()
logger.setLevel(logging.INFO) # Process INFO level and higher

# Remove existing handlers
for handler in logger.handlers[:]:
    logger.removeHandler(handler)

# 1. Handler for the MAIN log (Connections/Disconnections ONLY)
main_log_handler = logging.FileHandler(MAIN_LOG_FILE, encoding='utf-8')
main_log_handler.setLevel(logging.INFO) # Process ONLY INFO level messages
main_formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S') # Use standard date format
main_log_handler.setFormatter(main_formatter)
class InfoLevelFilter(logging.Filter):
    def filter(self, record):
        return record.levelno == logging.INFO
main_log_handler.addFilter(InfoLevelFilter()) # Apply the filter
logger.addHandler(main_log_handler)

# 2. Handler for the ERROR log (Warnings, Errors, Exceptions)
error_log_handler = logging.FileHandler(ERROR_LOG_FILE, encoding='utf-8')
error_log_handler.setLevel(logging.WARNING) # Process WARNING, ERROR, CRITICAL
error_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
error_log_handler.setFormatter(error_formatter)
logger.addHandler(error_log_handler)
# --- End Logging Setup ---


# --- Other Configurations from Loaded Config ---
STATUS_OFFLINE = "🔴"
STATUS_ONLINE = "🟢"
STATE_FILE = os.path.join(BASE_LOG_DIR, "estado_dispositivo.json")
HEADSET_CONFIG = config.get('headsets', {}) # e.g., {"Headset Loja 1": {"app_id": "12", "audio_pattern": "Modelo Headset XPTO", "ps_pattern": "*XPTO*"}, ...}
RESTART_ON_CRASH_APP_PATH = config.get('restart_app_path') # Path to the executable like RestartOnCrash.exe
SETTINGS_FILE_PATH = config.get('settings_ini_path') # Path to the settings.ini file
TARGET_APP_PROCESS_NAME = config.get('target_app_process_name', "microsip.exe") # Process to kill/manage
RESTART_APP_PROCESS_NAME = config.get('restart_app_process_name', "RestartOnCrash.exe") # Process name of the restart app itself
POWERSHELL_DEVICE_PATTERN = config.get('powershell_device_pattern', "*Jabra Link*") # Pattern for PowerShell Get-PnpDevice


# --- Funções Utilitárias (Timestamp, Cálculo de Tempo) ---
# (No changes needed here)
def get_timestamp():
    return datetime.now().strftime("%d/%m/%Y às %H:%M:%S")

def get_datetime_from_timestamp(timestamp_str):
    if not timestamp_str: return None
    try:
        return datetime.strptime(timestamp_str, "%d/%m/%Y às %H:%M:%S")
    except (ValueError, TypeError):
        logging.warning(f"Formato de timestamp inválido ao tentar converter: '{timestamp_str}'")
        return None

def calcular_tempo_desconexao(timestamp_desconexao):
    if not timestamp_desconexao: return "tempo desconhecido"
    data_desconexao = get_datetime_from_timestamp(timestamp_desconexao)
    if not data_desconexao: return "tempo desconhecido (timestamp inválido)"
    agora = datetime.now()
    if agora < data_desconexao: return "menos de um minuto"
    diferenca = agora - data_desconexao
    total_segundos = diferenca.total_seconds()
    if total_segundos < 0: total_segundos = 0
    dias = int(total_segundos // (24 * 3600))
    horas = int((total_segundos % (24 * 3600)) // 3600)
    minutos = int((total_segundos % 3600) // 60)
    if dias >= 1: return f"{dias} dia{'s' if dias > 1 else ''}"
    elif horas >= 1: return f"{horas} hora{'s' if horas > 1 else ''}"
    elif minutos >= 1: return f"{minutos} minuto{'s' if minutos > 1 else ''}"
    else: return "menos de um minuto"


# --- Funções de Estado (Salvar/Carregar) ---
def salvar_estado(estado):
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(estado, f, indent=4)
    except Exception as e:
        logging.error(f"Erro ao salvar estado em {STATE_FILE}: {e}")

def carregar_estado():
    # Initialize based on current config's headsets
    estado_padrao = {nome: {"desconectado": False, "timestamp": None} for nome in HEADSET_CONFIG.keys()}
    if not Path(STATE_FILE).exists():
        return estado_padrao
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            estado_carregado = json.load(f)

            # Sync with current config: Add missing, remove extra
            final_state = {}
            for nome_config in HEADSET_CONFIG.keys():
                if nome_config in estado_carregado:
                    final_state[nome_config] = estado_carregado[nome_config]
                else:
                    logging.warning(f"Headset '{nome_config}' da config não encontrado no estado salvo. Adicionando estado padrão.")
                    final_state[nome_config] = {"desconectado": False, "timestamp": None}

            # Log removed keys if any (optional)
            keys_removed = [k for k in estado_carregado if k not in HEADSET_CONFIG]
            if keys_removed:
                 logging.info(f"Removendo headsets não mais presentes na config do arquivo de estado: {', '.join(keys_removed)}")

            return final_state
    except json.JSONDecodeError as e:
        logging.error(f"Erro ao decodificar JSON do arquivo de estado {STATE_FILE}: {e}. Usando estado padrão para a config atual.")
        return estado_padrao
    except Exception as e:
        logging.error(f"Erro ao carregar estado de {STATE_FILE}: {e}. Usando estado padrão para a config atual.")
        return estado_padrao


# --- Funções de Interação Externa (Telegram, Processos, Arquivos) ---
def enviar_mensagem(mensagem):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": mensagem}
    try:
        response = requests.post(url, data=data, timeout=15)
        response.raise_for_status()
        logging.debug(f"Mensagem enviada com sucesso para o Telegram (Chat ID: {CHAT_ID[:4]}...{CHAT_ID[-4:]})") # Log success but obscure chat id
        return True
    except requests.exceptions.Timeout:
        logging.error("Erro ao enviar mensagem para o Telegram: Timeout")
        return False
    except requests.exceptions.RequestException as e:
        logging.error(f"Erro de rede/HTTP ao enviar mensagem para o Telegram: {e}")
        if hasattr(e, 'response') and e.response is not None:
            logging.error(f"Telegram response: Status {e.response.status_code}, Content: {e.response.text[:200]}...")
        return False
    except Exception as e:
        logging.error(f"Erro inesperado ao enviar mensagem para o Telegram: {e}")
        return False

def encerrar_processo(nome_processo):
    if not nome_processo:
        logging.warning("Tentativa de encerrar processo com nome vazio.")
        return
    nome_processo_lower = nome_processo.lower()
    killed = False
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            proc_name = proc.info.get('name')
            if proc_name and nome_processo_lower in proc_name.lower():
                pid = proc.info['pid']
                p = psutil.Process(pid)
                p.terminate()
                logging.info(f"Processo '{proc_name}' (PID: {pid}) encerrado.")
                killed = True
                # Could add a wait here if needed: p.wait(timeout=3)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass # Process might have already ended or permissions issue
        except Exception as e:
            logging.error(f"Erro ao tentar encerrar {proc.info.get('name','PID '+str(proc.info.get('pid')))}: {e}")
    #if not killed:
    #    logging.info(f"Nenhum processo correspondendo a '{nome_processo}' encontrado para encerrar.")


def modificar_settings(headset_nome, habilitar):
    """Modifica o arquivo INI de settings para habilitar/desabilitar a entrada do app associado ao headset."""
    headset_details = HEADSET_CONFIG.get(headset_nome)
    if not headset_details:
        logging.error(f"Detalhes de configuração para o Headset '{headset_nome}' não encontrados.")
        return
    app_id = headset_details.get('app_id') # e.g., "12"
    # Assuming a pattern like "AppName {app_id}\AppName.exe" - adjust if different
    app_rel_path_pattern = headset_details.get('app_path_pattern_in_settings') # e.g., "microsip {app_id}\\microsip.exe"

    if not app_id or not app_rel_path_pattern:
         logging.error(f"Configuração 'app_id' ou 'app_path_pattern_in_settings' ausente para '{headset_nome}' no config.json")
         return

    # Construct the actual relative path string using the app_id
    app_rel_path = app_rel_path_pattern.replace("{app_id}", str(app_id))

    if not SETTINGS_FILE_PATH or not Path(SETTINGS_FILE_PATH).exists():
        logging.error(f"Arquivo de configuração '{SETTINGS_FILE_PATH}' não encontrado ou não definido no config.json.")
        return

    try:
        with open(SETTINGS_FILE_PATH, "r", encoding="utf-8-sig") as file:
            linhas = file.readlines()

        nova_linhas = []
        dentro_do_bloco_correto = False
        bloco_encontrado = False
        modificacao_feita = False

        for i, linha in enumerate(linhas):
            linha_strip = linha.strip()

            # Detectar início de um novo bloco [Application...] para resetar 'dentro_do_bloco_correto'
            if linha_strip.startswith("[Application"):
                 if dentro_do_bloco_correto:
                     # Se estávamos dentro do bloco correto e chegamos a um novo, resetamos
                     dentro_do_bloco_correto = False

            # Encontrar a linha FileName correspondente ao app do headset
            # Use case-insensitive comparison for robustness
            if linha_strip.lower().startswith("filename=") and linha_strip.lower().endswith(app_rel_path.lower()):
                dentro_do_bloco_correto = True
                bloco_encontrado = True
                nova_linhas.append(linha)
                logging.debug(f"Encontrado bloco para '{app_rel_path}' no arquivo INI.")
                continue # Passa para a próxima linha

            # Se estamos dentro do bloco correto, procurar pela linha 'Enabled='
            if dentro_do_bloco_correto and linha_strip.lower().startswith("enabled="):
                valor_atual_str = linha_strip.split('=')[-1].strip()
                valor_novo = '1' if habilitar else '0'
                logging.debug(f"Bloco '{app_rel_path}': Enabled encontrado. Atual: '{valor_atual_str}', Desejado: '{valor_novo}'")
                if valor_atual_str != valor_novo:
                    nova_linhas.append(f"Enabled={valor_novo}\n")
                    modificacao_feita = True
                    logging.info(f"Modificado status 'Enabled' para '{valor_novo}' para '{headset_nome}' ({app_rel_path}) em '{os.path.basename(SETTINGS_FILE_PATH)}'.")
                else:
                    nova_linhas.append(linha) # Mantém a linha como está se não houver mudança
                # Importante: Sair do bloco após modificar 'Enabled' para evitar modificar outros blocos acidentalmente
                # Isso assume que 'Enabled=' vem depois de 'FileName=' no bloco.
                dentro_do_bloco_correto = False
                continue # Passa para a próxima linha

            # Adicionar todas as outras linhas sem modificação
            nova_linhas.append(linha)

        if not bloco_encontrado:
             logging.error(f"Bloco com 'FileName=...{app_rel_path}' não encontrado em {SETTINGS_FILE_PATH} para {headset_nome}.")
             return

        if modificacao_feita:
            try:
                # Backup opcional antes de sobrescrever
                # shutil.copy2(SETTINGS_FILE_PATH, SETTINGS_FILE_PATH + ".bak")
                with open(SETTINGS_FILE_PATH, "w", encoding="utf-8-sig") as file:
                    file.writelines(nova_linhas)
                logging.debug(f"Arquivo {SETTINGS_FILE_PATH} salvo com modificações.")
            except Exception as e:
                 logging.error(f"Erro ao reescrever {SETTINGS_FILE_PATH} após modificação para {headset_nome}: {e}")
        else:
            logging.debug(f"Nenhuma modificação necessária para '{headset_nome}' em {SETTINGS_FILE_PATH}.")

    except Exception as e:
        logging.exception(f"Erro ao ler ou processar {SETTINGS_FILE_PATH} para {headset_nome}: {e}")


# --- Funções de Verificação de Dispositivos ---
def verificar_dispositivos_audio():
    """Verifica dispositivos de saída de áudio usando PyAudio."""
    pa = None
    original_stderr = -1
    devnull = -1
    stderr_redirected = False
    try:
        # Redirect stderr to prevent PyAudio ALSA/PortAudio messages on console/log
        original_stderr = os.dup(2)
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, 2)
        stderr_redirected = True

        pa = pyaudio.PyAudio()

        # Restore stderr immediately after PyAudio initialization
        os.dup2(original_stderr, 2)
        os.close(devnull) # Close the descriptor for os.devnull
        os.close(original_stderr) # Close the duplicated original stderr descriptor
        stderr_redirected = False

        dispositivos_ativos_saida = []
        num_devices = pa.get_device_count()
        for i in range(num_devices):
            try:
                device_info = pa.get_device_info_by_index(i)
                # Check if it's an output device
                if device_info.get('maxOutputChannels', 0) > 0:
                    dispositivos_ativos_saida.append(device_info)
            except OSError as e:
                 logging.warning(f"PyAudio: Erro de OS ao obter info do dispositivo índice {i} (pode ser normal para alguns dispositivos virtuais): {e}")
            except Exception as e:
                 logging.error(f"PyAudio: Erro inesperado ao obter info do dispositivo índice {i}: {e}")
        logging.debug(f"PyAudio encontrou {len(dispositivos_ativos_saida)} dispositivos de saída.")
        return dispositivos_ativos_saida
    except Exception as e:
        logging.error(f"PyAudio: Erro crítico ao inicializar ou listar dispositivos: {e}")
        # Ensure stderr is restored if initialization fails
        if stderr_redirected:
            try:
                os.dup2(original_stderr, 2)
                os.close(devnull)
                os.close(original_stderr)
            except Exception as restore_e:
                 logging.error(f"Erro ao restaurar stderr após falha do PyAudio: {restore_e}")
        return [] # Return empty list on failure
    finally:
        if pa:
            try:
                pa.terminate()
            except Exception as e:
                logging.error(f"PyAudio: Erro ao terminar instância: {e}")
        # Ensure stderr is restored if function exits via finally (redundant but safe)
        if stderr_redirected:
             try:
                 os.dup2(original_stderr, 2)
                 os.close(devnull)
                 os.close(original_stderr)
             except Exception as final_restore_e:
                 logging.error(f"Erro ao restaurar stderr no finally: {final_restore_e}")


def count_devices_ps(device_name_pattern):
    """Conta dispositivos PnP usando PowerShell com base em um padrão de nome."""
    powershell_executable = shutil.which("powershell.exe")
    if not powershell_executable:
        # Try default path if shutil.which fails (e.g., PATH issues)
        powershell_executable = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
        if not os.path.exists(powershell_executable):
             logging.error(f"FATAL: PowerShell não encontrado. Verifique a instalação ou o PATH. Caminho tentado: {powershell_executable}")
             return -1 # Indicate critical error

    # Construct the PowerShell command securely using the pattern
    # Ensure the pattern doesn't contain malicious characters (basic check)
    if '"' in device_name_pattern or "'" in device_name_pattern or ';' in device_name_pattern:
        logging.error(f"Padrão de nome de dispositivo inválido detectado: {device_name_pattern}")
        return -1

    # Use double quotes inside the PowerShell string for the pattern
    ps_command_to_run = f'Get-PnpDevice -Class Media -Status OK | Where-Object {{ $_.Name -like "{device_name_pattern}" }} | Measure-Object | Select-Object -ExpandProperty Count'

    command_args = [
        powershell_executable,
        "-ExecutionPolicy", "Bypass",
        "-NoProfile",
        "-NonInteractive", # Prevent prompts
        "-Command", ps_command_to_run
    ]

    logging.debug(f"Executando PowerShell: {' '.join(command_args)}")

    try:
        result = subprocess.run(
            command_args,
            capture_output=True,
            text=True,
            check=True, # Raise exception for non-zero exit codes
            encoding='utf-8',
            errors='ignore',
            shell=False, # IMPORTANT: shell=False for security
            creationflags=subprocess.CREATE_NO_WINDOW # Hide PS window
        )
        stdout_output = result.stdout.strip()
        stderr_output = result.stderr.strip()

        if stderr_output:
            # Log stderr as warning, as PS sometimes outputs non-fatal errors here
            logging.warning(f"Saída STDERR do PowerShell (Contagem): {stderr_output}")

        if stdout_output.isdigit():
            count = int(stdout_output)
            logging.debug(f"PowerShell contou {count} dispositivo(s) com padrão '{device_name_pattern}'.")
            return count
        else:
            # Handle cases where the command runs but returns no number (e.g., no devices found returns nothing or specific text)
             if not stdout_output and not stderr_output: # No output likely means 0 devices
                 logging.debug(f"PowerShell não retornou contagem (provavelmente 0) para padrão '{device_name_pattern}'.")
                 return 0
             else:
                logging.error(f"Saída inesperada do PowerShell (Contagem) não é um número: STDOUT='{stdout_output}', STDERR='{stderr_output}'")
                return -1 # Indicate an error in parsing output
    except FileNotFoundError:
        logging.error(f"Erro Crítico: O caminho do PowerShell '{powershell_executable}' não foi encontrado.")
        return -1
    except subprocess.CalledProcessError as e:
        # Log detailed error information from the failed process
        stderr_err = e.stderr.strip() if e.stderr else "N/A"
        stdout_err = e.stdout.strip() if e.stdout else "N/A"
        logging.error(f"Erro ao executar comando PowerShell (Contagem). Código de Saída: {e.returncode}")
        logging.error(f"PS Stderr (on error): {stderr_err}")
        logging.error(f"PS Stdout (on error): {stdout_err}")
        return -1 # Indicate command execution error
    except Exception as e:
        # Catch any other unexpected exceptions during the process run
        logging.exception(f"Erro inesperado ao contar dispositivos via PowerShell (Contagem): {e}")
        return -1 # Indicate unexpected error


# --- Função Principal de Monitoramento ---

def monitorar_dispositivos():
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Monitor de Dispositivos Iniciado - Maquina: {NOME_DA_MAQUINA}")
    logging.info(f"Monitoramento iniciado na máquina {NOME_DA_MAQUINA}.")
    logging.info(f"Configuração carregada de: {CONFIG_FILE}")
    logging.info(f"Headsets monitorados: {', '.join(HEADSET_CONFIG.keys())}")
    logging.info(f"Diretório de Log: {BASE_LOG_DIR}")
    logging.info(f"Arquivo INI: {SETTINGS_FILE_PATH}")
    logging.info(f"App de Reinício: {RESTART_ON_CRASH_APP_PATH}")
    logging.info(f"Processo App Alvo: {TARGET_APP_PROCESS_NAME}")
    logging.info(f"Processo App Reinício: {RESTART_APP_PROCESS_NAME}")
    logging.info(f"Padrão PowerShell: {POWERSHELL_DEVICE_PATTERN}")
    # Log Telegram info carefully
    logging.info(f"Notificações Telegram: Habilitadas (Chat ID: {CHAT_ID[:4]}...{CHAT_ID[-4:]})")


    estado_dispositivos = carregar_estado()
    # Ensure state matches current config after loading
    estado_dispositivos = {k: estado_dispositivos.get(k, {"desconectado": False, "timestamp": None}) for k in HEADSET_CONFIG.keys()}
    salvar_estado(estado_dispositivos) # Save potentially updated state

    while True:
        try:
            dispositivos_audio_ativos = verificar_dispositivos_audio()
            # Prepare a set of lowercased names for efficient checking
            nomes_audio_ativos_lower = {d.get('name', '').lower() for d in dispositivos_audio_ativos if d.get('name')}

            # Use the configured PowerShell pattern
            dongle_count_ps = count_devices_ps(POWERSHELL_DEVICE_PATTERN)
            count_str = str(dongle_count_ps) if dongle_count_ps >= 0 else "N/A (Erro PS)"

            # Check each configured headset
            dispositivos_encontrados_audio = {}
            for nome_config, details in HEADSET_CONFIG.items():
                encontrado = False
                # Get the pattern specific to this headset from config
                audio_pattern = details.get('audio_pattern', '').lower()
                if not audio_pattern:
                    logging.warning(f"Padrão de áudio ('audio_pattern') não definido para '{nome_config}' no config.json. Não será possível detectar.")
                    dispositivos_encontrados_audio[nome_config] = False
                    continue

                # Check if any active audio device name contains the pattern
                for nome_audio_lower in nomes_audio_ativos_lower:
                    if audio_pattern in nome_audio_lower:
                        encontrado = True
                        break # Found it, no need to check other audio devices for this headset
                dispositivos_encontrados_audio[nome_config] = encontrado
                logging.debug(f"Headset '{nome_config}' (Padrão: '{audio_pattern}') Encontrado nos dispositivos de áudio: {encontrado}")

            desconectados_neste_ciclo = []
            reconectados_neste_ciclo = []

            # Compare current status with saved state
            for nome, encontrado_agora in dispositivos_encontrados_audio.items():
                if nome not in estado_dispositivos: # Should not happen if state loaded correctly, but safety check
                     logging.warning(f"Headset '{nome}' encontrado na verificação, mas ausente no estado. Re-inicializando estado.")
                     estado_dispositivos[nome] = {"desconectado": False, "timestamp": None} # Initialize state for safety
                     continue # Skip comparison this cycle

                estava_desconectado = estado_dispositivos[nome].get("desconectado", False) # Default to False if key missing

                if not encontrado_agora and not estava_desconectado:
                    # Device was connected, now it's not
                    desconectados_neste_ciclo.append(nome)
                    logging.debug(f"Status change detected: '{nome}' desconectado.")
                elif encontrado_agora and estava_desconectado:
                    # Device was disconnected, now it's back
                    reconectados_neste_ciclo.append(nome)
                    logging.debug(f"Status change detected: '{nome}' reconectado.")

            restart_necessario = False

            # Process disconnections
            if desconectados_neste_ciclo:
                timestamp_evento = get_timestamp() # Use same timestamp for log and telegram
                logging.info(f"Detectada desconexão de: {', '.join(desconectados_neste_ciclo)}. Encerrando {TARGET_APP_PROCESS_NAME}.")
                encerrar_processo(TARGET_APP_PROCESS_NAME) # Kill the target app only once if multiple disconnect
                restart_necessario = True
                for nome in desconectados_neste_ciclo:
                    log_message = f"{nome.capitalize()} foi desconectado da maquina {NOME_DA_MAQUINA}"
                    logging.info(log_message) # Logged to MAIN log file

                    estado_dispositivos[nome] = {"desconectado": True, "timestamp": timestamp_evento}
                    modificar_settings(nome, False) # Disable in INI file

                    mensagem_telegram = (f"🔌 {nome.capitalize()} DESCONECTADO da maquina {NOME_DA_MAQUINA} {STATUS_OFFLINE}\n"
                                        f"Horário: {timestamp_evento}\n"
                                        f"Contagem Dongles (PS): {count_str}")
                    enviar_mensagem(mensagem_telegram)

            # Process reconnections
            if reconectados_neste_ciclo:
                timestamp_evento = get_timestamp() # Use same timestamp for log and telegram
                logging.info(f"Detectada reconexão de: {', '.join(reconectados_neste_ciclo)}.")
                # Don't kill the app on reconnect, just enable and restart the manager
                restart_necessario = True
                for nome in reconectados_neste_ciclo:
                    log_message = f"{nome.capitalize()} foi reconectado na maquina {NOME_DA_MAQUINA}"
                    logging.info(log_message) # Logged to MAIN log file

                    timestamp_desconexao_anterior = estado_dispositivos[nome].get("timestamp")
                    tempo_desconectado = calcular_tempo_desconexao(timestamp_desconexao_anterior)
                    estado_dispositivos[nome] = {"desconectado": False, "timestamp": None} # Clear state
                    modificar_settings(nome, True) # Enable in INI file

                    mensagem_telegram = (f"🔌 {nome.capitalize()} RECONECTADO na maquina {NOME_DA_MAQUINA} {STATUS_ONLINE}\n"
                                         f"Horário: {timestamp_evento}\n"
                                         f"Tempo desconectado: {tempo_desconectado}\n"
                                         f"Contagem Dongles (PS): {count_str}")
                    enviar_mensagem(mensagem_telegram)


            # Restart the helper application if needed
            if restart_necessario:
                logging.info(f"Mudança de status detectada. Reiniciando o aplicativo auxiliar '{RESTART_APP_PROCESS_NAME}'.")
                encerrar_processo(RESTART_APP_PROCESS_NAME) # Kill existing instance first
                time.sleep(1) # Brief pause
                try:
                    if not RESTART_ON_CRASH_APP_PATH or not os.path.exists(RESTART_ON_CRASH_APP_PATH):
                         logging.error(f"Falha ao reiniciar: Caminho do aplicativo '{RESTART_ON_CRASH_APP_PATH}' inválido ou não encontrado (verifique config.json).")
                    else:
                         # Use Popen for non-blocking start
                         subprocess.Popen([RESTART_ON_CRASH_APP_PATH], shell=False) # Pass path as list item
                         logging.info(f"Aplicativo '{os.path.basename(RESTART_ON_CRASH_APP_PATH)}' iniciado.")
                except Exception as e:
                     logging.error(f"Falha ao executar {RESTART_ON_CRASH_APP_PATH}: {e}")

            # Save state if any changes occurred
            if desconectados_neste_ciclo or reconectados_neste_ciclo:
                salvar_estado(estado_dispositivos)

        except Exception as e:
            # Catch unexpected errors in the main loop
            logging.exception(f"ERRO INESPERADO no loop principal de monitoramento: {e}")
            # Send critical alert if possible
            enviar_mensagem(f"🚨 ERRO INESPERADO no script de monitoramento na maquina {NOME_DA_MAQUINA}. Verificar log de erros: {ERROR_LOG_FILE}. Erro: {e}")
            time.sleep(30) # Wait longer after a critical error

        # Wait before the next check cycle
        time.sleep(5)

# --- Ponto de Entrada ---
if __name__ == "__main__":
    try:
        # Check if config loaded correctly (handled by load_config exiting on failure)
        monitorar_dispositivos()
    except KeyboardInterrupt:
        print(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}] Monitor de Dispositivos Encerrado pelo Usuário.")
        logging.info("Monitoramento encerrado pelo usuário (KeyboardInterrupt).")
    except SystemExit as e:
         # Logged already by the functions causing exit (config load, env var load)
         print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Script encerrado devido a erro crítico na inicialização (código {e.code}). Verifique os logs.")
    except Exception as e:
        # Catch errors happening *outside* the main loop (very unlikely but possible)
        logging.exception(f"ERRO FATAL fora do loop principal: {e}")
        try:
            # Attempt to send a final alert
            enviar_mensagem(f"🚨 ERRO FATAL (fora do loop principal) no script de monitoramento na maquina {NOME_DA_MAQUINA}. Verificar logs em {BASE_LOG_DIR}. Erro: {e}")
        except Exception as final_e:
             logging.error(f"Falha ao enviar notificação de erro fatal: {final_e}")
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Script encerrado devido a erro fatal fora do loop principal. Verifique os logs.")
