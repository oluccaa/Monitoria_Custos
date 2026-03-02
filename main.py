from core.config import settings
from infrastructure.file_watcher import iniciar_monitoramento

def main():
    try:
        # 1. Valida .env
        settings.validate()
        
        # 2. Inicia o modo de observação contínua
        iniciar_monitoramento()

    except Exception as e:
        print(f"[FALHA CRÍTICA] Erro ao iniciar sistema: {e}")

if __name__ == "__main__":
    main()