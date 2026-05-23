"""
Auth dependencies para FastAPI.

Valida JWTs emitidos por Supabase Auth usando JWKS (claves públicas).

Funcionamiento:
1. Al primer uso, descarga el JWKS de Supabase (lista de claves públicas)
2. Cachea las claves en memoria
3. Para cada request: extrae el JWT, identifica qué clave lo firmó (kid),
   verifica la firma con esa clave pública, retorna user_id.

Soporta:
- ES256 (algoritmo nuevo de Supabase, actual)
- RS256 (otro algoritmo asimétrico común)
- HS256 (algoritmo legacy, por compatibilidad)
"""
from __future__ import annotations

from functools import lru_cache
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import settings


security = HTTPBearer(auto_error=False)


class AuthError(HTTPException):
    def __init__(self, detail: str = "No autenticado"):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )


@lru_cache(maxsize=1)
def get_jwks_client() -> PyJWKClient:
    """Cliente JWKS cacheado con las claves públicas de Supabase."""
    if not settings.supabase_url:
        raise AuthError("Backend mal configurado: falta SUPABASE_URL")

    base_url = settings.supabase_url.rstrip("/")
    jwks_url = f"{base_url}/auth/v1/.well-known/jwks.json"
    return PyJWKClient(jwks_url, cache_keys=True)


def decode_supabase_jwt(token: str) -> dict:
    """Decodifica y valida un JWT de Supabase soportando ES256/RS256/HS256."""
    try:
        unverified_header = jwt.get_unverified_header(token)
        algorithm = unverified_header.get("alg")
    except jwt.InvalidTokenError as e:
        raise AuthError(f"Token malformado: {e}")

    if not algorithm:
        raise AuthError("Token sin algoritmo declarado")

    if algorithm in ("ES256", "RS256"):
        return _decode_with_jwks(token, algorithm)
    elif algorithm == "HS256":
        return _decode_with_secret(token)
    else:
        raise AuthError(f"Algoritmo no soportado: {algorithm}")


def _decode_with_jwks(token: str, algorithm: str) -> dict:
    """Valida un JWT con clave pública obtenida del JWKS de Supabase."""
    try:
        jwks_client = get_jwks_client()
        signing_key = jwks_client.get_signing_key_from_jwt(token)

        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=[algorithm],
            audience="authenticated",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthError("Token expirado")
    except jwt.InvalidAudienceError:
        raise AuthError("Audience inválido en el token")
    except jwt.InvalidTokenError as e:
        raise AuthError(f"Token inválido: {e}")
    except Exception as e:
        raise AuthError(f"Error validando JWKS: {e}")


def _decode_with_secret(token: str) -> dict:
    """Valida un JWT con SUPABASE_JWT_SECRET (legacy HS256)."""
    if not settings.supabase_jwt_secret:
        raise AuthError(
            "Token usa HS256 pero falta SUPABASE_JWT_SECRET."
        )
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthError("Token expirado")
    except jwt.InvalidTokenError as e:
        raise AuthError(f"Token inválido: {e}")


def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> UUID:
    """Dependencia FastAPI: retorna el UUID del usuario autenticado."""
    if credentials is None:
        raise AuthError("Falta header Authorization")

    if credentials.scheme.lower() != "bearer":
        raise AuthError("Esquema de auth incorrecto, se espera Bearer")

    payload = decode_supabase_jwt(credentials.credentials)

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise AuthError("Token sin claim 'sub' (user_id)")

    try:
        return UUID(user_id_str)
    except ValueError:
        raise AuthError(f"user_id no es un UUID válido: {user_id_str}")
