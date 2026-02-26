import os
from dotenv import load_dotenv

# Carrega as variáveis do arquivo .env para o ambiente
load_dotenv()

class Settings:
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    EXCEL_FILE_PATH = os.getenv("EXCEL_FILE_PATH")

    @classmethod
    def validate(cls):
        if not cls.SUPABASE_URL or not cls.SUPABASE_KEY:
            raise ValueError("[ERRO] Credenciais do Supabase ausentes no .env")
        if not cls.EXCEL_FILE_PATH:
            raise ValueError("[ERRO] Caminho do arquivo Excel ausente no .env")

settings = Settings()