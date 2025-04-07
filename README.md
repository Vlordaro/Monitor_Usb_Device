# Monitor_USB: Monitoramento de Headsets com Notificações Telegram e Restart Automático

Sistema para monitorar em tempo real a conexão e desconexão de headsets (USB), com ações automatizadas como envio de notificações via Telegram, reinício de aplicativos e atualização de arquivos `.ini`.

**⚠️ ATENÇÃO DE SEGURANÇA:** Este script armazena informações sensíveis diretamente no código-fonte, como tokens do Telegram e caminhos de arquivos. **NÃO publique este repositório publicamente sem antes externalizar essas configurações em arquivos `.env`, `.json`, ou variáveis de ambiente.**

## Funcionalidades

*   **Monitoramento Contínuo:** Verifica a presença dos headsets listados no dicionário `HEADSET_CONFIG`, usando PyAudio.
*   **Logs Detalhados:**
    *   `monitoramento_headsets_[NOME_MAQUINA].txt` – registro de conexões/desconexões.
    *   `erros_monitoramento_[NOME_MAQUINA].txt` – avisos e erros de execução.
*   **Persistência de Estado:** Mantém um `estado_dispositivo.json` com o status dos dispositivos monitorados.
*   **Notificações Telegram:** Envia alertas de conexão ou desconexão para um chat do Telegram.
*   **Reinício de Aplicações:**
    *   Reinicia o processo de um aplicativo auxiliar (ex: `RestartOnCrash`).
    *   Encerra o processo de um aplicativo alvo (ex: `MicroSIP`) se o dispositivo for desconectado.
*   **Atualização de Arquivo `.ini`:** Altera seções específicas com base na conexão do headset.

## Requisitos

*   **SO:** Windows  
*   **Python:** 3.6+  
*   **PowerShell:** Utilizado para contagem de dispositivos USB  
*   **Bibliotecas Python:**
    ```bash
    pip install pyaudio psutil requests
    ```

## Instalação

1. **Clone o repositório:**
    ```bash
    git clone https://github.com/Vlordaro/Monitor_Usb_Device.git
    cd Monitor_Usb_Device
    ```

2. **Instale as dependências:**
    ```bash
    pip install pyaudio psutil requests
    ```

3. **Configure o script manualmente** conforme instruções abaixo.

## Configuração

Todas as configurações são feitas **diretamente no script `Dongle_Connect.py`**:

1. **Caminho dos logs:**
    ```python
    BASE_LOG_DIR = r"C:\CAMINHO\PARA\OS\LOGS"
    ```

2. **Token e Chat ID do Telegram:**
    ```python
    BOT_TOKEN = "SEU_BOT_TOKEN"
    CHAT_ID = "SEU_CHAT_ID"
    ```

3. **Lista de headsets:**
    ```python
    HEADSET_CONFIG = {
        "Nome do Headset 1": "12",
        "Nome do Headset 2": "14",
        "Nome do Headset 3": "16"
    }
    ```

4. **Caminhos de aplicativos auxiliares:**
    ```python
    RESTART_ON_CRASH = r"C:\Caminho\para\RestartOnCrash.exe"
    SETTINGS_FILE = r"C:\Caminho\para\seu\arquivo.ini"
    ```

5. **Dentro da função `contar_dispositivos_jabra_ps`:**
    Altere o padrão de busca do dispositivo: "Jabra"
    ```python
    ps_command_to_run = 'Get-PnpDevice -PresentOnly | Where-Object { $_.FriendlyName -like "*Jabra*" }'
    ```

6. **Processos a serem encerrados:**
    - Ex: `microsip.exe`, `RestartOnCrash.exe`

## Uso

Após editar o script:

```bash
python Monitor_USB.py
O monitoramento inicia em loop. Use Ctrl + C para parar.
```
## Segurança
🚫 Não compartilhe este código com suas credenciais do Telegram ou caminhos sensíveis.
✅ Recomendado: refatore para usar config.json ou .env + python-dotenv.


##Licença
MIT ©Vinicius Lordaro
