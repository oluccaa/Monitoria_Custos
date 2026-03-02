import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from application.sync_service import SyncBalancoService
from core.config import settings
import os

class ExcelHandler(FileSystemEventHandler):
    def __init__(self):
        self.service = SyncBalancoService()
        self.last_sync = 0

    def on_modified(self, event):
        # O Windows costuma disparar dois eventos de modificação seguidos. 
        # Esta trava de 2 segundos evita que o script rode duas vezes para o mesmo "Salvar".
        if event.src_path == os.path.abspath(settings.EXCEL_FILE_PATH):
            current_time = time.time()
            if current_time - self.last_sync > 2:
                print(f"\n[DETECTADO] Alteração no arquivo: {os.path.basename(event.src_path)}")
                try:
                    self.service.executar_sincronizacao()
                    self.last_sync = current_time
                except Exception as e:
                    print(f"[ERRO] Falha na sincronização automática: {e}")

def iniciar_monitoramento():
    path_to_watch = os.path.dirname(os.path.abspath(settings.EXCEL_FILE_PATH))
    event_handler = ExcelHandler()
    observer = Observer()
    observer.schedule(event_handler, path_to_watch, recursive=False)
    
    observer.start()
    print(f"[STATUS] Monitorando alterações em: {settings.EXCEL_FILE_PATH}")
    print("O sistema atualizará o Supabase automaticamente ao salvar o Excel. Pressione CTRL+C para parar.")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n[DESLIGADO] Monitoramento encerrado.")
    observer.join()