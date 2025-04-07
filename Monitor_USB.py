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

# --- Basic Configuration ---
NOME_DA_MAQUINA = socket.gethostname()
# CUSTOMIZE: Path where log files will be stored
BASE_LOG_DIR = r"C:\YOUR_LOG_PATH\Dongle_erro" 
os.makedirs(BASE_LOG_DIR, exist_ok=True)

# --- Log File Paths ---
MAIN_LOG_FILE = os.path.join(BASE_LOG_DIR, f"monitoramento_headsets_{NOME_DA_MAQUINA}.txt")
ERROR_LOG_FILE = os.path.join(BASE_LOG_DIR, f"erros_monitoramento_{NOME_DA_MAQUINA}.txt")

# --- Logging Setup ---
# Get the root logger
logger = logging.getLogger()
logger.setLevel(logging.INFO) # Process INFO level and higher

# Remove existing handlers
for handler in logger.handlers[:]:
    logger.removeHandler(handler)

# 1. Handler for the MAIN log (Connections/Disconnections ONLY)
main_log_handler = logging.FileHandler(MAIN_LOG_FILE, encoding='utf-8')
main_log_handler.setLevel(logging.INFO) # Process ONLY INFO level messages
# Format: Timestamp - Message (as requested)
main_formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S') # Use standard date format
main_log_handler.setFormatter(main_formatter)
# Filter: Only allow INFO level (we will only log connect/disconnect at this level)
# We define a filter that only allows records exactly at INFO level
class InfoLevelFilter(logging.Filter):
    def filter(self, record):
        return record.levelno == logging.INFO
main_log_handler.addFilter(InfoLevelFilter()) # Apply the filter
logger.addHandler(main_log_handler)

# 2. Handler for the ERROR log (Warnings, Errors, Exceptions)
error_log_handler = logging.FileHandler(ERROR_LOG_FILE, encoding='utf-8')
error_log_handler.setLevel(logging.WARNING) # Process WARNING, ERROR, CRITICAL
# Format: Timestamp, Level, Message
error_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
error_log_handler.setFormatter(error_formatter)
logger.addHandler(error_log_handler)
# --- End Logging Setup ---


# --- Other Configurations ---
# CUSTOMIZE: Telegram API Information
BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
CHAT_ID = "YOUR_TELEGRAM_CHAT_ID"
STATUS_OFFLINE = "🔴"
STATUS_ONLINE = "🟢"
STATE_FILE = os.path.join(BASE_LOG_DIR, "estado_dispositivo.json")

# CUSTOMIZE: Configure your devices here
# Format: "Device name": "microsip_number"
HEADSET_CONFIG = {
    "Device 1": "12",  # Replace "Device 1" with your actual device name
    "Device 2": "14",  # Replace "Device 2" with your actual device name
    "Device 3": "16"   # Replace "Device 3" with your actual device name
}

# CUSTOMIZE: Paths to required executables
RESTART_ON_CRASH = r"C:\path\to\RestartOnCrash.exe"  # Update with correct path
SETTINGS_FILE = r"C:\path\to\settings.ini"           # Update with correct path


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
# (No changes needed here - errors already logged to error log)
def salvar_estado(estado):
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(estado, f, indent=4)
    except Exception as e:
        logging.error(f"Erro ao salvar estado em {STATE_FILE}: {e}")

def carregar_estado():
    estado_padrao = {nome: {"desconectado": False, "timestamp": None} for nome in HEADSET_CONFIG}
    if not Path(STATE_FILE).exists():
        return estado_padrao
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            estado_carregado = json.load(f)
            for nome in HEADSET_CONFIG:
                if nome not in estado_carregado:
                    logging.warning(f"Headset '{nome}' da config não encontrado no estado salvo. Adicionando.")
                    estado_carregado[nome] = {"desconectado": False, "timestamp": None}
            keys_to_remove = [k for k in estado_carregado if k not in HEADSET_CONFIG]
            for k in keys_to_remove:
                 del estado_carregado[k]
            return estado_carregado
    except json.JSONDecodeError as e:
        logging.error(f"Erro ao decodificar JSON do arquivo de estado {STATE_FILE}: {e}. Usando estado padrão.")
        return estado_padrao
    except Exception as e:
        logging.error(f"Erro ao carregar estado de {STATE_FILE}: {e}. Usando estado padrão.")
        return estado_padrao


