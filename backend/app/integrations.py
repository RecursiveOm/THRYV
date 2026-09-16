"""Owned OAuth connections; fixed official endpoints, never model-supplied URLs."""

import asyncio
import base64
import hashlib
import json
import secrets
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, StrictBool
from sqlalchemy import delete, select, update

from app.auth import COOKIE_NAME, DB, Account, digest
from app.database import Integration, OAuthState, now
from app.errors import AppError
from app.vault import cipher

router = APIRouter()
SERVICE_TIMEOUT = 15
GOOGLE = "https://www.googleapis.com/auth/"
SERVICES = {
    "github": {"read": "repo", "write": "", "api": "https://api.github.com"},
    "gmail": {
        "read": GOOGLE + "gmail.readonly",
        "write": GOOGLE + "gmail.send",
        "api": "https://gmail.googleapis.com",
    },
    "calendar": {
        "read": GOOGLE + "calendar.readonly",
        "write": GOOGLE + "calendar.events",
        "api": "https://www.googleapis.com",
    },
    "drive": {"read": GOOGLE + "drive.readonly", "write": "", "api": "https://www.googleapis.com"},
}


def service_config(settings, service):
    if service not in SERVICES:
        raise AppError("integration_unknown", "This service is not supported.", 404)
    prefix = "github" if service == "github" else "google"
    identifier = getattr(settings, prefix + "_client_id")
    secret = getattr(settings, prefix + "_client_secret")
    if not identifier or not secret:
        raise AppError(
            "integration_unconfigured", "The host must configure this OAuth app first.", 503
        )
    return identifier, secret.get_secret_value()


def seal(settings, owner, service, data):
    return (
        cipher(settings)
        .encrypt(json.dumps({"owner": str(owner), "service": service, "data": data}).encode())
        .decode()
    )


def unseal(settings, owner, service, ciphertext):
    try:
        data = json.loads(cipher(settings).decrypt(ciphertext.encode()))
        if data["owner"] != str(owner) or data["service"] != service:
            raise ValueError
        return data["data"]
    except Exception:
        raise AppError(
            "integration_reconnect", "Reconnect this service in Connected Apps.", 409
        ) from None


class Transport:
    async def call(
        self, method, url, *, token=None, data=None, params=None, body=None, auth=None, text=False
    ):
        headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
        if token:
            headers["Authorization"] = "Bearer " + token
        try:
            async with (
                asyncio.timeout(SERVICE_TIMEOUT),
                httpx.AsyncClient(
                    trust_env=False, follow_redirects=False, timeout=SERVICE_TIMEOUT
                ) as client,
            ):
                async with client.stream(
                    method, url, headers=headers, data=data, params=params, json=body, auth=auth
                ) as response:
                    if response.status_code in (401, 403):
                        raise AppError(
                            "integration_reconnect",
                            "Service access expired or lacks permission; reconnect.",
                            409,
                        )
                    if response.status_code >= 300:
                        raise AppError(
                            "integration_unavailable",
                            "The service could not complete this request.",
                            422,
                        )
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 1_000_000:
                            raise AppError(
                                "integration_limit",
                                "Service response exceeds the safe size limit.",
                                422,
                            )
                    if text:
                        return raw.decode("utf-8", "replace")[:12000]
                    return json.loads(raw) if raw else {}
        except (httpx.HTTPError, ValueError, TimeoutError):
            raise AppError(
                "integration_unavailable", "The service request was unavailable.", 422
            ) from None


async def access(app, db, owner, service):
    item = await db.scalar(
        select(Integration).where(Integration.user_id == owner, Integration.service == service)
    )
    if not item or item.status != "connected":
        raise AppError("integration_reconnect", "Connect this service in Settings first.", 409)
    data = unseal(app.state.settings, owner, service, item.ciphertext)
    if item.expires_at and item.expires_at <= now() + 60:
        identifier, secret = service_config(app.state.settings, service)
        if not data.get("refresh_token"):
            raise AppError("integration_reconnect", "Reconnect this expired service.", 409)
        endpoint = (
            "https://github.com/login/oauth/access_token"
            if service == "github"
            else "https://oauth2.googleapis.com/token"
        )
        before = item.ciphertext
        try:
            fresh = await app.state.integrations.call(
                "POST",
                endpoint,
                data={
                    "client_id": identifier,
                    "client_secret": secret,
                    "grant_type": "refresh_token",
                    "refresh_token": data["refresh_token"],
                },
            )
            if not fresh.get("access_token"):
                raise AppError("integration_reconnect", "Reconnect this service.", 409)
        except AppError:
            await db.execute(
                update(Integration)
                .where(
                    Integration.user_id == owner,
                    Integration.service == service,
                    Integration.ciphertext == before,
                )
                .values(status="reconnect")
            )
            await db.commit()
            raise
        data.update(fresh)
        changed = await db.execute(
            update(Integration)
            .where(
                Integration.user_id == owner,
                Integration.service == service,
                Integration.ciphertext == before,
                Integration.status == "connected",
            )
            .values(
                ciphertext=seal(app.state.settings, owner, service, data),
                expires_at=now() + int(fresh.get("expires_in", 3600)),
            )
        )
        if not changed.rowcount:
            raise AppError(
                "integration_reconnect",
                "Connection changed during refresh; retry after checking Settings.",
                409,
            )
        await db.commit()
        await db.refresh(item)
    return item, data["access_token"]


