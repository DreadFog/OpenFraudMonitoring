from urllib.parse import urlparse
import logging

from models import DomainConfig

logger = logging.getLogger(__name__)


def normalize_domain(value: str) -> str:
    """Normalize a hostname or URL to a lowercase host without a port."""
    raw = (value or "").strip().lower()
    if "://" in raw:
        raw = urlparse(raw).hostname or ""
    else:
        raw = raw.split("/", 1)[0].split(":", 1)[0]
    return raw.rstrip(".")


def domain_from_url(url: str) -> str:
    return normalize_domain(urlparse(url or "").hostname or "")


def configured_domain_for_host(host: str):
    domain = normalize_domain(host)
    if not domain:
        return None
    return DomainConfig.query.filter_by(domain=domain, active=True).first()


def auth_cookie_present(request, host: str) -> bool:
    domain = normalize_domain(host)
    config = configured_domain_for_host(domain)
    cookie_name = config.auth_cookie_name if config else None
    present = bool(cookie_name and cookie_name in request.cookies)
    logger.debug(
        "auth cookie check: host=%s configured=%s cookie_name=%s cookie_present=%s authenticated=%s",
        domain or "<empty>",
        bool(config),
        cookie_name or "<none>",
        present,
        present,
    )
    return present


def add_session_domain(session_obj, url: str) -> None:
    domain = domain_from_url(url)
    if not domain:
        return
    domains = list(session_obj.domains or [])
    if domain not in domains:
        domains.append(domain)
        session_obj.domains = domains


def form_action_matches(configured_action: str, submitted_action: str) -> bool:
    configured = (configured_action or "").strip()
    submitted = (submitted_action or "").strip()
    if not configured or not submitted:
        return False
    if configured == submitted:
        return True

    # Browsers commonly report form.action as an absolute URL even when the
    # HTML form uses a relative action such as "/admin/login".
    if configured.startswith("/"):
        submitted_url = urlparse(submitted)
        submitted_path = submitted_url.path or "/"
        if submitted_url.query:
            submitted_path += f"?{submitted_url.query}"
        return submitted_path == configured
    return False


def form_matches_config(config, action: str, method: str, field_names: list[str]) -> bool:
    if not config or not config.form_action:
        return False
    configured_method = (config.form_method or "post").strip().lower()
    if (method or "post").strip().lower() != configured_method:
        return False
    if not form_action_matches(config.form_action, action):
        return False
    submitted = {str(name).strip().lower() for name in (field_names or []) if str(name).strip()}
    expected = {str(name).strip().lower() for name in (config.form_field_names or []) if str(name).strip()}
    return expected.issubset(submitted)


def matching_form_config(host: str, action: str, method: str, field_names: list[str]):
    config = configured_domain_for_host(host)
    matched = bool(config and form_matches_config(config, action, method, field_names))
    logger.debug(
        "auth form check: host=%s configured=%s action=%s method=%s submitted_field_count=%d matched=%s",
        normalize_domain(host) or "<empty>",
        bool(config),
        action or "<empty>",
        (method or "post").lower(),
        len(field_names or []),
        matched,
    )
    return config if matched else None
