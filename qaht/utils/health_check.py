"""
Health check system for API integrations

Monitors API availability, response times, and error rates.
"""
import logging
import time
from typing import Dict, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import json
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class HealthMetrics:
    """Health metrics for an API"""
    name: str
    status: str = "unknown"  # healthy, degraded, unhealthy, unknown
    last_check: Optional[datetime] = None
    last_success: Optional[datetime] = None
    last_failure: Optional[datetime] = None
    success_count: int = 0
    failure_count: int = 0
    total_requests: int = 0
    avg_response_time: float = 0.0
    error_rate: float = 0.0  # percentage
    last_error: Optional[str] = None
    requires_api_key: bool = False
    api_key_configured: bool = False


@dataclass
class HealthCheckResult:
    """Result of a health check"""
    success: bool
    response_time: float
    error: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)


class HealthChecker:
    """
    Health checker for API integrations

    Tracks health metrics and provides status reporting.
    """

    def __init__(self, cache_dir: Optional[Path] = None):
        self.metrics: Dict[str, HealthMetrics] = {}
        self.cache_dir = cache_dir or Path("cache")
        self.cache_dir.mkdir(exist_ok=True)
        self.metrics_file = self.cache_dir / "health_metrics.json"
        self._load_metrics()

    def register_source(self, name: str, requires_api_key: bool = False, api_key_configured: bool = False):
        """Register a new data source for health monitoring"""
        if name not in self.metrics:
            self.metrics[name] = HealthMetrics(
                name=name,
                requires_api_key=requires_api_key,
                api_key_configured=api_key_configured
            )
            logger.info(f"Registered health monitoring for: {name}")

    def check_health(self, name: str, check_func: Callable, timeout: float = 10.0) -> HealthCheckResult:
        """
        Run health check for a data source

        Args:
            name: Name of data source
            check_func: Function to execute for health check (should return True on success)
            timeout: Timeout in seconds

        Returns:
            HealthCheckResult with status and timing
        """
        if name not in self.metrics:
            self.register_source(name)

        start_time = time.time()
        result = HealthCheckResult(success=False, response_time=0.0)

        try:
            # Run the health check function
            success = check_func()
            result.success = bool(success)
            result.response_time = time.time() - start_time

            if result.success:
                result.error = None
            else:
                result.error = "Health check returned False"

        except Exception as e:
            result.success = False
            result.response_time = time.time() - start_time
            result.error = str(e)

        # Update metrics
        self._update_metrics(name, result)

        return result

    def record_request(self, name: str, success: bool, response_time: float = 0.0, error: Optional[str] = None):
        """
        Record API request result

        Args:
            name: Name of data source
            success: Whether request succeeded
            response_time: Response time in seconds
            error: Error message if failed
        """
        if name not in self.metrics:
            self.register_source(name)

        metrics = self.metrics[name]
        metrics.last_check = datetime.now()
        metrics.total_requests += 1

        if success:
            metrics.success_count += 1
            metrics.last_success = datetime.now()
        else:
            metrics.failure_count += 1
            metrics.last_failure = datetime.now()
            metrics.last_error = error

        # Update average response time
        if response_time > 0:
            total_time = metrics.avg_response_time * (metrics.total_requests - 1)
            metrics.avg_response_time = (total_time + response_time) / metrics.total_requests

        # Calculate error rate
        metrics.error_rate = (metrics.failure_count / metrics.total_requests * 100) if metrics.total_requests > 0 else 0.0

        # Determine status
        self._update_status(name)

        # Save metrics periodically
        if metrics.total_requests % 10 == 0:
            self._save_metrics()

    def _update_metrics(self, name: str, result: HealthCheckResult):
        """Update metrics based on health check result"""
        self.record_request(
            name=name,
            success=result.success,
            response_time=result.response_time,
            error=result.error
        )

    def _update_status(self, name: str):
        """Update health status based on metrics"""
        metrics = self.metrics[name]

        # If API key required but not configured
        if metrics.requires_api_key and not metrics.api_key_configured:
            metrics.status = "unconfigured"
            return

        # If no requests yet
        if metrics.total_requests == 0:
            metrics.status = "unknown"
            return

        # Check recent failures
        if metrics.last_failure:
            time_since_failure = datetime.now() - metrics.last_failure
            if time_since_failure < timedelta(minutes=5):
                # Recent failure within 5 minutes
                metrics.status = "unhealthy"
                return

        # Check error rate
        if metrics.error_rate >= 50:
            metrics.status = "unhealthy"
        elif metrics.error_rate >= 20:
            metrics.status = "degraded"
        elif metrics.error_rate < 20:
            metrics.status = "healthy"
        else:
            metrics.status = "unknown"

    def get_status(self, name: str) -> Optional[HealthMetrics]:
        """Get health metrics for a data source"""
        return self.metrics.get(name)

    def get_all_status(self) -> Dict[str, HealthMetrics]:
        """Get health metrics for all data sources"""
        return self.metrics.copy()

    def get_healthy_sources(self) -> List[str]:
        """Get list of healthy data sources"""
        return [name for name, metrics in self.metrics.items() if metrics.status == "healthy"]

    def get_unhealthy_sources(self) -> List[str]:
        """Get list of unhealthy data sources"""
        return [name for name, metrics in self.metrics.items() if metrics.status == "unhealthy"]

    def print_status_report(self):
        """Print health status report"""
        print("\n" + "="*80)
        print("🏥 API Health Status Report")
        print("="*80)
        print()

        if not self.metrics:
            print("No data sources registered for health monitoring.")
            return

        # Group by status
        statuses = {}
        for name, metrics in self.metrics.items():
            status = metrics.status
            if status not in statuses:
                statuses[status] = []
            statuses[status].append((name, metrics))

        # Status icons
        status_icons = {
            'healthy': '✅',
            'degraded': '⚠️',
            'unhealthy': '❌',
            'unconfigured': '🔧',
            'unknown': '❓'
        }

        # Print by status
        for status in ['healthy', 'degraded', 'unhealthy', 'unconfigured', 'unknown']:
            if status in statuses:
                print(f"{status_icons.get(status, '•')} {status.upper()}")
                print("-"*80)
                for name, metrics in statuses[status]:
                    print(f"  {name:20s} | Requests: {metrics.total_requests:4d} | "
                          f"Success: {metrics.success_count:4d} | Failures: {metrics.failure_count:4d} | "
                          f"Error Rate: {metrics.error_rate:5.1f}%")
                    if metrics.last_error:
                        print(f"    Last Error: {metrics.last_error[:100]}")
                print()

        # Summary
        print("="*80)
        total = len(self.metrics)
        healthy = len([m for m in self.metrics.values() if m.status == "healthy"])
        degraded = len([m for m in self.metrics.values() if m.status == "degraded"])
        unhealthy = len([m for m in self.metrics.values() if m.status == "unhealthy"])

        print(f"SUMMARY: {healthy}/{total} healthy, {degraded}/{total} degraded, {unhealthy}/{total} unhealthy")
        print("="*80)
        print()

    def _save_metrics(self):
        """Save metrics to cache file"""
        try:
            data = {}
            for name, metrics in self.metrics.items():
                data[name] = {
                    'status': metrics.status,
                    'last_check': metrics.last_check.isoformat() if metrics.last_check else None,
                    'last_success': metrics.last_success.isoformat() if metrics.last_success else None,
                    'last_failure': metrics.last_failure.isoformat() if metrics.last_failure else None,
                    'success_count': metrics.success_count,
                    'failure_count': metrics.failure_count,
                    'total_requests': metrics.total_requests,
                    'avg_response_time': metrics.avg_response_time,
                    'error_rate': metrics.error_rate,
                    'last_error': metrics.last_error,
                    'requires_api_key': metrics.requires_api_key,
                    'api_key_configured': metrics.api_key_configured
                }

            with open(self.metrics_file, 'w') as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            logger.error(f"Failed to save health metrics: {e}")

    def _load_metrics(self):
        """Load metrics from cache file"""
        try:
            if not self.metrics_file.exists():
                return

            with open(self.metrics_file, 'r') as f:
                data = json.load(f)

            for name, metrics_data in data.items():
                self.metrics[name] = HealthMetrics(
                    name=name,
                    status=metrics_data.get('status', 'unknown'),
                    last_check=datetime.fromisoformat(metrics_data['last_check']) if metrics_data.get('last_check') else None,
                    last_success=datetime.fromisoformat(metrics_data['last_success']) if metrics_data.get('last_success') else None,
                    last_failure=datetime.fromisoformat(metrics_data['last_failure']) if metrics_data.get('last_failure') else None,
                    success_count=metrics_data.get('success_count', 0),
                    failure_count=metrics_data.get('failure_count', 0),
                    total_requests=metrics_data.get('total_requests', 0),
                    avg_response_time=metrics_data.get('avg_response_time', 0.0),
                    error_rate=metrics_data.get('error_rate', 0.0),
                    last_error=metrics_data.get('last_error'),
                    requires_api_key=metrics_data.get('requires_api_key', False),
                    api_key_configured=metrics_data.get('api_key_configured', False)
                )

            logger.info(f"Loaded health metrics for {len(self.metrics)} sources")

        except Exception as e:
            logger.warning(f"Failed to load health metrics: {e}")


# Global health checker instance
_health_checker = None


def get_health_checker() -> HealthChecker:
    """Get or create global health checker instance"""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker()
    return _health_checker


if __name__ == '__main__':
    # Test health checker
    print("Testing health check system...")

    checker = HealthChecker()

    # Register some sources
    checker.register_source("TestAPI1", requires_api_key=True, api_key_configured=True)
    checker.register_source("TestAPI2", requires_api_key=False)

    # Simulate some requests
    for i in range(20):
        checker.record_request("TestAPI1", success=True, response_time=0.5)
    for i in range(5):
        checker.record_request("TestAPI1", success=False, error="Connection timeout")

    for i in range(15):
        checker.record_request("TestAPI2", success=True, response_time=0.3)

    # Print status
    checker.print_status_report()

    print("✅ Health check system test complete!")
