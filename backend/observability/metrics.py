"""
Metrics Collector
Custom metrics for RAG pipeline monitoring
"""
from typing import Dict, List
from dataclasses import dataclass
import time


@dataclass
class MetricPoint:
    """A single metric data point"""
    timestamp: float
    value: float
    labels: dict


class MetricsCollector:
    """
    Collects and aggregates custom metrics.

    Tracks:
    - Latency by operation type
    - Counts by category
    - Error rates
    - Resource usage
    """

    def __init__(self):
        self._counters: Dict[str, float] = {}
        self._gauges: Dict[str, float] = {}
        self._histograms: Dict[str, List[float]] = {}
        self._timers: Dict[str, List[float]] = {}

    def increment(self, name: str, value: float = 1.0, labels: dict = None):
        """Increment a counter metric"""
        key = self._make_key(name, labels)
        self._counters[key] = self._counters.get(key, 0) + value

    def gauge(self, name: str, value: float, labels: dict = None):
        """Set a gauge metric"""
        key = self._make_key(name, labels)
        self._gauges[key] = value

    def histogram(self, name: str, value: float, labels: dict = None):
        """Record a histogram value"""
        key = self._make_key(name, labels)
        if key not in self._histograms:
            self._histograms[key] = []
        self._histograms[key].append(value)

    def timer(self, name: str, labels: dict = None):
        """Context manager for timing operations"""
        return Timer(self, name, labels)

    def _make_key(self, name: str, labels: dict = None) -> str:
        """Create a metric key from name and labels"""
        if not labels:
            return name
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def get_counter(self, name: str, labels: dict = None) -> float:
        """Get counter value"""
        key = self._make_key(name, labels)
        return self._counters.get(key, 0)

    def get_gauge(self, name: str, labels: dict = None) -> float:
        """Get gauge value"""
        key = self._make_key(name, labels)
        return self._gauges.get(key, 0)

    def get_histogram_stats(self, name: str, labels: dict = None) -> dict:
        """Get histogram statistics"""
        key = self._make_key(name, labels)
        values = self._histograms.get(key, [])

        if not values:
            return {"count": 0, "sum": 0, "avg": 0, "min": 0, "max": 0}

        return {
            "count": len(values),
            "sum": sum(values),
            "avg": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
        }

    def get_all_metrics(self) -> dict:
        """Get all collected metrics"""
        return {
            "counters": self._counters.copy(),
            "gauges": self._gauges.copy(),
            "histograms": {
                k: self.get_histogram_stats(k)
                for k in self._histograms.keys()
            },
        }


class Timer:
    """Context manager for timing operations"""

    def __init__(self, collector: MetricsCollector, name: str, labels: dict = None):
        self.collector = collector
        self.name = name
        self.labels = labels
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed = (time.time() - self.start_time) * 1000
        self.collector.histogram(self.name, elapsed, self.labels)

    def elapsed_ms(self) -> float:
        if self.start_time is None:
            return 0
        return (time.time() - self.start_time) * 1000


_global_collector = MetricsCollector()


def get_collector() -> MetricsCollector:
    """Get global metrics collector"""
    return _global_collector
