import os
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Container name mapping: platform -> container name(s) to try
CONTAINER_MAP = {
    "honeygain": os.getenv("CONTAINER_HONEYGAIN", "honeygain"),
    "earnapp": os.getenv("CONTAINER_EARNAPP", "earnapp"),
    "iproyal": os.getenv("CONTAINER_IPROYAL", "iproyal_pawns"),
    "packetstream": os.getenv("CONTAINER_PACKETSTREAM", "packetstream"),
    "traffmonetizer": os.getenv("CONTAINER_TRAFFMONETIZER", "traffmonetizer"),
    "repocket": os.getenv("CONTAINER_REPOCKET", "repocket"),
    "earnfm": os.getenv("CONTAINER_EARNFM", "earnfm"),
    "proxyrack": os.getenv("CONTAINER_PROXYRACK", "proxyrack"),
    "bitping": os.getenv("CONTAINER_BITPING", "bitping"),
}

_executor = ThreadPoolExecutor(max_workers=2)


def _get_container_stats_sync(container_name: str) -> dict:
    """Runs in thread pool — docker SDK is synchronous."""
    try:
        import docker
        client = docker.from_env()
        try:
            container = client.containers.get(container_name)
        except docker.errors.NotFound:
            return {"status": "not_found", "cpu_percent": 0.0, "memory_mb": 0.0}

        status = container.status  # "running", "exited", etc.

        if status != "running":
            return {"status": status, "cpu_percent": 0.0, "memory_mb": 0.0}

        # One-shot stats (stream=False)
        stats = container.stats(stream=False)

        # CPU percent calculation (same formula as `docker stats`)
        cpu_delta = stats["cpu_stats"]["cpu_usage"]["total_usage"] - \
                    stats["precpu_stats"]["cpu_usage"]["total_usage"]
        system_delta = stats["cpu_stats"].get("system_cpu_usage", 0) - \
                       stats["precpu_stats"].get("system_cpu_usage", 0)
        num_cpus = stats["cpu_stats"].get("online_cpus") or \
                   len(stats["cpu_stats"]["cpu_usage"].get("percpu_usage", [1]))
        cpu_percent = (cpu_delta / system_delta * num_cpus * 100.0) if system_delta > 0 else 0.0

        # Memory in MB
        mem_usage = stats["memory_stats"].get("usage", 0)
        mem_cache = stats["memory_stats"].get("stats", {}).get("cache", 0)
        memory_mb = (mem_usage - mem_cache) / (1024 * 1024)

        return {
            "status": "running",
            "cpu_percent": round(cpu_percent, 2),
            "memory_mb": round(memory_mb, 1),
        }
    except ImportError:
        return {"status": "docker_unavailable", "cpu_percent": 0.0, "memory_mb": 0.0}
    except Exception as e:
        logger.warning(f"Docker stats error for {container_name}: {e}")
        return {"status": "error", "cpu_percent": 0.0, "memory_mb": 0.0}
    finally:
        try:
            client.close()
        except Exception:
            pass


async def collect_docker_stats() -> list[dict]:
    """Returns list of {platform, container_name, status, cpu_percent, memory_mb}."""
    loop = asyncio.get_event_loop()
    tasks = []
    for platform, container_name in CONTAINER_MAP.items():
        tasks.append((platform, container_name, loop.run_in_executor(
            _executor, _get_container_stats_sync, container_name
        )))

    results = []
    for platform, container_name, coro in tasks:
        stats = await coro
        results.append({
            "platform": platform,
            "container_name": container_name,
            **stats,
        })
    return results
