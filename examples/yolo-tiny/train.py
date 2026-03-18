import sys
from pathlib import Path


def load_yolo():
    try:
        from ultralytics import YOLO
    except ModuleNotFoundError:
        pyver = f"python{sys.version_info.major}.{sys.version_info.minor}"
        site_packages = Path(__file__).resolve().parent / ".venv" / "lib" / pyver / "site-packages"
        if not site_packages.is_dir():
            raise
        sys.path.insert(0, str(site_packages))
        from ultralytics import YOLO

    return YOLO


YOLO = load_yolo()


def extract_map50(metrics) -> float:
    box = getattr(metrics, "box", None)
    if box is not None:
        map50 = getattr(box, "map50", None)
        if map50 is not None:
            return float(map50)

    results_dict = getattr(metrics, "results_dict", None)
    if isinstance(results_dict, dict):
        for key in ("metrics/mAP50(B)", "metrics/mAP50", "mAP50"):
            if key in results_dict:
                return float(results_dict[key])

    raise RuntimeError("Unable to extract mAP50 from Ultralytics metrics output")


def main() -> None:
    model = YOLO("yolov8n.pt")
    if model.task != "detect":
        raise RuntimeError(f"Expected detect task, got {model.task!r}")

    metrics = model.train(data="coco8.yaml", epochs=10)
    if metrics is None:
        metrics = model.val(data="coco8.yaml")

    print(f"mAP50 {extract_map50(metrics):.6f}")


if __name__ == "__main__":
    main()
