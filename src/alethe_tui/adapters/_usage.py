"""Reported token counts, including cache without counting subsets twice."""


def token_number(value):
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def reported_tokens(usage):
    for key in ('total_tokens', 'totalTokens'):
        if key in usage:
            return token_number(usage[key])
    if 'inputTokens' in usage or 'outputTokens' in usage:
        required = ('inputTokens', 'outputTokens')
        cache = ('cacheReadTokens', 'cacheWriteTokens')
    else:
        required = ('input_tokens', 'output_tokens')
        # cached_input_tokens is already part of input_tokens (Codex).
        cache = ('cache_read_input_tokens', 'cache_creation_input_tokens')
    if not all(token_number(usage.get(key)) is not None for key in required):
        return None
    keys = required + tuple(key for key in cache if key in usage)
    if not all(token_number(usage[key]) is not None for key in keys):
        return None
    return sum(usage[key] for key in keys)
