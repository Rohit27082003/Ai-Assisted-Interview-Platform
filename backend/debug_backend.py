
import sys
import os

# Add backend to path
sys.path.append(os.getcwd())

try:
    print("Attempting to import app.core.config...")
    from app.core.config import get_settings
    settings = get_settings()
    print(f"Settings loaded. CHROMA_SERVER_PORT={settings.CHROMA_SERVER_PORT}")
    
    print("Attempting to import app.services.vector_store.chroma_service...")
    from app.services.vector_store.chroma_service import ChromaService
    
    print("Attempting to initialize ChromaService...")
    service = ChromaService()
    print("ChromaService initialized successfully.")
    
except Exception as e:
    print(f"❌ Error occurred: {e}")
    import traceback
    traceback.print_exc()
