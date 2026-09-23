def _idle_week_tick() -> None:
    try:
        from scripts.ether_week_tick import tick
        tick(push=False)
    except Exception:
        pass
    try:
        from scripts.live_status import write as live_status
        live_status()
    except Exception:
        pass
    try:
        from scripts.ether_evolve import cycle
        cycle()
    except Exception:
        return