class Connect(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allow_writes: StrictBool = False


@router.get("/api/integrations")
async def status(request: Request, user: Account, db: DB):
    items = {
        i.service: i
        for i in (await db.scalars(select(Integration).where(Integration.user_id == user.id))).all()
    }
    result = []
    for service in SERVICES:
        try:
            service_config(request.app.state.settings, service)
            configured = True
        except AppError:
            configured = False
        item = items.get(service)
        result.append(
            {
                "service": service,
                "configured": configured,
                "status": item.status if item else "disconnected",
                "identity": item.identity if item else None,
                "scopes": item.scopes.split() if item else [],
            }
        )
    return result


@router.post("/api/integrations/{service}/connect")
async def connect(service: str, body: Connect, request: Request, user: Account, db: DB):
    settings = request.app.state.settings
    identifier, _ = service_config(settings, service)
    raw, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    scopes = SERVICES[service]["read"]
    if body.allow_writes and SERVICES[service]["write"]:
        scopes += " " + SERVICES[service]["write"]
    if service != "github":
        scopes += " " + GOOGLE + "userinfo.email"
    await db.execute(
        delete(OAuthState).where(OAuthState.user_id == user.id, OAuthState.service == service)
    )
    db.add(
        OAuthState(
            state_hash=digest(raw),
            user_id=user.id,
            service=service,
            session_hash=digest(request.cookies[COOKIE_NAME]),
            verifier=seal(settings, user.id, service, {"verifier": verifier}),
            scopes=scopes,
            expires_at=now() + 300,
        )
    )
    await db.commit()
    params = {
        "client_id": identifier,
        "redirect_uri": settings.oauth_origin + f"/api/integrations/{service}/callback",
        "response_type": "code",
        "scope": scopes,
        "state": raw,
        "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .decode()
        .rstrip("="),
        "code_challenge_method": "S256",
    }
    if service != "github":
        params.update(access_type="offline", prompt="consent", include_granted_scopes="false")
    endpoint = (
        "https://github.com/login/oauth/authorize"
        if service == "github"
        else "https://accounts.google.com/o/oauth2/v2/auth"
    )
    return {"url": endpoint + "?" + urlencode(params)}


@router.get("/api/integrations/{service}/callback")
async def callback(
    service: str, request: Request, user: Account, db: DB, state: str = "", code: str = ""
):
    settings = request.app.state.settings
    identifier, secret = service_config(settings, service)
    if not 20 <= len(state) <= 200 or not 1 <= len(code) <= 2048:
        raise AppError("oauth_invalid", "OAuth consent was denied or expired; reconnect.", 400)
    row = (
        await db.execute(
            delete(OAuthState)
            .where(
                OAuthState.state_hash == digest(state),
                OAuthState.user_id == user.id,
                OAuthState.service == service,
                OAuthState.session_hash == digest(request.cookies[COOKIE_NAME]),
                OAuthState.expires_at > now(),
            )
            .returning(OAuthState)
        )
    ).scalar_one_or_none()
    if not row:
        raise AppError("oauth_invalid", "OAuth state was invalid, expired or already used.", 400)
    await db.commit()  # Claim state before any outbound exchange; no callback replay.
    verifier = unseal(settings, user.id, service, row.verifier)["verifier"]
    endpoint = (
        "https://github.com/login/oauth/access_token"
        if service == "github"
        else "https://oauth2.googleapis.com/token"
    )
    data = await request.app.state.integrations.call(
        "POST",
        endpoint,
        data={
            "client_id": identifier,
            "client_secret": secret,
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": settings.oauth_origin + f"/api/integrations/{service}/callback",
        },
    )
    scopes = data.get("scope", "").replace(",", " ").split()
    if not data.get("access_token") or not set(row.scopes.split()).issubset(scopes):
        raise AppError(
            "oauth_scope", "Required scopes were not granted. Reconnect with consent.", 409
        )
    identity = await request.app.state.integrations.call(
        "GET",
        "https://api.github.com/user"
        if service == "github"
        else "https://www.googleapis.com/oauth2/v2/userinfo",
        token=data["access_token"],
    )
    label = identity.get("login" if service == "github" else "email")
    if not label:
        raise AppError("oauth_identity", "Could not verify the connected account identity.", 409)
    item = await db.get(Integration, (user.id, service))
    if item is None:
        item = Integration(user_id=user.id, service=service)
        db.add(item)
    item.identity, item.scopes, item.status = str(label)[:200], " ".join(scopes), "connected"
    item.expires_at = now() + int(data["expires_in"]) if data.get("expires_in") else 0
    item.ciphertext = seal(settings, user.id, service, data)
    await db.commit()
    return RedirectResponse(
        settings.frontend_origin,
        status_code=303,
        headers={"Referrer-Policy": "no-referrer", "Cache-Control": "no-store"},
    )


@router.delete("/api/integrations/{service}")
async def disconnect(service: str, request: Request, user: Account, db: DB):
    item = await db.get(Integration, (user.id, service))
    revoked = True
    if item:
        try:
            data = unseal(request.app.state.settings, user.id, service, item.ciphertext)
            if service == "github":
                identifier, secret = service_config(request.app.state.settings, service)
                await request.app.state.integrations.call(
                    "DELETE",
                    f"https://api.github.com/applications/{identifier}/grant",
                    auth=(identifier, secret),
                    body={"access_token": data["access_token"]},
                )
            else:
                await request.app.state.integrations.call(
                    "POST",
                    "https://oauth2.googleapis.com/revoke",
                    data={"token": data.get("refresh_token") or data["access_token"]},
                )
        except AppError:
            revoked = False
        await db.delete(item)
    await db.execute(
        delete(OAuthState).where(OAuthState.user_id == user.id, OAuthState.service == service)
    )
    await db.commit()
    return {"disconnected": True, "provider_revoked": revoked}
