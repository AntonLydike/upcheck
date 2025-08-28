import time
from functools import wraps


def timed_cache(timeout: float):
    cache = {}
    clean_period = timeout * 10
    clean = [time.time() + clean_period]

    def wrapping(fn):
        argnames = fn.__code__.co_varnames[: fn.__code__.co_argcount]
        print(argnames)

        @wraps(fn)
        def wrapped(*args, **kwargs):
            t = time.time()

            # clean cache it next cache-clean is upon us
            if clean[0] < t:
                for key, (_, expires) in tuple(cache.items()):
                    if expires > t:
                        cache.pop(key)
                clean[0] = t + clean_period

            # generate tuple of args as cache key
            argtuple = tuple((*args, *(kwargs[name] for name in argnames[len(args) :])))

            # check for cache hit
            if argtuple in cache:
                res, expires = cache[argtuple]
                # check if cache hit is expired
                if expires > t:
                    return res

            # calculate result if no cache hit
            val = fn(*argtuple)
            # cache result, then return
            cache[argtuple] = (val, t + timeout)
            return val

        return wrapped

    return wrapping
