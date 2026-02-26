import json
from infrastructure.excel_adapter import ExcelAdapter
from infrastructure.supabase_adapter import SupabaseAdapter

class SyncBalancoService:
    def __init__(self):
        self.excel_adapter = ExcelAdapter()
        self.supabase_adapter = SupabaseAdapter()

    def executar_sincronizacao(self):
        print("[INFO] Lendo arquivo do Excel e processando regras de negocio...")
        
        # 1. Gera o JSON hierarquico
        dados_json = self.excel_adapter.gerar_estrutura_json()
        
        # 2. Salva o JSON para conferencia local
        nome_arquivo = "debug_balanco_2025.json"
        with open(nome_arquivo, "w", encoding="utf-8") as f:
            json.dump(dados_json, f, ensure_ascii=False, indent=4)
            
        print(f"[SUCESSO] Arquivo '{nome_arquivo}' gerado na raiz do projeto para consulta.")
        
        # 3. Envia para o Banco usando a nova logica de Hash (Upsert)
        print("[INFO] Hasheando estrutura do JSON e sincronizando com as tabelas do Supabase...")
        self.supabase_adapter.processar_e_inserir(dados_json)
        
        print("[SUCESSO] Sincronizacao finalizada. Todos os dados foram atualizados no banco sem duplicidade.")