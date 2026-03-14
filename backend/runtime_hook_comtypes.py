"""Runtime hook: disable comtypes cache generation (needed for frozen exe)."""
try:
    import comtypes.client
    comtypes.client.gen_dir = None
except ImportError:
    pass
