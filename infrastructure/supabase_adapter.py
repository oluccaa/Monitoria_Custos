import hashlib
from supabase import create_client, Client
from core.config import settings

class SupabaseAdapter:
    def __init__(self):
        self.client: Client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)

    def gerar_hash_unico(self, *args):
        """Gera um hash SHA-256 baseado nos argumentos passados."""
        # Junta os textos com um | (pipe) e remove espaços em branco extras
        texto_base = "|".join(str(a).strip().upper() for a in args)
        return hashlib.sha256(texto_base.encode('utf-8')).hexdigest()

    def processar_e_inserir(self, dados_json: dict):
        linhas_receitas = []
        linhas_investimentos = []
        linhas_despesas = []

        # --- 1. PREPARAR RESUMO OPERACIONAL ---
        resumo_dict = dados_json.get("resumo_operacional")
        amaurilio_dict = dados_json.get("total_amaurilio") # Pega o objeto do Amaurilio
        linha_resumo = None
        if resumo_dict:
            hash_resumo = self.gerar_hash_unico("RESUMO", 2025)
            linha_resumo = {
                "hash_id": hash_resumo,
                "ano_competencia": 2025,
                "receita_total": resumo_dict["receita_total"],
                "despesa_real_operacao": resumo_dict["despesa_real_operacao"],
                "resultado_operacional": resumo_dict["resultado_operacional"],
                "status": resumo_dict["status"],
                "total_amaurilio": amaurilio_dict.get("total_geral") if amaurilio_dict else 0.0
            }

        # --- 2. ACHATAR E HASHEAR LISTAS ---
        for receita in dados_json.get("receitas_detalhadas", []):
            nome = receita["nome_receita"]
            for mes_data in receita.get("detalhamento_mensal", []):
                # Hash = Nome + Mês + Ano Rec + Ano Comp
                hash_id = self.gerar_hash_unico(nome, mes_data["mes"], mes_data["ano_recebimento"], mes_data["ano_competencia"])
                linhas_receitas.append({
                    "hash_id": hash_id,
                    "nome_receita": nome,
                    "mes": mes_data["mes"],
                    "ano_recebimento": mes_data["ano_recebimento"],
                    "ano_competencia": mes_data["ano_competencia"],
                    "valor": mes_data["valor"]
                })

        for inv in dados_json.get("investimentos_detalhados", []):
            nome = inv["nome_investimento"]
            for mes_data in inv.get("detalhamento_mensal", []):
                hash_id = self.gerar_hash_unico(nome, mes_data["mes"], mes_data["ano_pagamento"], mes_data["ano_competencia"])
                linhas_investimentos.append({
                    "hash_id": hash_id,
                    "nome_investimento": nome,
                    "mes": mes_data["mes"],
                    "ano_pagamento": mes_data["ano_pagamento"],
                    "ano_competencia": mes_data["ano_competencia"],
                    "valor": mes_data["valor"]
                })

        for despesa in dados_json.get("despesas_detalhadas", []):
            nome = despesa["nome_despesa"]
            for mes_data in despesa.get("detalhamento_mensal", []):
                hash_id = self.gerar_hash_unico(nome, mes_data["mes"], mes_data["ano_pagamento"], mes_data["ano_competencia"])
                linhas_despesas.append({
                    "hash_id": hash_id,
                    "nome_despesa": nome,
                    "mes": mes_data["mes"],
                    "ano_pagamento": mes_data["ano_pagamento"],
                    "ano_competencia": mes_data["ano_competencia"],
                    "valor": mes_data["valor"]
                })

        # --- 3. ACHATAR TOTAL AMAURILIO ---
        amaurilio_data = dados_json.get("total_amaurilio")
        if amaurilio_data:
            nome = amaurilio_data["nome"]
            for mes_data in amaurilio_data.get("detalhamento_mensal", []):
                # Gera o Hash único para evitar duplicatas: Nome + Mês + Ano Pag + Ano Comp
                hash_id = self.gerar_hash_unico(
                    nome, 
                    mes_data["mes"], 
                    mes_data["ano_pagamento"], 
                    mes_data["ano_competencia"]
                )
                
                # Adiciona à lista de despesas para o banco
                linhas_despesas.append({
                    "hash_id": hash_id,
                    "nome_despesa": nome,
                    "mes": mes_data["mes"],
                    "ano_pagamento": mes_data["ano_pagamento"],
                    "ano_competencia": mes_data["ano_competencia"],
                    "valor": mes_data["valor"]
                })

        # --- 3. UPSERT NO BANCO (Insere ou Atualiza se o Hash existir) ---
        # Note o parâmetro on_conflict='hash_id'
        
        if linha_resumo:
            self.client.table("resumo_operacional").upsert(linha_resumo, on_conflict="hash_id").execute()
            print(" -> Resumo Operacional sincronizado (Upsert).")

        if linhas_receitas:
            res_rec = self.client.table("receitas").upsert(linhas_receitas, on_conflict="hash_id").execute()
            print(f" -> {len(res_rec.data)} registros de receitas sincronizados (Upsert).")
            
        if linhas_investimentos:
            res_inv = self.client.table("investimentos").upsert(linhas_investimentos, on_conflict="hash_id").execute()
            print(f" -> {len(res_inv.data)} registros de investimentos sincronizados (Upsert).")
            
        if linhas_despesas:
            res_desp = self.client.table("despesas").upsert(linhas_despesas, on_conflict="hash_id").execute()
            print(f" -> {len(res_desp.data)} registros de despesas sincronizados (Upsert).")