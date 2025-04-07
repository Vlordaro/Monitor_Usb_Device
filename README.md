# Monitor_USB: Monitor de Dispositivos de Áudio USB

Sistema para monitorar a conexão e desconexão de dispositivos de áudio USB configurados, automatizando ações como logging, notificações via Telegram e gerenciamento de aplicativos externos e arquivos de configuração.

## Funcionalidades

*   **Monitoramento Contínuo:** Verifica periodicamente a presença de dispositivos de áudio USB específicos conectados ao sistema (usando PyAudio e opcionalmente PowerShell para contagem).
*   **Logging Detalhado:** Registra eventos de conexão e desconexão em um arquivo de log principal (`monitoramento_conexao_*.txt`).
*   **Log de Erros:** Registra avisos, erros e exceções em um arquivo separado (`erros_monitoramento_*.txt`) para facilitar a depuração.
*   **Notificações Telegram:** Envia mensagens em tempo real para um chat do Telegram configurado sempre que um dispositivo monitorado é conectado ou desconectado, incluindo tempo de inatividade.
*   **Gerenciamento de Configuração:** Modifica automaticamente um arquivo `.ini` especificado para habilitar ou desabilitar entradas correspondentes aos dispositivos conectados/desconectados.
*   **Controle de Processos:** Encerra processos de aplicativos específicos (configurável) quando um dispositivo é desconectado.
*   **Reinício Automatizado:** Encerra e reinicia um aplicativo auxiliar (ex: um gerenciador como RestartOnCrash) após uma mudança no status de conexão do dispositivo para aplicar novas configurações.
*   **Configuração Externa:** Utiliza um arquivo `config.json` para configurações específicas do ambiente (dispositivos, caminhos) e variáveis de ambiente para dados sensíveis (token do Telegram).

## Requisitos

*   **Sistema Operacional:** Windows (devido ao uso de PowerShell para contagem de dispositivos, manipulação de caminhos `.exe`, e modificação de arquivos `.ini` no formato esperado).
*   **Python:** Versão 3.x.
*   **Bibliotecas Python:**
    *   `requests`
    *   `PyAudio`
    *   `psutil`
*   **PowerShell:** Necessário para a funcionalidade de contagem de dispositivos PnP (geralmente incluído no Windows).
*   **Aplicativos Externos:** O script interage com outros aplicativos cujos caminhos e nomes de processo são definidos no `config.json` (ex: o aplicativo alvo e o aplicativo de reinício).

## Instalação

1.  **Clone o Repositório:**
    ```bash
    git clone <URL_DO_SEU_REPOSITORIO>
    cd <NOME_DO_DIRETORIO>
    ```
2.  **Instale as Dependências:**
    ```bash
    pip install requests PyAudio psutil
    ```
    *   **Nota sobre PyAudio:** A instalação do `PyAudio` pode requerer dependências adicionais do sistema (como PortAudio). No Windows, `pip` frequentemente consegue instalar uma versão pré-compilada. Se encontrar problemas, consulte a [documentação oficial do PyAudio](https://people.csail.mit.edu/hubert/pyaudio/) ou procure por wheels pré-compilados para sua versão do Python e arquitetura.

## Configuração

1.  **Variáveis de Ambiente:** Defina as seguintes variáveis de ambiente no sistema onde o script será executado. Elas contêm informações sensíveis e não devem ser armazenadas no código ou no `config.json`.
    *   `TELEGRAM_BOT_TOKEN`: O token do seu bot do Telegram.
    *   `TELEGRAM_CHAT_ID`: O ID do chat do Telegram para onde as notificações serão enviadas.

2.  **Arquivo `config.json`:**
    *   Copie o arquivo `config.example.json` fornecido no repositório para um novo arquivo chamado `config.json` **no mesmo diretório do script**.
    *   **IMPORTANTE:** Adicione `config.json` ao seu arquivo `.gitignore` para evitar enviá-lo acidentalmente para o repositório.
    *   Edite `config.json` e ajuste os valores para corresponder ao seu ambiente:
        *   `log_directory`: Caminho para a pasta onde os logs (`.txt`) e o arquivo de estado (`estado_dispositivo.json`) serão salvos.
        *   `restart_app_path`: Caminho completo para o executável do aplicativo auxiliar a ser reiniciado (ex: `C:\\Caminho\\Para\\RestartOnCrash.exe`).
        *   `settings_ini_path`: Caminho completo para o arquivo `.ini` que será modificado.
        *   `target_app_process_name`: Nome do processo principal a ser encerrado na desconexão (ex: `microsip.exe`).
        *   `restart_app_process_name`: Nome do processo do aplicativo auxiliar a ser reiniciado (ex: `RestartOnCrash.exe`).
        *   `powershell_device_pattern`: Padrão de nome (com wildcards `*`) a ser usado no comando PowerShell `Get-PnpDevice` para contar dongles (ex: `"*Jabra Link*"` ou `"*Dispositivo USB XPTO*"`).
        *   `headsets`: Um dicionário contendo os dispositivos a serem monitorados. Para cada dispositivo:
            *   `"Nome Amigável Headset"`: (Chave) Um nome que você define, usado em logs e notificações.
            *   `app_id`: (Valor) O ID específico associado a este headset no arquivo `.ini`.
            *   `audio_pattern`: (Valor) Uma parte **distintiva** do nome do dispositivo como ele aparece na lista de dispositivos de áudio do Windows (case-insensitive). Ex: `"Jabra EVOLVE 20/30"`.
            *   `app_path_pattern_in_settings`: (Valor) O padrão exato da linha `FileName=` no arquivo `.ini`, usando `{app_id}` como placeholder que será substituído pelo `app_id` correspondente. Ex: `"microsip {app_id}\\microsip.exe"`.

## Uso

1.  Certifique-se de que as variáveis de ambiente estão definidas e o arquivo `config.json` está corretamente configurado.
2.  Execute o script principal a partir do seu terminal ou prompt de comando:
    ```bash
    python Monitor_USB.py
    ```
    *(Substitua `Monitor_USB.py` pelo nome real do seu arquivo Python, se for diferente).*
3.  O script começará a monitorar os dispositivos em segundo plano.
4.  Eventos de conexão/desconexão, modificações no `.ini`, gerenciamento de processos e notificações do Telegram ocorrerão automaticamente.
5.  Verifique os arquivos de log (`monitoramento_conexao_*.txt` e `erros_monitoramento_*.txt`) no diretório configurado para acompanhar a atividade e diagnosticar problemas.

## Licença

MIT
