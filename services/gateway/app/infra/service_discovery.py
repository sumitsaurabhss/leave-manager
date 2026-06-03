# services/gateway/app/infra/service_discovery.py
import random
import logging
from typing import Optional

import requests

from app.core.config import settings

logger = logging.getLogger("gateway.service-discovery")


def _consul_base_url() -> str:
  return f"http://{settings.consul_host}:{settings.consul_port}"


def discover_service_url(service_name: str) -> str:
  """
  Resolve a healthy service instance via Consul and return its base URL,
  e.g. 'http://users-service:8001'.
  """
  url = f"{_consul_base_url()}/v1/health/service/{service_name}?passing"
  logger.debug(
    "Discovering service via Consul",
    extra={"service_name": service_name, "url": url},
  )

  try:
    resp = requests.get(url, timeout=3)
    resp.raise_for_status()
  except requests.RequestException as exc:
    logger.error(
      "Failed to query Consul for service",
      extra={"service_name": service_name, "error": str(exc)},
    )
    raise RuntimeError(f"Consul service discovery error for {service_name}: {exc}") from exc

  services = resp.json()
  if not services:
    logger.warning(
      "No healthy instances found in Consul",
      extra={"service_name": service_name},
    )
    raise RuntimeError(f"No healthy instances found for {service_name}")

  srv = random.choice(services)
  svc = srv.get("Service", {})

  address: Optional[str] = svc.get("Address")
  if not address:
    # Fallback: use Service name or requested service_name
    address = svc.get("Service") or service_name

  port = svc.get("Port")
  if not port:
    logger.warning(
      "Service in Consul has no port; defaulting to 80",
      extra={"service_name": service_name},
    )
    port = 80

  base_url = f"http://{address}:{port}"
  logger.info(
    "Resolved service via Consul",
    extra={"service_name": service_name, "base_url": base_url},
  )
  return base_url