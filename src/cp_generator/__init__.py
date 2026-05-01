__all__ = ["CPGeneratorApp", "main"]


def __getattr__(name: str):
    if name in {"CPGeneratorApp", "main"}:
        from .app import CPGeneratorApp, main

        exports = {
            "CPGeneratorApp": CPGeneratorApp,
            "main": main,
        }
        return exports[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
