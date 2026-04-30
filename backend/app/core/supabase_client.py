"""
Cliente de Supabase compartido.
Proporciona dos clientes:
- service_client: usa service_role key, bypassa RLS. Solo para operaciones del backend.
- anon_client: usa anon key, respeta RLS. Para operaciones en nombre del usuario.
"""
from functools import lru_cache

from supabase import Client, create_client

from app.core.config import settings


@lru_cache(maxsize=1)
def get_service_client() -> Client:
    """
    Cliente con permisos elevados (service_role).
    Bypassa Row Level Security. Usar con cuidado.
    """
    if not settings.supabase_url or not settings.supabase_service_key:
        raise RuntimeError(
            "SUPABASE_URL y SUPABASE_SERVICE_KEY deben estar configuradas en .env"
        )
    return create_client(settings.supabase_url, settings.supabase_service_key)


@lru_cache(maxsize=1)
def get_anon_client() -> Client:
    """
    Cliente con permisos públicos (anon).
    Respeta Row Level Security.
    """
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise RuntimeError(
            "SUPABASE_URL y SUPABASE_ANON_KEY deben estar configuradas en .env"
        )
    return create_client(settings.supabase_url, settings.supabase_anon_key)
