import pandas as pd
import os
from core.config import settings

class ExcelAdapter:
    def __init__(self):
        self.caminho = settings.EXCEL_FILE_PATH

    def gerar_estrutura_json(self):
        if not os.path.exists(self.caminho):
            raise FileNotFoundError(f"Arquivo não encontrado em: {self.caminho}")

        df = pd.read_excel(self.caminho, sheet_name="Balanço Anual 2025", header=None)

        def achar_linha(palavra_chave):
            resultado = df[df[1].astype(str).str.contains(palavra_chave, case=False, na=False)]
            if not resultado.empty:
                return resultado.index[0]
            raise ValueError(f"Âncora '{palavra_chave}' não encontrada.")

        linha_receita = achar_linha('Adiantamento - Cliente YPFB')
        linha_boletas = achar_linha('Boletas de Garantia')
        linha_cap = achar_linha('Capitalização')
        linha_amaurilio = achar_linha('Total Amaurilio')
        linha_acos = achar_linha('Total Aços Vital')
        
        linha_inicio_despesas = achar_linha('Despesa') + 1
        df_despesas = df.iloc[linha_inicio_despesas:]
        linha_fim_despesas = df_despesas[df_despesas[1].astype(str).str.contains('Total Geral', case=False, na=False)].index[0]

        # Mapeamentos
        meses_entradas_banco = {
            2: {"mes": "Abril", "ano_rec": 2025}, 3: {"mes": "Maio", "ano_rec": 2025}, 4: {"mes": "Junho", "ano_rec": 2025}, 
            5: {"mes": "Julho", "ano_rec": 2025}, 6: {"mes": "Agosto", "ano_rec": 2025}, 7: {"mes": "Setembro", "ano_rec": 2025}, 
            8: {"mes": "Outubro", "ano_rec": 2025}, 9: {"mes": "Novembro", "ano_rec": 2025}, 10: {"mes": "Dezembro", "ano_rec": 2025}, 
            11: {"mes": "Janeiro", "ano_rec": 2026}
        }
        
        meses_despesas_banco = {
            2: {"mes": "Março", "ano_pag": 2025}, 3: {"mes": "Abril", "ano_pag": 2025}, 4: {"mes": "Maio", "ano_pag": 2025}, 
            5: {"mes": "Junho", "ano_pag": 2025}, 6: {"mes": "Julho", "ano_pag": 2025}, 7: {"mes": "Agosto", "ano_pag": 2025}, 
            8: {"mes": "Setembro", "ano_pag": 2025}, 9: {"mes": "Outubro", "ano_pag": 2025}, 10: {"mes": "Novembro", "ano_pag": 2025}, 
            11: {"mes": "Dezembro", "ano_pag": 2025}
        }

        # --- PROCESSAR RESUMO OPERACIONAL ---
        receita_total = round(float(df.iloc[linha_receita, 12]), 2)
        
        val_boleta = pd.to_numeric(df.iloc[linha_boletas, 12], errors='coerce')
        boletas = float(val_boleta) if pd.notna(val_boleta) else 0.0
        val_cap = pd.to_numeric(df.iloc[linha_cap, 12], errors='coerce')
        capitalizacao = float(val_cap) if pd.notna(val_cap) else 0.0
        total_investimentos = round(boletas + capitalizacao, 2)

        despesa_bruta_total = float(df.iloc[linha_amaurilio, 12]) + float(df.iloc[linha_acos, 12])
        despesa_real_operacao = round(despesa_bruta_total - total_investimentos, 2)
        resultado_operacional = round(receita_total - despesa_real_operacao, 2)

        resumo_operacional = {
            "receita_total": receita_total,
            "despesa_real_operacao": despesa_real_operacao,
            "resultado_operacional": resultado_operacional,
            "status": "SUPERÁVIT" if resultado_operacional >= 0 else "DÉFICIT"
        }

        # --- PROCESSAR RECEITAS ---
        nome_receita = str(df.iloc[linha_receita, 1]).strip()
        entradas_mensais = []
        for col_mes in range(2, 12):
            valor_mes = pd.to_numeric(df.iloc[linha_receita, col_mes], errors='coerce')
            if pd.notna(valor_mes) and valor_mes != 0:
                entradas_mensais.append({
                    "mes": meses_entradas_banco[col_mes]["mes"],
                    "ano_recebimento": meses_entradas_banco[col_mes]["ano_rec"],
                    "ano_competencia": 2025,
                    "valor": round(float(valor_mes), 2)
                })
        
        receitas_detalhadas = [{
            "nome_receita": nome_receita if nome_receita.lower() != 'nan' else "Faturamento Bruto",
            "total_geral": receita_total,
            "detalhamento_mensal": entradas_mensais
        }]

        # --- PROCESSAR INVESTIMENTOS ---
        investimentos_detalhados = []
        linhas_investimento = [linha_boletas, linha_cap]
        
        for idx in linhas_investimento:
            nome_inv = str(df.iloc[idx, 1]).strip()
            total_inv = pd.to_numeric(df.iloc[idx, 12], errors='coerce')
            
            if nome_inv.lower() != 'nan' and pd.notna(total_inv) and total_inv != 0:
                gastos_inv = []
                for col_mes in range(2, 12):
                    valor_mes = pd.to_numeric(df.iloc[idx, col_mes], errors='coerce')
                    if pd.notna(valor_mes) and valor_mes != 0:
                        gastos_inv.append({
                            "mes": meses_despesas_banco[col_mes]["mes"],
                            "ano_pagamento": meses_despesas_banco[col_mes]["ano_pag"],
                            "ano_competencia": 2025,
                            "valor": round(float(valor_mes), 2)
                        })
                investimentos_detalhados.append({
                    "nome_investimento": nome_inv,
                    "total_geral": round(float(total_inv), 2),
                    "detalhamento_mensal": gastos_inv
                })

        # --- PROCESSAR DESPESAS ---
        despesas_detalhadas = []
        for i in range(linha_inicio_despesas, linha_fim_despesas): 
            nome_despesa = str(df.iloc[i, 1]).strip()
            total_despesa = pd.to_numeric(df.iloc[i, 12], errors='coerce')
            
            if nome_despesa.lower() != 'nan' and pd.notna(total_despesa) and total_despesa != 0:
                gastos_mensais = []
                for col_mes in range(2, 12):
                    valor_mes = pd.to_numeric(df.iloc[i, col_mes], errors='coerce')
                    if pd.notna(valor_mes) and valor_mes != 0:
                        gastos_mensais.append({
                            "mes": meses_despesas_banco[col_mes]["mes"],
                            "ano_pagamento": meses_despesas_banco[col_mes]["ano_pag"],
                            "ano_competencia": 2025,
                            "valor": round(float(valor_mes), 2)
                        })
                
                despesas_detalhadas.append({
                    "nome_despesa": nome_despesa, 
                    "total_geral": round(float(total_despesa), 2),
                    "detalhamento_mensal": gastos_mensais
                })

        despesas_detalhadas.sort(key=lambda x: x["total_geral"], reverse=True)

        # --- PROCESSAR TOTAL AMAURILIO ---
        linha_amaurilio = achar_linha('Total Amaurilio')
        nome_amaurilio = "TOTAL AMAURILIO"
        total_amaurilio_geral = pd.to_numeric(df.iloc[linha_amaurilio, 12], errors='coerce')
        
        detalhamento_amaurilio = []
        if pd.notna(total_amaurilio_geral) and total_amaurilio_geral != 0:
            for col_mes in range(2, 12):
                valor_mes = pd.to_numeric(df.iloc[linha_amaurilio, col_mes], errors='coerce')
                if pd.notna(valor_mes) and valor_mes != 0:
                    detalhamento_amaurilio.append({
                        "mes": meses_despesas_banco[col_mes]["mes"],
                        "ano_pagamento": meses_despesas_banco[col_mes]["ano_pag"],
                        "ano_competencia": 2025,
                        "valor": round(float(valor_mes), 2)
                    })

        return {
            "resumo_operacional": resumo_operacional,
            "receitas_detalhadas": receitas_detalhadas,
            "investimentos_detalhados": investimentos_detalhados,
            "despesas_detalhadas": despesas_detalhadas,
            "total_amaurilio": {
                "nome": nome_amaurilio,
                "total_geral": round(float(total_amaurilio_geral), 2),
                "detalhamento_mensal": detalhamento_amaurilio
            }
        }