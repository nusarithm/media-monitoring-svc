from supabase import create_client, Client
from app.core.config import settings


class SupabaseClient:
    _instance: Client = None
    
    @classmethod
    def get_client(cls) -> Client:
        if cls._instance is None:
            cls._instance = create_client(
                settings.SUPABASE_URL,
                settings.SUPABASE_KEY
            )
        return cls._instance


class SupabaseServiceClient:
    _service_instance: Client = None

    @classmethod
    def get_client(cls) -> Client:
        if not settings.SUPABASE_SERVICE_ROLE_KEY:
            raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY is not set in environment")
        if cls._service_instance is None:
            cls._service_instance = create_client(
                settings.SUPABASE_URL,
                settings.SUPABASE_SERVICE_ROLE_KEY
            )
        return cls._service_instance


def get_supabase() -> Client:
    return SupabaseClient.get_client()


def get_supabase_service_role() -> Client:
    """Return a Supabase client authenticated with the service role key (bypasses RLS)."""
    return SupabaseServiceClient.get_client()
