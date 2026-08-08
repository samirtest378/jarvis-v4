"""Environment fixes that must run before frozen third-party imports."""

import os


# Librosa contains cache-enabled Numba decorators. PyInstaller modules do not
# have a normal source-file locator, so that disk cache cannot initialize.
# Neural synthesis continues to use PyTorch/MPS or CUDA.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

# Librosa asks Numba decorators to cache generated code, which is the exact
# operation a frozen module cannot perform. Preserve JIT compilation while
# forcing only the disk-cache flag off for decorators imported after this hook.
try:
    import numba

    def _without_disk_cache(decorator):
        def wrapped(*args, **kwargs):
            kwargs["cache"] = False
            return decorator(*args, **kwargs)
        return wrapped

    numba.jit = _without_disk_cache(numba.jit)
    numba.njit = _without_disk_cache(numba.njit)
    numba.vectorize = _without_disk_cache(numba.vectorize)
    numba.guvectorize = _without_disk_cache(numba.guvectorize)
except Exception:
    # The packaged dependency check will still surface a useful startup error.
    pass
