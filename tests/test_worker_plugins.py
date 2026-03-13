from open_researcher.worker_plugins import GPUAllocatorPlugin


class FakeGPUManager:
    def __init__(self, rows):
        self.rows = rows
        self.allow_same_gpu_packing = True
        self.last_reserved = None

    def refresh(self):
        return self.rows

    @staticmethod
    def effective_free_mb(gpu):
        reserved = sum(int(item.get("memory_mb", 0) or 0) for item in gpu.get("reservations", []))
        return max(int(gpu.get("memory_free", 0) or 0) - reserved, 0)

    def reserve(self, worker_id, request, metadata=None, preferred=None):
        target = preferred or {"host": self.rows[0]["host"], "device": self.rows[0]["device"]}
        self.last_reserved = {
            "worker_id": worker_id, "request": dict(request), "metadata": metadata, "preferred": target
        }
        return [
            {
                "id": "res-001",
                "host": target["host"],
                "device": target["device"],
                "memory_mb": int(request.get("gpu_mem_mb", 0) or 0),
            }
        ]

    def release_reservations(self, reservations):
        return None


def test_single_gpu_saturation_worker_slots_spread_one_per_gpu():
    manager = FakeGPUManager(
        [
            {"host": "local", "device": 0, "memory_total": 49152, "memory_free": 42000, "reservations": []},
            {"host": "local", "device": 1, "memory_total": 49152, "memory_free": 40000, "reservations": []},
        ]
    )
    plugin = GPUAllocatorPlugin(
        manager,
        scheduler_objective="single_gpu_saturation",
        default_memory_per_worker_mb=4096,
    )

    slots = plugin.worker_slots(4)

    assert slots == [{"host": "local", "device": 0}, {"host": "local", "device": 1}]


def test_single_gpu_saturation_allocation_hands_shape_choice_to_agent():
    manager = FakeGPUManager(
        [{"host": "local", "device": 0, "memory_total": 49152, "memory_free": 24576, "reservations": []}]
    )
    plugin = GPUAllocatorPlugin(
        manager,
        scheduler_objective="single_gpu_saturation",
        default_memory_per_worker_mb=4096,
        resource_profiles={
            "single_gpu_small": {"gpu_count": 1, "gpu_mem_mb": 10000, "expected_memory_mb": 11000},
            "single_gpu_large": {"gpu_count": 1, "gpu_mem_mb": 14000, "expected_memory_mb": 15000},
            "single_gpu_too_big": {"gpu_count": 1, "gpu_mem_mb": 20000, "expected_memory_mb": 21000},
        },
        single_task_headroom_ratio=0.10,
        single_task_headroom_mb=2048,
        single_gpu_qualification_timeout_minutes=12,
    )
    idea = {
        "id": "idea-001",
        "resource_request": {"gpu_count": 1, "gpu_mem_mb": 12000},
        "workload_label": "train",
    }

    allocation = plugin.allocate_for_idea("worker-0", idea, preferred={"host": "local", "device": 0})

    assert allocation is not None
    assert allocation.selected_profile["name"] == "__idea_default__"
    assert allocation.resource_request["exclusive"] is True
    assert allocation.resource_request["shareable"] is False
    assert allocation.env["OPEN_RESEARCHER_SINGLE_GPU_SATURATION"] == "1"
    assert allocation.env["OPEN_RESEARCHER_AGENT_OWNS_SATURATION_SHAPE"] == "1"
    assert allocation.saturation_context["qualification_timeout_minutes"] == 12
    assert [profile["name"] for profile in allocation.saturation_context["profiles"]] == [
        "single_gpu_small",
        "__idea_default__",
        "single_gpu_large",
        "single_gpu_too_big",
    ]
