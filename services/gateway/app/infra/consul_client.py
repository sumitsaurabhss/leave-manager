import logging
import socket
from typing import Optional

import requests

from app.core.config import settings

logger = logging.getLogger("consul-client")


def get_consul_base_url() -> str:
  return f"http://{settings.consul_host}:{settings.consul_port}"


def register_service(
  service_name: str,
  service_id: Optional[str] = None,
  address: Optional[str] = None,
  port: int = 0,
  tags: Optional[list[str]] = None,
  health_http: Optional[str] = None,
  interval: str = "10s",
):
  if service_id is None:
    hostname = socket.gethostname()
    service_id = f"{service_name}-{hostname}-{port}"

  if address is None:
    address = socket.gethostname()

  payload = {
    "Name": service_name,
    "ID": service_id,
    "Address": address,
    "Port": port,
    "Tags": tags or [],
  }

  if health_http:
    payload["Check"] = {
      "HTTP": health_http,
      "Interval": interval,
    }

  url = f"{get_consul_base_url()}/v1/agent/service/register"
  logger.info(
    "Registering service in Consul",
    extra={"service_name": service_name, "service_id": service_id, "url": url},
  )
  resp = requests.put(url, json=payload, timeout=5)
  resp.raise_for_status()


def discover_service(service_name: str) -> list[dict]:
  """
  Return list of healthy service instances from Consul.
  """
  url = f"{get_consul_base_url()}/v1/health/service/{service_name}?passing"
  logger.debug(
    "Discovering service in Consul",
    extra={"service_name": service_name, "url": url},
  )
  resp = requests.get(url, timeout=5)
  resp.raise_for_status()
  return resp.json()