# --- Funções de Interação Externa (Telegram, Processos, Arquivos) ---
# (No changes needed here - errors already logged to error log)
def enviar_mensagem(mensagem):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": mensagem}
    try:
        response = requests.post(url, data=data, timeout=15)
        response.raise_for_status()
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
    nome_processo_lower = nome_processo.lower()
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            proc_name = proc.info.get('name')
            if proc_name and nome_processo_lower in proc_name.lower():
                pid = proc.info['pid']
                p = psutil.Process(pid)
                p.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        except Exception as e:
            logging.error(f"Erro ao tentar encerrar {proc.info.get('name','PID '+str(proc.info.get('pid')))}: {e}")

def modificar_settings(headset, habilitar):
    numero_microsip = HEADSET_CONFIG.get(headset)
    if not numero_microsip:
        logging.error(f"Configuração (número Microsip) para o Headset '{headset}' não encontrada.")
        return
    microsip_rel_path = f"microsip {numero_microsip}\\microsip.exe"
    if not Path(SETTINGS_FILE).exists():
        logging.error(f"Arquivo de configuração {SETTINGS_FILE} não encontrado.")
        return
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8-sig") as file:
            linhas = file.readlines()
        nova_linhas = []
        dentro_do_bloco_correto = False
        bloco_encontrado = False
        modificacao_feita = False
        for i, linha in enumerate(linhas):
            linha_strip = linha.strip()
            if linha_strip.startswith("[Application"):
                 if dentro_do_bloco_correto: dentro_do_bloco_correto = False
            if linha_strip.lower().startswith("filename=") and linha_strip.lower().endswith(microsip_rel_path.lower()):
                dentro_do_bloco_correto = True
                bloco_encontrado = True
                nova_linhas.append(linha)
                continue
            if dentro_do_bloco_correto and linha_strip.lower().startswith("enabled="):
                valor_atual_str = linha_strip.split('=')[-1].strip()
                valor_novo = '1' if habilitar else '0'
                if valor_atual_str != valor_novo:
                    nova_linhas.append(f"Enabled={valor_novo}\n")
                    modificacao_feita = True
                else:
                    nova_linhas.append(linha)
                continue
            nova_linhas.append(linha)
        if not bloco_encontrado:
             logging.error(f"Bloco com 'FileName=...{microsip_rel_path}' não encontrado em {SETTINGS_FILE} para {headset}.")
             return
        if modificacao_feita:
            try:
                with open(SETTINGS_FILE, "w", encoding="utf-8-sig") as file:
                    file.writelines(nova_linhas)
            except Exception as e:
                 logging.error(f"Erro ao reescrever {SETTINGS_FILE} após modificação para {headset}: {e}")
    except Exception as e:
        logging.exception(f"Erro ao ler ou processar {SETTINGS_FILE} para {headset}: {e}")


# --- Funções de Verificação de Dispositivos ---
# (No changes needed here - errors already logged to error log)
def verificar_dispositivos_audio():
    pa = None
    original_stderr = -1 # Initialize
    devnull = -1
    stderr_redirected = False
    try:
        # Redirect stderr before PyAudio init
        original_stderr = os.dup(2)
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, 2)
        stderr_redirected = True
        # Initialize PyAudio with stderr suppressed
        pa = pyaudio.PyAudio()
        # Restore stderr immediately after init
        os.dup2(original_stderr, 2)
        os.close(devnull)
        os.close(original_stderr)
        stderr_redirected = False

        dispositivos_ativos_saida = []
        num_devices = pa.get_device_count()
        for i in range(num_devices):
            try:
                device_info = pa.get_device_info_by_index(i)
                if device_info.get('maxOutputChannels', 0) > 0:
                    dispositivos_ativos_saida.append(device_info)
            except OSError as e:
                 logging.error(f"PyAudio: Erro de OS ao obter info do dispositivo índice {i}: {e}")
            except Exception as e:
                 logging.error(f"PyAudio: Erro ao obter info do dispositivo índice {i}: {e}")
        return dispositivos_ativos_saida
    except Exception as e:
        logging.error(f"PyAudio: Erro crítico ao listar dispositivos: {e}")
        # Ensure stderr restored if init fails
        if stderr_redirected:
            try: os.dup2(original_stderr, 2); os.close(devnull); os.close(original_stderr)
            except: pass
        return []
    finally:
        if pa:
            try: pa.terminate()
            except Exception as e: logging.error(f"PyAudio: Erro ao terminar instância: {e}")
        # Ensure stderr restored if function exits via finally
        if stderr_redirected:
             try: os.dup2(original_stderr, 2); os.close(devnull); os.close(original_stderr)
             except: pass

