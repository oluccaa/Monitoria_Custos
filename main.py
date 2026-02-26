from core.config import settings
from application.sync_service import SyncBalancoService # <-- Sem o "ç"

def main():
    try:
        # 1. Valida se o .env está configurado corretamente
        settings.validate()
        
        # 2. Instancia e roda o serviço
        servico = SyncBalancoService() # <-- Sem o "ç"
        servico.executar_sincronizacao()

    except Exception as e:
        print(f"[FALHA CRÍTICA] Ocorreu um erro na execução: {e}")

if __name__ == "__main__":
    main()