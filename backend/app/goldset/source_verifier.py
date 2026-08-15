from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx
import yaml

from backend.app.goldset.errors import (
    GoldSetCurationError,
    GoldSetCurationErrorCode,
)
from backend.app.goldset.models import (
    SourceReference,
    SourceVerificationResult,
    VerificationStatus,
)


ROOT = Path(__file__).resolve().parents[3]


class OfficialSourceVerifier:
    """Bounded live verification against an allowlisted official HTTPS host."""

    def __init__(
        self,
        *,
        rules_path: Path | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.rules_path = rules_path or ROOT / "configs" / "goldset_rules.yaml"
        self.rules = self._load_rules(self.rules_path)["source_verification"]
        self.max_response_bytes = int(self.rules["max_response_bytes"])
        self._owns_client = client is None
        self.client = client or httpx.Client(
            timeout=float(self.rules["timeout_seconds"]),
            follow_redirects=True,
            headers={"User-Agent": "breast-research-goldset-verifier/0.1"},
        )

    def verify(self, source: SourceReference) -> SourceVerificationResult:
        checked_at = datetime.now(timezone.utc)
        deterministic_failure = self._validate_reference(source)
        if deterministic_failure:
            return self._failed(source, checked_at, deterministic_failure)
        try:
            with self.client.stream(
                "GET",
                source.url,
                headers={"Accept": "application/json,text/html,text/plain;q=0.9,*/*;q=0.1"},
            ) as response:
                content = bytearray()
                truncated = False
                for chunk in response.iter_bytes():
                    remaining = self.max_response_bytes + 1 - len(content)
                    if remaining <= 0:
                        truncated = True
                        break
                    content.extend(chunk[:remaining])
                    if len(content) > self.max_response_bytes:
                        truncated = True
                        del content[self.max_response_bytes :]
                        break
                digest = hashlib.sha256(bytes(content)).hexdigest()
                status = response.status_code
                final_url = str(response.url)
        except httpx.HTTPError as exc:
            return self._failed(
                source,
                checked_at,
                f"Official source request failed: {exc.__class__.__name__}",
            )

        final_url_failure = self._validate_final_url(source, final_url)
        if final_url_failure:
            return self._failed(
                source,
                checked_at,
                final_url_failure,
                checked_url=final_url,
                http_status=status,
                response_sha256=digest,
                content_truncated=truncated,
            )

        if status < 200 or status >= 300:
            return self._failed(
                source,
                checked_at,
                f"Official source returned HTTP {status}.",
                checked_url=final_url,
                http_status=status,
                response_sha256=digest,
                content_truncated=truncated,
            )
        marker = source.accession.casefold().encode("utf-8")
        if marker not in bytes(content).lower():
            return self._failed(
                source,
                checked_at,
                "Official response did not contain the requested accession.",
                checked_url=final_url,
                http_status=status,
                response_sha256=digest,
                content_truncated=truncated,
            )
        return SourceVerificationResult(
            verification_id=self._verification_id(source, digest),
            source=source,
            status=VerificationStatus.VERIFIED,
            checked_at=checked_at,
            checked_url=final_url,
            http_status=status,
            response_sha256=digest,
            content_truncated=truncated,
            reason="Accession was found in a successful response from an allowlisted official host.",
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def _validate_reference(self, source: SourceReference) -> str | None:
        source_rules = self.rules["sources"].get(source.source_database.value)
        if not isinstance(source_rules, dict):
            return f"Unsupported source database: {source.source_database.value}"
        if not re.fullmatch(source_rules["accession_pattern"], source.accession):
            return "Accession does not match the official source format."
        parsed = urlparse(source.url)
        if parsed.scheme.casefold() != "https" or not parsed.hostname:
            return "Source URL must use HTTPS and include a hostname."
        if parsed.username or parsed.password or parsed.port not in {None, 443}:
            return "Source URL cannot contain credentials or a non-HTTPS port."
        hostname = parsed.hostname.casefold()
        allowed_hosts = [host.casefold() for host in source_rules["allowed_hosts"]]
        if not any(
            hostname == allowed or hostname.endswith(f".{allowed}")
            for allowed in allowed_hosts
        ):
            return "Source URL hostname is not allowlisted for this database."
        if source.accession.casefold() not in unquote(source.url).casefold():
            return "Source URL does not contain the requested accession."
        return None

    def _validate_final_url(
        self,
        source: SourceReference,
        final_url: str,
    ) -> str | None:
        source_rules = self.rules["sources"][source.source_database.value]
        parsed = urlparse(final_url)
        if (
            parsed.scheme.casefold() != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.port not in {None, 443}
        ):
            return "Final source URL is not a permitted official HTTPS URL."
        hostname = parsed.hostname.casefold()
        allowed_hosts = [host.casefold() for host in source_rules["allowed_hosts"]]
        if not any(
            hostname == allowed or hostname.endswith(f".{allowed}")
            for allowed in allowed_hosts
        ):
            return "Official source redirected outside its allowlisted domain."
        return None

    @classmethod
    def _failed(
        cls,
        source: SourceReference,
        checked_at: datetime,
        reason: str,
        *,
        checked_url: str | None = None,
        http_status: int | None = None,
        response_sha256: str | None = None,
        content_truncated: bool = False,
    ) -> SourceVerificationResult:
        seed = response_sha256 or "no-response"
        return SourceVerificationResult(
            verification_id=cls._verification_id(source, seed),
            source=source,
            status=VerificationStatus.FAILED,
            checked_at=checked_at,
            checked_url=checked_url,
            http_status=http_status,
            response_sha256=response_sha256,
            content_truncated=content_truncated,
            reason=reason,
        )

    @staticmethod
    def _verification_id(source: SourceReference, response_digest: str) -> str:
        material = (
            f"{source.source_database.value}|{source.accession}|{source.url}|"
            f"{response_digest}"
        ).encode("utf-8")
        return f"source-verification:{hashlib.sha256(material).hexdigest()[:24]}"

    @staticmethod
    def _load_rules(path: Path) -> dict:
        try:
            rules = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(rules.get("source_verification"), dict):
                raise ValueError("missing source_verification section")
            return rules
        except (OSError, ValueError, yaml.YAMLError) as exc:
            raise GoldSetCurationError(
                GoldSetCurationErrorCode.INVALID_CONFIGURATION,
                "Cannot load Gold Set source verification rules.",
                details={"path": str(path), "error": str(exc)},
            ) from exc