# CUSTOMIZE: Change the device name being monitored here
def contar_dispositivos_jabra_ps():
    powershell_executable = shutil.which("powershell.exe")
    if not powershell_executable:
        powershell_executable = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
        if not os.path.exists(powershell_executable):
             logging.error(f"FATAL: PowerShell path not found: {powershell_executable}. Cannot count devices.")
             return -1
    # CUSTOMIZE: Replace "Jabra Link 400" with your device name
    device_name = "Jabra Link 400"  # Change this to your device name
    ps_command_to_run = f'Get-PnpDevice -Class Media -Status OK | Where-Object {{ $_.Name -like "*{device_name}*" }}'
    command_args = [ powershell_executable, "-ExecutionPolicy", "Bypass", "-NoProfile", "-Command", ps_command_to_run ]
    try:
        result = subprocess.run(
            command_args, capture_output=True, text=True, check=True,
            encoding='utf-8', errors='ignore', shell=False,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        stdout_output = result.stdout.strip()
        stderr_output = result.stderr.strip()
        if stderr_output: logging.warning(f"PS List Output STDERR: {stderr_output}")
        count = 0
        if stdout_output:
            lines = stdout_output.splitlines()
            for line in lines:
                if line.strip().startswith("OK "): count += 1
        return count
    except FileNotFoundError:
        logging.error(f"Erro Crítico: O caminho do PowerShell '{powershell_executable}' não foi encontrado.")
        return -1
    except subprocess.CalledProcessError as e:
        stderr_err = e.stderr.strip() if e.stderr else "N/A"
        stdout_err = e.stdout.strip() if e.stdout else "N/A"
        logging.error(f"Erro ao executar comando PowerShell (Listar). Código: {e.returncode}")
        logging.error(f"PS Stderr (on error): {stderr_err}")
        logging.error(f"PS Stdout (on error): {stdout_err}")
        return -1
    except Exception as e:
        logging.exception(f"Erro inesperado ao contar Jabra via PowerShell (Listar): {e}")
        return -1

# --- Função Principal de Monitoramento ---

def monitorar_dispositivos():
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Monitor de Headsets Iniciado - Maquina: {NOME_DA_MAQUINA}")
    estado_dispositivos = carregar_estado()

    while True:
        try:
            dispositivos_audio_ativos = verificar_dispositivos_audio()
            nomes_audio_ativos = [d.get('name', '').lower() for d in dispositivos_audio_ativos]
            jabra_dongle_count_ps = contar_dispositivos_jabra_ps()
            jabra_count_str = str(jabra_dongle_count_ps) if jabra_dongle_count_ps >= 0 else "N/A"

            dispositivos_encontrados_audio = {nome: False for nome in HEADSET_CONFIG}
            for nome_config in HEADSET_CONFIG:
                nome_lower = nome_config.lower()
                nome_simplificado = nome_lower.replace("hs ", "")
                for nome_audio in nomes_audio_ativos:
                    if nome_lower in nome_audio or nome_simplificado in nome_audio:
                        dispositivos_encontrados_audio[nome_config] = True
                        break

            desconectados_neste_ciclo = []
            reconectados_neste_ciclo = []
            for nome, encontrado_agora in dispositivos_encontrados_audio.items():
                estava_desconectado = estado_dispositivos[nome].get("desconectado", False)
                if not encontrado_agora and not estava_desconectado:
                    desconectados_neste_ciclo.append(nome)
                elif encontrado_agora and estava_desconectado:
                    reconectados_neste_ciclo.append(nome)

            restart_necessario = False

            if desconectados_neste_ciclo:
                timestamp_telegram = get_timestamp() # Use same timestamp for log and telegram
                restart_necessario = True
                encerrar_processo("microsip.exe")
                for nome in desconectados_neste_ciclo:
                    # --- LOG TO MAIN FILE (INFO Level) ---
                    log_message = f"{nome.capitalize()} foi desconectado da maquina {NOME_DA_MAQUINA}"
                    logging.info(log_message)
                    # -------------------------------------
                    estado_dispositivos[nome] = {"desconectado": True, "timestamp": timestamp_telegram} # Use consistent timestamp
                    modificar_settings(nome, False)
                    mensagem_telegram = (f"🎧 {nome.capitalize()} foi desconectado da maquina {NOME_DA_MAQUINA}{STATUS_OFFLINE}\n"
                                        f"Horário: {timestamp_telegram}\n"
                                        f"Atualmente há {jabra_count_str} Dongles conectados.")
                    enviar_mensagem(mensagem_telegram)

            if reconectados_neste_ciclo:
                timestamp_telegram = get_timestamp() # Use same timestamp for log and telegram
                restart_necessario = True
                for nome in reconectados_neste_ciclo:
                    # --- LOG TO MAIN FILE (INFO Level) ---
                    log_message = f"{nome.capitalize()} foi reconectado da maquina {NOME_DA_MAQUINA}"
                    logging.info(log_message)
                    # ------------------------------------
                    timestamp_desconexao_anterior = estado_dispositivos[nome].get("timestamp")
                    tempo_desconectado = calcular_tempo_desconexao(timestamp_desconexao_anterior)
                    estado_dispositivos[nome] = {"desconectado": False, "timestamp": None} # Clear timestamp on reconnect
                    modificar_settings(nome, True)
                    mensagem_telegram = (f"🎧 {nome.capitalize()} foi reconectado na maquina {NOME_DA_MAQUINA}{STATUS_ONLINE}\n"
                                         f"Horário: {timestamp_telegram}\n"
                                         f"Tempo desconectado: {tempo_desconectado}\n"
                                         f"Atualmente há {jabra_count_str} Dongles conectados.")
                    enviar_mensagem(mensagem_telegram)


            if restart_necessario:
                encerrar_processo("RestartOnCrash.exe")
                time.sleep(1)
                try:
                    if not os.path.exists(RESTART_ON_CRASH):
                         logging.error(f"Falha ao reiniciar: Arquivo {RESTART_ON_CRASH} não encontrado.")
                    else:
                         subprocess.Popen(RESTART_ON_CRASH, shell=False)
                except Exception as e:
                     logging.error(f"Falha ao executar {RESTART_ON_CRASH}: {e}")

            if desconectados_neste_ciclo or reconectados_neste_ciclo:
                salvar_estado(estado_dispositivos)

        except Exception as e:
            logging.exception(f"ERRO CRÍTICO no loop principal: {e}")
            time.sleep(30)

        time.sleep(5)

# --- Ponto de Entrada ---
if __name__ == "__main__":
    try:
        monitorar_dispositivos()
    except KeyboardInterrupt:
        print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] Monitor de Headsets Encerrado pelo Usuário.")
    except Exception as e:
        logging.exception(f"ERRO FATAL fora do loop principal: {e}")
        try:
            enviar_mensagem(f"🚨 ERRO FATAL no script de monitoramento na maquina {NOME_DA_MAQUINA}. Verificar logs em {BASE_LOG_DIR}.")
        except Exception as final_e:
             logging.error(f"Falha ao enviar notificação de erro fatal: {final_e}")

# --- END OF FILE Dongle_Connect.py ---
