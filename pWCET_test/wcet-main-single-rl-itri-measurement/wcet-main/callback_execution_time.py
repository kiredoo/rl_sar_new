from dataclasses import dataclass, field

@dataclass
class CallbackExecutionTime:
    """
    Execution sampled from eBPF program.
    """
    name: str = ""
    samples: list = field(default_factory=list)


@dataclass
class CallbackExecutionTimeCollection:
    """
    Maintain a set of sampled callback execution times, plus auxiliary data.
    These fields match the design documents.
    """
    unit: str = "nanosecond"
    sampling_time: str = ""
    hostname: str = ""
    callbacks: list = field(default_factory=list)
